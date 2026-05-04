"""Starlette web dashboard for EvoScientist agent monitoring."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from sse_starlette.sse import EventSourceResponse

from .frontend import DASHBOARD_HTML

logger = logging.getLogger(__name__)

# Set by server.py before app starts
_manager_ref = None


def set_manager(manager):
    global _manager_ref
    _manager_ref = manager


def _mgr():
    return _manager_ref


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
    """POST endpoint to restart the dashboard process.

    Spawns a helper script that: waits for response to flush,
    kills all processes on port 8420, waits for port to free,
    then launches a fresh standalone dashboard.
    """
    import subprocess

    launcher = Path(__file__).parent.parent / "start_dashboard_standalone.py"
    port = 8420

    restart_script = f'''
import subprocess, time, sys, socket

port = {port}
launcher = r"{launcher}"

# 1. Wait for HTTP response to flush
time.sleep(1.5)

# 2. Kill only Python processes listening on port 8420
try:
    result = subprocess.run(
        ["bash", "-c", "lsof -ti :{port} | xargs -I{{}} sh -c 'ps -o comm= -p {{}} | grep -q python && kill {{}}'"],
        capture_output=True, text=True, timeout=5)
except Exception:
    pass

# 3. Wait for port to be free
for _ in range(20):
    time.sleep(0.5)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("0.0.0.0", port))
            break
    except OSError:
        continue

# 4. Launch new dashboard
subprocess.Popen(
    [sys.executable, launcher],
    cwd=launcher.rsplit("/", 1)[0],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
'''

    try:
        subprocess.Popen(
            [sys.executable, "-c", restart_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.error(f"Failed to schedule restart: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    return JSONResponse({"status": "restarting", "message": "Dashboard restarting in ~3 seconds..."})


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


# ── App factory ──

def create_dashboard_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/", homepage),
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
            Route("/api/restart", restart_api, methods=["POST"]),
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
    """Start the dashboard as a standalone subprocess.

    Uses subprocess to avoid daemon-thread event-loop conflicts with
    the MCP stdio server. Dashboard reads session state from the shared
    checkpoint database, so sessions created via MCP are visible.

    Falls back to in-process thread if the standalone launcher is unavailable.
    """
    import subprocess
    import time

    # Check for port conflicts and clean up stale processes
    if not _is_port_free(port):
        logger.warning(f"Port {port} is occupied. Attempting to free it...")
        killed = _kill_port_occupant(port)
        if killed:
            time.sleep(0.5)
        if not _is_port_free(port):
            logger.error(f"Port {port} still occupied after cleanup. Dashboard not started.")
            return

    # ── Primary: launch as standalone subprocess ──
    launcher = Path(__file__).parent.parent / "start_dashboard_standalone.py"
    if launcher.exists():
        try:
            proc = subprocess.Popen(
                [subprocess.sys.executable, str(launcher)],
                cwd=str(launcher.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            if not _is_port_free(port):
                logger.info(f"Dashboard running (subprocess pid={proc.pid}) on http://{host}:{port}/")
                return
            else:
                logger.warning("Dashboard subprocess started but port not bound. Retrying with thread fallback...")
                proc.kill()
        except Exception as e:
            logger.warning(f"Dashboard subprocess failed: {e}. Trying thread fallback...")

    # ── Fallback: in-process daemon thread (legacy) ──
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
            loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error(f"Dashboard thread crashed: {type(e).__name__}: {e}")
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True, name="evo-dashboard")
    t.start()
    time.sleep(1.5)

    if _is_port_free(port):
        logger.error(f"Dashboard failed to bind port {port} (both subprocess and thread).")
    else:
        logger.info(f"Dashboard running (thread fallback) on http://{host}:{port}/")
