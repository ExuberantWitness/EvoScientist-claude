"""Starlette web dashboard for EvoScientist agent monitoring."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from sse_starlette.sse import EventSourceResponse

from .frontend import DASHBOARD_HTML

# Dashboard 直驱 PESController + pipeline_protocol
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from pipeline_protocol import (
    atomic_read, atomic_write, dashboard_write,
    dashboard_write_approval, dashboard_heartbeat_age,
    dashboard_get_heartbeat,
)
from pes_controller import (
    PESController, PHASE_PLAN, PHASE_CODE, PHASE_WRITE, PHASE_REVIEW,
    AGENT_SDK_PHASES,
)

logger = logging.getLogger(__name__)

# Set by server.py before app starts
_manager_ref = None
_bridge_ref = None
_watchdog_ref = None

# Agent SDK 子进程的阶段 (W4 Code 改为 Plan-driven 模式，不再用 SDK)
AGENT_SDK_PHASES = {PHASE_WRITE, PHASE_REVIEW}


def set_watchdog(watchdog):
    global _watchdog_ref
    _watchdog_ref = watchdog

def _watchdog():
    return _watchdog_ref

def set_manager(manager):
    global _manager_ref
    _manager_ref = manager


def set_bridge(bridge):
    global _bridge_ref
    _bridge_ref = bridge


def _mgr():
    return _manager_ref


def _bridge():
    return _bridge_ref


# ── Claim Chain helpers ──

def _read_jsonl(path: Path, limit: int = 200):
    """Read last N entries from a JSONL file."""
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries[-limit:]


# ── Routes ──

async def homepage(request):
    return HTMLResponse(DASHBOARD_HTML)


async def list_sessions_api(request):
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    mgr.refresh_sessions()
    return JSONResponse(mgr.list_sessions())


async def session_detail_api(request):
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]
    result = await mgr.get_status(sid)
    return JSONResponse(result)


async def session_state_api(request):
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]
    return JSONResponse(mgr.get_stream_state(sid))


async def pipeline_state_api(request):
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]
    return JSONResponse(mgr.get_pipeline_state(sid))


async def pipeline_control_api(request):
    """POST endpoint for pipeline control (pause/resume/switch)."""
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]

    if request.method == "GET":
        return JSONResponse(mgr.get_pipeline_control(sid))

    # POST
    try:
        body = json.loads((await request.body()).decode())
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    action = body.get("action")
    if not action:
        return JSONResponse({"error": "missing 'action' field"}, status_code=400)

    result = mgr.pipeline_control(
        session_id=sid,
        action=action,
        phase=body.get("phase"),
    )
    return JSONResponse(result)


async def memory_api(request):
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]
    return JSONResponse(await mgr.get_memory(sid))


# ── Claim Chain API ──

async def claim_chain_api(request):
    """Serve Claim Chain atoms and relations for a session's workspace."""
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]
    mgr._load_sessions_from_disk()
    if sid not in mgr.sessions:
        return JSONResponse({"error": f"Session {sid} not found"}, status_code=404)

    session = mgr.sessions[sid]
    workspace = Path(session.workspace_dir) / "vault" / "_index"

    atoms = _read_jsonl(workspace / "atoms.jsonl")
    relations = _read_jsonl(workspace / "relations.jsonl")

    # Build summary
    active_atoms = [a for a in atoms if a.get("status") == "active"]
    type_counts = {}
    for a in active_atoms:
        t = a["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    rel_type_counts = {}
    for r in relations:
        t = r["type"]
        rel_type_counts[t] = rel_type_counts.get(t, 0) + 1

    # Build graph edges for visualization
    atom_map = {a["id"]: a for a in atoms}
    edges = []
    for r in relations:
        if r["source_id"] in atom_map and r["target_id"] in atom_map:
            edges.append({
                "source": r["source_id"],
                "source_title": atom_map[r["source_id"]]["title"],
                "target": r["target_id"],
                "target_title": atom_map[r["target_id"]]["title"],
                "type": r["type"],
                "evidence": r.get("evidence", ""),
            })

    return JSONResponse({
        "atoms": atoms,
        "relations": relations,
        "edges": edges,
        "summary": {
            "total_atoms": len(atoms),
            "active_atoms": len(active_atoms),
            "atom_types": type_counts,
            "total_relations": len(relations),
            "relation_types": rel_type_counts,
        },
    })


async def evolve_grid_api(request):
    """Serve evolve grid state for a session's workspace."""
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
    sid = request.path_params["session_id"]
    mgr._load_sessions_from_disk()
    if sid not in mgr.sessions:
        return JSONResponse({"error": f"Session {sid} not found"}, status_code=404)

    session = mgr.sessions[sid]
    archive_dir = Path(session.workspace_dir) / "evolve_archive"

    state_path = archive_dir / "evolve_state.json"
    config_path = archive_dir / "evolve_config.json"

    state = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))

    cells = state.get("cells", {})
    filled = {k: v for k, v in cells.items() if v.get("elite_id")}
    total = len(cells)

    return JSONResponse({
        "config": config,
        "cells": cells,
        "summary": {
            "total_cells": total,
            "filled_cells": len(filled),
            "coverage": f"{100 * len(filled) / max(total, 1):.0f}%",
            "best_score": max((v["elite_score"] for v in filled.values()), default=None),
        },
        "best_variants": sorted(
            [{"cell": k, **v} for k, v in filled.items()],
            key=lambda x: x["elite_score"], reverse=True,
        ),
    })


async def restart_api(request):
    """POST endpoint to restart the dashboard process."""
    import subprocess

    helper = Path(__file__).parent.parent / "restart_dashboard.py"
    python_bin = sys.executable

    try:
        subprocess.Popen(
            [python_bin, str(helper)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.error(f"Failed to schedule restart: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    return JSONResponse({"status": "restarting", "message": "Dashboard restarting in ~4 seconds..."})


async def sse_events(request):
    """SSE endpoint for real-time event streaming."""
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"}, status_code=503)

    sid = request.path_params["session_id"]
    if sid not in mgr.sessions:
        return JSONResponse({"error": f"Session {sid} not found"}, status_code=404)

    async def event_generator():
        queue = mgr.event_bus.subscribe(sid)
        try:
            # Replay recent history (capped to avoid overwhelming client)
            for event in mgr.event_bus.get_recent_events(sid, limit=30):
                try:
                    yield {"event": "agent_event", "data": json.dumps(event, default=str)}
                except Exception as e:
                    logger.warning(f"SSE replay error: {e}")

            # Stream new events
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "agent_event", "data": json.dumps(event, default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": ""}
                except Exception as e:
                    logger.warning(f"SSE stream error: {e}")
                    yield {"event": "heartbeat", "data": ""}
        except Exception as e:
            logger.error(f"SSE generator crashed: {e}")
        finally:
            mgr.event_bus.unsubscribe(sid, queue)

    return EventSourceResponse(event_generator(), send_timeout=60)


# ── Graph visualization pages ──

_CLAIM_CHAIN_GRAPH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claim Chain Graph</title>
<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#bc8cff;--cyan:#39d2c0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}
.header{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;padding:8px 16px;border-bottom:1px solid var(--border);background:var(--surface)}
.header h1{font-size:14px;font-weight:600;color:var(--accent)}
.header a{color:var(--dim);font-size:12px;text-decoration:none}
.header a:hover{color:var(--text)}
#main-panel{flex:1 1 auto;position:relative;overflow:hidden;min-height:0}
#network{width:100%;height:100%}
.sidebar{position:absolute;top:8px;right:8px;width:320px;max-height:calc(100% - 16px);background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:12px;overflow-y:auto;display:none;z-index:10}
.sidebar.show{display:block}
.sidebar h3{font-size:13px;color:var(--accent);margin-bottom:8px}
.sidebar .field{margin-bottom:6px}
.sidebar .field .label{color:var(--dim);font-size:11px}
.sidebar .field .value{color:var(--text);margin-top:2px}
.sidebar .tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.sidebar .tag{background:var(--border);color:var(--text);padding:1px 6px;border-radius:3px;font-size:10px}
.toolbar{position:absolute;top:8px;left:8px;display:flex;gap:4px;z-index:10}
.toolbar button{background:var(--surface);border:1px solid var(--border);color:var(--dim);border-radius:4px;padding:4px 8px;font-size:11px;cursor:pointer}
.toolbar button:hover{background:var(--border);color:var(--text)}
#minimap{position:absolute;bottom:8px;right:8px;width:160px;height:120px;background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden;z-index:5}
.stats{position:absolute;bottom:8px;left:8px;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:11px;z-index:5}
.stats .row{display:flex;justify-content:space-between;gap:16px;margin:2px 0}
.stats .num{color:var(--accent);font-weight:600}
.legend{position:absolute;top:8px;right:8px;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:11px;z-index:5}
.legend .item{display:flex;align-items:center;gap:6px;margin:3px 0}
.legend .dot{width:10px;height:10px;border-radius:50%}
</style>
</head>
<body>
<div class="header">
  <h1>Claim Chain — Knowledge Graph</h1>
  <div style="display:flex;gap:12px;align-items:center">
    <span id="session-label" style="font-size:12px;color:var(--dim)"></span>
    <a href="javascript:void(0)" onclick="initGraph()">Refresh</a>
    <a href="/">&#8592; Dashboard</a>
  </div>
</div>
<div id="main-panel">
  <div id="network"></div>
  <div class="toolbar" id="toolbar">
    <button id="btnFit" title="Fit all nodes in view">Fit</button>
    <button id="btnReset" title="Reset zoom to 1:1">1:1</button>
  </div>
  <div class="sidebar" id="sidebar"></div>
  <div class="stats" id="stats"></div>
  <div class="legend" id="legend">
    <div class="item"><div class="dot" style="background:#58a6ff"></div> method</div>
    <div class="item"><div class="dot" style="background:#3fb950"></div> verification</div>
    <div class="item"><div class="dot" style="background:#d29922"></div> fact</div>
    <div class="item"><div class="dot" style="background:#bc8cff"></div> theorem</div>
    <div style="margin-top:4px;border-top:1px solid var(--border);padding-top:4px">
      <div class="item"><span style="color:#3fb950">&#8594;</span> validates</div>
      <div class="item"><span style="color:#f85149">&#8594;</span> contradicts</div>
      <div class="item"><span style="color:#58a6ff">&#8212;&#8258;</span> specializes</div>
      <div class="item"><span style="color:#d29922">&#8212;&#8258;</span> boundary_of</div>
      <div class="item"><span style="color:#8b949e">&#8212;&#8258;</span> other</div>
    </div>
  </div>
  <div id="minimap"></div>
</div>
<script>
const sid = window.location.pathname.split('/')[2];
document.getElementById('session-label').textContent = 'Session: ' + sid;
const typeColors = {method:'#58a6ff',verification:'#3fb950',fact:'#d29922',theorem:'#bc8cff'};
const relColors = {validates:'#3fb950',contradicts:'#f85149',specializes:'#58a6ff',boundary_of:'#d29922',causes:'#8b949e',compares_to:'#bc8cff',derives:'#8b949e',motivates:'#8b949e'};
const relWidths = {validates:3,contradicts:3,specializes:2,boundary_of:2};
const relDashes = {specializes:[5,5],boundary_of:[5,5],causes:[3,3]};

function initGraph(){
  var container = document.getElementById('network');
  // clear previous
  container.innerHTML = '';
  document.getElementById('sidebar').classList.remove('show');
  document.getElementById('sidebar').innerHTML = '';
  document.getElementById('stats').innerHTML = '';

  fetch('/api/sessions/'+sid+'/claim-chain').then(function(resp){
    if(!resp.ok){container.innerHTML='<div style="color:#f85149;padding:40px;text-align:center">API error: '+resp.status+'</div>';return;}
    resp.json().then(function(data){
      if(!data.atoms||data.atoms.length===0){container.innerHTML='<div style="color:#d29922;padding:40px;text-align:center">No atoms found in Claim Chain for session '+sid+'</div>';return;}

      var nodes = data.atoms.map(function(a){ return {
        id:a.id, label:a.title.length>28?a.title.slice(0,25)+'...':a.title,
        title:a.title+'<br>'+a.content.slice(0,120),
        color:{background:typeColors[a.type]||'#8b949e',border:typeColors[a.type]||'#8b949e'},
        font:{color:'#c9d1d9',size:12}, shape:'box', borderWidth:1,
        _data:a
      }});
      var edges = data.relations.map(function(r){ return {
        from:r.source_id, to:r.target_id,
        label:r.type, color:{color:relColors[r.type]||'#8b949e'},
        width:relWidths[r.type]||1.5, dashes:relDashes[r.type]||false,
        font:{color:'#8b949e',size:9,strokeColor:'#0d1117',strokeWidth:3},
        arrows:'to', smooth:{type:'curvedCW',roundness:0.2},
        title:r.evidence||''
      }});

      var gData = {nodes:new vis.DataSet(nodes),edges:new vis.DataSet(edges)};
      var options = {
        physics:{barnesHut:{gravitationalConstant:-2500,centralGravity:0.35,springLength:130,damping:0.2},stabilization:{iterations:200,fit:true}},
        interaction:{hover:true,tooltipDelay:100,zoomView:true,dragNodes:true,navigationButtons:false}
      };
      var network = new vis.Network(container, gData, options);
      window.network = network;

      network.once('stabilizationIterationsDone', function(){
        network.fit({animation:{duration:600,easingFunction:'easeInOutQuad'}});
      });

      // click nodes
      network.on('click',function(params){
        if(params.nodes.length>0){
          var nd = nodes.find(function(n){return n.id===params.nodes[0];});
          if(!nd) return;
          var a = nd._data;
          var sb = document.getElementById('sidebar');
          sb.innerHTML = '<h3>'+a.title+'</h3>'+
            '<div class="field"><div class="label">Type</div><div class="value">'+a.type+'</div></div>'+
            '<div class="field"><div class="label">Content</div><div class="value">'+a.content+'</div></div>'+
            '<div class="field"><div class="label">Evidence Level</div><div class="value">'+(a.evidence_level||'')+'</div></div>'+
            '<div class="field"><div class="label">Status</div><div class="value">'+(a.status||'')+'</div></div>'+
            (a.tags&&a.tags.length?'<div class="field"><div class="label">Tags</div><div class="tags">'+a.tags.map(function(t){return '<span class="tag">'+t+'</span>';}).join('')+'</div></div>':'');
          sb.classList.add('show');
          document.getElementById('legend').style.display = 'none';
        } else {
          document.getElementById('sidebar').classList.remove('show');
          document.getElementById('legend').style.display = '';
        }
      });

      // stats
      var s = data.summary;
      document.getElementById('stats').innerHTML =
        '<div class="row"><span>Atoms</span><span class="num">'+s.active_atoms+'/'+s.total_atoms+'</span></div>'+
        '<div class="row"><span>Relations</span><span class="num">'+s.total_relations+'</span></div>'+
        Object.entries(s.relation_types).map(function(e){return '<div class="row"><span>'+e[0]+'</span><span class="num">'+e[1]+'</span></div>';}).join('');

      // minimap
      setTimeout(function(){
        var mm = document.getElementById('minimap');
        var mmNodes = new vis.DataSet(nodes.map(function(n){ return {id:n.id,label:'',shape:'dot',size:3,color:{background:typeColors[n._data.type]||'#30363d',border:typeColors[n._data.type]||'#30363d'}} }));
        var mmEdges = new vis.DataSet(edges.map(function(e){ return {from:e.from,to:e.to,color:{color:'#30363d'},width:0.3,smooth:false} }));
        var mmNet = new vis.Network(mm, {nodes:mmNodes,edges:mmEdges}, {
          physics:{barnesHut:{gravitationalConstant:-800,centralGravity:0.5,springLength:60},stabilization:{iterations:80,fit:true}},
          interaction:{dragNodes:false,dragView:false,zoomView:false,hover:true},
          edges:{smooth:false}
        });
        mmNet.once('stabilized', function(){ mmNet.fit({animation:false}); });
        mm.addEventListener('click', function(e){
          var pos = mmNet.DOMtoCanvas({x:e.offsetX,y:e.offsetY});
          network.moveTo({position:pos,scale:network.getScale(),animation:{duration:300}});
        });
      }, 1200);
    }).catch(function(err){
      container.innerHTML='<div style="color:#f85149;padding:40px;text-align:center">JSON parse error: '+err.message+'</div>';
    });
  }).catch(function(err){
    container.innerHTML='<div style="color:#f85149;padding:40px;text-align:center">Fetch error: '+err.message+'</div>';
  });
}

// toolbar
document.getElementById('btnFit').addEventListener('click',function(){
  if(window.network) window.network.fit({animation:{duration:400,easingFunction:'easeInOutQuad'}});
});
document.getElementById('btnReset').addEventListener('click',function(){
  if(window.network) window.network.moveTo({scale:1,animation:{duration:400}});
});

// start
initGraph();
</script>
</body>
</html>"""


_EVOLVE_GRID_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Evolve Grid</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--red:#f85149;--yellow:#d29922}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);padding:20px}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
.header h1{font-size:16px;color:var(--accent)}
.header a{color:var(--dim);font-size:12px;text-decoration:none}
.stats{display:flex;gap:20px;margin-bottom:20px;font-size:13px}
.stats .stat{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px 16px}
.stats .stat .label{color:var(--dim);font-size:11px}
.stats .stat .value{color:var(--accent);font-size:18px;font-weight:700;margin-top:2px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:var(--surface);color:var(--dim);text-align:left;padding:8px 12px;border:1px solid var(--border);font-size:11px;text-transform:uppercase}
td{padding:8px 12px;border:1px solid var(--border)}
tr:hover td{background:rgba(88,166,255,0.05)}
.empty{color:var(--dim);font-style:italic}
.filled{color:var(--green)}
.best{color:var(--accent);font-weight:700}
</style>
</head>
<body>
<div class="header">
  <h1>Evolve Grid — MAP-Elites Archive</h1>
  <div style="display:flex;gap:12px;align-items:center">
    <span id="session-label" style="font-size:12px;color:var(--dim)"></span>
    <a href="javascript:void(0)" onclick="loadData()">Refresh</a>
    <a href="/">&#8592; Dashboard</a>
  </div>
</div>
<div class="stats" id="stats"></div>
<table id="grid-table"></table>
<script>
const sid = window.location.pathname.split('/')[2];
document.getElementById('session-label').textContent = 'Session: ' + sid;
async function loadData(){
  const resp = await fetch('/api/sessions/'+sid+'/evolve-grid');
  const data = await resp.json();
  const s = data.summary;
  document.getElementById('stats').innerHTML =
    '<div class="stat"><div class="label">Coverage</div><div class="value">'+s.filled_cells+'/'+s.total_cells+'</div></div>'+
    '<div class="stat"><div class="label">Best Score</div><div class="value">'+(s.best_score||'---')+'</div></div>'+
    '<div class="stat"><div class="label">Coverage %</div><div class="value">'+s.coverage+'</div></div>';
  const cells = data.cells;
  const best = data.best_variants;
  const bestScore = best.length>0?best[0].elite_score:0;
  let html = '<tr><th>Cell</th><th>Variant</th><th>Score</th><th>Bar</th></tr>';
  const sorted = Object.entries(cells).sort((a,b)=>{
    const sa = a[1].elite_score||-1, sb = b[1].elite_score||-1;
    return sb-sa;
  });
  for(const [key, cell] of sorted){
    const isBest = cell.elite_id && cell.elite_score === bestScore;
    const cls = isBest?'best':cell.elite_id?'filled':'empty';
    const barWidth = cell.elite_score?Math.min(100,Math.round(cell.elite_score/(bestScore||1)*100)):0;
    const barColor = isBest?'var(--accent)':cell.elite_id?'var(--green)':'var(--border)';
    html += '<tr><td class="'+cls+'">'+key+'</td><td>'+(cell.elite_id||'---')+'</td><td class="'+cls+'">'+(cell.elite_score!=null?cell.elite_score.toFixed(1):'---')+'</td><td><div style="background:'+barColor+';height:16px;width:'+barWidth+'%;border-radius:3px;min-width:'+(barWidth>0?'2px':'0')+'"></div></td></tr>';
  }
  document.getElementById('grid-table').innerHTML = html;
}
loadData();
</script>
</body>
</html>"""


async def claim_chain_graph_page(request):
    """Serve interactive Claim Chain graph visualization."""
    return HTMLResponse(_CLAIM_CHAIN_GRAPH_HTML)


async def evolve_grid_page(request):
    """Serve evolve grid visualization page."""
    return HTMLResponse(_EVOLVE_GRID_PAGE_HTML)


async def post_internal_event(request):
    """接收 PESController 推送的事件，转发到 EventBus SSE 流。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    session_id = body.get("session_id", "")
    event_type = body.get("type", "pipeline_step")
    data = body.get("data", {})

    if not session_id:
        return JSONResponse({"error": "session_id required"}, status_code=400)

    mgr = _mgr()
    if mgr and hasattr(mgr, "event_bus"):
        import time as _time
        mgr.event_bus.publish(session_id, {
            "type": event_type,
            "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "data": data,
        })
        return JSONResponse({"published": True, "session_id": session_id})
    return JSONResponse({"error": "no manager available"}, status_code=503)


# ── PES Pipeline Control ──

_PES_PIPELINE_CONTROL_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PES Pipeline Monitor</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#bc8cff;--cyan:#39d2c0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);padding:20px;max-width:1000px;margin:0 auto}
h1{font-size:18px;color:var(--accent);margin-bottom:8px}
a{color:var(--dim);font-size:12px;text-decoration:none}
a:hover{color:var(--text)}
.session-label{font-size:12px;color:var(--dim);margin-bottom:16px}

.status-bar{display:flex;gap:16px;margin-bottom:20px;font-size:13px;flex-wrap:wrap}
.status-bar .item{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:8px 14px}
.status-bar .item .label{color:var(--dim);font-size:11px}
.status-bar .item .value{color:var(--accent);font-size:16px;font-weight:700;margin-top:2px}
.status-bar .item .value.awaiting{color:var(--yellow)}
.status-bar .item .value.terminated{color:var(--red)}
.status-bar .item .value.in-progress{color:var(--green)}

.flow{display:flex;align-items:center;gap:4px;margin-bottom:24px;flex-wrap:wrap;padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:8px}
.flow .node{padding:8px 14px;border-radius:6px;font-size:12px;text-align:center;min-width:70px;border:2px solid var(--border);background:var(--bg);position:relative}
.flow .node.completed{border-color:var(--green);color:var(--green)}
.flow .node.current{border-color:var(--accent);color:var(--accent);background:rgba(88,166,255,0.1);font-weight:700}
.flow .node.current::after{content:'';position:absolute;bottom:-8px;left:50%;transform:translateX(-50%);width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:6px solid var(--accent)}
.flow .arrow{color:var(--dim);font-size:16px}

.steps-section{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.steps-section h2{font-size:14px;color:var(--accent);margin-bottom:12px}
.step-list{display:flex;flex-direction:column;gap:4px}
.step-item{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:4px;font-size:12px}
.step-item .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.step-item.done .dot{background:var(--green)}
.step-item.done{color:var(--dim)}
.step-item.active .dot{background:var(--accent);animation:pulse 1.5s infinite}
.step-item.active{color:var(--accent);font-weight:600;background:rgba(88,166,255,0.08)}
.step-item.pending .dot{background:var(--border)}
.step-item.pending{color:var(--dim)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}

.gap-section{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.gap-section h2{font-size:14px;color:var(--accent);margin-bottom:12px}
.gap-section .row{display:flex;justify-content:space-between;padding:4px 0;font-size:13px}
.gap-section .row .val{color:var(--accent);font-weight:600}
.gap-section .row .val.met{color:var(--green)}
.gap-section .row .val.not-met{color:var(--red)}
.gap-section .no-target{color:var(--yellow);font-size:13px;font-style:italic}

.controls{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.controls h2{font-size:14px;color:var(--dim);margin-bottom:8px}
.controls .hint{font-size:11px;color:var(--dim);margin-bottom:12px;font-style:italic}
.controls .btn-row{display:flex;gap:8px;flex-wrap:wrap}
.controls button{padding:10px 20px;border-radius:6px;border:1px solid var(--border);font-size:13px;font-weight:600;cursor:pointer;transition:all 0.15s}
.controls button:disabled{opacity:0.4;cursor:not-allowed}
.cmd-bar{display:flex;gap:8px;margin-bottom:8px;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:6px}
.cmd-bar .prompt{color:var(--accent);font-weight:700;font-size:16px;line-height:36px;margin:0 4px}
.cmd-bar input{flex:1;background:transparent;border:none;color:var(--text);font-size:14px;outline:none;font-family:monospace}
.cmd-bar input::placeholder{color:var(--dim)}
.cmd-bar .btn-cmd{padding:6px 16px;background:var(--accent);color:#fff;border:none;border-radius:4px;font-size:13px;cursor:pointer}
.cmd-hints{font-size:10px;color:var(--dim);margin-bottom:12px;font-family:monospace}
.cmd-status{font-size:12px;color:var(--yellow);padding:4px 0}
.cmd-status.completed{color:var(--green)}
.btn-next{background:#1a3a1a;color:var(--accent);border-color:var(--accent) !important}
.btn-next:hover:not(:disabled){background:#2a4a2a}
.btn-satisfied{background:#1a3a1a;color:var(--green);border-color:var(--green) !important}
.btn-satisfied:hover:not(:disabled){background:#2a5a2a}
.btn-unsatisfied{background:#3a2a1a;color:var(--yellow);border-color:var(--yellow) !important}
.btn-unsatisfied:hover:not(:disabled){background:#5a3a1a}
.btn-write{background:#1a1a3a;color:var(--purple);border-color:var(--purple) !important}
.btn-write:hover:not(:disabled){background:#2a2a5a}
.btn-terminate{background:#3a1a1a;color:var(--red);border-color:var(--red) !important}
.btn-terminate:hover:not(:disabled){background:#5a1a1a}
.btn-back-plan{background:#1a3a3a;color:var(--cyan);border-color:var(--cyan) !important}
.btn-back-plan:hover:not(:disabled){background:#2a5a5a}

.log-section{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}
.log-section h2{font-size:14px;color:var(--accent);margin-bottom:8px}
.log{max-height:250px;overflow-y:auto;font-family:'SF Mono',SFMono-Regular,Consolas,monospace;font-size:12px;color:var(--dim)}
.log .entry{padding:3px 0;border-bottom:1px solid rgba(48,54,61,0.4)}
.log .entry:last-child{border-bottom:none}
.log .entry.success{color:var(--green)}
.log .entry.error{color:var(--red)}
.log .entry.info{color:var(--accent)}
.log .entry .ts{color:var(--dim);margin-right:8px;font-size:10px}

/* Watchdog alerts */
.watchdog-section{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.watchdog-section h2{font-size:14px;color:var(--accent);margin-bottom:8px;display:flex;align-items:center;gap:8px}
.watchdog-section h2 .count{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
.watchdog-section h2 .count.error{background:rgba(248,81,73,0.2);color:var(--red)}
.watchdog-section h2 .count.warning{background:rgba(210,153,34,0.2);color:var(--yellow)}
.watchdog-section h2 .count.info{background:rgba(88,166,255,0.2);color:var(--accent)}
.watchdog-section h2 .count.clean{background:rgba(63,185,80,0.2);color:var(--green)}
.alert-item{display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:4px;margin-bottom:4px;font-size:12px;border-left:3px solid var(--border)}
.alert-item.error{border-left-color:var(--red);background:rgba(248,81,73,0.08)}
.alert-item.warning{border-left-color:var(--yellow);background:rgba(210,153,34,0.06)}
.alert-item.info{border-left-color:var(--accent);background:rgba(88,166,255,0.05)}
.alert-item .alert-icon{font-size:16px;flex-shrink:0}
.alert-item .alert-body{flex:1}
.alert-item .alert-msg{color:var(--text);margin-bottom:2px}
.alert-item .alert-suggestion{color:var(--dim);font-size:11px;font-style:italic}
.alert-item .alert-meta{color:var(--dim);font-size:10px;margin-top:2px}
.no-alerts{color:var(--green);font-size:13px;padding:4px 0}

/* 阶段概览条 — 8-pill strip (AutoR-inspired) */
.stage-strip{display:flex;align-items:center;gap:3px;margin-bottom:20px;padding:12px 16px;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow-x:auto}
.stage-pill{flex:1;min-width:70px;padding:10px 8px;border-radius:6px;text-align:center;font-size:11px;border:2px solid var(--border);background:var(--bg);transition:all 0.2s;position:relative}
.stage-pill .pill-name{font-weight:600;margin-bottom:2px}
.stage-pill .pill-count{font-size:10px;color:var(--dim)}
.stage-pill.completed{border-color:var(--green);background:rgba(63,185,80,0.08)}
.stage-pill.completed .pill-name{color:var(--green)}
.stage-pill.completed .pill-count{color:var(--green)}
.stage-pill.current{border-color:var(--accent);background:rgba(88,166,255,0.1);box-shadow:0 0 8px rgba(88,166,255,0.15)}
.stage-pill.current .pill-name{color:var(--accent);font-weight:700}
.stage-pill.current .pill-count{color:var(--accent)}
.stage-pill.future{border-color:var(--border);opacity:0.5}
.stage-pill.future .pill-name{color:var(--dim)}
.stage-strip .strip-arrow{color:var(--dim);font-size:14px;flex-shrink:0}

/* 决策历史和验证弹窗 */
.decision-section{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.decision-section h2{font-size:13px;color:var(--dim);margin-bottom:8px;cursor:pointer;display:flex;align-items:center;gap:6px}
.decision-section h2 .toggle{font-size:11px;color:var(--accent)}
.decision-list{max-height:200px;overflow-y:auto;font-size:11px}
.decision-item{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(48,54,61,0.3);color:var(--dim)}
.decision-item .d-action{font-weight:600;flex-shrink:0;width:70px}
.decision-item .d-action.satisfied{color:var(--green)}
.decision-item .d-action.unsatisfied{color:var(--yellow)}
.decision-item .d-action.jump{color:var(--purple)}
.decision-item .d-action.terminate{color:var(--red)}
.decision-item .d-phase{flex-shrink:0}
.decision-item .d-ts{color:var(--dim);font-size:10px;margin-left:auto;flex-shrink:0}

/* 验证弹窗 */
.validation-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:100;align-items:center;justify-content:center}
.validation-overlay.show{display:flex}
.validation-dialog{background:var(--surface);border:1px solid var(--red);border-radius:8px;padding:20px;max-width:500px;width:90%}
.validation-dialog h3{color:var(--red);font-size:15px;margin-bottom:8px}
.validation-dialog .msg{color:var(--text);font-size:13px;margin-bottom:12px}
.validation-dialog .missing-list{list-style:none;padding:0;margin-bottom:12px}
.validation-dialog .missing-list li{padding:4px 0;font-size:12px;color:var(--yellow)}
.validation-dialog .missing-list li::before{content:'- ';color:var(--red)}
.validation-dialog button{padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px}

/* 产物/结果展示区 */
.artifacts-section{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.artifacts-section h2{font-size:14px;color:var(--accent);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.artifacts-section h2 .badge{font-size:11px;padding:1px 8px;border-radius:10px;background:rgba(88,166,255,0.15);color:var(--accent)}
.artifacts-section h2 .badge.done{background:rgba(63,185,80,0.15);color:var(--green)}
.artifacts-section h3{font-size:13px;color:var(--dim);margin:12px 0 6px}
.artifacts-empty{color:var(--dim);font-size:12px;font-style:italic;padding:4px 0}

/* 方案卡片 */
.proposal-card{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:6px;font-size:12px}
.proposal-card.winner{border-color:var(--yellow);background:rgba(210,153,34,0.06)}
.proposal-card .prop-title{color:var(--accent);font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:6px}
.proposal-card .prop-title .rank{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--border);color:var(--dim)}
.proposal-card .prop-title .rank.winner-rank{background:rgba(210,153,34,0.2);color:var(--yellow);font-weight:700}
.proposal-card .prop-hypothesis{color:var(--dim);margin-bottom:4px;font-style:italic}
.proposal-card .prop-method{color:var(--text);font-family:monospace;font-size:11px;white-space:pre-wrap}
.proposal-card .prop-scores{display:flex;gap:12px;margin-top:6px;flex-wrap:wrap}
.proposal-card .prop-scores .score{font-size:11px;color:var(--dim)}
.proposal-card .prop-scores .score span{color:var(--accent);font-weight:600}
.proposal-card .prop-axioms{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.proposal-card .prop-axioms .axiom{font-size:10px;padding:1px 6px;border-radius:3px;background:var(--border);color:var(--dim)}

/* 锦标赛表格 */
.tourney-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
.tourney-table th{text-align:left;padding:6px 8px;border-bottom:2px solid var(--border);color:var(--dim);font-size:11px}
.tourney-table td{padding:6px 8px;border-bottom:1px solid rgba(48,54,61,0.4)}
.tourney-table tr:hover td{background:rgba(88,166,255,0.04)}
.tourney-table tr.winner-row td{background:rgba(210,153,34,0.06)}
.tourney-table .elo{color:var(--yellow);font-weight:700}
.tourney-table .score-num{font-weight:600}
.tourney-table .score-num.high{color:var(--green)}
.tourney-table .score-num.mid{color:var(--yellow)}
.tourney-table .score-num.low{color:var(--red)}

/* 获胜者高亮区 */
.winner-highlight{background:rgba(210,153,34,0.08);border:1px solid var(--yellow);border-radius:6px;padding:12px;margin-bottom:12px}
.winner-highlight .winner-label{font-size:11px;color:var(--yellow);font-weight:700;margin-bottom:4px;text-transform:uppercase}
.winner-highlight .winner-title{font-size:14px;color:var(--accent);font-weight:700;margin-bottom:6px}
.winner-highlight .winner-meta{font-size:12px;color:var(--dim)}

/* SME 映射卡片 */
.sme-list{display:flex;flex-direction:column;gap:4px}
.sme-item{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px 10px;font-size:11px;display:flex;align-items:center;gap:8px}
.sme-item .sme-type{font-size:10px;padding:1px 5px;border-radius:3px;font-weight:600}
.sme-item .sme-type.map{background:rgba(88,166,255,0.15);color:var(--accent)}
.sme-item .sme-type.sme{background:rgba(188,140,255,0.15);color:var(--purple)}
.sme-item .sme-type.graft{background:rgba(210,153,34,0.15);color:var(--yellow)}
.sme-item .sme-arrow{color:var(--dim)}
.sme-item .sme-domains{color:var(--text)}

/* 进度摘要 */
.progress-summary{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.progress-summary h2{font-size:14px;color:var(--accent);margin-bottom:12px}
.progress-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.progress-item{background:var(--bg);border:1px solid var(--border);border-radius:5px;padding:8px 10px;font-size:12px;display:flex;align-items:center;gap:6px}
.progress-item .p-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.progress-item .p-dot.done{background:var(--green)}
.progress-item .p-dot.active{background:var(--accent);animation:pulse 1.5s infinite}
.progress-item .p-dot.pending{background:var(--border)}
.progress-item.done{color:var(--dim)}
.progress-item.active{color:var(--accent);font-weight:600}
.progress-item.pending{color:var(--dim)}
</style>
</head>
<body>
<h1>Pipeline Monitor</h1>
<div class="session-label" id="session-label"></div>
<a href="/">&#8592; Dashboard</a>

<div class="status-bar" id="status-bar">
  <div class="item"><div class="label">Phase</div><div class="value" id="phase-val">---</div></div>
  <div class="item"><div class="label">Status</div><div class="value" id="status-val">---</div></div>
  <div class="item"><div class="label">Iteration</div><div class="value" id="iter-val">0</div></div>
  <div class="item"><div class="label">Step</div><div class="value" id="step-val">-</div></div>
</div>

<div class="stage-strip" id="stage-strip"></div>

<div class="flow" id="flow"></div>

<div class="steps-section" id="steps-section" style="display:none">
  <h2>当前阶段步骤</h2>
  <div class="step-list" id="step-list"></div>
</div>

<div class="gap-section" id="gap-section" style="display:none">
  <h2>Gap Analysis</h2>
  <div id="gap-content"></div>
</div>

<!-- 多Agent讨论产物展示 -->
<div class="artifacts-section" id="sme-section" style="display:none">
  <h2>
    多Agent讨论产物
    <span class="badge" id="sme-count-badge">--</span>
    <span class="badge done" id="sme-done-badge" style="display:none">已完成</span>
  </h2>
  <div id="sme-content"></div>
</div>

<!-- 锦标赛结果展示 -->
<div class="artifacts-section" id="tourney-section" style="display:none">
  <h2>
    ELO 锦标赛结果
    <span class="badge" id="tourney-count-badge">--</span>
    <span class="badge done" id="tourney-done-badge" style="display:none">已完成</span>
  </h2>
  <div id="tourney-highlight"></div>
  <div style="overflow-x:auto"><table class="tourney-table" id="tourney-table"></table></div>
</div>

<!-- 进度摘要 -->
<div class="progress-summary" id="progress-summary">
  <h2>产出摘要</h2>
  <div id="progress-content">
    <div class="artifacts-empty">等待执行第一步...</div>
  </div>
</div>

<!-- W4 Code 用户操作指引 (generate_code_plan / wait_user_code 时显示) -->
<div class="steps-section" id="code-instruction" style="display:none"></div>

<!-- 命令行输入区 -->
<div class="cmd-bar" id="cmd-bar">
  <span class="prompt">></span>
  <input type="text" id="cmdInput" placeholder='init "改进Actor-Critic提升Hopper-v4"' />
  <button class="btn-cmd" onclick="execCmd()">执行</button>
</div>
<div class="cmd-hints">命令: init "问题" | next | satisfied | unsatisfied | jump_write | terminate</div>

<div class="controls" id="controls">
  <h2>控制面板</h2>
  <div class="btn-row">
    <button class="btn-next" id="btn-next" onclick="execNext()">执行下一步</button>
  </div>
  <div class="btn-row" style="margin-top:8px">
    <button class="btn-satisfied" id="btn-satisfied" onclick="doTransition('satisfied')">满意 → 下一阶段</button>
    <button class="btn-unsatisfied" id="btn-unsatisfied" onclick="doTransition('unsatisfied')">不满意 → 重做</button>
    <button class="btn-back-plan" id="btn-back-plan" onclick="doTransition('jump_to_plan')">回到 Plan → 重新规划</button>
    <button class="btn-write" id="btn-write" onclick="doTransition('jump_to_write')">跳到写作</button>
    <button class="btn-terminate" id="btn-terminate" onclick="doTransition('terminate')">终止管线</button>
  </div>
  <div class="cmd-status" id="cmd-status" style="display:none"></div>
</div>

<div class="log-section">
  <h2>事件日志</h2>
  <div class="log" id="log"></div>
</div>

<div class="watchdog-section" id="watchdog-section">
  <h2>Watchdog 异常检测 <span class="count" id="watchdog-count"></span></h2>
  <div id="watchdog-alerts"></div>
</div>

<!-- 验证弹窗 (AutoR-inspired artifact gate) -->
<div class="validation-overlay" id="validation-overlay">
  <div class="validation-dialog">
    <h3>阶段产物不完整</h3>
    <div class="msg" id="validation-msg"></div>
    <ul class="missing-list" id="validation-missing"></ul>
    <button onclick="document.getElementById('validation-overlay').classList.remove('show')">关闭</button>
  </div>
</div>

<!-- 决策历史 (AutoR-inspired decision ledger) -->
<div class="decision-section" id="decision-section" style="display:none">
  <h2 onclick="toggleDecisionLedger()">
    决策历史
    <span class="toggle" id="decision-toggle">(展开)</span>
  </h2>
  <div class="decision-list" id="decision-list" style="display:none"></div>
</div>

<script>
const sid = window.location.pathname.split('/')[2];
document.getElementById('session-label').textContent = 'Session: ' + sid;

const PHASES = ["W2 Plan","W3 Research","W3.5 Ideate","W4 Code","W5 Analyze","W6 Write","W7 Review","已终止"];
const PHASE_LABELS = {"W2 Plan":"Plan","W3 Research":"Research","W3.5 Ideate":"Ideate","W4 Code":"Code","W5 Analyze":"Analyze","W6 Write":"Write","W7 Review":"Review","已终止":"终止"};
const CHAIN_STEPS = {
  "W2 Plan":     ["STEP管线分析","多Agent讨论","ELO锦标赛","Evolution Memory","写入Claim Chain"],
  "W3 Research": ["STEP管线分析","多Agent讨论","ELO锦标赛","Evolution Memory","文献调研","写入Claim Chain"],
  "W3.5 Ideate": ["STEP管线分析","多Agent讨论","ELO锦标赛","Evolution Memory","写入Claim Chain"],
  "W4 Code":     ["STEP管线分析","写入Claim Chain","生成代码计划","等待用户实现"],
  "W5 Analyze":  ["STEP管线分析","实验分析扫描","多Agent Judge","Evolution Memory","写入Claim Chain","Island分配"],
  "W6 Write":    ["撰写论文"],
  "W7 Review":   ["审阅论文"]
};

let workspaceDir = "";
let eventSource = null;

function addLog(msg, cls) {
  const log = document.getElementById('log');
  const entry = document.createElement('div');
  entry.className = 'entry ' + (cls || '');
  const now = new Date().toLocaleTimeString();
  entry.innerHTML = '<span class="ts">' + now + '</span>' + msg;
  log.prepend(entry);
  if (log.children.length > 150) log.lastChild.remove();
}

function renderStageStrip(state, currentPhase) {
  var strip = document.getElementById('stage-strip');
  var phases = ["W2 Plan","W3 Research","W3.5 Ideate","W4 Code","W5 Analyze","W6 Write","W7 Review"];
  var labels = {"W2 Plan":"Plan","W3 Research":"Research","W3.5 Ideate":"Ideate","W4 Code":"Code","W5 Analyze":"Analyze","W6 Write":"Write","W7 Review":"Review"};
  var deliverables = state.deliverables || [];
  var currentIdx = phases.indexOf(currentPhase);
  if (currentIdx < 0 && currentPhase === '已终止') currentIdx = phases.length;

  // Count deliverables per phase
  var phaseCounts = {};
  deliverables.forEach(function(d) {
    var p = d.phase || '';
    if (!phaseCounts[p]) phaseCounts[p] = 0;
    phaseCounts[p]++;
  });

  // Expected steps per phase (from CHAIN_STEPS)
  var expected = {"W2 Plan":5,"W3 Research":6,"W3.5 Ideate":5,"W4 Code":4,"W5 Analyze":6,"W6 Write":1,"W7 Review":1};

  var html = '';
  phases.forEach(function(p, i) {
    var label = labels[p] || p;
    var count = phaseCounts[p] || 0;
    var exp = expected[p] || 1;
    var cls = '';
    if (i < currentIdx) cls = 'completed';
    else if (i === currentIdx && currentPhase !== '已终止') cls = 'current';
    else cls = 'future';
    if (i > 0) html += '<span class="strip-arrow">→</span>';
    html += '<div class="stage-pill ' + cls + '">' +
      '<div class="pill-name">' + label + '</div>' +
      '<div class="pill-count">' + count + '/' + exp + '</div>' +
    '</div>';
  });
  strip.innerHTML = html;
}

function renderDecisionLedger(state) {
  var section = document.getElementById('decision-section');
  var list = document.getElementById('decision-list');
  var ledger = state.decision_ledger || [];
  if (ledger.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';

  var actionLabels = {satisfied:'满意→下一步', unsatisfied:'不满意→重做', jump_to_plan:'回到Plan', jump_to_write:'跳到写作', terminate:'终止'};
  var actionCls = {satisfied:'satisfied', unsatisfied:'unsatisfied', jump_to_plan:'jump', jump_to_write:'jump', terminate:'terminate'};
  var recent = ledger.slice(-20).reverse();
  var html = '';
  recent.forEach(function(d) {
    var actLabel = actionLabels[d.action] || d.action;
    var actCls = actionCls[d.action] || '';
    var ts = d.timestamp ? new Date(d.timestamp * 1000).toLocaleString() : '';
    var phaseStr = d.from_phase ? (PHASE_LABELS[d.from_phase] || d.from_phase) : '';
    if (d.to_phase) phaseStr += ' → ' + (PHASE_LABELS[d.to_phase] || d.to_phase);
    var valNote = d.validation_passed === false ? ' (验证失败)' : '';
    html += '<div class="decision-item">' +
      '<span class="d-action ' + actCls + '">' + actLabel + '</span>' +
      '<span class="d-phase">' + phaseStr + valNote + '</span>' +
      '<span class="d-ts">' + ts + '</span>' +
    '</div>';
  });
  list.innerHTML = html;
}

function toggleDecisionLedger() {
  var list = document.getElementById('decision-list');
  var toggle = document.getElementById('decision-toggle');
  if (list.style.display === 'none') {
    list.style.display = '';
    toggle.textContent = '(收起)';
  } else {
    list.style.display = 'none';
    toggle.textContent = '(展开)';
  }
}

function showValidationError(missing, warnings) {
  var overlay = document.getElementById('validation-overlay');
  var msg = document.getElementById('validation-msg');
  var list = document.getElementById('validation-missing');
  msg.textContent = '以下产物缺失，请先完成当前阶段的所有步骤再转换：';
  var items = '';
  missing.forEach(function(m) { items += '<li>' + m + '</li>'; });
  if (warnings && warnings.length > 0) {
    warnings.forEach(function(w) { items += '<li style="color:var(--yellow)">⚠ ' + w + '</li>'; });
  }
  list.innerHTML = items;
  overlay.classList.add('show');
}

function renderFlow(phase, status) {
  const flow = document.getElementById('flow');
  const phaseIdx = PHASES.indexOf(phase);
  let html = '';
  PHASES.forEach(function(p, i) {
    if (p === '已终止') return;
    const label = PHASE_LABELS[p] || p;
    let cls = '';
    if (i < phaseIdx) cls = 'completed';
    else if (i === phaseIdx && status !== 'terminated') cls = 'current';
    if (i > 0) html += '<span class="arrow">&#8594;</span>';
    html += '<div class="node ' + cls + '">' + label + '</div>';
  });
  flow.innerHTML = html;
}

function renderSteps(phase, stepIdx) {
  const section = document.getElementById('steps-section');
  const list = document.getElementById('step-list');
  const steps = CHAIN_STEPS[phase];
  if (!steps || steps.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  document.getElementById('step-val').textContent = Math.min(stepIdx + 1, steps.length) + '/' + steps.length;
  let html = '';
  steps.forEach(function(s, i) {
    let cls = i < stepIdx ? 'done' : (i === stepIdx ? 'active' : 'pending');
    html += '<div class="step-item ' + cls + '"><div class="dot"></div>' + s + '</div>';
  });
  list.innerHTML = html;
}

function renderGap(gap) {
  const section = document.getElementById('gap-section');
  const content = document.getElementById('gap-content');
  if (!gap) { section.style.display = 'none'; return; }
  section.style.display = '';
  if (gap.target_score === null || gap.target_score === undefined) {
    content.innerHTML = '<div class="no-target">未定义成功目标 (success_criteria.md)</div>';
    return;
  }
  const met = gap.target_met;
  const verdict = met ? '<span class="val met">达标!</span>' : '<span class="val not-met">未达标</span>';
  content.innerHTML =
    '<div class="row"><span>Target</span><span class="val">' + gap.target_score + '</span></div>' +
    '<div class="row"><span>Best Score</span><span class="val">' + gap.best_score + '</span></div>' +
    '<div class="row"><span>Gap</span><span class="val ' + (met?'met':'not-met') + '">' + (gap.gap !== null ? gap.gap : '---') + '</span></div>' +
    '<div class="row"><span>Gap %</span><span class="val">' + (gap.gap_percent !== null ? gap.gap_percent.toFixed(1) + '%' : '---') + '</span></div>' +
    '<div class="row"><span>CC Atoms</span><span class="val">' + gap.cc_atom_count + '</span></div>' +
    '<div class="row"><span>Grid</span><span class="val">' + gap.grid_filled + '/' + gap.grid_total + '</span></div>' +
    '<div class="row"><span>Iteration</span><span class="val">' + gap.iteration + '</span></div>' +
    '<div class="row"><span>Verdict</span>' + verdict + '</div>';
}

function renderArtifacts(state) {
  var ctx = state.last_pipeline_context || {};
  var sme = ctx.sme_mappings || [];
  var proposals = ctx.proposals || [];
  var evals = ctx.evaluation || [];

  // SME mappings section
  var smeSection = document.getElementById('sme-section');
  var smeContent = document.getElementById('sme-content');
  var smeCount = document.getElementById('sme-count-badge');
  var smeDone = document.getElementById('sme-done-badge');
  if (sme.length > 0) {
    smeSection.style.display = '';
    smeCount.textContent = sme.length + ' 个映射';
    smeDone.style.display = '';
    var smeHtml = '<div class="sme-list">';
    sme.forEach(function(m) {
      var typeClass = (m.type || '').toLowerCase();
      var arrow = m.arrow || '→';
      smeHtml += '<div class="sme-item">' +
        '<span class="sme-type ' + typeClass + '">' + (m.type || 'Map') + '</span>' +
        '<span class="sme-domains">' +
          '<span>' + (m.source_domain || '?') + ':' + (m.source_pattern || []).join('×') + '</span>' +
          ' <span class="sme-arrow">' + arrow + '</span> ' +
          '<span>' + (m.target_domain || '?') + ':' + (m.target_pattern || []).join('×') + '</span>' +
        '</span>' +
      '</div>';
    });
    smeHtml += '</div>';
    smeContent.innerHTML = smeHtml;
  } else {
    smeSection.style.display = 'none';
  }

  // Proposals summary (compact cards)
  var propSection = document.getElementById('prop-section');
  if (!propSection && proposals.length > 0 && !document.getElementById('tourney-section').style.display || true) {
    // Show proposals inline within the tournament section if no separate prop section
  }
}

function renderTournament(tourney, ctx) {
  var section = document.getElementById('tourney-section');
  var highlight = document.getElementById('tourney-highlight');
  var table = document.getElementById('tourney-table');
  var countBadge = document.getElementById('tourney-count-badge');
  var doneBadge = document.getElementById('tourney-done-badge');

  var ranked = tourney && (tourney.ranked || tourney.proposals);
  var proposals = ctx && ctx.proposals;
  if (!ranked && !proposals) {
    section.style.display = 'none';
    return;
  }

  section.style.display = '';
  var items = ranked || proposals || [];

  if (tourney && tourney.status === 'completed') {
    doneBadge.style.display = '';
    countBadge.textContent = items.length + ' 个方案 (已排序)';
  } else if (items.length > 0) {
    doneBadge.style.display = 'none';
    countBadge.textContent = items.length + ' 个方案 (待排序)';
  }

  // Winner highlight
  var winner = (tourney && tourney.winner) ? items.find(function(p) { return (p.id || p.title) === tourney.winner; }) : null;
  if (!winner && items.length > 0) winner = items[0];
  if (winner && tourney && tourney.status === 'completed') {
    highlight.innerHTML =
      '<div class="winner-highlight">' +
        '<div class="winner-label">锦标赛获胜方案</div>' +
        '<div class="winner-title">' + (winner.title || winner.id || '') + '</div>' +
        '<div class="winner-meta">' +
          'Elo: <strong style="color:var(--yellow)">' + (typeof winner.elo_rating === 'number' ? winner.elo_rating.toFixed(0) : winner.elo_rating || '--') + '</strong>' +
          ' | 新颖性: <strong>' + (typeof winner.novelty === 'number' ? winner.novelty.toFixed(1) : winner.novelty || '--') + '</strong>' +
          ' | 可行性: <strong>' + (typeof winner.feasibility === 'number' ? winner.feasibility.toFixed(1) : winner.feasibility || '--') + '</strong>' +
          ' | 相关性: <strong>' + (typeof winner.relevance === 'number' ? winner.relevance.toFixed(1) : winner.relevance || '--') + '</strong>' +
        '</div>' +
      '</div>';
  } else {
    highlight.innerHTML = '';
  }

  // Build table
  var hasScores = items.length > 0 && (items[0].elo_rating !== undefined || items[0].novelty !== undefined);
  var shown = items.slice(0, 10);
  var htm = '<thead><tr><th>#</th><th>标题</th>';
  if (hasScores) htm += '<th>Elo</th><th>新颖性</th><th>可行性</th><th>相关性</th>';
  htm += '<th>方法概要</th></tr></thead><tbody>';
  shown.forEach(function(p, i) {
    var isWinner = winner && (p.id || p.title) === (winner.id || winner.title);
    var scoreClass = function(v) { return v >= 7 ? 'high' : (v >= 5 ? 'mid' : 'low'); };
    var title = p.title || p.id || 'proposal_' + i;
    if (title.length > 80) title = title.substring(0, 77) + '...';
    var method = p.method_sketch || p.hypothesis || '';
    if (method.length > 100) method = method.substring(0, 97) + '...';
    htm += '<tr class="' + (isWinner ? 'winner-row' : '') + '">' +
      '<td>' + (i + 1) + '</td>' +
      '<td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + (p.title || '').replace(/"/g,'&quot;') + '">' + title + '</td>';
    if (hasScores) {
      htm += '<td class="elo">' + (typeof p.elo_rating === 'number' ? p.elo_rating.toFixed(0) : '--') + '</td>' +
        '<td class="score-num ' + scoreClass(p.novelty || 0) + '">' + (typeof p.novelty === 'number' ? p.novelty.toFixed(1) : '--') + '</td>' +
        '<td class="score-num ' + scoreClass(p.feasibility || 0) + '">' + (typeof p.feasibility === 'number' ? p.feasibility.toFixed(1) : '--') + '</td>' +
        '<td class="score-num ' + scoreClass(p.relevance || 0) + '">' + (typeof p.relevance === 'number' ? p.relevance.toFixed(1) : '--') + '</td>';
    }
    htm += '<td style="font-size:11px;color:var(--dim);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + method.replace(/"/g,'&quot;') + '">' + method + '</td>' +
      '</tr>';
  });
  if (items.length > 10) {
    htm += '<tr><td colspan="' + (hasScores ? 7 : 3) + '" style="text-align:center;color:var(--dim);padding:8px">... 以及 ' + (items.length - 10) + ' 个更多方案</td></tr>';
  }
  htm += '</tbody>';
  table.innerHTML = htm;
}

function renderProgressSummary(state, phase, stepIdx) {
  var container = document.getElementById('progress-content');
  var deliverables = state.deliverables || [];
  var items = [];

  // Phase label mapping
  var phaseLabels = {'W2 Plan':'Plan','W3 Research':'Research','W3.5 Ideate':'Ideate','W4 Code':'Code','W5 Analyze':'Analyze','W6 Write':'Write','W7 Review':'Review'};
  var phaseLabel = phaseLabels[phase] || phase;

  // 1. 研究问题 (always first)
  if (state.research_topic) {
    items.push({label: '研究问题', value: state.research_topic.substring(0, 60), icon: 'done', phase: ''});
  }

  // 2. Phase and iteration
  items.push({label: '当前阶段', value: phaseLabel + ' (It.' + (state.iteration||0) + ', Step ' + (stepIdx||0) + ')', icon: 'active', phase: ''});

  // 3. Deliverables from state.deliverables (canonical source)
  var dlIcon = {'pipeline_context':'done','multi_agent_discuss':'done','elo_tournament':'done',
                'evolution_memory':'done','write_claim_chain':'done','scan_islands_rubrics':'done',
                'island_assign':'done','research_notes':'done','paper':'done','review':'done'};
  var dlLabel = {'pipeline_context':'STEP管线分析','multi_agent_discuss':'多Agent讨论','elo_tournament':'ELO锦标赛',
                 'evolution_memory':'Evolution Memory','write_claim_chain':'Claim Chain写入','scan_islands_rubrics':'实验分析',
                 'island_assign':'Island分配','research_notes':'研究笔记','paper':'论文报告','review':'审阅'};

  deliverables.forEach(function(d) {
    var icon = dlIcon[d.type] || 'done';
    var label = dlLabel[d.type] || d.type;
    var summary = d.summary || '';
    if (summary.length > 80) summary = summary.substring(0, 77) + '...';
    items.push({label: label, value: summary, icon: icon, phase: d.phase || ''});
  });

  // 4. Context-based supplements (when no deliverables recorded yet)
  if (deliverables.length === 0) {
    var ctx = state.last_pipeline_context || {};
    var proposals = ctx.proposals || [];
    var sme = ctx.sme_mappings || [];
    if (sme.length > 0) {
      items.push({label: 'SME映射', value: sme.length + ' 个跨域映射', icon: 'done'});
    }
    if (proposals.length > 0) {
      items.push({label: '研究方案', value: proposals.length + ' 个方案', icon: 'done'});
    }
    var tourney = state.last_tournament_result || {};
    if (tourney.status === 'completed') {
      items.push({label: 'ELO排序', value: '已完成 (胜者已选出)', icon: 'done'});
    }
  }

  // 5. Gap Analysis
  if (state.last_gap_analysis && state.last_gap_analysis.target_score !== undefined) {
    items.push({label: 'Gap Analysis', value: 'Target: ' + state.last_gap_analysis.target_score, icon: 'done'});
  }

  // 6. Agent report (W6 Write / W7 Review via Agent SDK)
  if (state.last_report) {
    var rpt = state.last_report;
    var rptSummary = (rpt.step_name || '') + ': ' + (rpt.result || '').substring(0, 60);
    items.push({label: 'Agent报告', value: rptSummary, icon: 'done'});
  }

  if (items.length === 0) {
    container.innerHTML = '<div class="artifacts-empty">等待执行第一步...</div>';
    return;
  }

  var html = '<div class="progress-grid">';
  items.forEach(function(item) {
    html += '<div class="progress-item ' + item.icon + '">' +
      '<div class="p-dot ' + item.icon + '"></div>' +
      '<div><strong>' + item.label + '</strong><br><span style="font-size:10px;color:var(--dim)">' + (item.phase ? '[' + (phaseLabels[item.phase]||item.phase) + '] ' : '') + item.value + '</span></div>' +
    '</div>';
  });
  html += '</div>';
  container.innerHTML = html;
}

function updateControls(status, phase, cmd, taskRunning, activeTask) {
  const awaiting = status === 'awaiting_decision';
  const terminated = status === 'terminated' || phase === '已终止';
  const cmdBusy = cmd && (cmd.status === 'pending' || cmd.status === 'executing');

  // 执行下一步按钮：多Agent任务进行中 / awaiting / terminated / execBusy 时禁用
  document.getElementById('btn-next').disabled = awaiting || terminated || cmdBusy || execBusy || taskRunning;

  // 决策按钮：仅 awaiting 时启用
  document.getElementById('btn-unsatisfied').disabled = !awaiting;
  document.getElementById('btn-satisfied').disabled = !awaiting;
  document.getElementById('btn-write').disabled = !awaiting || terminated;
  document.getElementById('btn-terminate').disabled = terminated;
  document.getElementById('btn-back-plan').disabled = terminated;

  // 命令/任务状态指示器
  var statusEl = document.getElementById('cmd-status');
  if (taskRunning || activeTask) {
    statusEl.style.display = '';
    statusEl.textContent = '⏳ 多Agent任务进行中，请等待完成...';
    statusEl.className = 'cmd-status pending';
  } else if (cmdBusy) {
    statusEl.style.display = '';
    statusEl.textContent = cmd.status === 'pending' ? '等待 Claude Code 认领命令...' : 'Claude Code 正在执行...';
    statusEl.className = 'cmd-status ' + cmd.status;
  } else if (cmd && cmd.status === 'completed') {
    statusEl.style.display = '';
    statusEl.textContent = '步骤完成';
    statusEl.className = 'cmd-status completed';
  } else {
    statusEl.style.display = 'none';
  }
}

// 命令行输入处理
function execCmd() {
  var input = document.getElementById('cmdInput').value.trim();
  if (!input) return;
  document.getElementById('cmdInput').value = '';

  if (input.startsWith('init ')) {
    var topic = input.substring(5).replace(/^"|"$/g, '');
    addLog('初始化管线: ' + topic, 'info');
    fetch('/api/pipeline/init', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({workspace_dir: workspaceDir, research_topic: topic})
    }).then(function(r) { return r.json(); }).then(function(d) {
      addLog('Init: ' + JSON.stringify(d), 'info');
      refreshState();
    });
  } else {
    var actionMap = {next:'sub_loop', satisfied:'transition', unsatisfied:'transition', jump_write:'transition', terminate:'transition', jump_plan:'transition'};
    var cmd = input.replace(/^\//, '');
    var action = actionMap[cmd] || 'sub_loop';

    if (action === 'transition') {
      doTransition(cmd);
    } else if (action === 'sub_loop') {
      execNext();
    }
  }
}

let execBusy = false;

// 执行下一步 (Dashboard 直驱)
function execNext() {
  if (execBusy) {
    addLog('上一个操作正在进行中，请稍后再点击', 'error');
    return;
  }
  execBusy = true;
  document.getElementById('btn-next').disabled = true;
  addLog('执行下一步...', 'info');
  fetch('/api/pipeline/execute', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({workspace_dir: workspaceDir})
  }).then(function(r) { return r.json(); }).then(function(d) {
    execBusy = false;
    if (d.task_running) {
      addLog('⚠ ' + d.error, 'error');
    } else if (d.task_started) {
      addLog('后台任务已启动: ' + d.detail, 'info');
      addLog('⏳ 讨论进行中，等待完成后自动解锁...', 'info');
    } else if (d.agent_spawned) {
      addLog('Agent SDK 子进程已启动: ' + d.task, 'info');
    } else if (d.waiting_for_user) {
      addLog('⏳ 等待用户完成代码实现...', 'info');
      if (d.instruction) {
        showCodeInstruction(d.instruction);
      }
    } else if (d.plan_path) {
      addLog('Plan已生成: ' + d.plan_path, 'success');
      if (d.instruction) {
        showCodeInstruction(d.instruction);
      }
    } else if (d.step_done) {
      addLog('阶段完成: ' + d.message, 'info');
      hideCodeInstruction();
    } else if (d.executed) {
      addLog('已执行: ' + (d.detail || d.step || 'OK'), 'info');
    } else {
      addLog('已执行: ' + JSON.stringify(d), 'info');
    }
    refreshState();
  }).catch(function(e) {
    execBusy = false;
    addLog('请求失败: ' + e.message, 'error');
    refreshState();
  });
}

function showCodeInstruction(text) {
  var panel = document.getElementById('code-instruction');
  if (!panel) return;
  panel.style.display = '';
  panel.innerHTML = '<h2>W4 Code — 用户操作指引</h2><pre style=\"white-space:pre-wrap;font-size:13px;color:var(--accent);background:rgba(88,166,255,0.08);padding:12px;border-radius:6px;border:1px solid var(--accent);\">' + text.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>';
}

function hideCodeInstruction() {
  var panel = document.getElementById('code-instruction');
  if (panel) panel.style.display = 'none';
}

async function loadWorkspace() {
  // 优先从 URL query param 获取 workspace (bootstrap 时传递)
  const qp = new URLSearchParams(window.location.search);
  const wsFromUrl = qp.get('workspace');
  if (wsFromUrl) {
    workspaceDir = wsFromUrl;
    addLog('Workspace from URL: ' + wsFromUrl, 'info');
    return true;
  }
  // Fallback: 从 session 列表查找
  try {
    const resp = await fetch('/api/sessions');
    const sessions = await resp.json();
    const session = sessions.find(function(s) { return s.session_id === sid; });
    if (session && session.workspace_dir) {
      workspaceDir = session.workspace_dir;
      return true;
    }
    addLog('Session ' + sid + ' 未找到或无 workspace_dir', 'error');
    return false;
  } catch (e) {
    addLog('加载 session 失败: ' + e.message, 'error');
    return false;
  }
}

async function refreshState() {
  if (!workspaceDir) return;
  try {
    const resp = await fetch('/api/pipeline/state?workspace=' + encodeURIComponent(workspaceDir));
    if (!resp.ok) { addLog('State fetch error: ' + resp.status, 'error'); return; }
    const state = await resp.json();
    const phase = state.phase || '---';
    const status = state.status || '---';
    const iter = state.iteration || 0;
    const stepIdx = state.sub_loop_step || 0;
    const activeTask = state.active_task;

    document.getElementById('phase-val').textContent = phase;
    const statusEl = document.getElementById('status-val');
    const statusMap = {'awaiting_decision':'等待决策','in_progress':'执行中','terminated':'已终止','not_initialized':'未初始化'};
    statusEl.textContent = statusMap[status] || status;
    statusEl.className = 'value' + (status === 'awaiting_decision' ? ' awaiting' : '') + (status === 'terminated' ? ' terminated' : '') + (status === 'in_progress' ? ' in-progress' : '');
    document.getElementById('iter-val').textContent = iter;

    // 非 W4 Code 阶段时隐藏旧的用户操作指引
    if (phase !== 'W4 Code' || status !== 'awaiting_user_code') {
      document.getElementById('code-instruction').style.display = 'none';
    }

    // 检查 session 是否在运行 (多Agent任务进行中)
    // 以 active_task 为主锁 (Dashboard _execute_step 管理)
    // session status 仅作辅助确认, 不独立触发锁定
    let taskRunning = false;
    if (activeTask) {
      const elapsed = (Date.now()/1000) - (activeTask.started_at || 0);
      if (elapsed < 1800) {
        taskRunning = true;
      }
    }
    // session status 只在 activeTask 存在时做辅助确认
    if (taskRunning) {
      try {
        const sResp = await fetch('/api/sessions/' + sid);
        if (sResp.ok) {
          const sData = await sResp.json();
          // 如果 session 已经 completed/error/idle，说明讨论已完成，可以解锁
          if (sData.status === 'completed' || sData.status === 'error' || sData.status === 'idle') {
            taskRunning = false;
          }
        }
      } catch(e) {}
    }

    renderStageStrip(state, phase);
    renderFlow(phase, status);
    renderSteps(phase, stepIdx);
    renderGap(state.last_gap_analysis);
    renderArtifacts(state);
    renderTournament(state.last_tournament_result, state.last_pipeline_context);
    renderProgressSummary(state, phase, stepIdx);
    renderDecisionLedger(state);
    updateControls(status, phase, state.command, taskRunning, activeTask);
    refreshWatchdog();
  } catch (e) {
    addLog('Refresh error: ' + e.message, 'error');
  }
}

let watchdogAlerts = [];

async function refreshWatchdog() {
  try {
    const resp = await fetch('/api/watchdog/alerts?limit=10&session_id=' + encodeURIComponent(sid));
    if (!resp.ok) return;
    const alerts = await resp.json();
    if (JSON.stringify(alerts) === JSON.stringify(watchdogAlerts)) return;
    watchdogAlerts = alerts;
    renderWatchdog(alerts);
  } catch(e) {}
}

function renderWatchdog(alerts) {
  const container = document.getElementById('watchdog-alerts');
  const countEl = document.getElementById('watchdog-count');
  if (!alerts || alerts.length === 0) {
    container.innerHTML = '<div class="no-alerts">Pipeline 状态正常</div>';
    countEl.textContent = '无异常';
    countEl.className = 'count clean';
    return;
  }
  const sevOrder = {error:0, warning:1, info:2};
  const sorted = alerts.slice().sort((a,b) => (sevOrder[a.severity]||9) - (sevOrder[b.severity]||9));
  const errCount = sorted.filter(a => a.severity==='error').length;
  const warnCount = sorted.filter(a => a.severity==='warning').length;
  const worstSev = errCount > 0 ? 'error' : (warnCount > 0 ? 'warning' : 'info');
  countEl.textContent = alerts.length + ' 条告警';
  countEl.className = 'count ' + worstSev;

  const icons = {error:'❌', warning:'⚠️', info:'ℹ️'};
  const cats = {stall:'停滞检测', timeout:'超时', heartbeat:'心跳', lock:'锁', state:'状态不一致'};
  let html = '';
  sorted.forEach(function(a) {
    const elapsed = a.elapsed ? (a.elapsed >= 60 ? (a.elapsed/60).toFixed(1) + 'min' : a.elapsed.toFixed(0) + 's') : '';
    const meta = [a.phase, a.step, elapsed].filter(Boolean).join(' · ');
    html += '<div class="alert-item ' + a.severity + '">' +
      '<div class="alert-icon">' + (icons[a.severity] || '?') + '</div>' +
      '<div class="alert-body">' +
        '<div class="alert-msg">[' + (cats[a.category] || a.category) + '] ' + a.message + '</div>' +
        '<div class="alert-suggestion">→ ' + a.suggestion + '</div>' +
        '<div class="alert-meta">' + meta + '</div>' +
      '</div>' +
    '</div>';
  });
  container.innerHTML = html;
}

async function doTransition(action) {
  if (!workspaceDir) { addLog('workspace 未加载', 'error'); return; }
  const labels = {satisfied:'满意-下一步', unsatisfied:'不满意-重做', jump_to_write:'强制进入写作', terminate:'终止管线', jump_to_plan:'回到 Plan'};
  addLog('备用控制: ' + labels[action], 'info');
  try {
    const resp = await fetch('/api/pipeline/transition', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({workspace_dir: workspaceDir, action: action}),
    });
    const result = await resp.json();
    if (result.error) {
      // Check for artifact validation failure
      if (resp.status === 400 && result.missing_artifacts) {
        showValidationError(result.missing_artifacts, result.warnings);
        addLog('产物验证失败: ' + result.missing_artifacts.join('; '), 'error');
      } else {
        addLog('错误: ' + result.error, 'error');
      }
    } else {
      const msg = result.transitioned
        ? ('阶段转换: ' + (result.from || '') + ' -> ' + result.to)
        : ('重做阶段: ' + (result.phase || ''));
      addLog(msg, 'success');
      if (result.validation && result.validation.warnings && result.validation.warnings.length > 0) {
        addLog('验证通过但有警告: ' + result.validation.warnings.join('; '), 'info');
      }
    }
    await refreshState();
  } catch (e) {
    addLog('Transition error: ' + e.message, 'error');
  }
}

function connectSSE() {
  if (eventSource) { eventSource.close(); }
  eventSource = new EventSource('/api/sessions/' + sid + '/events');
  eventSource.addEventListener('agent_event', function(e) {
    try {
      const ev = JSON.parse(e.data);
      if (ev.type && ev.type.startsWith('pipeline_')) {
        const detail = ev.data ? JSON.stringify(ev.data) : '';
        addLog('[' + ev.type + '] ' + detail, 'info');
      }
    } catch(ex) {}
  });
  eventSource.addEventListener('heartbeat', function() {});
  eventSource.addEventListener('watchdog_alert', function(e) {
    try {
      const alert = JSON.parse(e.data);
      if (alert && alert.severity === 'error') {
        addLog('⚠ Watchdog: ' + alert.message, 'error');
      }
      refreshWatchdog();
    } catch(ex) {}
  });
}

async function init() {
  addLog('初始化 Pipeline Monitor...', 'info');
  const ok = await loadWorkspace();
  if (ok) {
    addLog('Workspace: ' + workspaceDir, 'info');
    await refreshState();
    connectSSE();
    setInterval(refreshState, 2000);
  }
}
init();
</script>
</body>
</html>"""


# ── PES Pipeline Control ──

async def pes_pipeline_page(request):
    """管线监控页面（从 session 自动获取 workspace）。"""
    return HTMLResponse(_PES_PIPELINE_CONTROL_HTML)


async def pes_pipeline_transition_api(request):
    """Dashboard 直接操作 PIPELINE_STATE.json 执行阶段流转。无需 8421 代理。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    workspace = body.get("workspace_dir", "")
    action = body.get("action", "satisfied")

    if not workspace:
        return JSONResponse({"error": "workspace_dir required"}, status_code=400)

    state_path = Path(workspace) / "PIPELINE_STATE.json"
    if not state_path.exists():
        return JSONResponse({"error": "no pipeline state found"}, status_code=404)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    phase = state.get("phase", "")

    # 清除跨阶段残留的 agent 状态 (避免 active_task 等泄露到下一阶段)
    _clear_stale_agent_state(state)

    # 初始化决策账本 (AutoR-inspired: human decision audit trail)
    if "decision_ledger" not in state:
        state["decision_ledger"] = []

    # 阶段转换前的产物验证 (AutoR-inspired: artifact-backed validation)
    if action == "satisfied":
        validation = _validate_phase_artifacts(phase, state, Path(workspace))
        if not validation["valid"]:
            return JSONResponse({
                "error": f"阶段产物不完整，无法进入下一阶段",
                "missing_artifacts": validation["missing"],
                "warnings": validation.get("warnings", []),
                "validation_details": validation["details"],
            }, status_code=400)

    # 记录决策到账本 (AutoR-inspired)
    ledger_entry = {
        "timestamp": time.time(),
        "action": action,
        "from_phase": phase,
        "iteration": state.get("iteration", 0),
    }

    if action == "satisfied":
        next_phase = _auto_next_phase(phase, state)
        state["phase"] = next_phase
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state.pop("command", None)
        if phase == "W5 Analyze":
            state["iteration"] = state.get("iteration", 0) + 1
        # 记录账本
        ledger_entry["to_phase"] = next_phase
        ledger_entry["validation_passed"] = validation.get("valid", True)
        state["decision_ledger"].append(ledger_entry)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        # 追加可读记忆文件 (AutoR-inspired)
        try:
            _append_phase_memory(phase, state, Path(workspace))
        except Exception:
            pass
        return JSONResponse({"transitioned": True, "from": phase, "to": next_phase,
                            "validation": {"passed": True, "warnings": validation.get("warnings", [])}})

    elif action == "unsatisfied":
        if phase == "W7 Review":
            state["phase"] = "W6 Write"
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state.pop("command", None)
        ledger_entry["to_phase"] = state["phase"]
        state["decision_ledger"].append(ledger_entry)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": False, "phase": state["phase"],
                            "message": f"重做阶段 '{state['phase']}'"})

    elif action == "jump_to_plan":
        state["phase"] = "W2 Plan"
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state["iteration"] = state.get("iteration", 0) + 1
        ledger_entry["to_phase"] = "W2 Plan"
        state["decision_ledger"].append(ledger_entry)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": True, "to": "W2 Plan", "iteration": state["iteration"]})

    elif action == "jump_to_write":
        gap = state.get("last_gap_analysis")
        if not gap or gap.get("target_score") is None:
            return JSONResponse({"error": "无法进入写作：未定义成功目标。请先创建 success_criteria.md"}, status_code=400)
        state["phase"] = "W6 Write"
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state.pop("command", None)
        ledger_entry["to_phase"] = "W6 Write"
        state["decision_ledger"].append(ledger_entry)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": True, "to": "W6 Write"})

    elif action == "terminate":
        state["phase"] = "已终止"
        state["status"] = "terminated"
        ledger_entry["to_phase"] = "已终止"
        state["decision_ledger"].append(ledger_entry)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": True, "to": "已终止"})

    return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)


def _validate_phase_artifacts(phase: str, state: dict, ws_path: Path) -> dict:
    """AutoR-inspired: 阶段产物完整性验证（严格级：state + 文件 + 内容）。

    返回 {"valid": bool, "missing": [...], "warnings": [...], "details": {...}}
    """
    missing = []
    warnings = []
    details = {}

    vault = ws_path / "vault"
    index_dir = vault / "_index"
    ctx = state.get("last_pipeline_context", {})
    deliverables = state.get("deliverables", [])
    phase_dls = [d for d in deliverables if d.get("phase") == phase]

    if phase == "W2 Plan":
        # State checks
        proposals = ctx.get("proposals", [])
        if not proposals:
            missing.append("last_pipeline_context.proposals 为空")
        tourney = state.get("last_tournament_result", {})
        ranked = tourney.get("ranked") or tourney.get("proposals") or []
        if not ranked:
            missing.append("last_tournament_result.ranked 为空 — ELO 锦标赛未完成")
        # File checks
        atoms_files = list(index_dir.glob("atoms*.jsonl")) if index_dir.exists() else []
        if not atoms_files:
            missing.append("vault/_index/ 中无 atoms 文件 — write_claim_chain 未执行")
        # Content checks
        if atoms_files:
            try:
                atom_count = sum(1 for _ in open(atoms_files[0]) if _.strip())
                details["cc_atoms"] = atom_count
                if len(proposals) > 0 and atom_count < len(proposals):
                    warnings.append(f"CC atoms ({atom_count}) 少于 proposals ({len(proposals)})")
            except Exception:
                warnings.append("无法读取 CC atoms 文件")
        details["proposals"] = len(proposals)
        details["ranked"] = len(ranked)

    elif phase == "W3 Research":
        # Inherit W2 checks + research notes
        proposals = ctx.get("proposals", [])
        if not proposals:
            missing.append("last_pipeline_context.proposals 为空")
        tourney = state.get("last_tournament_result", {})
        ranked = tourney.get("ranked") or tourney.get("proposals") or []
        if not ranked:
            missing.append("last_tournament_result 为空")
        notes_path = ws_path / "research_notes.md"
        if not notes_path.exists():
            missing.append("research_notes.md 不存在")
        elif notes_path.stat().st_size < 200:
            missing.append(f"research_notes.md 内容不足 ({notes_path.stat().st_size} bytes)")
        details["research_notes_bytes"] = notes_path.stat().st_size if notes_path.exists() else 0

    elif phase == "W3.5 Ideate":
        # Same as W2 Plan
        proposals = ctx.get("proposals", [])
        if not proposals:
            missing.append("last_pipeline_context.proposals 为空")
        tourney = state.get("last_tournament_result", {})
        ranked = tourney.get("ranked") or tourney.get("proposals") or []
        if not ranked:
            missing.append("last_tournament_result.ranked 为空")
        atoms_files = list(index_dir.glob("atoms*.jsonl")) if index_dir.exists() else []
        if not atoms_files:
            missing.append("vault/_index/ 中无 atoms 文件")
        details["proposals"] = len(proposals)
        details["ranked"] = len(ranked)

    elif phase == "W4 Code":
        # Plan may be at workspace root or iterations/N/implementation_plan.md
        plan_path = ws_path / "implementation_plan.md"
        if not plan_path.exists():
            # Check iterations directory
            iter_plans = sorted(ws_path.glob("iterations/*/implementation_plan.md"))
            if iter_plans:
                plan_path = iter_plans[-1]  # Use most recent
        if not plan_path.exists():
            missing.append("implementation_plan.md 不存在")
        elif plan_path.stat().st_size < 200:
            missing.append(f"implementation_plan.md 内容不足 ({plan_path.stat().st_size} bytes)")
        code_results = state.get("code_results", [])
        has_code_dl = any(d.get("type") in ("code", "wait_user_code") for d in phase_dls)
        if not code_results and not has_code_dl:
            warnings.append("code_results 为空且无代码交付物记录 — 实验可能未执行")
        details["plan_bytes"] = plan_path.stat().st_size if plan_path.exists() else 0

    elif phase == "W5 Analyze":
        analysis = state.get("analysis_summary", {})
        algorithms = analysis.get("algorithms", [])
        if not algorithms:
            missing.append("analysis_summary.algorithms 为空 — 实验未分析")
        has_scan = any(d.get("type") == "scan_islands_rubrics" for d in phase_dls)
        has_island = any(d.get("type") == "island_assign" for d in phase_dls)
        if not has_scan:
            missing.append("缺少 scan_islands_rubrics 交付物")
        if not has_island:
            missing.append("缺少 island_assign 交付物")
        details["algorithms"] = len(algorithms)

    elif phase in ("W6 Write", "W7 Review"):
        # W6/W7 走 Agent SDK 子进程，轻量验证
        if not state.get("last_report"):
            warnings.append("last_report 为空 — Agent SDK 可能未产出")
        has_paper = any(d.get("type") == "paper" for d in phase_dls)
        if not has_paper:
            warnings.append("缺少 paper 交付物记录")

    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "warnings": warnings,
        "details": details,
    }


def _append_phase_memory(phase: str, state: dict, ws_path: Path):
    """AutoR-inspired: 阶段完成时追加结构化摘要到 vault/memory.md。"""
    vault = ws_path / "vault"
    vault.mkdir(exist_ok=True)
    memory_path = vault / "memory.md"

    ctx = state.get("last_pipeline_context", {})
    tourney = state.get("last_tournament_result", {})
    analysis = state.get("analysis_summary", {})
    deliverables = state.get("deliverables", [])
    phase_dls = [d for d in deliverables if d.get("phase") == phase]
    topic = state.get("research_topic", "")

    lines = []
    if not memory_path.exists():
        lines.append(f"# EvoScientist Research Memory")
        lines.append(f"")
        lines.append(f"Topic: {topic}")
        lines.append(f"")

    lines.append(f"## {phase} — {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"")

    # 产物摘要
    if phase_dls:
        lines.append("### Deliverables")
        for d in phase_dls:
            lines.append(f"- **{d.get('step','')}** ({d.get('type','')}): {d.get('summary','')}")
        lines.append("")

    # 锦标赛结果
    ranked = tourney.get("ranked") or tourney.get("proposals") or []
    if ranked:
        lines.append("### Top Proposals")
        for i, p in enumerate(ranked[:3]):
            title = p.get("title", f"proposal_{i}")
            elo = p.get("elo_rating", "")
            lines.append(f"{i+1}. {title}" + (f" (Elo: {elo:.0f})" if elo else ""))
        lines.append("")

    # 实验分析
    algorithms = analysis.get("algorithms", [])
    if algorithms:
        lines.append("### Experiment Results")
        lines.append("| Algorithm | Mean | N |")
        lines.append("|-----------|------|---|")
        for a in algorithms[:10]:
            lines.append(f"| {a.get('algorithm','?')} | {a.get('mean','?')} | {a.get('n','?')} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    with open(memory_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _clear_stale_agent_state(state: dict) -> None:
    """清除跨阶段残留的 agent 状态，防止 active_task 等泄露到下一阶段。"""
    _STALE_KEYS = (
        "active_task", "agent_heartbeat", "agent_report",
        "approval_request", "approval_response", "command",
    )
    for key in _STALE_KEYS:
        state.pop(key, None)


def _auto_next_phase(phase: str, state: dict) -> str:
    """内联流转逻辑，不依赖 PESController 类导入。"""
    order = ["W2 Plan", "W3 Research", "W3.5 Ideate", "W4 Code", "W5 Analyze", "W6 Write", "W7 Review"]
    if phase == "W5 Analyze":
        sc_path = Path(state.get("config", {}).get("workspace", "")) / "success_criteria.md"
        if not sc_path.exists():
            return "W2 Plan"
        import re
        content = sc_path.read_text(encoding="utf-8")
        target = None
        for pat in [r"target[:\s]+(\d+\.?\d*)", r"目标[:\s]+(\d+\.?\d*)"]:
            m = re.search(pat, content, re.IGNORECASE)
            if m:
                target = float(m.group(1))
                break
        if target is not None:
            ft_path = Path(state.get("config", {}).get("workspace", "")) / "fitness_tracker.jsonl"
            best = 0
            if ft_path.exists():
                with open(ft_path) as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            best = max(best, entry.get("score", 0))
                        except Exception:
                            continue
            if best >= target:
                return "W6 Write"
        return "W2 Plan"
    if phase == "W6 Write":
        return "已终止"  # 满意→终止（不满意由用户选W7 Review）
    if phase == "W7 Review":
        return "W6 Write"  # Review后回到Write
    idx = order.index(phase) if phase in order else -1
    if idx >= 0 and idx < len(order) - 1:
        return order[idx + 1]
    return "已终止"


async def pes_pipeline_state_api(request):
    """管线详细状态（含 gap_analysis、CC/Grid 统计）。"""
    workspace = request.query_params.get("workspace", "")
    if not workspace:
        return JSONResponse({"error": "workspace required"}, status_code=400)

    state_path = Path(workspace) / "PIPELINE_STATE.json"
    if not state_path.exists():
        return JSONResponse({"error": "no pipeline state found"}, status_code=404)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        # Auto-migrate old phase names
        phase = state.get("phase", "")
        _MIGRATION = {"方案提出":"W2 Plan","文献调研":"W3 Research","ELO筛选":"W3.5 Ideate","实验执行":"W4 Code","结果分析":"W5 Analyze","论文写作":"W6 Write","论文审阅":"W7 Review"}
        if phase in _MIGRATION:
            state["phase"] = _MIGRATION[phase]

        # Auto-clear active_task if multi-agent discussion finished
        active_task = state.get("active_task")
        sid = state.get("session_id") or state.get("agent_session_id")
        if active_task and active_task.get("type") == "evo_discuss" and sid:
            cleared = False
            mgr = _mgr()
            if mgr:
                try:
                    mgr._load_sessions_from_disk()
                    sess = mgr.sessions.get(sid)
                    agent_status = sess.status if sess else None
                    # Also check metadata file for more recent status
                    meta_file = Path(workspace) / ".evo_sessions" / f"{sid}.json"
                    if meta_file.exists():
                        try:
                            meta = json.loads(meta_file.read_text(encoding="utf-8"))
                            agent_status = meta.get("status") or agent_status
                        except Exception:
                            pass
                    if agent_status in ("completed", "error"):
                        cleared = True
                except Exception:
                    pass
            # Fallback: clear stale lock after 30 min regardless of status
            if not cleared:
                started = active_task.get("started_at", 0)
                if started and (time.time() - started) > 1800:
                    cleared = True
            if cleared:
                state.pop("active_task", None)
                state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

        # Auto-register session metadata so it appears on home page
        if sid:
            _ensure_session_registered(sid, workspace)

        return JSONResponse(state)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def pes_pipeline_init_api(request):
    """Dashboard 端管线初始化：创建 workspace 目录 + 写 PIPELINE_STATE.json。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    workspace = body.get("workspace_dir", "")
    research_topic = body.get("research_topic", "")

    if not workspace or not research_topic:
        return JSONResponse({"error": "workspace_dir and research_topic required"}, status_code=400)

    import uuid as _uuid
    ws_path = Path(workspace)
    # 创建 vault/ 完整目录树
    vault_dir = ws_path / "vault"
    for d in ["evolve_archive", "artifacts",
              "Algorithms", "Bottlenecks", "Islands", "Iterations",
              "_index", "_pipeline", "_memory"]:
        (vault_dir / d).mkdir(parents=True, exist_ok=True)

    # 生成 session_id (与 bootstrap 一致: sess_<uuid8>)
    session_id = f"sess_{_uuid.uuid4().hex[:8]}"

    state_path = ws_path / "PIPELINE_STATE.json"
    state = {
        "phase": "W2 Plan",
        "iteration": 0,
        "sub_loop_step": 0,
        "status": "in_progress",
        "timestamp": __import__("time").time(),
        "session_id": session_id,
        "agent_session_id": session_id,
        "research_topic": research_topic,
        "config": {},
        "needs_init": True,
        "needs_intake": True,
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    # 注册到 .evo_sessions/ (Dashboard 通过此目录发现 session)
    import time as _time
    session_meta = {
        "session_id": session_id,
        "workspace_dir": str(ws_path),
        "vault_dir": str(vault_dir),
        "research_topic": research_topic,
        "created_at": _time.time(),
    }
    evo_dir = ws_path / ".evo_sessions"
    evo_dir.mkdir(parents=True, exist_ok=True)
    (evo_dir / f"{session_id}.json").write_text(
        json.dumps(session_meta, indent=2, ensure_ascii=False))

    return JSONResponse({"initialized": True, "workspace_dir": workspace,
                         "session_id": session_id, "phase": "W2 Plan"})


async def pes_pipeline_command_api(request):
    """Dashboard 下发命令到 Claude Code：写入 command 到 PIPELINE_STATE.json。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    workspace = body.get("workspace_dir", "")
    action = body.get("action", "sub_loop")
    params = body.get("params", {})

    if not workspace:
        return JSONResponse({"error": "workspace_dir required"}, status_code=400)

    state_path = Path(workspace) / "PIPELINE_STATE.json"
    if not state_path.exists():
        return JSONResponse({"error": "no pipeline state found. Use /api/pipeline/init first."}, status_code=404)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    cmd_id = f"cmd_{int(__import__('time').time())}"
    state["command"] = {
        "id": cmd_id,
        "action": action,
        "params": params,
        "status": "pending",
        "result": None,
        "timestamp": __import__("time").time(),
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    return JSONResponse({"command_written": True, "command_id": cmd_id, "action": action})


async def pes_pipeline_execute_api(request):
    """Dashboard 驱动执行管线步骤。

    根据当前阶段选择执行方式:
    - W2/W3/W3.5/W5: Dashboard 直驱 (调 PESController + evo-agents)
    - W4/W6/W7: spawn Agent SDK 子进程
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    workspace = body.get("workspace_dir", "")
    if not workspace:
        return JSONResponse({"error": "workspace_dir required"}, status_code=400)

    ws_path = Path(workspace)
    state_path = ws_path / "PIPELINE_STATE.json"
    if not state_path.exists():
        return JSONResponse({"error": "no pipeline state found"}, status_code=404)

    state = atomic_read(state_path)
    phase = state.get("phase", "")
    session_id = state.get("session_id") or state.get("agent_session_id") or ""

    # 检查是否有正在执行的 multi-agent 任务 (对标 Ping Island 事件锁)
    # 主线锁: PIPELINE_STATE.json 中的 active_task
    active_task = state.get("active_task")

    # 1. PipelineBridge 活跃任务检查 (in-memory, 较可靠)
    bridge = _bridge()
    if bridge and session_id and bridge.is_task_running(session_id):
        task = bridge.get_active_task(session_id)
        return JSONResponse({
            "error": f"上一个阶段 ({task.get('type','unknown') if task else 'unknown'}) 正在进行中，请等待完成后再点击",
            "task_running": True,
        })

    # 2. AgentManager session status — 仅当 active_task 存在时作辅助确认
    mgr = _mgr()
    if active_task and session_id and mgr:
        try:
            agent_status = await mgr.get_status(session_id)
            if agent_status.get("status") == "running":
                return JSONResponse({
                    "error": "上一个阶段正在进行中，请等待完成后再点击",
                    "task_running": True,
                })
        except Exception:
            pass  # session 不存在时忽略

    # 3. active_task 锁检查 — 先尝试自动清除已完成的锁
    if active_task:
        mgr = _mgr()
        if mgr and session_id:
            try:
                mgr._load_sessions_from_disk()
                sess = mgr.sessions.get(session_id)
                # Also check agent status from disk metadata (may be newer than in-memory)
                agent_status = sess.status if sess else None
                if sess and (not agent_status or agent_status in ("completed", "error", "recovered")):
                    # Check metadata file for a more recent status
                    meta_file = ws_path / ".evo_sessions" / f"{session_id}.json"
                    if meta_file.exists():
                        try:
                            meta = json.loads(meta_file.read_text(encoding="utf-8"))
                            agent_status = meta.get("status") or agent_status
                        except Exception:
                            pass
                if agent_status in ("completed", "error"):
                    state.pop("active_task", None)
                    atomic_write(state_path, state)
                    active_task = None
                elif agent_status is None or agent_status == "recovered":
                    # Agent not yet started or in unknown state — clear stale lock after 30 min
                    started = active_task.get("started_at", 0)
                    if started and (time.time() - started) > 1800:
                        state.pop("active_task", None)
                        atomic_write(state_path, state)
                        active_task = None
            except Exception:
                pass
    if active_task:
        elapsed = time.time() - active_task.get("started_at", 0)
        if elapsed < 1800:  # 30分钟内认为仍在执行
            return JSONResponse({
                "error": f"上一个阶段 ({active_task.get('type','unknown')}) 正在进行中，请等待完成后再点击",
                "task_running": True,
            })

    # Agent SDK 阶段：spawn 子进程
    if phase in AGENT_SDK_PHASES:
        if _is_agent_running(state_path):
            return JSONResponse({"error": "Agent is already running"}, status_code=409)
        task = {PHASE_CODE: "code", PHASE_WRITE: "write", PHASE_REVIEW: "review"}.get(phase, "code")
        _spawn_agent_task(ws_path, task, session_id)
        return JSONResponse({"agent_spawned": True, "phase": phase, "task": task})

    # Dashboard 直驱阶段：调 PESController.sub_loop() 并真实执行
    try:
        ctrl = PESController(ws_path, session_id=session_id)
        step = ctrl.sub_loop()
    except Exception as e:
        logger.exception(f"PESController.sub_loop failed: {e}")
        return JSONResponse({"error": f"Pipeline step failed: {e}", "phase": phase}, status_code=500)

    if step.get("done"):
        state = atomic_read(state_path)
        state["status"] = "awaiting_decision"
        state["command"] = None
        atomic_write(state_path, state)
        return JSONResponse({"step_done": True, "phase": step["phase"],
                             "message": f"阶段 '{step['phase']}' 完成，等待用户决策"})

    if step.get("action") == "wait_for_decision":
        return JSONResponse({"waiting": True, "phase": step["phase"],
                             "message": "等待用户决策"})

    # ── 真实执行步骤 ──
    try:
        result = await _execute_step(step, ws_path, session_id, state_path)
        return JSONResponse(result)
    except Exception as e:
        logger.exception(f"_execute_step failed: {e}")
        return JSONResponse({"error": f"Step execution failed: {e}", "phase": step.get("phase", phase)}, status_code=500)


async def _execute_step(step: dict, ws_path: Path, session_id: str,
                        state_path: Path) -> dict:
    """真实执行管线步骤。根据 step.action 分发到 evo-agents 或本地处理。"""
    action = step.get("action")
    phase = step.get("phase", "")
    step_name = step.get("step", "")
    result = {"executed": True, "phase": phase, "step": step_name, "action": action}

    mgr = _mgr()

    if action == "pipeline_context":
        # run_step_pipeline 已在 PESController._build_step() 内部完成
        # context_bundle 已写入 state.last_pipeline_context
        result["detail"] = "STEP管线分析已完成"
        ctx = step.get("context_bundle", {})
        _record_deliverable(state_path, step_name, phase,
                          "pipeline_context",
                          f"提案: {len(ctx.get('proposals',[]))}, SME映射: {len(ctx.get('sme_mappings',[]))}",
                          {"proposals": len(ctx.get("proposals", [])),
                           "mappings": len(ctx.get("sme_mappings", [])),
                           "evaluations": len(ctx.get("evaluation", []))})
        _push_internal_event(session_id, "step_executed",
                             {"phase": phase, "step": step_name, "detail": "STEP pipeline completed"})

    elif action == "multi_agent":
        tool = step.get("tool", "")
        if not mgr:
            result["warning"] = "AgentManager未初始化，跳过multi_agent执行"
            return result

        if tool == "evo_discuss":
            # 确保 session 存在且有 agent
            # 先触发磁盘扫描，加载 bootstrap 后新创建的 session
            mgr._load_sessions_from_disk()
            session = mgr.sessions.get(session_id)
            original_session_id = session_id  # 保留 bootstrap 创建的 session_id
            if not session:
                ws = str(ws_path)
                # 按 workspace 查找已有 session (可能用了不同的 session_id)
                existing = [s for s in mgr.sessions.values()
                           if s.workspace_dir == ws and s.agent is not None]
                if existing:
                    session = existing[0]
                    session_id = session.session_id
                else:
                    await mgr.create_session(workspace_dir=ws)
                    sessions_list = mgr.list_sessions()
                    if sessions_list:
                        session_id = sessions_list[-1]["session_id"]
                    session = mgr.sessions.get(session_id)
                    # 注册新的 agent session 到 .evo_sessions (不改 workspace 级别 session_id)
                    mgr._save_session_meta(session)
                # 只更新 agent_session_id，不覆盖 bootstrap 的 session_id
                if session_id != original_session_id:
                    state = atomic_read(state_path)
                    state["agent_session_id"] = session_id
                    atomic_write(state_path, state)

            if session and session.agent is None:
                await mgr._ensure_agent(session)

            # 写 active_task 锁
            state = atomic_read(state_path)
            state["active_task"] = {"type": "evo_discuss", "started_at": time.time(),
                                     "session_id": session_id, "phase": phase}
            atomic_write(state_path, state)

            _push_internal_event(session_id, "discuss_started",
                                 {"phase": phase, "topic": str(step.get("topic", ""))[:200]})
            try:
                discuss_resp = await mgr.discuss(
                    session_id=session_id,
                    topic=step.get("topic", ""),
                    agents=step.get("agents"),
                    exclude_agents=step.get("exclude_agents"),
                )
                if isinstance(discuss_resp, dict) and "error" in discuss_resp:
                    raise RuntimeError(f"discuss rejected: {discuss_resp['error']}")

                # 轮询等待讨论完成，确保步骤在讨论结束后才推进
                result["detail"] = "讨论已启动"
                result["task_started"] = True
                for _ in range(72):  # 最多等 6 分钟 (72 × 5s)
                    await asyncio.sleep(5)
                    s = await mgr.get_status(session_id)
                    agent_status = s.get("status", "")
                    if agent_status in ("completed", "error"):
                        break
                # 讨论完成后清除 active_task 锁
                state = atomic_read(state_path)
                state.pop("active_task", None)
                # 捕获讨论结果到 state
                sess = mgr.sessions.get(session_id) if mgr else None
                if sess and hasattr(sess, 'last_response') and sess.last_response:
                    discuss_results = state.get("discuss_results", [])
                    discuss_results.append({
                        "phase": phase,
                        "step": step_name,
                        "response": str(sess.last_response)[:5000],
                        "timestamp": time.time(),
                    })
                    state["discuss_results"] = discuss_results
                atomic_write(state_path, state)
                result["detail"] = "多Agent讨论已完成"
                _record_deliverable(state_path, step_name, phase,
                                  "multi_agent_discuss",
                                  "多Agent跨领域讨论完成",
                                  {"agents": step.get("agents", [])})
            except Exception as e:
                result["error"] = f"evo_discuss失败: {e}"
                state = atomic_read(state_path)
                state.pop("active_task", None)
                atomic_write(state_path, state)

            _push_internal_event(session_id, "discuss_completed",
                                 {"phase": phase, "result": result})

        elif tool == "evo_run_tournament":
            state = atomic_read(state_path)
            ctx = state.get("last_pipeline_context", {})
            proposals = ctx.get("proposals", [])
            # 确保每个 proposal 有 id 字段 (run_tournament 要求)
            for i, p in enumerate(proposals):
                if "id" not in p:
                    p["id"] = p.get("title", f"proposal_{i}")
            if not proposals:
                result["warning"] = "无proposals可供锦标赛排序"
            else:
                try:
                    tourney_result = await mgr.run_tournament(
                        session_id=session_id,
                        proposals=proposals,
                    )
                    state["last_tournament_result"] = tourney_result
                    atomic_write(state_path, state)
                    result["detail"] = f"ELO完成: winner={tourney_result.get('winner', 'N/A')}"
                    ranked_count = len(tourney_result.get("ranked", []))
                    _record_deliverable(state_path, step_name, phase,
                                      "elo_tournament",
                                      f"ELO排序完成: {ranked_count}方案, 胜者{(tourney_result.get('winner','') or '')[:60]}",
                                      {"ranked": ranked_count, "winner_elo": tourney_result.get("winner_elo")})
                except Exception as e:
                    result["error"] = f"run_tournament失败: {e}"

        elif tool == "evo_distill":
            state = atomic_read(state_path)
            tourney = state.get("last_tournament_result", {})
            distill_type = step.get("distill_type", "ide")
            try:
                kwargs = {
                    "session_id": session_id,
                    "distill_type": distill_type,
                    "proposals": tourney.get("ranked") if tourney else None,
                }
                # ive (W3 Research): pass prior failures from analysis_summary
                if distill_type == "ive":
                    analysis = state.get("analysis_summary", {})
                    contradicted = analysis.get("contradicted", [])
                    if contradicted:
                        kwargs["failure_info"] = {
                            "direction": contradicted[0],
                            "reason": f"W3 Research: {len(contradicted)} contradictions found",
                            "score": 0.0,
                        }
                    else:
                        # Fallback: record that W3 Research ran without finding contradictions
                        kwargs["failure_info"] = {
                            "direction": "W3 Research completed",
                            "reason": "No contradictions found — all proposals passed feasibility",
                            "score": 1.0,
                        }
                # ese (W5 Analyze): pass experiment strategy results
                elif distill_type == "ese":
                    analysis = state.get("analysis_summary", {})
                    validated = analysis.get("validated", [])
                    if validated:
                        kwargs["strategy_info"] = {
                            "strategy": f"W5 validated: {', '.join(validated[:5])}",
                            "outcome": "SUCCESS",
                            "details": analysis.get("agent_conclusion", "")[:500],
                            "score": 1.0,
                        }
                    else:
                        kwargs["strategy_info"] = {
                            "strategy": "W5 Analyze completed",
                            "outcome": "PARTIAL",
                            "details": analysis.get("agent_conclusion", "")[:500],
                            "score": 0.5,
                        }
                await mgr.distill(**kwargs)
                result["detail"] = f"Evolution Memory已记录 (type={distill_type})"
                _record_deliverable(state_path, step_name, phase,
                                  "evolution_memory",
                                  f"EM已记录 (type={distill_type})",
                                  {"distill_type": distill_type})
            except Exception as e:
                result["error"] = f"evo_distill失败: {e}"

    elif action == "invoke_skill":
        skill = step.get("skill", "")
        # ── W5 Analyze: 三个关键步骤的实际执行 ──
        if skill == "/evo-analyze":
            result = await _do_scan_islands_rubrics(step, ws_path, session_id, state_path, mgr, result)
        elif skill == "/evo-claim":
            result = await _do_write_claim_chain(step, ws_path, session_id, state_path, result)
        elif skill == "/evo-iterate":
            result = await _do_island_assign(step, ws_path, session_id, state_path, result)
        elif skill == "/evo-research":
            # W3 Research: 从 pipeline context 生成研究笔记，写入 vault
            result = await _do_web_research(step, ws_path, session_id, state_path, result)
        elif skill == "/evo-write":
            # W6 Write: 确保 deliverable 可见 — 在 state 中记录路径
            result = await _do_write_paper(step, ws_path, session_id, state_path, result)
        elif skill == "/evo-review":
            # W7 Review: 确保 deliverable 可见
            result = await _do_review_paper(step, ws_path, session_id, state_path, result)
        else:
            _push_internal_event(session_id, "skill_invoked",
                                 {"phase": phase, "skill": skill})
            result["detail"] = f"Skill {skill} 已调用"

    elif action == "ingest_results":
        state = atomic_read(state_path)
        ingested = state.get("ingested_results", [])
        result["detail"] = f"已扫描 {len(ingested)} 个实验结果"

    elif action == "generate_code_plan":
        plan_path = step.get("plan_path", "")
        result["detail"] = "implementation_plan.md 已生成"
        result["plan_path"] = plan_path
        result["plan_id"] = step.get("plan_id", "")
        result["instruction"] = step.get("instruction", "")
        _push_internal_event(session_id, "code_plan_generated",
                             {"phase": phase, "plan_path": plan_path})

    elif action == "wait_user_code":
        result["detail"] = "等待用户完成代码实现"
        result["waiting_for_user"] = True
        result["instruction"] = step.get("instruction", "")

    else:
        result["detail"] = f"未识别的action: {action}"

    return result


# ── W5 Analyze 辅助函数 ──

async def _do_scan_islands_rubrics(step: dict, ws_path: Path, session_id: str,
                                     state_path: Path, mgr, result: dict) -> dict:
    """W5 Analyze Step 1: 扫描实验结果，生成结构化分析，调 agents 评判。

    Python 硬编码编排流程:
    1. 读 PIPELINE_STATE.code_results (由 /evo-code-agent-post 写入)
    2. 按算法/种子分组，计算统计量
    3. 组装分析 prompt → 调 mgr.discuss() 让 agents 评判
    4. Parse agent 回复 → 提取结论 → 写 state["analysis_summary"]
    """
    state = atomic_read(state_path)
    code_results = state.get("code_results", [])

    if not code_results:
        # Phase H: 优先从 event log 读取 (canonical source)
        code_results = _read_experiment_results_from_event_log(ws_path)
    if not code_results:
        # Fallback: vault/_index/events.jsonl
        evt_path = ws_path / "vault" / "_index" / "events.jsonl"
        if evt_path.exists():
            import json as _json
            tmp_results = []
            with open(evt_path) as f:
                for line in f:
                    try:
                        e = _json.loads(line.strip())
                        if e.get("event_type") == "expt_completed":
                            p = e.get("payload", {})
                            tmp_results.append({
                                "algorithm": p.get("algo_id", "unknown"),
                                "score_mean": p.get("score_mean", 0),
                                "status": "success" if p.get("success") else "failed",
                                "code_path": p.get("code_path", ""),
                            })
                    except Exception:
                        pass
            code_results = tmp_results

    if not code_results:
        result["warning"] = "无实验结果数据 (code_results 空, fitness_history 空)"
        return result

    # 计算统计量
    algo_stats = {}
    for r in code_results:
        name = r.get("algorithm", "unknown")
        score = r.get("score_mean", r.get("score", 0))
        if name not in algo_stats:
            algo_stats[name] = {"scores": [], "status": r.get("status", "?")}
        algo_stats[name]["scores"].append(float(score))

    algo_summary = []
    for name, data in sorted(algo_stats.items()):
        scores = data["scores"]
        algo_summary.append({
            "algorithm": name,
            "mean": round(sum(scores) / len(scores), 2),
            "min": round(min(scores), 2),
            "max": round(max(scores), 2),
            "n": len(scores),
            "status": data["status"],
        })

    # 组装分析 prompt，调 agents 评判
    if mgr:
        mgr._load_sessions_from_disk()
    if mgr and session_id in mgr.sessions:
        summary_json = json.dumps(algo_summary, indent=2, ensure_ascii=False)
        analysis_prompt = (
            f"[W5 Analyze] 实验数据分析。以下是 {len(algo_summary)} 个算法的实验结果:\n\n"
            f"{summary_json}\n\n"
            "请分析:\n"
            "1. 排名: 哪个算法最强? 是否有统计显著差异?\n"
            "2. 矛盾: 是否有预期之外的失败? (预期应好的算法实际差了)\n"
            "3. 异常: 是否有天花板效应, 高方差, 或异常行为?\n"
            "4. 建议: 下一轮迭代应重点探索什么方向?\n"
            "请用结构化格式回复，以便 Python parse。"
        )
        try:
            await mgr.discuss(session_id=session_id, topic=analysis_prompt,
                             agents=["analyst"], exclude_agents=["code-agent", "debug-agent"])
            # 简版轮询
            for _ in range(200):
                await asyncio.sleep(3)
                status = await mgr.get_status(session_id)
                if status.get("status") in ("completed", "error"):
                    break
            sess = mgr.sessions.get(session_id)
            agent_conclusion = sess.last_response[:3000] if sess else ""

            # 尝试 parse agent 回复 → 提取结构化结论
            validated, contradicted, ceiling = _parse_agent_conclusion(
                agent_conclusion, algo_summary)
        except Exception as e:
            agent_conclusion = f"Agent 分析失败: {e}"
            validated, contradicted, ceiling = [], [], []
            logger.warning(f"scan_islands_rubrics agent discussion failed: {e}")

        # 写分析摘要到 state (保留已有的 validated/contradicted/ceiling)
        state = atomic_read(state_path)
        existing = state.get("analysis_summary", {})
        state["analysis_summary"] = {
            "algorithms": algo_summary,
            "agent_conclusion": agent_conclusion[:3000],
            "validated": validated if validated else existing.get("validated", []),
            "contradicted": contradicted if contradicted else existing.get("contradicted", []),
            "ceiling_effects": ceiling if ceiling else existing.get("ceiling_effects", []),
            "timestamp": time.time(),
        }
        atomic_write(state_path, state)
        result["detail"] = f"实验分析完成: {len(algo_summary)} 个算法, {len(code_results)} 条结果"
        current_phase = state.get("phase", step.get("phase", ""))
        _record_deliverable(state_path, step.get("step", "scan_islands"), current_phase,
                          "scan_islands_rubrics",
                          f"分析: {len(algo_summary)}算法, {len(code_results)}结果",
                          {"algorithms": len(algo_summary), "results": len(code_results)})
    else:
        # 无 AgentManager 时只用统计量
        validated, contradicted, ceiling = [], [], []
        state = atomic_read(state_path)
        existing = state.get("analysis_summary", {})
        state["analysis_summary"] = {
            "algorithms": algo_summary,
            "agent_conclusion": "(无 AgentManager, 仅统计)",
            "validated": validated if validated else existing.get("validated", []),
            "contradicted": contradicted if contradicted else existing.get("contradicted", []),
            "ceiling_effects": ceiling if ceiling else existing.get("ceiling_effects", []),
            "timestamp": time.time(),
        }
        atomic_write(state_path, state)
        result["detail"] = f"实验统计完成: {len(algo_summary)} 个算法 (无 AgentManager)"

    _push_internal_event(session_id, "analysis_completed",
                         {"phase": "W5 Analyze", "algorithms": len(algo_summary)})

    # 将实验分析结论蒸馏到 Evolution Memory (ese type)
    if mgr and session_id in mgr.sessions:
        try:
            analysis = state.get("analysis_summary", {})
            validated = analysis.get("validated", [])
            contradicted = analysis.get("contradicted", [])
            if validated or contradicted:
                await mgr.distill(
                    session_id=session_id,
                    distill_type="ese",
                    strategy_info={
                        "strategy": f"W5: validated={validated[:3]}, contradicted={contradicted[:3]}",
                        "outcome": "SUCCESS" if validated else "PARTIAL",
                        "details": analysis.get("agent_conclusion", "")[:500],
                        "score": len(validated) / max(len(validated) + len(contradicted), 1),
                    },
                )
        except Exception:
            pass

    return result


async def _do_write_claim_chain(step: dict, ws_path: Path, session_id: str,
                                  state_path: Path, result: dict) -> dict:
    """W5 Analyze Step 4: 写入 CC atoms + relations。

    Python 硬编码:
    1. 读 state["analysis_summary"]
    2. 每个算法 → CC.add_atom(type="fact", tags=["experiment", algo_name])
    3. Pairwise 比较 → CC.add_relation(type="validates"/"contradicts")
    4. 代码路径 → CC.add_relation(type="implements")
    """
    from claim_chain import ClaimChain
    cc = ClaimChain(str(ws_path / "vault" / "_index"), base_dir=str(ws_path / "vault" / "_index"))

    state = atomic_read(state_path)
    current_phase = state.get("phase", step.get("phase", ""))
    analysis = state.get("analysis_summary", {})
    code_results = state.get("code_results", [])
    algorithms = analysis.get("algorithms", [])
    pipeline_ctx = state.get("last_pipeline_context", {})
    proposals = pipeline_ctx.get("proposals", [])

    written_atoms = []
    written_relations = []
    atom_id_map = {}  # name → atom_id

    # ── 路径 A: 无实验数据 → 从 pipeline proposals 写入 CC atoms ──
    if not algorithms and proposals:
        for i, prop in enumerate(proposals):
            title = prop.get("title", f"proposal_{i}")
            hypothesis = prop.get("hypothesis", "")
            method = prop.get("method_sketch", "")[:800]
            content = json.dumps({
                "title": title,
                "hypothesis": hypothesis,
                "method_sketch": method,
                "novelty_claim": prop.get("novelty_claim", ""),
                "primitives_used": prop.get("primitives_used", []),
            }, ensure_ascii=False)
            atom = cc.add_atom(
                type="method",
                title=title,
                content=content,
                tags=["proposal", "ideation", f"rank_{i+1}"],
                evidence_level="llm_analysis",
                metadata={"proposal_id": prop.get("id", ""), "elo_rating": prop.get("elo_rating", 0)},
            )
            written_atoms.append(atom["id"])
            atom_id_map[title] = atom["id"]

        # 如果 tournament 已排序, 创建 validates relations (rank N → rank N+1)
        tourney = state.get("last_tournament_result", {})
        ranked = tourney.get("ranked") or tourney.get("proposals") or []
        if ranked and len(ranked) >= 2:
            for k in range(len(ranked) - 1):
                winner = ranked[k].get("title", "")
                loser = ranked[k + 1].get("title", "")
                w_id = atom_id_map.get(winner)
                l_id = atom_id_map.get(loser)
                if w_id and l_id:
                    rel = cc.add_relation(type="validates", source_id=w_id, target_id=l_id,
                                          evidence=f"ELO tournament: rank {k+1} > rank {k+2}")
                    written_relations.append(rel["id"])

        result["detail"] = f"CC 写入 (proposals): {len(written_atoms)} atoms, {len(written_relations)} relations"
        _record_deliverable(state_path, step.get("step", "write_cc"), current_phase,
                          "write_claim_chain",
                          f"CC写入: {len(written_atoms)} atoms, {len(written_relations)} relations",
                          {"atoms": len(written_atoms), "relations": len(written_relations)})
        _push_internal_event(session_id, "cc_written",
                             {"phase": "W2 Plan", "atoms": len(written_atoms),
                              "relations": len(written_relations)})
        return result

    # ── 路径 B: 无数据 → 初始化空 CC 文件 (确保 vault 结构可见) ──
    if not algorithms:
        # touch empty files so vault structure is visible
        cc.get_graph_summary()
        result["detail"] = "CC 已初始化 (暂无数据, 待实验完成后写入)"
        return result

    # ── 路径 C: 有实验数据 → 写入 experiment atoms + pairwise relations ──
    for algo in algorithms:
        name = algo["algorithm"]
        code_path = ""
        for r in code_results:
            if r.get("algorithm") == name:
                code_path = r.get("code_path", "")
                break

        content = json.dumps(algo, ensure_ascii=False)
        atom = cc.add_atom(
            type="fact",
            title=f"{name}: score={algo['mean']} (n={algo['n']})",
            content=content,
            tags=["experiment", name.lower(), "w5-analyze"],
            evidence_level="experiment",
        )
        written_atoms.append(atom["id"])
        atom_id_map[name] = atom["id"]

    for i in range(len(algorithms)):
        for j in range(i + 1, len(algorithms)):
            a = algorithms[i]
            b = algorithms[j]
            a_id = atom_id_map.get(a["algorithm"])
            b_id = atom_id_map.get(b["algorithm"])
            if not a_id or not b_id:
                continue
            if a["mean"] > b["mean"] * 1.10:
                rel = cc.add_relation(type="validates", source_id=a_id, target_id=b_id,
                                      evidence=f"{a['algorithm']}({a['mean']}) > {b['algorithm']}({b['mean']})")
                written_relations.append(rel["id"])
            elif b["mean"] > a["mean"] * 1.10:
                rel = cc.add_relation(type="validates", source_id=b_id, target_id=a_id,
                                      evidence=f"{b['algorithm']}({b['mean']}) > {a['algorithm']}({a['mean']})")
                written_relations.append(rel["id"])

    ceiling_effects = analysis.get("ceiling_effects", [])
    if ceiling_effects:
        for algo in algorithms:
            atom_id = atom_id_map.get(algo["algorithm"])
            if atom_id:
                try:
                    cc.add_relation(
                        type="boundary_of",
                        source_id=atom_id,
                        target_id=atom_id,
                        evidence=f"ceiling_effect: {algo['algorithm']}({algo['mean']})"
                    )
                    written_relations.append(-1)
                except Exception:
                    pass

    result["detail"] = f"CC 写入: {len(written_atoms)} atoms, {len(written_relations)} relations"
    _record_deliverable(state_path, step.get("step", "write_cc"), current_phase,
                      "write_claim_chain",
                      f"CC写入: {len(written_atoms)} atoms, {len(written_relations)} relations",
                      {"atoms": len(written_atoms), "relations": len(written_relations)})
    _push_internal_event(session_id, "cc_written",
                         {"phase": "W5 Analyze", "atoms": len(written_atoms),
                          "relations": len(written_relations)})
    return result


async def _do_island_assign(step: dict, ws_path: Path, session_id: str,
                              state_path: Path, result: dict) -> dict:
    """W5 Analyze Step 5: 代码归档到 island + Grid 分配。

    使用真实 API: IslandManager.detect_and_assign() + CellGrid.record_result()
    + set_claim_atom_id() 建立 CC↔island 关联。
    """
    from cell_grid import CellGrid
    from island_manager import IslandManager
    from claim_chain import ClaimChain

    state = atomic_read(state_path)
    analysis = state.get("analysis_summary", {})
    code_results = state.get("code_results", [])
    algorithms = analysis.get("algorithms", [])

    if not algorithms:
        result["warning"] = "无 analysis_summary, 跳过 Island 分配"
        return result

    grid = CellGrid(str(ws_path / "vault" / "evolve_archive"))
    islands = IslandManager(ws_path / "vault" / "evolve_archive")
    cc = ClaimChain(str(ws_path / "vault" / "_index"), base_dir=str(ws_path / "vault" / "_index"))
    assigned = 0

    # 读 CC atoms 找匹配的 experiment atom_id
    cc_atoms = cc.get_atoms(limit=200)
    _meta_tags = {"experiment", "w5-analyze", "benchmark", "literature", "method", "survey"}
    algo_atom_map = {}  # algorithm_name → atom_id
    for a in cc_atoms:
        if "experiment" in a.get("tags", []):
            for tag in a.get("tags", []):
                if tag.lower() not in _meta_tags:
                    algo_atom_map[tag.upper()] = a["id"]

    for algo in algorithms:
        name = algo["algorithm"]
        score = algo["mean"]

        # 找代码路径和 CC atom
        code_path = ""
        for r in code_results:
            if r.get("algorithm") == name:
                code_path = r.get("code_path", "")
                break
        atom_id = algo_atom_map.get(name.upper())

        variant_id = f"v_{name.lower()}_{int(time.time())}"

        # Island 分配
        try:
            # 尝试基于 method_family 匹配 cell key
            cell_key = f"*+*+*+{name.lower()}"  # fallback cell key
            island_id = islands.detect_and_assign(
                variant_id=variant_id,
                cell_key=cell_key,
                score=score,
                dims={},
                method_family=name,
            )
            # 建立 CC atom ↔ island 关联
            if atom_id and island_id:
                try:
                    islands.set_claim_atom_id(island_id, variant_id, atom_id)
                except Exception:
                    pass
            assigned += 1
        except Exception as e:
            logger.warning(f"Island assign failed for {name}: {e}")
            continue

        # Grid 分配
        try:
            grid.record_result(
                variant_id=variant_id,
                score=score,
                descriptor={"algorithm": name, "source": "w5-analyze"},
                claim_conditions={"code_path": code_path},
            )
        except Exception as e:
            logger.warning(f"Grid record failed for {name}: {e}")

        # CC implements relation: atom → island
        if atom_id:
            try:
                cc.add_relation(
                    type="implements",
                    source_id=atom_id,
                    target_id=atom_id,  # target 是 island_id, 但 CC relations 只支持 atom_id
                    evidence=f"island={island_id}, variant={variant_id}, code={code_path}",
                )
            except Exception:
                pass

    # 检测 milestones 和 anomalies
    try:
        grid.detect_milestones()
    except Exception:
        pass

    result["detail"] = f"Island 分配: {assigned}/{len(algorithms)} 个算法"
    current_phase = state.get("phase", step.get("phase", ""))
    _record_deliverable(state_path, step.get("step", "island_assign"), current_phase,
                      "island_assign",
                      f"Island分配: {assigned}/{len(algorithms)}算法",
                      {"assigned": assigned, "total": len(algorithms)})
    _push_internal_event(session_id, "island_assigned",
                         {"phase": "W5 Analyze", "assigned": assigned})
    return result


def _read_experiment_results_from_event_log(ws_path: Path) -> list[dict]:
    """Phase H 新方法: 从 event log 读实验结果 (替代 fitness_history parsing).

    偏好 event log 因为它是 canonical source of truth.
    """
    index_dir = ws_path / "vault" / "_index"
    events_path = index_dir / "events.jsonl"
    if not events_path.exists():
        return []
    results = []
    with open(events_path, "r") as f:
        for line in f:
            try:
                e = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if e.get("event_type") == "expt_completed":
                p = e.get("payload", {})
                results.append({
                    "algorithm": p.get("algo_id", "unknown"),
                    "score_mean": p.get("score_mean", 0),
                    "score_std": p.get("score_std", 0),
                    "seeds": p.get("seeds", 0),
                    "status": "success" if p.get("success") else "failed",
                    "code_path": p.get("code_path", ""),
                })
    return results


def _parse_fitness_history(ft_path: Path) -> list[dict]:
    """DEPRECATED: 从 fitness_tracker.jsonl 解析实验结果。

    请改用 experiment_recorder.record_experiment_result() + event log 读取。
    """
    import warnings
    warnings.warn("_parse_fitness_history is deprecated. Use experiment_recorder + event log.", DeprecationWarning)
    results = []
    with open(ft_path, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                results.append({
                    "algorithm": entry.get("method", entry.get("algorithm", "unknown")),
                    "score_mean": entry.get("score", 0),
                    "status": "success" if entry.get("score", 0) > -1e9 else "failed",
                    "code_path": entry.get("code_path", ""),
                })
            except (json.JSONDecodeError, KeyError):
                pass
    return results


def _parse_agent_conclusion(agent_text: str, algo_summary: list[dict]) -> tuple[list, list, list]:
    """DEPRECATED: 从 agent 回复中提取结构化结论 (关键词匹配).

    请改用 pipeline_stages.AnalysisOutput Pydantic schema + LLM structured JSON output.
    此函数将在下一个 milestone 中删除.
    """
    import warnings
    warnings.warn("_parse_agent_conclusion is deprecated. Use Pydantic AnalysisOutput.", DeprecationWarning)
    validated = []
    contradicted = []
    ceiling = []

    text_lower = agent_text.lower()
    algo_names = [a["algorithm"].lower() for a in algo_summary]

    for name in algo_names:
        if f"{name}" in text_lower and ("最佳" in text_lower or "最强" in text_lower or "best" in text_lower or "排名第一" in text_lower):
            validated.append(name.upper())
        if f"{name}" in text_lower and ("矛盾" in text_lower or "预期不符" in text_lower or "contradict" in text_lower or "未超越" in text_lower):
            contradicted.append(name.upper())

    if "天花板" in text_lower or "ceiling" in text_lower:
        ceiling.append("ceiling_effect_detected")

    return validated, contradicted, ceiling


def _ensure_session_registered(session_id: str, workspace: str):
    """确保 session 在 AgentManager 的 session 列表中可见。

    写入 .evo_sessions/{sid}.json 和全局 registry，
    AgentManager.refresh_sessions() 会加载它们。
    """
    ws = Path(workspace)
    sdir = ws / ".evo_sessions"
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        meta = {
            "session_id": session_id,
            "workspace_dir": str(ws),
            "thread_id": session_id,
            "created_at": __import__("time").time(),
            "model": "claude",
            "provider": "anthropic",
            "status": "idle",
            "sub_agents_used": [],
            "thread_count": 0,
            "thread_summaries": [],
            "last_response": "",
            "fitness_history": [],
        }
        (sdir / f"{session_id}.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Update global registry
        base_dir = Path(os.getcwd())
        rpath = base_dir / ".evo_session_registry.json"
        registry = {}
        if rpath.exists():
            try:
                registry = json.loads(rpath.read_text(encoding="utf-8"))
            except Exception:
                pass
        registry[session_id] = str(ws)
        rpath.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    except Exception:
        pass  # 注册失败不阻塞


def _is_agent_running(state_path: Path) -> bool:
    """检查 agent 子进程是否在运行（通过心跳）。

    排除 degraded_mode 心跳 — agent 进程存活但无法执行 SDK，不算 running。
    """
    hb = dashboard_get_heartbeat(state_path)
    if not hb:
        return False
    # degraded_mode 表示 agent 因缺少依赖无法启动，不算 running
    if hb.get("last_step") == "degraded_mode":
        return False
    age = time.time() - hb.get("timestamp", 0)
    return age < 120  # 心跳在 120 秒内 → agent 仍在运行


def _spawn_agent_task(workspace: Path, task: str, session_id: str):
    """后台启动 Agent SDK 子进程。"""
    agent_script = str(Path(_TOOLS_DIR) / "agent_task.py")
    cmd = [
        sys.executable, agent_script,
        "--task", task,
        "--workspace", str(workspace),
        "--session-id", session_id,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(workspace),
    )
    # 后台线程读取输出
    def _read_output():
        for line in proc.stdout:
            logger.info(f"[Agent {task}] {line.rstrip()}")
        proc.wait()
        logger.info(f"[Agent {task}] exited with code {proc.returncode}")
    threading.Thread(target=_read_output, daemon=True).start()


def _push_internal_event(session_id: str, event_type: str, data: dict):
    """推送事件到内部事件总线 (同进程内存队列)。"""
    try:
        from .event_bus import EventBus
        bus = EventBus()
        bus.publish(session_id, {"type": event_type, "data": data})
    except Exception:
        pass


def _record_deliverable(state_path: Path, step_name: str, phase: str,
                        deliverable_type: str, summary: str, detail: dict = None):
    """记录步骤交付物到 PIPELINE_STATE。Dashboard 前端据此展示进度和产物。"""
    state = atomic_read(state_path)
    if "deliverables" not in state:
        state["deliverables"] = []
    state["deliverables"].append({
        "step": step_name,
        "phase": phase,
        "type": deliverable_type,
        "summary": summary,
        "detail": detail or {},
        "timestamp": time.time(),
    })
    atomic_write(state_path, state)


async def _do_web_research(step: dict, ws_path: Path, session_id: str,
                           state_path: Path, result: dict) -> dict:
    """W3 Research invoke_skill_research: 将管线上下文写入 research_notes.md 文件。

    从 last_pipeline_context 提取 proposals、SME mappings、evaluations，
    生成结构化研究笔记，写入 vault 供后续阶段使用。
    """
    state = atomic_read(state_path)
    ctx = state.get("last_pipeline_context", {})
    proposals = ctx.get("proposals", [])
    sme_mappings = ctx.get("sme_mappings", [])
    evaluations = ctx.get("evaluation", [])
    tourney = state.get("last_tournament_result", {})
    ranked = tourney.get("ranked") or tourney.get("proposals") or []
    topic = state.get("research_topic", "")

    notes_path = ws_path / "research_notes.md"
    lines = [
        f"# Research Notes: {topic}",
        f"",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Phase: W3 Research",
        f"",
        f"## Summary",
        f"- Proposals generated: {len(proposals)}",
        f"- SME cross-domain mappings: {len(sme_mappings)}",
        f"- Evaluations completed: {len(evaluations)}",
        f"",
    ]

    # SME mappings
    if sme_mappings:
        lines.append("## Structure-Mapped Cross-Domain Insights")
        lines.append("")
        for m in sme_mappings[:10]:
            src = f"{m.get('source_domain','?')}({' × '.join(m.get('source_pattern',[]))})"
            tgt = f"{m.get('target_domain','?')}({' × '.join(m.get('target_pattern',[]))})"
            lines.append(f"- **{m.get('type','Map')}**: {src} → {tgt}")
        lines.append("")

    # Tournament-ranked proposals
    items = ranked if ranked else proposals
    if items:
        lines.append("## Top Proposals (ELO Ranked)" if ranked else "## Proposals")
        lines.append("")
        for i, p in enumerate(items[:8]):
            title = p.get("title", f"proposal_{i}")
            hypothesis = p.get("hypothesis", "")
            method = p.get("method_sketch", "")[:200]
            elo = p.get("elo_rating", "")
            lines.append(f"### {i+1}. {title}")
            if elo:
                lines.append(f"Elo: {elo:.0f} | Novelty: {p.get('novelty','?')} | Feasibility: {p.get('feasibility','?')} | Relevance: {p.get('relevance','?')}")
            if hypothesis:
                lines.append(f"**Hypothesis**: {hypothesis}")
            if method:
                lines.append(f"**Method**: {method}")
            lines.append("")
    else:
        lines.append("## Research Directions")
        lines.append("No proposals generated yet. Run W2 Plan first.")
        lines.append("")

    lines.append("---")
    lines.append("*Auto-generated by EvoScientist W3 Research step*")

    notes_path.write_text("\n".join(lines), encoding="utf-8")
    _record_deliverable(state_path, step.get("step", "research"),
                        step.get("phase", ""), "research_notes",
                        f"研究笔记已写入: {len(items)} 方案, {len(sme_mappings)} 映射",
                        {"path": str(notes_path), "proposals": len(items), "mappings": len(sme_mappings)})
    result["detail"] = f"研究笔记已写入 vault ({len(items)} 方案)"
    _push_internal_event(session_id, "research_completed",
                         {"phase": "W3 Research", "file": str(notes_path)})
    return result


async def _do_write_paper(step: dict, ws_path: Path, session_id: str,
                          state_path: Path, result: dict) -> dict:
    """W6 Write: 检查是否已有 paper/report，若无则生成占位。"""
    state = atomic_read(state_path)
    topic = state.get("research_topic", "")

    # 检查 vault 中是否已有 report
    vault = ws_path / "vault"
    reports = list(vault.glob("*.md")) + list((vault / "artifacts").glob("*.md") if (vault / "artifacts").exists() else [])
    existing = [r for r in reports if "report" in r.name.lower() or "paper" in r.name.lower()]

    if existing:
        result["detail"] = f"已有报告: {existing[0].name}"
        _record_deliverable(state_path, "write_paper", step.get("phase", "W6 Write"),
                          "paper", f"论文报告已存在: {existing[0].name}",
                          {"path": str(existing[0])})
    else:
        # 生成骨架报告
        report_path = vault / "artifacts" / "draft_report.md"
        report_path.parent.mkdir(exist_ok=True)
        lines = [
            f"# {topic or 'Research Report'}",
            f"",
            f"## Abstract",
            f"(待写入)",
            f"",
            f"## Method",
            f"(基于 W2-W5 实验结果)",
            f"",
            f"## Results",
            f"(从 analysis_summary 提取)",
            f"",
            f"## Conclusion",
            f"(待写入)",
        ]
        report_path.write_text("\n".join(lines), encoding="utf-8")
        _record_deliverable(state_path, "write_paper", step.get("phase", "W6 Write"),
                          "paper", f"论文骨架已生成: draft_report.md",
                          {"path": str(report_path)})
        result["detail"] = "论文骨架已生成 (draft_report.md)"
    return result


async def _do_review_paper(step: dict, ws_path: Path, session_id: str,
                           state_path: Path, result: dict) -> dict:
    """W7 Review: 记录审阅状态。"""
    state = atomic_read(state_path)
    _record_deliverable(state_path, "review_paper", step.get("phase", "W7 Review"),
                      "review", "审阅步骤已触发 — 请检查审阅结果",
                      {"phase": "W7 Review"})
    result["detail"] = "审阅步骤已记录"
    return result


# ── PipelineBridge startup ──

def start_bridge():
    """在 Dashboard 的 asyncio loop 中启动 PipelineBridge socket server。"""
    bridge = _bridge()
    if bridge is None:
        return
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(bridge.start())
        logger.info("PipelineBridge socket server scheduled")
    except Exception as e:
        logger.warning(f"PipelineBridge start failed: {e}")


# ── Watchdog API ──

async def watchdog_alerts_api(request):
    """GET /api/watchdog/alerts — return latest watchdog alerts, filtered by session_id."""
    wd = _watchdog()
    if not wd:
        return JSONResponse({"error": "watchdog not running"}, status_code=503)
    limit = int(request.query_params.get("limit", 50))
    session_id = request.query_params.get("session_id", "")
    return JSONResponse(wd.get_alerts(limit=limit, session_id=session_id or None))


async def watchdog_stats_api(request):
    """GET /api/watchdog/stats — return watchdog statistics."""
    wd = _watchdog()
    if not wd:
        return JSONResponse({"error": "watchdog not running"}, status_code=503)
    return JSONResponse(wd.get_stats())


async def watchdog_check_now_api(request):
    """POST /api/watchdog/check — run a one-shot check and return alerts."""
    wd = _watchdog()
    if not wd:
        return JSONResponse({"error": "watchdog not running"}, status_code=503)
    alerts = wd.check_now()
    return JSONResponse({"alerts": [a if isinstance(a, dict) else {
        "id": a.id, "severity": a.severity, "category": a.category,
        "message": a.message, "suggestion": a.suggestion,
        "session_id": a.session_id, "phase": a.phase, "step": a.step,
        "elapsed": round(a.elapsed, 1), "threshold": a.threshold,
        "timestamp": a.timestamp,
    } for a in alerts], "count": len(alerts)})


# ── App factory ──

def create_dashboard_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/", homepage),
            Route("/api/pipeline/init", pes_pipeline_init_api, methods=["POST"]),
            Route("/api/pipeline/command", pes_pipeline_command_api, methods=["POST"]),
            Route("/api/pipeline/execute", pes_pipeline_execute_api, methods=["POST"]),
            Route("/api/pipeline/transition", pes_pipeline_transition_api, methods=["POST"]),
            Route("/api/pipeline/state", pes_pipeline_state_api),
            Route("/api/sessions", list_sessions_api),
            Route("/api/sessions/{session_id}", session_detail_api),
            Route("/api/sessions/{session_id}/state", session_state_api),
            Route("/api/sessions/{session_id}/events", sse_events),
            Route("/api/sessions/{session_id}/pipeline", pipeline_state_api),
            Route("/api/sessions/{session_id}/pipeline/control", pipeline_control_api, methods=["GET", "POST"]),
            Route("/api/sessions/{session_id}/memory", memory_api),
            Route("/api/sessions/{session_id}/claim-chain", claim_chain_api),
            Route("/api/sessions/{session_id}/evolve-grid", evolve_grid_api),
            Route("/sessions/{session_id}/graph", claim_chain_graph_page),
            Route("/sessions/{session_id}/grid", evolve_grid_page),
            Route("/sessions/{session_id}/pipeline", pes_pipeline_page),
            Route("/api/restart", restart_api, methods=["POST"]),
            Route("/api/internal/events", post_internal_event, methods=["POST"]),
            Route("/api/watchdog/alerts", watchdog_alerts_api),
            Route("/api/watchdog/stats", watchdog_stats_api),
            Route("/api/watchdog/check", watchdog_check_now_api, methods=["POST"]),
        ],
    )


def _kill_port_occupant(port: int) -> bool:
    """Kill any process occupying the given port. Returns True if something was killed."""
    import subprocess
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split()
        if pids:
            for pid in pids:
                try:
                    subprocess.run(["kill", pid], timeout=3)
                    logger.info(f"Killed stale process {pid} on port {port}")
                except Exception:
                    pass
            import time
            time.sleep(0.5)
            return True
    except Exception:
        pass
    return False


def _is_port_free(port: int) -> bool:
    """Check if a port is available."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def start_dashboard(host: str = "0.0.0.0", port: int = 8420):
    """Start the dashboard in-process as a daemon thread.

    Must run in the same process as the AgentManager so SSE events
    from sub-agent execution are streamed to the browser in real-time.
    """
    import subprocess
    import time

    # Kill stale standalone dashboard processes on the port
    _kill_port_occupant(port)
    time.sleep(0.3)

    # ── In-process daemon thread (shares AgentManager with MCP server) ──
    import threading
    import asyncio

    app = create_dashboard_app()
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 启动 PipelineBridge socket server (对标 Ping Island HookSocketServer)
            bridge = _bridge()
            if bridge:
                loop.run_until_complete(bridge.start())
                logger.info("PipelineBridge socket server started")

            # 启动 Pipeline Watchdog (rule-based 异常检测)
            mgr = _mgr()
            if mgr:
                from pipeline_watchdog import PipelineWatchdog
                # Watchdog discovers workspaces from session registry at runtime
                wd = PipelineWatchdog(
                    workspace_dir=str(Path.cwd()),
                    event_bus=mgr.event_bus,
                    agent_manager=mgr,
                    poll_interval=20,
                )
                loop.run_until_complete(wd.start())
                set_watchdog(wd)
                logger.info("PipelineWatchdog started")

            loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error(f"Dashboard thread crashed: {type(e).__name__}: {e}")
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True, name="evo-dashboard")
    t.start()
    time.sleep(1.5)

    if server.started:
        logger.info(f"Dashboard running on http://{host}:{port}/")
    else:
        logger.warning(f"Dashboard thread started but may not be serving yet on port {port}")
