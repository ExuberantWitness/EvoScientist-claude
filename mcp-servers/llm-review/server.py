#!/usr/bin/env python3
"""
LLM Review MCP Server — Generic OpenAI-compatible LLM for cross-model review.

Supports: GPT, DeepSeek, Kimi, MiniMax, GLM, Qwen, and any OpenAI-compatible API.

Environment variables:
  LLM_API_KEY       — API key (required)
  LLM_BASE_URL      — API endpoint (default: https://api.openai.com/v1)
  LLM_MODEL         — Model name (default: gpt-4o)
  LLM_FALLBACK_MODEL — Retry model on failure (optional)

Install:
  pip install -r requirements.txt
  claude mcp add llm-review -- python3 /path/to/server.py
"""

import os
import sys
import json
import asyncio
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import run_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "600"))

# Conversation threads for multi-turn
threads: dict[str, list[dict[str, str]]] = {}

server = Server("llm-review")


async def call_llm(messages: list[dict[str, str]], model: str | None = None) -> str:
    """Call the LLM API and return the response text."""
    model = model or MODEL
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 504 and FALLBACK_MODEL:
                # Retry with fallback model
                payload["model"] = FALLBACK_MODEL
                resp = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            raise


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="chat",
            description="Send a prompt to the LLM for review. Returns the response.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The review prompt to send",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Optional thread ID for multi-turn conversation",
                    },
                    "system": {
                        "type": "string",
                        "description": "Optional system prompt override",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "chat":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    if not API_KEY:
        return [TextContent(type="text", text="Error: LLM_API_KEY not set")]

    prompt = arguments["prompt"]
    thread_id = arguments.get("thread_id", "")
    system = arguments.get("system", "You are a rigorous scientific reviewer.")

    messages: list[dict[str, str]] = []

    if thread_id and thread_id in threads:
        messages = threads[thread_id].copy()
    else:
        messages = [{"role": "system", "content": system}]

    messages.append({"role": "user", "content": prompt})

    try:
        response = await call_llm(messages)
    except Exception as e:
        return [TextContent(type="text", text=f"LLM API error: {e}")]

    messages.append({"role": "assistant", "content": response})

    # Save thread
    if thread_id:
        threads[thread_id] = messages
    else:
        import uuid
        thread_id = str(uuid.uuid4())[:8]
        threads[thread_id] = messages

    result = json.dumps({"thread_id": thread_id, "response": response})
    return [TextContent(type="text", text=result)]


async def main():
    await run_server(server)


if __name__ == "__main__":
    asyncio.run(main())
