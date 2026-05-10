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

# Agent SDK 需要子进程的阶段
AGENT_SDK_PHASES = {PHASE_CODE, PHASE_WRITE, PHASE_REVIEW}


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
    if sid not in mgr.sessions:
        return JSONResponse({"error": f"Session {sid} not found"}, status_code=404)

    session = mgr.sessions[sid]
    workspace = Path(session.workspace_dir) / "claim_chain"

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
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#bc8cff}
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
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#bc8cff}
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

<div class="flow" id="flow"></div>

<div class="steps-section" id="steps-section" style="display:none">
  <h2>当前阶段步骤</h2>
  <div class="step-list" id="step-list"></div>
</div>

<div class="gap-section" id="gap-section" style="display:none">
  <h2>Gap Analysis</h2>
  <div id="gap-content"></div>
</div>

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

<script>
const sid = window.location.pathname.split('/')[2];
document.getElementById('session-label').textContent = 'Session: ' + sid;

const PHASES = ["W2 Plan","W3 Research","W3.5 Ideate","W4 Code","W5 Analyze","W6 Write","W7 Review","已终止"];
const PHASE_LABELS = {"W2 Plan":"Plan","W3 Research":"Research","W3.5 Ideate":"Ideate","W4 Code":"Code","W5 Analyze":"Analyze","W6 Write":"Write","W7 Review":"Review","已终止":"终止"};
const CHAIN_STEPS = {
  "W2 Plan":     ["看CC/EM","多Agent讨论","ELO锦标赛","Evolution Memory"],
  "W3 Research": ["看CC/EM","多Agent研究","ELO锦标赛","Evolution Memory","文献调研","写入CC"],
  "W3.5 Ideate": ["看CC/EM","多Agent构思","ELO锦标赛","Evolution Memory"],
  "W4 Code":     ["看CC/EM","单Agent代码实现"],
  "W5 Analyze":  ["看CC","Island/Rubric扫描","多Agent Judge","Evolution Memory","写入CC","Island分配"],
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
    var actionMap = {next:'sub_loop', satisfied:'transition', unsatisfied:'transition', jump_write:'transition', terminate:'transition'};
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
    } else if (d.step_done) {
      addLog('阶段完成: ' + d.message, 'info');
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

    renderFlow(phase, status);
    renderSteps(phase, stepIdx);
    renderGap(state.last_gap_analysis);
    updateControls(status, phase, state.command, taskRunning, activeTask);
    refreshWatchdog();
  } catch (e) {
    addLog('Refresh error: ' + e.message, 'error');
  }
}

let watchdogAlerts = [];

async function refreshWatchdog() {
  try {
    const resp = await fetch('/api/watchdog/alerts?limit=10');
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
  const labels = {satisfied:'满意-下一步', unsatisfied:'不满意-重做', jump_to_write:'强制进入写作', terminate:'终止管线'};
  addLog('备用控制: ' + labels[action], 'info');
  try {
    const resp = await fetch('/api/pipeline/transition', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({workspace_dir: workspaceDir, action: action}),
    });
    const result = await resp.json();
    if (result.error) {
      addLog('错误: ' + result.error, 'error');
    } else {
      const msg = result.transitioned
        ? ('阶段转换: ' + (result.from || '') + ' -> ' + result.to)
        : ('重做阶段: ' + (result.phase || ''));
      addLog(msg, 'success');
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

    if action == "satisfied":
        next_phase = _auto_next_phase(phase, state)
        state["phase"] = next_phase
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state.pop("command", None)  # 清除旧命令
        if phase == "W5 Analyze":
            state["iteration"] = state.get("iteration", 0) + 1
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": True, "from": phase, "to": next_phase})

    elif action == "unsatisfied":
        if phase == "W7 Review":
            state["phase"] = "W6 Write"
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state.pop("command", None)  # 清除旧命令
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": False, "phase": state["phase"],
                            "message": f"重做阶段 '{state['phase']}'"})

    elif action == "jump_to_write":
        gap = state.get("last_gap_analysis")
        if not gap or gap.get("target_score") is None:
            return JSONResponse({"error": "无法进入写作：未定义成功目标。请先创建 success_criteria.md"}, status_code=400)
        state["phase"] = "W6 Write"
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state.pop("command", None)  # 清除旧命令
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": True, "to": "W6 Write"})

    elif action == "terminate":
        state["phase"] = "已终止"
        state["status"] = "terminated"
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return JSONResponse({"transitioned": True, "to": "已终止"})

    return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)


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
            mgr = _mgr()
            if mgr:
                try:
                    sess = mgr.sessions.get(sid)
                    if sess and sess.status in ("completed", "error", "idle"):
                        state.pop("active_task", None)
                        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
                except Exception:
                    pass

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

    ws_path = Path(workspace)
    for d in ["claim_chain", "evolve_archive", "memory", "artifacts"]:
        (ws_path / d).mkdir(parents=True, exist_ok=True)

    state_path = ws_path / "PIPELINE_STATE.json"
    state = {
        "phase": "W2 Plan",
        "iteration": 0,
        "sub_loop_step": 0,
        "status": "in_progress",
        "timestamp": __import__("time").time(),
        "session_id": None,
        "research_topic": research_topic,
        "config": {},
        "needs_init": True,
        "needs_intake": True,
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    return JSONResponse({"initialized": True, "workspace_dir": workspace, "phase": "W2 Plan"})


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

    # 3. active_task 锁检查 (主线)
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
    ctrl = PESController(ws_path)
    step = ctrl.sub_loop()

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
    result = await _execute_step(step, ws_path, session_id, state_path)
    return JSONResponse(result)


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
        _push_internal_event(session_id, "step_executed",
                             {"phase": phase, "step": step_name, "detail": "STEP pipeline completed"})

    elif action == "multi_agent":
        tool = step.get("tool", "")
        if not mgr:
            result["warning"] = "AgentManager未初始化，跳过multi_agent执行"
            return result

        if tool == "evo_discuss":
            # 确保 session 存在且有 agent
            session = mgr.sessions.get(session_id)
            if not session:
                ws = str(ws_path)
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
                state = atomic_read(state_path)
                state["session_id"] = session_id
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

                # 不长时间轮询 — 启动后立即返回，前端通过 refreshState 追踪完成
                status = await mgr.get_status(session_id)
                if status.get("status") == "error":
                    raise RuntimeError(f"discuss failed: {status}")

                result["detail"] = "讨论已在后台启动"
                result["task_started"] = True
                # 不清除 active_task — 让前端 refreshState 检测完成后自动清除
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
                except Exception as e:
                    result["error"] = f"run_tournament失败: {e}"

        elif tool == "evo_distill":
            state = atomic_read(state_path)
            tourney = state.get("last_tournament_result", {})
            try:
                await mgr.distill(
                    session_id=session_id,
                    distill_type=step.get("distill_type", "ide"),
                    proposals=tourney.get("ranked") if tourney else None,
                )
                result["detail"] = f"Evolution Memory已记录 (type={step.get('distill_type', 'ide')})"
            except Exception as e:
                result["error"] = f"evo_distill失败: {e}"

    elif action == "invoke_skill":
        skill = step.get("skill", "")
        _push_internal_event(session_id, "skill_invoked",
                             {"phase": phase, "skill": skill})
        result["detail"] = f"Skill {skill} 已调用"

    elif action == "ingest_results":
        state = atomic_read(state_path)
        ingested = state.get("ingested_results", [])
        result["detail"] = f"已扫描 {len(ingested)} 个实验结果"

    else:
        result["detail"] = f"未识别的action: {action}"

    return result


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
    """GET /api/watchdog/alerts — return latest watchdog alerts."""
    wd = _watchdog()
    if not wd:
        return JSONResponse({"error": "watchdog not running"}, status_code=503)
    limit = int(request.query_params.get("limit", 50))
    return JSONResponse(wd.get_alerts(limit=limit))


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
