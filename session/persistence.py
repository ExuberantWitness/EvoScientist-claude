"""OpenRath-style JSONL WAL session persistence.

Write-Ahead Log format with atomic rename for crash durability:
  {session_id}.jsonl.__partial__  →  {session_id}.jsonl  (on close)

Record types:
  header  — session metadata (schema_version, id, parent_session_ids, etc.)
  chunk   — conversation turn (prompt + response)
  trailer — closure metadata (closed_at, final_chunk_count, status)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1


# ── Data types ──

@dataclass
class PersistedSession:
    """Deserialized session from JSONL WAL file."""
    header: dict
    chunks: list[dict]
    trailer: dict | None
    closed: bool
    file_path: Path


# ── Writer ──

class SessionWriter:
    """Append-only JSONL WAL writer. Writes to .__partial__, renames to .jsonl on close."""

    def __init__(self, file_path: Path) -> None:
        self._partial_path = Path(str(file_path) + ".__partial__")
        self._final_path = file_path
        self._partial_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(str(self._partial_path), "w", encoding="utf-8")
        self._chunk_index = 0
        self._closed = False

    def write_header(self, session_id: str, workspace_dir: str = "",
                     parent_session_ids: list[str] | None = None,
                     model: str = "", provider: str = "",
                     metadata: dict | None = None) -> None:
        header = {
            "record_type": "header",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parent_session_ids": parent_session_ids or [],
            "model": model,
            "provider": provider,
            "metadata": metadata or {},
        }
        self._write_line(header)

    def write_chunk(self, kind: str, prompt: str = "", response: str = "",
                    parsed: dict | None = None, agent_name: str = "",
                    metadata: dict | None = None) -> None:
        chunk = {
            "record_type": "chunk",
            "index": self._chunk_index,
            "kind": kind,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": agent_name,
        }
        if prompt:
            chunk["prompt"] = prompt[:10000]
        if response:
            chunk["response"] = response[:8000]
        if parsed:
            chunk["parsed"] = parsed
        if metadata:
            chunk["metadata"] = metadata

        self._write_line(chunk)
        self._chunk_index += 1

    def write_trailer(self, status: str = "completed") -> None:
        trailer = {
            "record_type": "trailer",
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "final_chunk_count": self._chunk_index,
            "status": status,
        }
        self._write_line(trailer)

    def close(self, status: str = "completed") -> None:
        """Write trailer and atomically rename .__partial__ → .jsonl."""
        if self._closed:
            return
        self.write_trailer(status)
        self._fd.close()
        os.rename(str(self._partial_path), str(self._final_path))
        self._closed = True
        logger.info(f"Session persisted: {self._final_path} ({self._chunk_index} chunks)")

    def abandon(self) -> None:
        """Close without trailer/rename — leaves .__partial__ as crash signal."""
        if self._closed:
            return
        self._fd.close()
        self._closed = True
        logger.warning(f"Session abandoned: {self._partial_path}")

    def _write_line(self, record: dict) -> None:
        self._fd.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fd.flush()


# ── Loader ──

def load_session(file_path: Path) -> PersistedSession:
    """Parse a session JSONL file. Falls back to .__partial__ if .jsonl missing."""
    path = file_path
    if not path.exists():
        partial = Path(str(path) + ".__partial__")
        if partial.exists():
            path = partial
        else:
            raise FileNotFoundError(f"No session file found: {file_path}")

    header = None
    chunks = []
    trailer = None
    closed = False

    with open(str(path), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rt = record.get("record_type")
            if rt == "header":
                header = record
            elif rt == "chunk":
                chunks.append(record)
            elif rt == "trailer":
                trailer = record
                closed = True

    if header is None:
        raise ValueError(f"Session file missing header record: {path}")

    return PersistedSession(
        header=header,
        chunks=chunks,
        trailer=trailer,
        closed=closed,
        file_path=path,
    )


def list_persisted_sessions(sessions_dir: Path) -> list[dict]:
    """List all session headers from a sessions directory."""
    sessions = []
    if not sessions_dir.exists():
        return sessions

    for path in sessions_dir.glob("*.jsonl"):
        try:
            with open(str(path), "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    record = json.loads(first_line)
                    if record.get("record_type") == "header":
                        record["file_path"] = str(path)
                        record["closed"] = True
                        sessions.append(record)
        except Exception:
            continue

    # Also list partial (crashed) sessions
    for path in sessions_dir.glob("*.jsonl.__partial__"):
        try:
            with open(str(path), "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    record = json.loads(first_line)
                    if record.get("record_type") == "header":
                        record["file_path"] = str(path)
                        record["closed"] = False
                        sessions.append(record)
        except Exception:
            continue

    return sorted(sessions, key=lambda s: s.get("created_at", ""), reverse=True)
