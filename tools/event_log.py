"""Event Log: append-only canonical audit trail.

Phase D 核心模块. 原则:
  - Event log = canonical source of truth
  - 所有 *meta.json 是 derived snapshot, 可从 event log 完全重建
  - Conflict resolution: event log wins
  - 并发安全: payload < 4KB (Linux PIPE_BUF), 大内容走 file reference
  - schema_version 字段保证向前兼容
"""

import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1

# Valid event types
EVENT_TYPES = {
    "algo_created", "algo_status_change", "algo_linked_to_claim",
    "expt_completed", "expt_failed",
    "claim_added", "claim_relation_added", "claim_status_change",
    "island_created", "island_assigned", "island_merged",
    "bottleneck_discovered", "bottleneck_addressed", "bottleneck_resolved",
    "iteration_step_created",
    "markdown_written", "markdown_appended",
    "index_rebuilt", "snapshot_rebuilt",
    "anomaly_detected", "contradiction_found",
}


@dataclass
class Event:
    id: str
    ts: float
    schema_version: int
    session_id: str
    event_type: str
    object_type: str        # "algorithm" | "experiment" | "claim" | "bottleneck" | "island" | "iteration_step"
    object_id: str
    payload: dict           # 只放 ID + metadata (< 4KB), 大文本走 file reference
    parent_event_id: str = ""


class EventLog:
    """Append-only event log. Canonical source of truth."""

    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)
        self.path = self.session_dir / "vault" / "_index" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_materialized: dict[str, str] = {}  # {object_id: last_event_id}

    def record(self, event_type: str, object_type: str, object_id: str,
               payload: dict, *, parent_event_id: str = "",
               ts: float | None = None) -> Event:
        """追加一条 event. 返回创建的 Event."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}. Must be one of {sorted(EVENT_TYPES)}")

        event = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            ts=ts or time.time(),
            schema_version=SCHEMA_VERSION,
            session_id="",  # filled by caller if needed
            event_type=event_type,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
            parent_event_id=parent_event_id,
        )
        # Validate payload size (< 4KB for atomic append)
        payload_json = json.dumps(event.__dict__, ensure_ascii=False)
        if len(payload_json) > 4096:
            raise ValueError(f"Event payload too large ({len(payload_json)} bytes). "
                           "Max 4096 bytes for atomic append. Use file references for large content.")

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(payload_json + "\n")

        self._last_materialized[object_id] = event.id
        return event

    def query(self, *, object_id: str = "", event_type: str = "",
              object_type: str = "", since: float = 0.0,
              limit: int = 100) -> list[Event]:
        """查询 event log."""
        results = []
        if not self.path.exists():
            return results
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if object_id and data.get("object_id") != object_id:
                    continue
                if event_type and data.get("event_type") != event_type:
                    continue
                if object_type and data.get("object_type") != object_type:
                    continue
                if since and data.get("ts", 0) < since:
                    continue
                results.append(Event(**data))
                if len(results) >= limit:
                    break
        return results

    def latest_event_id(self, object_id: str) -> str:
        """返回某对象的最新 event id (乐观锁)."""
        events = self.query(object_id=object_id, limit=1)
        return events[0].id if events else ""

    def all_ids(self) -> set[str]:
        """所有 event IDs (用于 invariants 测试)."""
        ids = set()
        if not self.path.exists():
            return ids
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
        return ids

    # ── 物化视图 ──

    def materialize_algorithms(self) -> dict[str, dict]:
        """从 event log 重建所有 Algorithm 的当前状态."""
        algos = {}
        events = self.query(object_type="algorithm", limit=10000)
        for e in events:
            algo_id = e.object_id
            if algo_id not in algos:
                algos[algo_id] = {"id": algo_id, "status": "PROPOSED", "events": []}
            if e.event_type == "algo_created":
                algos[algo_id].update(e.payload)
            elif e.event_type == "algo_status_change":
                algos[algo_id]["status"] = e.payload.get("new_status", algos[algo_id]["status"])
            algos[algo_id]["events"].append(e.id)
        return algos

    def materialize_bottlenecks(self) -> dict[str, dict]:
        """从 event log 重建所有 Bottleneck 的当前状态."""
        bottlenecks = {}
        events = self.query(object_type="bottleneck", limit=10000)
        for e in events:
            bn_id = e.object_id
            if bn_id not in bottlenecks:
                bottlenecks[bn_id] = {"id": bn_id, "status": "open", "events": []}
            if e.event_type == "bottleneck_discovered":
                bottlenecks[bn_id].update(e.payload)
            elif e.event_type == "bottleneck_addressed":
                bottlenecks[bn_id]["status"] = f"addressed_by:{e.payload.get('algo_id', '')}"
            elif e.event_type == "bottleneck_resolved":
                bottlenecks[bn_id]["status"] = "resolved"
            bottlenecks[bn_id]["events"].append(e.id)
        return bottlenecks

    def get_methods_found(self) -> list[dict]:
        """物化视图: status=VALIDATED 的 Algorithm = Methods Found."""
        return [a for a in self.materialize_algorithms().values()
                if a.get("status") == "VALIDATED"]

    def get_timeline(self, limit: int = 50) -> list[dict]:
        """最近 N 条 event (时间线)."""
        return [e.__dict__ for e in self.query(limit=limit)]

    # ── 重建 ──

    def rebuild_snapshots(self) -> dict:
        """从 event log 重建所有 algo_meta.json / island_meta.json."""
        algos = self.materialize_algorithms()
        bottlenecks = self.materialize_bottlenecks()

        rebuilt = {"algorithms": 0, "bottlenecks": 0}
        for algo_id, state in algos.items():
            meta_path = self.session_dir / "vault" / "_index" / f"{algo_id}_meta.json"
            meta_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
            rebuilt["algorithms"] += 1

        for bn_id, state in bottlenecks.items():
            meta_path = self.session_dir / "vault" / "_index" / f"{bn_id}_meta.json"
            meta_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
            rebuilt["bottlenecks"] += 1

        self.record("snapshot_rebuilt", "system", "all",
                    {"algorithms": rebuilt["algorithms"],
                     "bottlenecks": rebuilt["bottlenecks"]})
        return rebuilt

    # ── Invariant 校验 ──

    def check_contradictions(self) -> list[dict]:
        """检测矛盾: 同一对节点同时有 validates 和 contradicts."""
        from markdown_parser import _read_jsonl
        relations = _read_jsonl(self.session_dir / "vault" / "_index" / "relations.jsonl")
        pairs = defaultdict(set)
        contradictions = []
        for r in relations:
            pair = (r["source_id"], r["target_id"])
            pairs[pair].add(r["type"])
            if "validates" in pairs[pair] and "contradicts" in pairs[pair]:
                contradictions.append({"pair": pair, "types": list(pairs[pair])})
        return contradictions


# ── 便捷工厂 ──

def create_event_log(session_dir: str | Path) -> EventLog:
    return EventLog(session_dir)
