"""Starlette web dashboard for EvoScientist agent monitoring."""

import asyncio
import importlib
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

from sdk.dashboard.frontend import DASHBOARD_HTML

from pes_controller.protocol import (
    atomic_read, atomic_write, dashboard_write,
    dashboard_write_approval, dashboard_heartbeat_age,
    dashboard_get_heartbeat,
)
from pes_controller import (
    PESController, PHASE_PLAN_1, PHASE_CODE,
    PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
    PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE, PHASE_REVIEW,
    PRODUCT_SPECS, TRANSITIONS,
)

logger = logging.getLogger(__name__)


# ── Hot-reload removed in v5 (phase handlers are standalone modules) ──



# Set by server.py before app starts
_manager_ref = None
_bridge_ref = None
_watchdog_ref = None

# Phase constants for pipeline monitoring (Agent SDK removed — all phases use SkillExecutor)
_W7_PHASES = {PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
              PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE, PHASE_REVIEW}


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
    if _manager_ref is None:
        _manager_ref = _LightweightManager()
    return _manager_ref


class _LightweightManager:
    """File-based session discovery + EventBus, no AgentManager dependency.

    Used when the dashboard runs standalone (run_dashboard.py) without
    the full AgentManager / langchain stack.  Routes that need real
    agent interaction (send_message, discuss, etc.) will return a
    graceful "not available" error.
    """

    def __init__(self):
        from session.event_bus import EventBus
        self.event_bus = EventBus()
        self.sessions = {}

    def refresh_sessions(self):
        """Scan filesystem for session directories."""
        self._load_sessions_from_disk()

    def list_sessions(self):
        self._load_sessions_from_disk()
        return [
            {"session_id": k, "workspace_dir": v.get("workspace_dir", ""),
             "status": v.get("status", "idle"), "phase": v.get("phase", "")}
            for k, v in self.sessions.items()
        ]

    def _load_sessions_from_disk(self):
        base = Path(__file__).resolve().parent.parent.parent
        reg = base / ".evo_session_registry.json"
        if reg.exists():
            try:
                registry = json.loads(reg.read_text(encoding="utf-8"))
                for sid, ws in registry.items():
                    sp = Path(ws) / "PIPELINE_STATE.json"
                    state = {}
                    if sp.exists():
                        try:
                            state = json.loads(sp.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    self.sessions[sid] = {
                        "workspace_dir": ws,
                        "status": state.get("status", "idle"),
                        "phase": state.get("phase", ""),
                    }
            except Exception:
                pass

    async def get_status(self, sid):
        if sid not in self.sessions:
            self._load_sessions_from_disk()
        if sid not in self.sessions:
            return {"error": f"Session {sid} not found"}
        info = self.sessions[sid]
        return {"session_id": sid, "status": info.get("status", "idle"),
                "workspace_dir": info.get("workspace_dir", "")}

    def get_stream_state(self, sid):
        return {"session_id": sid, "status": "idle", "steps": []}

    def get_pipeline_state(self, sid):
        info = self.sessions.get(sid, {})
        ws = info.get("workspace_dir", "")
        if ws:
            sp = Path(ws) / "PIPELINE_STATE.json"
            if sp.exists():
                try:
                    return json.loads(sp.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return {}

    def get_pipeline_control(self, sid):
        return {"session_id": sid, "status": "no_control"}

    def pipeline_control(self, session_id, action, phase=None):
        return {"error": "Pipeline control requires AgentManager"}

    async def get_memory(self, sid):
        return {"error": "Memory requires AgentManager"}


def _bridge():
    return _bridge_ref



# ── Routes ──

async def homepage(request):
    return HTMLResponse(DASHBOARD_HTML)


async def list_sessions_api(request):
    mgr = _mgr()
    if mgr:
        mgr.refresh_sessions()
        return JSONResponse(mgr.list_sessions())
    # Fallback: scan sessions directory when AgentManager not initialized
    sessions = []
    # Derive from project root: sdk/dashboard/monitor.py → project root
    _project = Path(__file__).resolve().parent.parent
    sessions_base = _project / 'sessions'
    if not sessions_base.exists():
        sessions_base = _project.parent / 'sessions'
    if sessions_base.exists():
        for sd in sorted(sessions_base.glob('sess_*'), key=lambda p: p.stat().st_mtime, reverse=True):
            sp = sd / 'PIPELINE_STATE.json'
            if not sp.exists():
                continue
            try:
                state = json.loads(sp.read_text(encoding='utf-8'))
                sessions.append({
                    'session_id': sd.name,
                    'workspace_dir': str(sd),
                    'status': state.get('status', 'unknown'),
                    'phase': state.get('phase', ''),
                    'created_at': state.get('created_at', ''),
                })
            except Exception:
                pass
    return JSONResponse(sessions)


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
    workspace = Path(session.workspace_dir) / "_index"

    from claim_chain.chain import ClaimChainV2
    cc = ClaimChainV2(workspace / "cc.db")
    atoms = cc.get_atoms()
    relations = cc.get_relations()
    cc.close()

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


async def agent_replay_page(request):
    """Serve self-contained Agent Session Replay page.

    Reads agent conversation logs from _index/agents/ and generates
    an interactive timeline with proposal cards, prompt inspection,
    and per-agent navigation. Zero external dependencies.
    """
    session_id = request.path_params.get("session_id", "")
    workspace_dir = request.query_params.get("workspace", "")
    if not workspace_dir:
        # Look up workspace from session registry
        rpath = Path(
            os.path.join(
                os.path.dirname(__file__), "..", "..",
                ".evo_session_registry.json"
            )
        )
        if rpath.exists():
            try:
                registry = json.loads(rpath.read_text(encoding="utf-8"))
                workspace_dir = registry.get(session_id, "")
            except Exception:
                pass

    if not workspace_dir:
        return HTMLResponse("<h1>Session not found</h1>", status_code=404)

    try:
        from session.replay import build_replay_html
        html = build_replay_html(Path(workspace_dir))
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(
            f"<h1>Replay Error</h1><pre>{e}</pre>",
            status_code=500,
        )


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

_PIPELINE_HTML_PATH = Path(__file__).parent / "static" / "index.html"


def _load_pipeline_html():
    if _PIPELINE_HTML_PATH.exists():
        return _PIPELINE_HTML_PATH.read_text(encoding="utf-8")
    return "<html><body>Dashboard static/index.html not found</body></html>"


async def pes_pipeline_page(request):
    """管线监控页面（从 session 自动获取 workspace）。"""
    return HTMLResponse(_load_pipeline_html())


async def pes_pipeline_transition_api(request):
    """阶段流转 — 委托给 controller_v5.PESController.transition_phase()。

    支持的 actions:
      satisfied       — W2-W6 自动推进（调用 _auto_next_phase）
      advance         — W7.1-W8 人工选择目标 phase（需 target_phase）
      redo            — 重做当前 phase
      redo_with_review— 带审稿意见重做
      jump_to_plan    — 跳回 W2 问题分析
      terminate       — 终止流水线
    """
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

    from pes_controller.controller_v5 import PESController as PESControllerV5
    ctrl = PESControllerV5(workspace_dir=workspace)

    target_phase = body.get("target_phase")
    feedback = body.get("feedback", "")
    selected_plan = body.get("selected_plan")

    result = ctrl.transition_phase(
        action=action,
        target_phase=target_phase,
        feedback=feedback,
        selected_plan=selected_plan,
    )

    status_code = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status_code)


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
        _MIGRATION = {"方案提出":"W2 问题分析","文献调研":"W3 方案方向","ELO筛选":"W4 具体方案生成","实验执行":"W5 代码实现","结果分析":"W6 结果分析","论文写作":"W7.1 论文计划","论文审阅":"W8 审阅"}
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
                atomic_write(state_path, state)

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
    # 创建 session 完整目录树
    data_dir = ws_path  # no vault/ layer
    for d in ["evolve_archive", "artifacts",
              "Algorithms", "Bottlenecks", "Islands", "iterations",
              "_index", "_pipeline", "_memory"]:
        (data_dir / d).mkdir(parents=True, exist_ok=True)

    # 生成 session_id (与 bootstrap 一致: sess_<uuid8>)
    session_id = f"sess_{_uuid.uuid4().hex[:8]}"

    state_path = ws_path / "PIPELINE_STATE.json"
    state = {
        "phase": "W2 问题分析",
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
    atomic_write(state_path, state)

    # 注册到 .evo_sessions/ + 全局 registry (AgentManager 恢复依赖)
    _ensure_session_registered(session_id, workspace)
    # 补充 research_topic 到 meta 文件
    evo_dir = ws_path / ".evo_sessions"
    meta_file = evo_dir / f"{session_id}.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["research_topic"] = research_topic
            meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        except Exception:
            pass

    return JSONResponse({"initialized": True, "workspace_dir": workspace,
                         "session_id": session_id, "phase": "W2 问题分析"})


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
    atomic_write(state_path, state)

    return JSONResponse({"command_written": True, "command_id": cmd_id, "action": action})




async def pes_pipeline_execute_api(request):
    """Dashboard 驱动执行管线步骤 — delegates to PESControllerV5.

    All step execution now happens inside phase handlers.
    This route just calls sub_loop() and returns the result.
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

    # Lock check: reject if awaiting_decision or terminated
    state = atomic_read(state_path)
    phase = state.get("phase", "")
    status = state.get("status", "")
    if status == "awaiting_decision":
        return JSONResponse({"waiting": True, "phase": phase,
                             "message": "等待用户决策"})
    if status == "terminated":
        return JSONResponse({"error": "Pipeline terminated", "phase": phase}, status_code=400)

    # Execute via PESControllerV5 (phase handlers do all the work)
    try:
        from pes_controller.controller_v5 import PESController as PESControllerV5
        ctrl = PESControllerV5(workspace_dir=workspace)
        step = ctrl.sub_loop()
    except Exception as e:
        logger.exception(f"PESControllerV5.sub_loop failed: {e}")
        return JSONResponse({"error": f"Pipeline step failed: {e}", "phase": phase}, status_code=500)

    # Handle completion
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

    # Step executed by phase handler — return result
    return JSONResponse({"executed": True, **step})

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
            "model": "deepseek-chat",
            "provider": "deepseek",
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
            Route("/sessions/{session_id}/replay", agent_replay_page),
            Route("/api/restart", restart_api, methods=["POST"]),
            Route("/api/internal/events", post_internal_event, methods=["POST"]),
            Route("/api/watchdog/alerts", watchdog_alerts_api),
            Route("/api/watchdog/stats", watchdog_stats_api),
            Route("/api/watchdog/check", watchdog_check_now_api, methods=["POST"]),
        ],
    )


def _kill_port_occupant(port: int) -> bool:
    """Kill any process occupying the given port. Cross-platform (Linux + Windows)."""
    import subprocess
    import sys
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-aon"],
                capture_output=True, text=True, timeout=5,
            )
            pids = set()
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        pids.add(parts[-1])
            for pid in pids:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid], timeout=3,
                                   capture_output=True)
                    logger.info(f"Killed stale process {pid} on port {port}")
                except Exception:
                    pass
            if pids:
                import time
                time.sleep(0.5)
                return True
        else:
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
                try:
                    from pes_controller.watchdog import PipelineWatchdog
                except ImportError:
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
