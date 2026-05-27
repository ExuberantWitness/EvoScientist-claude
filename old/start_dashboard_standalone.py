"""Standalone dashboard launcher. Starts the EvoScientist dashboard
with a fresh AgentManager, PipelineBridge, and PipelineWatchdog."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")
# Also add tools/ for pipeline_watchdog import
_tools = str(Path(__file__).resolve().parent.parent / "tools")
if _tools not in sys.path:
    sys.path.insert(0, _tools)

from evo_agent_manager.dashboard import create_dashboard_app, set_manager, set_watchdog
from evo_agent_manager.manager import AgentManager
from pipeline_watchdog import PipelineWatchdog

mgr = AgentManager(base_dir=None)
set_manager(mgr)


async def main():
    # Start Pipeline Watchdog (rule-based anomaly detection)
    wd = PipelineWatchdog(
        workspace_dir=str(Path.cwd()),
        event_bus=mgr.event_bus,
        agent_manager=mgr,
        poll_interval=20,
    )
    await wd.start()
    set_watchdog(wd)
    print("  PipelineWatchdog started")

    # Start uvicorn
    import uvicorn
    config = uvicorn.Config(
        create_dashboard_app(), host="0.0.0.0", port=8420,
        log_level="warning", loop="asyncio",
    )
    server = uvicorn.Server(config)
    print("Starting EvoScientist Dashboard on http://localhost:8420")
    print("  Claim Chain API: /api/sessions/{sid}/claim-chain")
    print("  Evolve Grid API: /api/sessions/{sid}/evolve-grid")
    print("  Watchdog API: /api/watchdog/alerts")
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
