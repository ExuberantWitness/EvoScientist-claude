"""Standalone Dashboard launcher — 不依赖 MCP server 的独立启动。

用法:
    python tools/start_dashboard.py [--port 8420]

必须用 evo-agents conda env 的 Python 启动 (有 langgraph/aiosqlite 等依赖):
    /home/exuber/anaconda3/envs/evo-agents/bin/python tools/start_dashboard.py
"""

import os
import sys
import time
from pathlib import Path

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
    start_dashboard(port=args.port)
    print(f"Dashboard + PipelineBridge started on http://localhost:{args.port}/", flush=True)

    # Keep process alive
    while True:
        time.sleep(60)
