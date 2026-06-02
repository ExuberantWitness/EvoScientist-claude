"""Experiment Recorder: Agent 调用此 tool 记录实验结果.

Phase H 核心模块. 替代所有散文 parser.
Agent 不直接写文件 — 调这个 tool, Python 做参数校验 + 写 event + 更新 Markdown.
"""

import json
import time
from datetime import datetime
from pathlib import Path

try:
    from tools.event_log import EventLog, create_event_log
    from tools.vault_manager import VaultManager
except ImportError:
    from event_log import EventLog, create_event_log
    from vault_manager import VaultManager

# 状态机转换表
VALID_TRANSITIONS = {
    "PROPOSED":    {"IMPLEMENTED"},
    "IMPLEMENTED": {"TESTED"},
    "TESTED":      {"VALIDATED", "REFUTED"},
    "REFUTED":     {"ARCHIVED"},
    "VALIDATED":   {"ARCHIVED"},
}


class InvalidTransition(Exception):
    pass


# 状态顺序: 用于判断是否允许“重入”
STATUS_ORDER = ["PROPOSED", "IMPLEMENTED", "TESTED", "VALIDATED", "REFUTED", "ARCHIVED"]


def transition_algo(algo_id: str, new_status: str, event_log: EventLog) -> str:
    """推进算法状态机 (Python 校验).

    如果当前状态已经 >= 目标状态, 跳过 (幂等).
    """
    algos = event_log.materialize_algorithms()
    current = algos.get(algo_id, {}).get("status", "PROPOSED")
    if current == new_status:
        return current  # 幂等
    if current in STATUS_ORDER and new_status in STATUS_ORDER:
        if STATUS_ORDER.index(current) >= STATUS_ORDER.index(new_status):
            return current  # 已经超过目标, 不倒退
    if new_status not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Invalid transition: {current} → {new_status}")
    event_log.record("algo_status_change", "algorithm", algo_id,
                    {"old_status": current, "new_status": new_status})
    return new_status


def record_experiment_result(
    session_dir: str,
    algo_id: str,
    env: str,
    score_mean: float,
    score_std: float,
    seeds: int = 3,
    code_path: str = "",
    success: bool = True,
    extra_notes: str = "",
) -> dict:
    """Agent 调用此 tool 记录实验结果. Python 校验 + 写 event + 更新 Markdown.

    Args:
        session_dir: session 目录 (如 /.../sessions/sess_xxx)
        algo_id: 算法 ID (如 "emtd3")
        env: 环境名 (如 "Hopper-v4")
        score_mean: 平均分数
        score_std: 标准差
        seeds: 种子数
        code_path: 代码路径
        success: 实验是否成功
        extra_notes: 额外备注
    """
    session_path = Path(session_dir)
    el = create_event_log(session_path)

    # 1. 校验
    if score_std < 0:
        raise ValueError(f"score_std must be non-negative, got {score_std}")
    if seeds < 1:
        raise ValueError(f"seeds must be >= 1, got {seeds}")

    # 1.5 从 Markdown frontmatter 同步现有状态 (如 event log 中无记录)
    try:
        from tools.markdown_parser import parse_frontmatter
    except ImportError:
        from markdown_parser import parse_frontmatter
    algo_file = session_path / "Algorithms" / f"{algo_id}.md"
    current_status = "PROPOSED"
    if algo_file.exists():
        meta = parse_frontmatter(algo_file.read_text(encoding="utf-8"))
        current_status = meta.get("status", "PROPOSED")
    algos = el.materialize_algorithms()
    if algo_id not in algos:
        el.record("algo_created", "algorithm", algo_id,
                 {"name": algo_id, "status": current_status})
    # Bridge: if event log is behind Markdown, skip ahead (idempotent)
    materialized = algos.get(algo_id, {})
    mat_status = materialized.get("status", "PROPOSED")
    if mat_status in STATUS_ORDER and current_status in STATUS_ORDER:
        for i in range(STATUS_ORDER.index(mat_status),
                       min(STATUS_ORDER.index(current_status), STATUS_ORDER.index("TESTED"))):
            nxt = STATUS_ORDER[i+1]
            if nxt not in VALID_TRANSITIONS.get(STATUS_ORDER[i], set()):
                continue
            try:
                transition_algo(algo_id, nxt, el)
            except InvalidTransition:
                pass

    # 2. 算法状态推进
    try:
        transition_algo(algo_id, "TESTED", el)
    except InvalidTransition:
        pass  # already tested or beyond

    # 3. 记录 experiment event
    expt_id = f"exp_{algo_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    el.record("expt_completed", "experiment", expt_id, {
        "algo_id": algo_id, "env": env, "seeds": seeds,
        "score_mean": score_mean, "score_std": score_std,
        "code_path": code_path, "success": success,
        "extra_notes": extra_notes,
    })

    # 4. 根据结果推进算法状态
    new_status = "VALIDATED" if success else "REFUTED"
    transition_algo(algo_id, new_status, el)

    # 5. 更新 Markdown (实验历史段, 只追加)
    algo_file = session_path / "Algorithms" / f"{algo_id}.md"
    if algo_file.exists():
        append_experiment_to_markdown(algo_file, {
            "algo_id": algo_id, "env": env, "seeds": seeds,
            "score_mean": score_mean, "score_std": score_std,
            "success": success, "extra_notes": extra_notes,
        })

    # 6. 同步到 Claim Chain (cc.db)
    cc_result = _sync_experiment_to_cc(session_path, algo_id, env, score_mean, score_std,
                                        seeds, code_path, success, extra_notes)

    return {
        "experiment_id": expt_id,
        "algo_id": algo_id,
        "new_status": new_status,
        "score": f"{score_mean:.1f}±{score_std:.1f}",
        "cc_synced": cc_result,
    }


def _sync_experiment_to_cc(session_path: Path, algo_id: str, env: str,
                            score_mean: float, score_std: float, seeds: int,
                            code_path: str, success: bool, extra_notes: str) -> dict:
    """Write experiment result to Claim Chain (cc.db)."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from claim_chain.chain import ClaimChainV2
    except Exception:
        return {"synced": False, "error": "Cannot import ClaimChainV2"}

    # Read iteration/phase from PIPELINE_STATE for temporal metadata
    iter_num = 0
    current_phase = "W5 代码实现"
    ps_path = session_path / "PIPELINE_STATE.json"
    if ps_path.exists():
        try:
            ps = json.loads(ps_path.read_text(encoding="utf-8"))
            iter_num = ps.get("iteration", 0)
            current_phase = ps.get("phase", current_phase)
        except Exception:
            pass

    idx_dir = session_path / "_index"
    vault_idx = session_path / "vault" / "_index"
    db_path = None
    for d in [idx_dir, vault_idx]:
        candidate = d / "cc.db"
        if candidate.exists():
            db_path = candidate
            break

    if not db_path:
        idx_dir.mkdir(parents=True, exist_ok=True)
        db_path = idx_dir / "cc.db"

    try:
        cc = ClaimChainV2(db_path)
    except Exception as e:
        return {"synced": False, "error": f"Cannot open CC: {e}"}

    try:
        existing = cc.get_atoms()
        status = "validated" if success else "refuted"
        tags = ["experiment", algo_id, status]
        content = json.dumps({
            "score_mean": score_mean, "score_std": score_std,
            "seeds": seeds, "env": env, "status": status, "success": success,
        }, ensure_ascii=False)
        title = f"Experiment: {algo_id}"
        exp_meta = {"iter": iter_num, "phase": current_phase,
                    "created_at_iso": datetime.now().isoformat(),
                    "algo_id": algo_id, "env": env}

        matched_atom = None
        for a in existing:
            if a.get("title") == title or a.get("title", "").startswith(f"Experiment: {algo_id}"):
                matched_atom = a
                break

        exp_atom_id = None
        if matched_atom:
            exp_atom_id = matched_atom["id"]
            existing_meta = matched_atom.get("metadata", {})
            existing_meta.update(exp_meta)
            existing_meta["updated_at_iso"] = datetime.now().isoformat()
            cc.conn.execute(
                "UPDATE nodes SET content=?, tags=?, status=?, summary=?, metadata=?, embedding=NULL WHERE id=?",
                (content, json.dumps(tags), status, f"{title}: {score_mean:.1f}±{score_std:.1f}",
                 json.dumps(existing_meta, ensure_ascii=False), exp_atom_id),
            )
        else:
            import uuid, time as _time
            exp_atom_id = f"node_{int(_time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
            from datetime import timezone
            now = datetime.now(timezone.utc).isoformat()
            cc.conn.execute(
                "INSERT INTO nodes (id, title, type, summary, created_at, content, tags, status, metadata, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (exp_atom_id, title, "method", f"{title}: {score_mean:.1f}±{score_std:.1f}",
                 now, content, json.dumps(tags), status,
                 json.dumps(exp_meta, ensure_ascii=False)),
            )

        cc.commit()

        # 查找匹配的 proposal/baseline atom 并建立 validates 边
        edges_created = 0
        for a in existing:
            a_title = a.get("title", "").lower()
            a_tags = a.get("tags", [])
            # 精确匹配 algo_id
            if algo_id.lower() == a_title or algo_id.lower() in a_title:
                if a["id"] != exp_atom_id:
                    try:
                        cc.add_relation(exp_atom_id, a["id"], "validates",
                                        evidence=f"score={score_mean:.1f}±{score_std:.1f}, seeds={seeds}",
                                        metadata={"algo_id": algo_id, "status": status})
                        edges_created += 1
                    except Exception:
                        pass
            # 模糊匹配：algo_id 片段在 proposal 标题中
            elif "proposal" in a_tags and len(algo_id) >= 4:
                for kw in [algo_id.lower(), algo_id.replace("_", "").lower()]:
                    if kw in a_title.replace(" ", "").replace("-", ""):
                        try:
                            cc.add_relation(exp_atom_id, a["id"], "validates",
                                            evidence=f"score={score_mean:.1f}±{score_std:.1f}, seeds={seeds}",
                                            metadata={"algo_id": algo_id, "status": status})
                            edges_created += 1
                            break
                        except Exception:
                            pass

        cc.commit()
        cc.close()
        return {"synced": True, "atom_id": exp_atom_id, "edges_created": edges_created}
    except Exception as e:
        try:
            cc.close()
        except Exception:
            pass
        return {"synced": False, "error": str(e)}


def append_experiment_to_markdown(md_path: Path, result: dict):
    """在 Markdown 文件的 '实验历史' 段追加新结果."""
    text = md_path.read_text(encoding="utf-8")
    date_str = datetime.now().strftime("%Y-%m-%d")
    entry = (
        f"\n### {date_str}: {result['env']} ({result['seeds']} seeds, test)\n"
        f"- score: {result['score_mean']:.1f} ± {result['score_std']:.1f}\n"
    )
    if result.get("extra_notes"):
        entry += f"- 备注: {result['extra_notes']}\n"
    if result.get("success"):
        entry += f"- 状态: ✅ VALIDATED\n"

    if "## 实验历史" in text:
        # Append after the section header
        text = text.rstrip() + entry
    else:
        # Add section before end
        text = text.rstrip() + f"\n\n## 实验历史 (只追加, 不修改)\n{entry}"

    md_path.write_text(text, encoding="utf-8")
