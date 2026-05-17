"""Pipeline Bootstrap — 创建 Obsidian vault + Session + 输出 Dashboard URL。

用法:
    python tools/bootstrap.py "研究问题" /path/to/EvoScientist-claude
"""

import json
import os
import sys
import uuid
import urllib.parse
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent  # EvoScientist-claude/
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from pipeline_protocol import atomic_read, atomic_write
from pes_controller import PESController, PHASE_PLAN
from vault_manager import VaultManager


def bootstrap(research_topic: str, project_dir: str) -> dict:
    """创建完整 pipeline session: vault + PESController + Dashboard URL."""
    proj = Path(project_dir).resolve()

    # 1. 生成 session_id + 创建 Obsidian vault
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    mgr = VaultManager(proj / "sessions" / session_id)
    mgr.init_vault(session_id, research_topic)

    # 2. PESController init (CC + Grid + PIPELINE_STATE)
    # PESController 使用 session_dir 作为 workspace
    session_dir = mgr.session_dir
    ctrl = PESController(str(session_dir), session_id=session_id)
    ctrl.init(research_topic=research_topic)

    # 3. 写入 PIPELINE_STATE (兼容 Dashboard API 从 workspace 读)
    state = atomic_read(session_dir / "PIPELINE_STATE.json")
    state["session_id"] = session_id
    state["agent_session_id"] = session_id
    state["session_dir"] = str(session_dir)
    state["vault_dir"] = str(mgr.vault_dir)
    state["research_topic"] = research_topic
    state["status"] = "in_progress"
    atomic_write(session_dir / "PIPELINE_STATE.json", state)

    dashboard_url = (
        f"http://localhost:8420/sessions/{session_id}/pipeline"
        f"?workspace={urllib.parse.quote(str(session_dir))}"
    )

    # 4. 注册 session 到 .evo_sessions/ (Dashboard AgentManager 通过此目录发现 session)
    # Dashboard 从 agent-manager/.evo_sessions/ 扫描, 所以写入两个位置
    session_data = {
        "session_id": session_id,
        "workspace_dir": str(session_dir),
        "vault_dir": str(mgr.vault_dir),
        "research_topic": research_topic,
        "created_at": __import__('time').time(),
    }
    for evo_base in [proj, PROJECT_DIR / "agent-manager"]:
        evo_sessions_dir = evo_base / ".evo_sessions"
        evo_sessions_dir.mkdir(parents=True, exist_ok=True)
        (evo_sessions_dir / f"{session_id}.json").write_text(
            json.dumps(session_data, indent=2, ensure_ascii=False))

    return {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "vault_dir": str(mgr.vault_dir),
        "phase": state.get("phase", PHASE_PLAN),
        "dashboard_url": dashboard_url,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/bootstrap.py \"研究问题\" [project_dir]")
        print("  project_dir 默认为 EvoScientist-claude 目录")
        sys.exit(1)

    research_topic = sys.argv[1]
    project_dir = sys.argv[2] if len(sys.argv) > 2 else str(PROJECT_DIR)

    result = bootstrap(research_topic, project_dir)

    print(f"session_id:    {result['session_id']}")
    print(f"session_dir:   {result['session_dir']}")
    print(f"vault_dir:     {result['vault_dir']}")
    print(f"phase:         {result['phase']}")
    print(f"dashboard_url: {result['dashboard_url']}")
    print()
    print("=" * 48)
    print("Pipeline 已就绪。请在浏览器中打开:")
    print(f"  {result['dashboard_url']}")
    print("Obsidian vault 可用 Obsidian 打开:")
    print(f"  {result['vault_dir']}")
    print("=" * 48)


if __name__ == "__main__":
    main()
