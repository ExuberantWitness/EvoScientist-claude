"""Standalone dashboard launcher. Starts the EvoScientist dashboard
with a fresh AgentManager that recovers existing sessions."""

import sys
sys.path.insert(0, ".")

from evo_agent_manager.dashboard import create_dashboard_app, set_manager
from evo_agent_manager.manager import AgentManager

mgr = AgentManager(base_dir=None)
set_manager(mgr)

import uvicorn
print("Starting EvoScientist Dashboard on http://localhost:8420")
print("  Claim Chain API: /api/sessions/{sid}/claim-chain")
print("  Evolve Grid API: /api/sessions/{sid}/evolve-grid")
uvicorn.run(create_dashboard_app(), host="0.0.0.0", port=8420, log_level="warning")
