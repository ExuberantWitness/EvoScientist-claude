"""LLM-driven strategy proposal agent for meta-evolution.

Analyzes fitness trends, evolution logs, and memory statistics to propose
modifications to strategy configuration files. Inspired by the Hyperagents
approach (arXiv:2603.19461) but modifies markdown skill files instead of
Python source code.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

META_SYSTEM_PROMPT = """\
You are a Meta-Agent responsible for analyzing a research system's runtime state and proposing strategy improvements.

Your responsibilities:
1. Analyze fitness trends: which metrics are rising/falling/stagnant
2. Diagnose root causes: why certain strategies work/fail
3. Propose modifications: specific changes to the strategy file content
4. Explain rationale: why this modification will improve system performance

You modify markdown-format strategy configuration files containing key-value parameters and strategy descriptions.

Guidelines:
- Adjust numeric parameters in small increments (e.g., 0.5 -> 0.55, not 0.5 -> 0.8)
- Keep the markdown structure intact
- Only change 1-3 parameters per modification
- Base your changes on the data provided, not speculation

Output strict JSON format:
{"new_content": "complete new strategy file content (markdown)", "rationale": "one paragraph explaining the changes", "changes_summary": ["change1", "change2", ...]}
"""

MUTATION_SYSTEM_PROMPT = """\
You are a mutation operator for an evolutionary strategy system. Make small, targeted changes to the strategy file.

Rules:
- Change only 1-2 parameters
- Keep changes small (10-20% adjustment for numeric values)
- Maintain the file structure
- Do not remove sections, only modify values

Output strict JSON format:
{"new_content": "complete new strategy file content (markdown)", "mutation_description": "what changed and why"}
"""


def _parse_json(text: str) -> dict | None:
    """Extract JSON from LLM response."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def _call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 4000) -> str:
    """Call LLM via OpenAI-compatible API."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class MetaAgent:
    """LLM-driven strategy proposal agent."""

    def __init__(self, model: str = "deepseek-chat"):
        self.model = model

    async def propose_modification(
        self,
        target_file: str,
        current_strategy: str,
        fitness_history: list[dict],
        evolution_log: list[dict],
        memory_stats: dict,
    ) -> tuple[str, str]:
        """Propose a strategy modification based on runtime state.

        Returns:
            (new_content, rationale) tuple. On failure, returns (current_strategy, error_msg).
        """
        # Summarize fitness history (last 5 entries)
        fitness_summary = "No fitness data yet."
        if fitness_history:
            recent = fitness_history[-5:]
            fitness_summary = "\n".join(
                f"  - Run {i+1}: score={e.get('score', 'N/A'):.3f}, task={e.get('task_id', 'N/A')[:30]}"
                for i, e in enumerate(recent)
            )

        # Summarize evolution log (last 5 entries)
        log_summary = "No evolution events."
        if evolution_log:
            recent_log = evolution_log[-5:]
            log_summary = "\n".join(
                f"  - {e.get('type', 'unknown')}: {str(e)[:100]}"
                for e in recent_log
            )

        user_prompt = f"""\
## Target Strategy File: {target_file}

## Current Strategy Content:
{current_strategy}

## Recent Fitness History:
{fitness_summary}

## Recent Evolution Events:
{log_summary}

## Memory Statistics:
{json.dumps(memory_stats, indent=2)}

Based on the above data, analyze the system's performance and propose specific modifications to the strategy file.
Output your response as JSON with "new_content", "rationale", and "changes_summary" fields."""

        try:
            raw = await _call_llm(META_SYSTEM_PROMPT, user_prompt, temperature=0.7, max_tokens=4000)
            parsed = _parse_json(raw)
            if not parsed or "new_content" not in parsed:
                return current_strategy, f"Failed to parse proposal: {raw[:200]}"
            return parsed["new_content"], parsed.get("rationale", "No rationale provided")
        except Exception as e:
            logger.error(f"[MetaAgent] Proposal failed: {e}")
            return current_strategy, f"MetaAgent error: {e}"

    async def propose_mutation(
        self,
        parent_content: str,
        target_file: str,
        fitness_history: list[dict],
    ) -> tuple[str, str]:
        """Lighter-weight mutation for population-based search.

        Returns:
            (mutated_content, mutation_description)
        """
        scores = [e.get("score", 0) for e in fitness_history[-5:]] if fitness_history else []
        score_str = ", ".join(f"{s:.3f}" for s in scores) if scores else "no data"

        user_prompt = f"""\
## Target: {target_file}
## Parent Content:
{parent_content}
## Recent Scores: [{score_str}]

Propose a small mutation to this strategy file. Change only 1-2 numeric parameters by 10-20%.
Output JSON with "new_content" and "mutation_description"."""

        try:
            raw = await _call_llm(MUTATION_SYSTEM_PROMPT, user_prompt, temperature=0.8, max_tokens=3000)
            parsed = _parse_json(raw)
            if not parsed or "new_content" not in parsed:
                return parent_content, f"Mutation parse failed: {raw[:200]}"
            return parsed["new_content"], parsed.get("mutation_description", "Unknown mutation")
        except Exception as e:
            logger.error(f"[MetaAgent] Mutation failed: {e}")
            return parent_content, f"Mutation error: {e}"
