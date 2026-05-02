"""LLM-based article quality evaluation.

Replaces the naive length-based eval_score with multi-criteria quality scoring
via LLM judge, with heuristic fallback.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """\
You are a research article quality evaluator. Rate the article on 5 dimensions (each 1-10):

1. **Relevance**: Does the article address the original research query directly?
2. **Depth**: Does it provide substantive analysis, not just surface summaries?
3. **Specificity**: Does it include concrete data, methods, citations (not vague claims)?
4. **Structure**: Does it follow scientific article conventions (abstract, background, analysis, conclusion)?
5. **Originality**: Does it add new insights beyond restating common knowledge?

Respond ONLY with valid JSON:
{"relevance": N, "depth": N, "specificity": N, "structure": N, "originality": N, "feedback": "brief explanation of strengths and weakest dimensions"}
"""

WEIGHTS = {
    "relevance": 0.30,
    "depth": 0.25,
    "specificity": 0.20,
    "structure": 0.10,
    "originality": 0.15,
}


def _parse_json(text: str) -> dict | None:
    """Extract JSON object from LLM response text."""
    # Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code fence
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } in text
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def evaluate_article(
    article: str,
    query: str,
    model: str = "deepseek-chat",
) -> dict:
    """Evaluate article quality via LLM judge.

    Returns:
        {"score": float(0-1), "dimensions": {...}, "feedback": str}
    """
    if not article or len(article.strip()) < 50:
        return {
            "score": 0.0,
            "dimensions": {k: 0 for k in WEIGHTS},
            "feedback": "Article too short or empty",
        }

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        logger.warning("[Scoring] No API key available, falling back to heuristic")
        return heuristic_score(article, query)

    prompt = (
        f"## Research Query\n{query[:1000]}\n\n"
        f"## Article to Evaluate\n{article[:8000]}\n\n"
        "Rate this article on the 5 dimensions. Respond with JSON only."
    )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500,
                },
            )
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]

        parsed = _parse_json(raw)
        if not parsed:
            logger.warning("[Scoring] Failed to parse LLM response, using heuristic")
            return heuristic_score(article, query)

        dimensions = {}
        for key in WEIGHTS:
            val = parsed.get(key, 5)
            dimensions[key] = max(1, min(10, float(val)))

        score = sum(dimensions[k] * WEIGHTS[k] for k in WEIGHTS) / 10.0
        feedback = parsed.get("feedback", "")

        return {
            "score": round(score, 4),
            "dimensions": {k: round(v, 2) for k, v in dimensions.items()},
            "feedback": feedback,
        }

    except Exception as e:
        logger.error(f"[Scoring] LLM evaluation failed: {e}")
        return heuristic_score(article, query)


def heuristic_score(article: str, query: str) -> dict:
    """Structure-based heuristic scoring. Capped at 0.7 (should not exceed LLM score)."""
    score = 0.0
    dims = {"relevance": 3, "depth": 3, "specificity": 3, "structure": 3, "originality": 3}

    # Has section headings
    if re.search(r"^#{1,3}\s+\S+", article, re.MULTILINE):
        score += 0.1
        dims["structure"] += 2

    # Has references/citations
    if re.search(r"\[\d+\]|doi:|arXiv:|https?://\S+\.\w{2,}", article):
        score += 0.15
        dims["specificity"] += 3

    # Reasonable word count
    word_count = len(article.split())
    if 500 <= word_count <= 8000:
        score += 0.2
        dims["depth"] += 2

    # Query keyword overlap
    query_words = set(re.findall(r"[a-zA-Z一-鿿]{3,}", query.lower()))
    article_words = set(re.findall(r"[a-zA-Z一-鿿]{3,}", article.lower()))
    overlap = len(query_words & article_words)
    if query_words:
        kw_score = min(overlap / max(len(query_words), 1), 1.0) * 0.3
        score += kw_score
        dims["relevance"] += int(kw_score / 0.3 * 4)

    # Contains specific data
    if re.search(r"\d+\.?\d*%|\d+\.\d{2,}|p\s*[<>=]\s*0\.\d+", article):
        score += 0.1
        dims["specificity"] += 2

    # Has abstract section
    if re.search(r"(?i)abstract|introduction|summary", article[:2000]):
        score += 0.1
        dims["structure"] += 1

    score = min(score, 0.7)
    for k in dims:
        dims[k] = max(1, min(10, dims[k]))

    return {
        "score": round(score, 4),
        "dimensions": dims,
        "feedback": "Heuristic evaluation (LLM unavailable)",
    }
