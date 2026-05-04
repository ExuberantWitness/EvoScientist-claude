#!/bin/bash
# Start EvoScientist Dashboard as a standalone background service.
# Usage: bash scripts/start_dashboard.sh [port]
#
# The dashboard auto-discovers sessions from .evo_sessions/ directories
# and the .evo_session_registry.json file. No restart needed when new
# sessions are created — the /api/sessions endpoint refreshes on each call.

set -e

PORT="${1:-8420}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Kill any existing dashboard on this port
OLD_PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
    echo "Killing old process on port $PORT (PID: $OLD_PID)"
    kill $OLD_PID 2>/dev/null || true
    sleep 1
fi

cd "$PROJECT_DIR/agent-manager"

echo "Starting dashboard on http://0.0.0.0:$PORT/"
nohup python start_dashboard_standalone.py > /tmp/evo-dashboard.log 2>&1 &
DASH_PID=$!
echo "Dashboard PID: $DASH_PID"
echo "Log: /tmp/evo-dashboard.log"
echo "Visit: http://localhost:$PORT/"

# Verify it started
sleep 2
if curl -s "http://localhost:$PORT/api/sessions" > /dev/null 2>&1; then
    echo "Dashboard is running."
else
    echo "WARNING: Dashboard may not have started. Check log:"
    echo "  tail -20 /tmp/evo-dashboard.log"
fi
