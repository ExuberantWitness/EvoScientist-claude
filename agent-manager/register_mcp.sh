#!/usr/bin/env bash
# Register EvoScientist Agent Manager as Claude Code MCP server
set -euo pipefail

ENV_NAME="${1:-evo-agents}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Registering MCP Server with Claude Code ==="

# Check claude CLI
if ! command -v claude &>/dev/null; then
    echo "ERROR: 'claude' CLI not found."
    echo "Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
fi

# Verify core modules exist
if [ ! -f "$SCRIPT_DIR/evoscientist_core/EvoScientist/EvoScientist.py" ]; then
    echo "ERROR: Core modules not found at $SCRIPT_DIR/evoscientist_core/"
    echo "Run extract_core.sh first: ./extract_core.sh /path/to/EvoScientist-main"
    exit 1
fi

# Verify conda env
if ! conda env list | grep -q "^${ENV_NAME} "; then
    echo "ERROR: Conda env '$ENV_NAME' not found."
    echo "Run setup_env.sh first: ./setup_env.sh"
    exit 1
fi

# Quick import test
echo "Testing core imports..."
conda run --no-banner -n "$ENV_NAME" python -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/evoscientist_core')
sys.path.insert(0, '$SCRIPT_DIR')
from evo_agent_manager.server import run_test
" 2>/dev/null && echo "  Core imports OK" || echo "  WARNING: Some imports may fail (non-critical at this stage)"

# Register MCP
echo ""
echo "Registering MCP server..."
claude mcp add evo-agents \
    -- conda run --no-banner -n "$ENV_NAME" \
    python -m evo_agent_manager.server \
    --base-dir "$SCRIPT_DIR"

echo ""
echo "=== MCP Registration Complete ==="
echo ""
echo "Verify: claude mcp list"
echo ""
echo "Available tools in Claude Code:"
echo "  evo_create_session  — Create multi-agent session"
echo "  evo_send            — Send message to agents"
echo "  evo_discuss         — Multi-agent discussion"
echo "  evo_status          — Session status"
echo "  evo_list_sessions   — List sessions"
echo "  evo_resume          — Resume session"
echo "  evo_approve         — Approve agent actions"
echo "  evo_get_memory      — Read agent memory"
