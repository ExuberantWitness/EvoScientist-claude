"""LLM-driven GitHub search retry for baseline discovery.

When GitHub search returns 0 results, instead of falling back to static lists,
this module:
1. Calls LLM to analyze failure cause (bad keywords? too specific? language issue?)
2. LLM generates 2-3 reformulated queries
3. Retries GitHub search with reformulated queries
4. Loops up to MAX_RETRY_ROUNDS (3) until results found or all variants exhausted
5. Only if ALL queries fail, reports honest failure
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

MAX_RETRY_ROUNDS = 3

SEARCH_FAILURE_ANALYSIS_PROMPT = """\
GitHub code search returned ZERO results for query: "{query}"
Original research topic: "{topic}"

Analyze why this search likely failed. Consider:
- Are the keywords too specific or narrow?
- Is there a language mismatch (e.g., Chinese terms in an English-dominated code ecosystem)?
- Are the technical terms correct for this domain?
- Would broader or more standard terminology work better?

Then generate 2-3 alternative search queries that would be more likely to find
relevant open-source implementations. Use English technical terms.

Output as valid JSON only:
{{
  "analysis": "Brief explanation of why the search failed",
  "reformulated_queries": ["query1", "query2", "query3"],
  "suggested_terms": ["term1", "term2", "term3"]
}}
"""


async def llm_reformulate_query(
    llm_call: Callable[[str], Awaitable[str]],
    original_query: str,
    research_topic: str,
    previous_failures: list[str] | None = None,
) -> dict:
    """Ask LLM to analyze search failure and reformulate query.

    Args:
        llm_call: Async function that takes a prompt and returns LLM response.
        original_query: The query that failed.
        research_topic: The broader research topic for context.
        previous_failures: Queries that also failed (to avoid repetition).

    Returns:
        dict with "analysis", "reformulated_queries", "suggested_terms".
    """
    prompt = SEARCH_FAILURE_ANALYSIS_PROMPT.format(
        query=original_query, topic=research_topic
    )
    if previous_failures:
        prompt += (
            "\n\nPrevious queries that ALSO returned 0 results "
            "(DO NOT repeat these):\n"
        )
        for pf in previous_failures:
            prompt += f"- {pf}\n"
        prompt += (
            "\nGenerate queries that are meaningfully DIFFERENT "
            "from these failures."
        )

    try:
        response = await llm_call(prompt)
        text = response.strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try ```json code fence extraction
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))

        # Try any {...} block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))

        raise ValueError(
            f"Could not parse LLM reformulation response: {text[:200]}"
        )
    except Exception as e:
        logger.warning(f"LLM query reformulation failed: {e}")
        return {
            "analysis": "LLM call failed",
            "reformulated_queries": [],
            "suggested_terms": [],
        }
