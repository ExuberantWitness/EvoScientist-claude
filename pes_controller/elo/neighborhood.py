"""RND (Relative Neighbor Density) evaluator based on arxiv 2503.01508.

Implements the exact algorithm from the paper:
- Embedding: BGE-M3 (M3-Embedding), 1024-dim, cosine distance
- ND(v) = mean(cosine_dist to Q nearest neighbors)
- RND_score = percentile_rank(ND_idea among P neighbors' NDs)
- P=100, Q=50 (paper's empirical optimal)
- Low RND = sparse region = more novel

Knowledge space persisted as session_dir/_index/rnd_kb.jsonl
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants from the paper
# ---------------------------------------------------------------------------
P_NEIGHBORS = 100   # number of nearest neighbors of the idea
Q_NEIGHBORS = 50     # number of nearest neighbors for density computation
EMBED_DIM = 1024


class RNDEvaluator:
    """BGE-M3 embedding + RND computation (paper algorithm)."""

    def __init__(self, kb_path: Path | str | None = None):
        self._kb_path = Path(kb_path) if kb_path else None
        self._model = None  # lazy-init BGE-M3
        self._entries: list[dict] = []        # [{text, embedding, ...}]
        self._embeddings: np.ndarray | None = None  # (N, 1024) cache
        self._dirty = False

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    _MODEL_NAME = "BAAI/bge-m3"
    _MODELSCOPE_CACHE = Path.home() / ".cache" / "modelscope" / "BAAI" / "bge-m3"

    @property
    def model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            # Try ModelScope local cache first, fall back to HuggingFace
            if self._MODELSCOPE_CACHE.exists():
                model_path = str(self._MODELSCOPE_CACHE)
                logger.info(f"Loading BGE-M3 from ModelScope cache: {model_path}")
            else:
                model_path = self._MODEL_NAME
                logger.info(f"Loading BGE-M3 from HuggingFace: {model_path}")
            self._model = BGEM3FlagModel(model_path, use_fp16=True)
        return self._model

    def _encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts to BGE-M3 dense embeddings (1024-dim)."""
        if not texts:
            return np.empty((0, EMBED_DIM), dtype=np.float32)
        out = self.model.encode(texts, return_dense=True, batch_size=32)
        vecs = out["dense_vecs"]
        if isinstance(vecs, list):
            vecs = np.array(vecs, dtype=np.float32)
        return vecs

    # ------------------------------------------------------------------
    # Knowledge space
    # ------------------------------------------------------------------

    def add(self, text: str, source_type: str = "", metadata: dict | None = None) -> None:
        """Embed a piece of knowledge and add to the space."""
        if not text or not text.strip():
            return
        emb = self._encode([text])[0]
        entry = {
            "id": f"kb_{int(time.time()*1000)}_{len(self._entries)}",
            "text": text[:1000000],
            "embedding": emb.tolist(),
            "source_type": source_type,
            "metadata": metadata or {},
        }
        self._entries.append(entry)
        self._embeddings = None  # invalidate cache
        self._dirty = True

    def add_batch(self, items: list[dict]) -> None:
        """Batch-add knowledge items. Each: {text, source_type, metadata}."""
        if not items:
            return
        texts = [it["text"] for it in items if it.get("text", "").strip()]
        if not texts:
            return
        embs = self._encode(texts)
        for i, it in enumerate(items):
            if not it.get("text", "").strip():
                continue
            self._entries.append({
                "id": f"kb_{int(time.time()*1000)}_{len(self._entries)}",
                "text": it["text"][:1000000],
                "embedding": embs[i].tolist(),
                "source_type": it.get("source_type", ""),
                "metadata": it.get("metadata", {}),
            })
        self._embeddings = None
        self._dirty = True

    def _rebuild_cache(self) -> None:
        if self._embeddings is not None:
            return
        n = len(self._entries)
        if n == 0:
            self._embeddings = np.empty((0, EMBED_DIM), dtype=np.float32)
            return
        arr = np.zeros((n, EMBED_DIM), dtype=np.float32)
        for i, e in enumerate(self._entries):
            emb = e.get("embedding")
            if emb is not None and len(emb) == EMBED_DIM:
                arr[i] = np.array(emb, dtype=np.float32)
        self._embeddings = arr

    @property
    def size(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        if self._kb_path is None:
            return
        self._kb_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._kb_path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._dirty = False
        logger.info(f"RND KB saved: {len(self._entries)} entries -> {self._kb_path}")

    def load(self) -> None:
        if self._kb_path is None or not self._kb_path.exists():
            return
        loaded = []
        with open(self._kb_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    loaded.append(json.loads(line))
        self._entries = loaded
        self._embeddings = None
        self._dirty = False
        logger.info(f"RND KB loaded: {len(self._entries)} entries")

    # ------------------------------------------------------------------
    # RND Algorithm (paper §3.3)
    # ------------------------------------------------------------------

    def compute_rnd(self, proposal_text: str) -> dict:
        """Compute RND score for a proposal.

        Returns:
            {rnd, novelty_coarse, nearest_neighbors: [{text, source_type, distance}]}
        """
        # Step 1: embed the proposal
        proposal_emb = self._encode([proposal_text])[0]
        return self._compute_rnd_from_embedding(proposal_emb)

    def compute_rnd_batch(self, proposals: list[dict]) -> list[dict]:
        """Compute RND for multiple proposals. Each dict needs 'method_sketch' or 'text'."""
        texts = [p.get("method_sketch", p.get("text", ""))[:1000000] for p in proposals]
        embs = self._encode(texts)
        results = []
        for i, p in enumerate(proposals):
            r = self._compute_rnd_from_embedding(embs[i])
            r["proposal_title"] = p.get("title", "")[:80]
            results.append(r)
        return results

    def _compute_rnd_from_embedding(self, proposal_emb: np.ndarray) -> dict:
        """Core RND algorithm."""
        self._rebuild_cache()
        n_total = len(self._entries)

        if n_total == 0:
            # No knowledge yet -> neutral
            return {"rnd": 50.0, "novelty_coarse": 0.5,
                    "nearest_neighbors": [], "note": "empty_kb"}

        # --- find P nearest neighbors of the proposal ---
        p_actual = min(P_NEIGHBORS, n_total)
        distances_full = _cosine_distances(proposal_emb, self._embeddings)
        p_indices = np.argpartition(distances_full, p_actual - 1)[:p_actual]
        p_indices = p_indices[np.argsort(distances_full[p_indices])]

        # --- compute ND for the proposal: mean cosine_dist to its Q nearest ---
        q_actual = min(Q_NEIGHBORS, n_total)
        q_indices_proposal = np.argpartition(distances_full, q_actual - 1)[:q_actual]
        nd_proposal = float(np.mean(distances_full[q_indices_proposal]))

        # --- compute ND for each of the P neighbors ---
        neighbor_nds = []
        for idx in p_indices:
            neighbor_emb = self._embeddings[idx]
            dists_n = _cosine_distances(neighbor_emb, self._embeddings)
            # exclude self
            dists_n[idx] = float("inf")
            q_actual_n = min(Q_NEIGHBORS, n_total - 1)
            q_idx_n = np.argpartition(dists_n, q_actual_n - 1)[:q_actual_n]
            neighbor_nds.append(float(np.mean(dists_n[q_idx_n])))

        # --- RND = percentile rank of proposal's ND among neighbor NDs ---
        # Lower = more novel
        nds_arr = np.array(neighbor_nds)
        count_le = int(np.sum(nds_arr <= nd_proposal))
        rnd = (count_le / p_actual) * 100.0

        # RND: higher = sparser = more novel. Normalize to 0-1.
        novelty_coarse = rnd / 100.0

        # Collect nearest neighbors for context
        nearest = []
        for idx in p_indices[:5]:
            entry = self._entries[idx]
            nearest.append({
                "text": entry["text"][:300],
                "source_type": entry.get("source_type", ""),
                "distance": float(distances_full[idx]),
            })

        return {
            "rnd": round(rnd, 2),
            "novelty_coarse": round(novelty_coarse, 4),
            "nd_proposal": round(nd_proposal, 6),
            "nearest_neighbors": nearest,
            "p_actual": p_actual,
            "q_actual": q_actual,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine_distances(query: np.ndarray, db: np.ndarray) -> np.ndarray:
    """Cosine distance = 1 - cosine_similarity. query: (D,), db: (N, D) -> (N,)"""
    query_norm = query / (np.linalg.norm(query) + 1e-8)
    db_norm = db / (np.linalg.norm(db, axis=1, keepdims=True) + 1e-8)
    sim = np.dot(db_norm, query_norm)
    return 1.0 - sim
