#!/usr/bin/env python3
"""Unified EvoScientist Dashboard launcher.

Single entry point — initializes the dashboard with a lightweight
session manager (no AgentManager / langchain dependency).
For full MCP server with 17 evo-* tools, use `python -m sdk.server`.
"""
import sys, os
PROJECT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

from sdk.dashboard.monitor import create_dashboard_app
import uvicorn

if __name__ == '__main__':
    # LightweightManager is auto-created on first _mgr() call.
    # No AgentManager needed — PES pipeline uses PESControllerV5 directly.
    print("Flux-Insight Dashboard (standalone mode)")

    app = create_dashboard_app()
    print("Dashboard: http://localhost:8420")
    uvicorn.run(app, host='0.0.0.0', port=8420, log_level='warning')
