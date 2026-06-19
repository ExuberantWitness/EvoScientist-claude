"""Pipeline Bootstrap — 创建 Session 目录 + 输出 Dashboard URL。

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

from pes_controller.protocol import atomic_read, atomic_write
from pes_controller import PESController, PHASE_INTAKE
from plugins.reporting.vault_manager import SessionStore


def bootstrap(research_topic: str, project_dir: str) -> dict:
    """创建完整 pipeline session: 目录树 + PESController + Dashboard URL。"""
    proj = Path(project_dir).resolve()

    # 1. 生成 session_id + 创建 session 目录
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    session_dir = proj / "sessions" / session_id
    store = SessionStore(session_dir)
    store.init_dirs(session_id, research_topic)

    # 2. PESController init (CC + Grid + PIPELINE_STATE)
    ctrl = PESController(str(session_dir), session_id=session_id)
    ctrl.init(research_topic=research_topic)

    # 3. 写入 PIPELINE_STATE (含 DomainConfig)
    state = atomic_read(session_dir / "PIPELINE_STATE.json")
    state["session_id"] = session_id
    state["agent_session_id"] = session_id
    state["session_dir"] = str(session_dir)
    state["research_topic"] = research_topic
    state["status"] = "in_progress"

    # Detect domain from research topic keywords and load DomainConfig preset
    try:
        from plugins.ideation.domain_presets import get_domain_preset
        topic_lower = research_topic.lower()
        # Normalize: replace hyphens/underscores with spaces for flexible matching
        topic_normalized = topic_lower.replace("-", " ").replace("_", " ")
        # Simple keyword-based domain detection
        if any(kw.replace("-", " ") in topic_normalized for kw in [
            "reinforcement learning", "rl", "actor-critic", "actor critic",
            "policy gradient", "q-learning", "deep rl", "continuous control",
            "model-free", "model-based rl", "exploration", "reward function",
            "markov decision", "mdp",
        ]):
            domain_name = "reinforcement_learning"
        elif any(kw.replace("-", " ") in topic_normalized for kw in [
            "classification", "regression", "supervised", "imagenet", "cifar", "mnist",
        ]):
            domain_name = "supervised_learning"
        elif any(kw.replace("-", " ") in topic_normalized for kw in [
            "protein", "genome", "biology", "cell", "dna", "rna", "molecule",
        ]):
            domain_name = "biology_simulation"
        else:
            domain_name = "general"
        state["domain_name"] = domain_name
        state["domain_config"] = get_domain_preset(domain_name)
    except ImportError:
        state["domain_name"] = "general"
        state["domain_config"] = {}

    atomic_write(session_dir / "PIPELINE_STATE.json", state)

    dashboard_url = (
        f"http://localhost:8420/sessions/{session_id}/pipeline"
        f"?workspace={urllib.parse.quote(str(session_dir))}"
    )

    # 4. 注册 session 到 .evo_sessions/
    session_data = {
        "session_id": session_id,
        "workspace_dir": str(session_dir),
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
        "phase": state.get("phase", PHASE_INTAKE),
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
    print(f"phase:         {result['phase']}")
    print(f"dashboard_url: {result['dashboard_url']}")
    print()
    print("=" * 48)
    print("Pipeline 已就绪。请在浏览器中打开:")
    print(f"  {result['dashboard_url']}")
    print("后续所有操作都在 Dashboard 网页端完成。")
    print("=" * 48)


if __name__ == "__main__":
    main()
