"""Pipeline 7 阶段 + GoSRetriever + Pydantic Schema.

Phase E 核心模块. Graphify 风格: 每个阶段是独立 Python 函数, dict→dict.
"""

from pathlib import Path
from pydantic import BaseModel

# ── LLM Output Schemas (Pydantic) ──

class ValidatedAlgo(BaseModel):
    algorithm_id: str = ""
    score_vs_baseline: str = ""
    evidence: list[str] = []
    bottleneck_addressed: str = ""
    new_bottlenecks: list[str] = []

class RefutedAlgo(BaseModel):
    algorithm_id: str = ""
    reason: str = ""
    evidence: list[str] = []

class BottleneckDiscovered(BaseModel):
    title: str = ""
    category: str = ""
    evidence: str = ""
    affects: list[str] = []

class NextDirection(BaseModel):
    target_bottleneck: str = ""
    suggested_approach: str = ""
    priority: str = "medium"  # high|medium|low

class AnalysisOutput(BaseModel):
    validated: list[ValidatedAlgo] = []
    refuted: list[RefutedAlgo] = []
    bottlenecks_discovered: list[BottleneckDiscovered] = []
    bottlenecks_resolved: list[str] = []
    evolution_edges: list[dict] = []
    next_directions: list[NextDirection] = []


# ── GoSRetriever ──

class GoSRetriever:
    """GoS 上下文检索: 混合播种 → 反向追溯 → 上下文水合."""

    def __init__(self, session_dir: Path):
        from tools.markdown_parser import GraphQuery, EDGE_WEIGHTS, STRONG_CAUSAL
        self.session_dir = session_dir
        self.index_dir = session_dir / "vault" / "_index"
        self.gq = GraphQuery(self.index_dir)
        self.EDGE_WEIGHTS = EDGE_WEIGHTS
        self.STRONG_CAUSAL = STRONG_CAUSAL

    def seed(self, current_methods: list[str], keywords: list[str]) -> list[str]:
        """混合播种: 当前方法 + keyword search."""
        seeds = set(current_methods)
        results = self.gq.search_nodes(keywords)
        for r in results:
            seeds.add(r["id"])
        return list(seeds)

    def traceback(self, seeds: list[str], max_hops: int = 2) -> list[dict]:
        """反向追溯 parent chain + bottleneck chain."""
        from collections import defaultdict
        scores = defaultdict(float)
        reasons = defaultdict(list)

        for seed in seeds:
            scores[seed] += 2.0
            reasons[seed].append("seed")
            chain = self.gq.get_evolution_chain(seed, max_depth=max_hops)
            for edge in chain:
                w = self.EDGE_WEIGHTS.get(edge["type"], 0.3)
                scores[edge["target_id"]] += w
                reasons[edge["target_id"]].append(
                    f"{edge['type']}←{edge['source_id']} (w={w:.1f})")

        return [{"node_id": nid, "score": round(sc, 2), "reasons": reasons[nid]}
                for nid, sc in sorted(scores.items(), key=lambda x: x[1], reverse=True)
                if sc > 0.1]

    def hydrate(self, ranked: list[dict], max_tokens: int = 8000) -> str:
        """上下文水合: 高优先级全量, 中优先级摘要, 低优先级引用."""
        from tools.markdown_parser import _read_jsonl
        from tools.vault_manager import VaultManager

        atoms = _read_jsonl(self.index_dir / "atoms.jsonl")
        atom_map = {a["id"]: a for a in atoms}
        vault_mgr = VaultManager(self.session_dir)

        sections = []
        budget = max_tokens
        for item in ranked[:10]:
            if budget <= 0:
                break
            node_id = item["node_id"]
            score = item["score"]

            if score >= 1.0:  # High priority: full content
                md_file = list(vault_mgr.vault_dir.rglob(f"{node_id}.md"))
                if md_file:
                    text = md_file[0].read_text(encoding="utf-8")[:1500]
                    sections.append(f"### {node_id} (score={score})\n{text}")
                    budget -= len(text) // 3
            elif score >= 0.5:  # Medium: summary
                atom = atom_map.get(node_id, {})
                title = atom.get("title", node_id)
                tags = atom.get("tags", [])
                status = atom.get("status", "")
                sections.append(f"- {node_id}: {title} [status={status}, tags={tags}]"[:200])
            else:  # Low: reference only
                sections.append(f"- ref: [[{node_id}]]")

        return "\n\n".join(sections)


# ── 7 Pipeline Stages (Graphify style: dict→dict, no global state) ──

def stage1_gather(session_dir: Path, code_results: list[dict]) -> dict:
    """GATHER: 读 code_results + event log → 结构化 context bundle."""
    from tools.event_log import EventLog
    el = EventLog(session_dir)
    expts = el.query(event_type="expt_completed", limit=20)
    return {
        "experiments": [e.payload for e in expts],
        "code_results": code_results,
        "session_dir": str(session_dir),
    }

def stage2_seed(context: dict) -> dict:
    """SEED: GoS 混合播种 → 反向追溯 → prompt 构造."""
    session_dir = Path(context["session_dir"])
    retriever = GoSRetriever(session_dir)
    exp_algos = [e.get("algo_id", "") for e in context["experiments"]]
    keywords = ["rl", "actor-critic", "hopper"]  # from research topic
    seeds = retriever.seed(exp_algos, keywords)
    ranked = retriever.traceback(seeds)
    hydrated = retriever.hydrate(ranked)
    context["prompt"] = hydrated
    context["ranked_nodes"] = ranked
    return context

def stage3_parse(transcript: str) -> dict:
    """PARSE: Pydantic 解析 → 置信度赋值."""
    import json
    try:
        data = json.loads(transcript)
        output = AnalysisOutput.model_validate(data)
        return {"conclusions": output.model_dump(), "rejected": [], "error": ""}
    except Exception as e:
        return {"conclusions": None, "rejected": [], "error": str(e)}

def stage4_write(conclusions: dict, session_dir: Path, event_log) -> dict:
    """WRITE: CC atoms/relations + 状态机推进."""
    written = {"atoms": 0, "relations": 0, "status_changes": 0}
    if not conclusions.get("validated"):
        return written
    # Status changes
    for v in conclusions.get("validated", []):
        event_log.record("algo_status_change", "algorithm", v["algorithm_id"],
                        {"old_status": "TESTED", "new_status": "VALIDATED"})
        written["status_changes"] += 1
    for r in conclusions.get("refuted", []):
        event_log.record("algo_status_change", "algorithm", r["algorithm_id"],
                        {"old_status": "TESTED", "new_status": "REFUTED"})
        written["status_changes"] += 1
    return written

def stage5_delta_prep(conclusions: dict, session_dir: Path) -> dict:
    """DELTA+PREP: 写 delta.json + 构建下次种子."""
    delta = {
        "new_algos": [], "experiments": [],
        "claim_changes": conclusions,
        "dead_ends": conclusions.get("refuted", []),
        "open_problems": conclusions.get("bottlenecks_discovered", []),
    }
    delta_path = session_dir / "vault" / "_pipeline" / "delta_latest.json"
    import json
    delta_path.write_text(json.dumps(delta, indent=2, ensure_ascii=False))
    return delta
