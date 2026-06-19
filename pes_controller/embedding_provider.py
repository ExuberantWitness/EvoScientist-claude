"""Embedding provider — BGE-M3 本地 / API / LLM 语义指纹。

三种 provider:
  1. BGEM3Provider     — 本地 BGE-M3 (FlagEmbedding), 1024-dim, 需 GPU
  2. APIEmbeddingProvider — /v1/embeddings 端点, 任意 OpenAI 兼容 provider
  3. LLMEmbeddingProvider — DeepSeek Chat API 生成 64-dim 语义指纹, 无需本地模型

用法:
  provider = get_embedding_provider()
  vecs = provider.encode(["hello", "world"])  # np.ndarray (N, D)

环境变量:
  EMBEDDING_PROVIDER  — "bge_m3" | "api" | "llm" | "" (auto-detect)
  EMBEDDING_API_KEY   — API key (default: DEEPSEEK_API_KEY)
  EMBEDDING_BASE_URL  — API base URL (default: DEEPSEEK_BASE_URL)
  EMBEDDING_MODEL     — model name (default: deepseek-chat)
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts → (N, D) float32 ndarray."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class BGEM3Provider(EmbeddingProvider):
    """本地 BGE-M3 via FlagEmbedding (requires pip install FlagEmbedding)."""

    _MODEL_NAME = "BAAI/bge-m3"
    _MODELSCOPE_CACHE = Path.home() / ".cache" / "modelscope" / "BAAI" / "bge-m3"

    def __init__(self):
        from FlagEmbedding import BGEM3FlagModel

        if self._MODELSCOPE_CACHE.exists():
            model_path = str(self._MODELSCOPE_CACHE)
        else:
            model_path = self._MODEL_NAME
        logger.info("Loading BGE-M3 from %s", model_path)
        self._model = BGEM3FlagModel(model_path, use_fp16=True)
        logger.info("BGE-M3 loaded (dim=1024)")

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)
        out = self._model.encode(texts, return_dense=True, batch_size=32)
        vecs = out["dense_vecs"]
        if isinstance(vecs, list):
            vecs = np.array(vecs, dtype=np.float32)
        return vecs

    @property
    def dimension(self) -> int:
        return 1024

    @property
    def name(self) -> str:
        return "bge-m3"


class APIEmbeddingProvider(EmbeddingProvider):
    """OpenAI SDK /v1/embeddings — works with any compatible endpoint."""

    def __init__(self, api_key: str, base_url: str, model: str):
        import os
        from openai import OpenAI
        os.environ.setdefault("NO_PROXY", "*")
        os.environ.setdefault("no_proxy", "*")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._base_url = base_url
        self._dim: int | None = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        all_embs: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self.client.embeddings.create(model=self._model, input=batch)
            for item in resp.data:
                all_embs.append(item.embedding)
        arr = np.array(all_embs, dtype=np.float32)
        if self._dim is None:
            self._dim = arr.shape[1]
        return arr

    @property
    def dimension(self) -> int:
        if self._dim is None:
            raise RuntimeError(
                "Embedding dimension unknown — call encode() first. "
                "If this fails, the API endpoint may not support /v1/embeddings."
            )
        return self._dim

    @property
    def name(self) -> str:
        return f"api:{self._model}"


# ---------------------------------------------------------------------------
# LLM Semantic Fingerprint — DeepSeek Chat API 生成 64-dim 向量
# ---------------------------------------------------------------------------

_DIM = 64

_SYSTEM_PROMPT = """You are a semantic encoder that converts text into a 64-dimensional vector for similarity search.

CRITICAL: Texts about SIMILAR topics MUST get SIMILAR vectors (high cosine similarity). Texts about DIFFERENT topics MUST get DIFFERENT vectors.

The 64 dimensions encode:
- Dims 0-15: Domain (RL, NLP, CV, robotics, optimization, systems, theory, etc.)
- Dims 16-31: Methodology (theoretical, empirical, simulation, analytical, survey, etc.)
- Dims 32-47: Technique (policy gradient, attention, CNN, Bayesian, evolutionary, etc.)
- Dims 48-63: Object-level (algorithm, architecture, dataset, metric, application, etc.)

Rules:
- Output ONLY a JSON array of 64 floats between -1.0 and 1.0
- Be CONSISTENT: same topic = same pattern regardless of wording
- RL algorithms (PPO, SAC, DQN, TD3) MUST cluster together
- NLP models (BERT, GPT, T5) MUST cluster together
- Test your output: would cosine_sim(PPO_text, DQN_text) > cosine_sim(PPO_text, BERT_text)?"""

_SINGLE_PROMPT = """Encode this text into a 64-dim semantic vector.
Output ONLY a JSON array of 64 floats.

Text:
{text}"""

_BATCH_PROMPT = """Encode each of the following {count} texts into 64-dim semantic vectors.
Output ONLY a JSON array of arrays (one inner array per text).

Texts:
{texts}"""


class LLMEmbeddingProvider(EmbeddingProvider):
    """Uses LLM chat API (DeepSeek) to generate 64-dim semantic fingerprint vectors.

    No local model or GPU needed. Works with any OpenAI-compatible chat endpoint.
    Supports batching (up to 5 texts per API call) to reduce cost.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        import os
        from openai import OpenAI
        os.environ.setdefault("NO_PROXY", "*")
        os.environ.setdefault("no_proxy", "*")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._base_url = base_url
        self._cache: dict[str, list[float]] = {}

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, _DIM), dtype=np.float32)

        results: list[list[float]] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        # Check cache
        for i, t in enumerate(texts):
            key = t[:500]
            if key in self._cache:
                results.append(self._cache[key])
            else:
                results.append([])
                uncached_indices.append(i)
                uncached_texts.append(t)

        # Batch encode uncached texts
        if uncached_texts:
            batch_results = self._batch_encode(uncached_texts)
            for j, (idx, vec) in enumerate(zip(uncached_indices, batch_results)):
                results[idx] = vec
                key = uncached_texts[j][:500]
                self._cache[key] = vec

        return np.array(results, dtype=np.float32)

    def _batch_encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts one-by-one via LLM chat API for best consistency."""
        all_vecs: list[list[float]] = []
        for text in texts:
            vecs = self._call_llm([text])
            all_vecs.extend(vecs)
        return all_vecs

    def _call_llm(self, texts: list[str]) -> list[list[float]]:
        """Call LLM and parse 64-dim vectors from response."""
        if len(texts) == 1:
            user_msg = _SINGLE_PROMPT.format(text=texts[0][:3000])
        else:
            numbered = "\n".join(f"{i+1}. {t[:500]}" for i, t in enumerate(texts))
            user_msg = _BATCH_PROMPT.format(count=len(texts), texts=numbered)

        try:
            resp = self.client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_completion_tokens=4096,
                temperature=0.0,
            )
            content = resp.choices[0].message.content or ""
            return self._parse_vectors(content, len(texts))
        except Exception as e:
            logger.warning("LLM embedding call failed: %s", e)
            return [self._zero_vector() for _ in texts]

    def _parse_vectors(self, content: str, expected: int) -> list[list[float]]:
        """Parse JSON array(s) from LLM response."""
        content = content.strip()

        # Try to extract JSON from code block
        if "```" in content:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                content = content[start:end]

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM embedding response")
            return [self._zero_vector() for _ in range(expected)]

        # Single text → single array
        if isinstance(parsed, list) and len(parsed) > 0:
            if isinstance(parsed[0], (int, float)):
                # Single vector: [0.1, 0.2, ...]
                vec = self._normalize(parsed[:_DIM])
                return [vec]
            elif isinstance(parsed[0], list):
                # Multiple vectors: [[0.1, ...], [0.2, ...]]
                return [self._normalize(v[:_DIM]) for v in parsed[:expected]]

        return [self._zero_vector() for _ in range(expected)]

    @staticmethod
    def _normalize(vals: list) -> list[float]:
        """Normalize to exactly _DIM dimensions, L2-normalize."""
        vec = [float(v) for v in vals]
        # Pad or truncate
        if len(vec) < _DIM:
            vec.extend([0.0] * (_DIM - len(vec)))
        vec = vec[:_DIM]
        # Clamp to [-1, 1]
        vec = [max(-1.0, min(1.0, v)) for v in vec]
        # L2 normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 1e-8:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def _zero_vector() -> list[float]:
        return [0.0] * _DIM

    @property
    def dimension(self) -> int:
        return _DIM

    @property
    def name(self) -> str:
        return f"llm:{self._model}"


# ── Provider factory ──

_cached_provider: EmbeddingProvider | None = None


def get_embedding_provider(force: str = "") -> EmbeddingProvider | None:
    """Get best available embedding provider.

    Args:
        force: "bge_m3" | "api" | "llm" to force a specific provider, "" for auto-detect.
    """
    global _cached_provider
    if _cached_provider is not None and not force:
        return _cached_provider

    provider: EmbeddingProvider | None = None

    if force == "api":
        provider = _try_api_provider()
    elif force == "llm":
        provider = _try_llm_provider()
    elif force == "bge_m3":
        provider = _try_bge_provider()
    else:
        pref = os.environ.get("EMBEDDING_PROVIDER", "")
        if pref == "api":
            provider = _try_api_provider() or _try_llm_provider()
        elif pref == "llm":
            provider = _try_llm_provider()
        elif pref == "bge_m3":
            provider = _try_bge_provider() or _try_llm_provider()
        else:
            provider = _try_bge_provider() or _try_llm_provider()

    if provider is not None:
        _cached_provider = provider
        logger.info("Embedding provider: %s", provider.name)
    else:
        logger.warning("No embedding provider available")
    return provider


def reset_provider():
    """Reset cached provider (e.g. after user changes config)."""
    global _cached_provider
    _cached_provider = None


def _try_bge_provider() -> EmbeddingProvider | None:
    try:
        return BGEM3Provider()
    except ImportError:
        logger.info("FlagEmbedding not installed, skipping BGE-M3")
    except Exception as e:
        logger.warning("BGE-M3 init failed: %s", e)
    return None


def _try_api_provider() -> EmbeddingProvider | None:
    api_key = os.environ.get("EMBEDDING_API_KEY", "")
    base_url = os.environ.get("EMBEDDING_BASE_URL", "")
    model = os.environ.get("EMBEDDING_MODEL", "")

    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not base_url:
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not model:
        model = os.environ.get("EMBEDDING_MODEL", "deepseek-chat")

    if not api_key:
        return None

    try:
        return APIEmbeddingProvider(api_key=api_key, base_url=base_url, model=model)
    except Exception as e:
        logger.warning("API embedding provider init failed: %s", e)
    return None


def _try_llm_provider() -> EmbeddingProvider | None:
    api_key = os.environ.get("EMBEDDING_API_KEY", "")
    base_url = os.environ.get("EMBEDDING_BASE_URL", "")
    model = os.environ.get("EMBEDDING_MODEL", "")

    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not base_url:
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not model:
        model = os.environ.get("EMBEDDING_MODEL", "deepseek-chat")

    if not api_key:
        logger.warning("No API key for LLM embedding provider")
        return None

    try:
        return LLMEmbeddingProvider(api_key=api_key, base_url=base_url, model=model)
    except Exception as e:
        logger.warning("LLM embedding provider init failed: %s", e)
    return None
