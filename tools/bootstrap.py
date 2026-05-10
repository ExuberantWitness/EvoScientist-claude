"""Pipeline Bootstrap — 一键初始化工作空间、创建 Session、输出 Dashboard URL。

用法:
    python tools/bootstrap.py "研究问题" /path/to/workspace
"""

import json
import os
import sys
import uuid
import urllib.parse
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from pipeline_protocol import atomic_read, atomic_write
from pes_controller import PESController, PHASE_PLAN


def bootstrap(research_topic: str, workspace_dir: str) -> dict:
    ws = Path(workspace_dir).resolve()
    ws.mkdir(parents=True, exist_ok=True)

    # 1. PESController init — 创建目录结构 + CC/Grid + PIPELINE_STATE.json
    ctrl = PESController(ws)
    init_result = ctrl.init(research_topic=research_topic)

    # 2. 更新 state — 写入临时 session_id
    state = atomic_read(ws / "PIPELINE_STATE.json")
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    state["session_id"] = session_id
    state["agent_session_id"] = session_id
    state["status"] = "in_progress"
    atomic_write(ws / "PIPELINE_STATE.json", state)

    dashboard_url = f"http://localhost:8420/sessions/{session_id}/pipeline?workspace={urllib.parse.quote(str(ws))}"

    # 3. 注册到 evo-agents AgentManager session registry
    try:
        _agent_mgr_dir = str(Path(__file__).resolve().parent.parent / "agent-manager")
        if _agent_mgr_dir not in sys.path:
            sys.path.insert(0, _agent_mgr_dir)
        from evo_agent_manager.manager import AgentManager
        import asyncio
        mgr = AgentManager(base_dir=str(ws))
        asyncio.run(mgr.create_session(workspace_dir=str(ws)))
        # 获取 AgentManager 生成的真实 session_id 并回写
        sessions = mgr.list_sessions()
        if sessions:
            real_sid = sessions[-1]["session_id"]
            state["session_id"] = real_sid
            state["agent_session_id"] = real_sid
            atomic_write(ws / "PIPELINE_STATE.json", state)
            session_id = real_sid
            dashboard_url = f"http://localhost:8420/sessions/{real_sid}/pipeline?workspace={urllib.parse.quote(str(ws))}"
            print(f"[bootstrap] Session registered: {real_sid}", file=sys.stderr)
    except Exception as e:
        print(f"[bootstrap] AgentManager registration failed ({e}), using local session_id.", file=sys.stderr)

    return {
        "session_id": session_id,
        "workspace": str(ws),
        "phase": state["phase"],
        "dashboard_url": dashboard_url,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/bootstrap.py \"研究问题\" [workspace_dir]")
        print("  workspace_dir 默认为当前目录")
        sys.exit(1)

    research_topic = sys.argv[1]
    workspace_dir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    result = bootstrap(research_topic, workspace_dir)

    print(f"session_id:    {result['session_id']}")
    print(f"workspace:     {result['workspace']}")
    print(f"phase:         {result['phase']}")
    print(f"dashboard_url: {result['dashboard_url']}")
    print()
    print("================================================")
    print("Pipeline 已就绪。请在浏览器中打开:")
    print(f"  {result['dashboard_url']}")
    print("后续所有操作都在 Dashboard 网页端完成。")
    print("================================================")


if __name__ == "__main__":
    main()
