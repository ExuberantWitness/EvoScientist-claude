#!/usr/bin/env python3
"""Unified EvoScientist Dashboard launcher.

Single entry point — initializes AgentManager, wires it to the dashboard,
then starts uvicorn. No legacy path manipulation needed.
"""
import sys, os
PROJECT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)
sys.path.insert(0, str(PROJECT))  # ensure absolute

from session.manager import AgentManager
from sdk.dashboard.monitor import create_dashboard_app, set_manager
import uvicorn

if __name__ == '__main__':
    mgr = AgentManager(use_persistent_checkpointer=False)
    set_manager(mgr)
    print(f"AgentManager initialized: {len(mgr.sessions)} sessions")

    app = create_dashboard_app()
    print("Dashboard: http://localhost:8420")
    uvicorn.run(app, host='0.0.0.0', port=8420, log_level='warning')
