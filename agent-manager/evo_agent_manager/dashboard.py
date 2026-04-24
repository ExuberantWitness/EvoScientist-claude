"""Starlette web dashboard for EvoScientist agent monitoring."""

import asyncio
import json
import logging

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


# ── Routes ──

async def homepage(request):
    return HTMLResponse(DASHBOARD_HTML)


async def list_sessions_api(request):
    mgr = _mgr()
    if not mgr:
        return JSONResponse({"error": "manager not initialized"})
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
    """Start the dashboard in-process (shares AgentManager with MCP server).

    Uses uvicorn in a daemon thread so the dashboard and MCP server share
    the same AgentManager instance — sessions created via MCP are immediately
    visible on the dashboard.
    """
    import threading
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

    app = create_dashboard_app()
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        import asyncio
        asyncio.run(server.serve())

    t = threading.Thread(target=_run, daemon=True, name="evo-dashboard")
    t.start()
    time.sleep(1)

    if _is_port_free(port):
        logger.error(f"Dashboard failed to bind port {port}.")
    else:
        logger.info(f"Dashboard running on http://{host}:{port}/")
