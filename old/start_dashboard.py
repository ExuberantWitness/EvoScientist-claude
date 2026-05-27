"""Standalone Dashboard launcher — 不依赖 MCP server 的独立启动。

用法:
    python tools/start_dashboard.py [--port 8420]

必须用 evo-agents conda env 的 Python 启动 (有 langgraph/aiosqlite 等依赖):
    /home/exuber/anaconda3/envs/evo-agents/bin/python tools/start_dashboard.py
"""

import json
import os
import sys
import time
from pathlib import Path


def _register_codegraph_mcp():
    """Auto-register CodeGraph as MCP server in ~/.claude/mcp.json."""
    mcp_config_path = Path.home() / ".claude" / "mcp.json"
    try:
        if mcp_config_path.exists():
            config = json.loads(mcp_config_path.read_text())
        else:
            config = {}
        config.setdefault("mcpServers", {})
        if "codegraph" not in config["mcpServers"]:
            config["mcpServers"]["codegraph"] = {
                "type": "stdio",
                "command": "npx",
                "args": ["@colbymchenry/codegraph", "serve", "--mcp"],
            }
            mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
            mcp_config_path.write_text(json.dumps(config, indent=2))
            print(f"[start_dashboard] CodeGraph MCP registered in {mcp_config_path}")
        else:
            print("[start_dashboard] CodeGraph MCP already registered")
    except Exception as e:
        print(f"[start_dashboard] CodeGraph MCP registration failed: {e}")

# 使用绝对路径, 无论从哪里启动都指向正确位置
_PROJECT_ROOT = Path("/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude")
AGENT_MANAGER_DIR = str(_PROJECT_ROOT / "agent-manager")
TOOLS_DIR = str(_PROJECT_ROOT / "tools")

if AGENT_MANAGER_DIR not in sys.path:
    sys.path.insert(0, AGENT_MANAGER_DIR)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
os.chdir(AGENT_MANAGER_DIR)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Start EvoScientist Dashboard")
    parser.add_argument("--port", type=int, default=8420)
    args = parser.parse_args()

    # Ensure API keys are available (same defaults as server.py)
    _defaults = {
        "OPENAI_API_KEY": "sk-d56c7dbcd28c44b689773a3f544486b2",
        "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
        "OPENAI_API_BASE": "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY": "sk-d56c7dbcd28c44b689773a3f544486b2",
        "TAVILY_API_KEY": "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",
    }
    for k, v in _defaults.items():
        os.environ.setdefault(k, v)

    from evo_agent_manager.manager import AgentManager
    from evo_agent_manager.dashboard import set_manager, set_bridge, start_dashboard
    from evo_agent_manager.pipeline_bridge import PipelineBridge

    mgr = AgentManager(use_persistent_checkpointer=False)
    bridge = PipelineBridge()
    bridge.set_event_bus(mgr.event_bus)
    bridge.set_manager(mgr)
    set_manager(mgr)
    set_bridge(bridge)

    _register_codegraph_mcp()

    start_dashboard(port=args.port)
    print(f"Dashboard + PipelineBridge started on http://localhost:{args.port}/", flush=True)

    # Keep process alive
    while True:
        time.sleep(60)
