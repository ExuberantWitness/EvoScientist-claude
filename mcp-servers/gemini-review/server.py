#!/usr/bin/env python3
"""
Gemini Review MCP Server — Google Gemini as scientific reviewer.

Environment variables:
  GEMINI_API_KEY         — Google AI API key (required)
  GEMINI_REVIEW_MODEL    — Model name (default: gemini-2.5-flash)

Install:
  pip install -r requirements.txt
  claude mcp add gemini-review -- python3 /path/to/server.py
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

API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
MODEL = os.environ.get("GEMINI_REVIEW_MODEL", "gemini-2.5-flash")
TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "600"))

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

threads: dict[str, list[dict]] = {}

server = Server("gemini-review")


async def call_gemini(contents: list[dict], system: str = "") -> str:
    """Call Gemini API and return response text."""
    url = f"{BASE_URL}/models/{MODEL}:generateContent?key={API_KEY}"

    payload: dict[str, Any] = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    payload["generationConfig"] = {"temperature": 0.7, "maxOutputTokens": 4096}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="review",
            description="Send a prompt to Gemini for scientific review.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The review prompt to send",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Optional thread ID for multi-turn",
                    },
                    "system": {
                        "type": "string",
                        "description": "Optional system prompt",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "review":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    if not API_KEY:
        return [TextContent(type="text", text="Error: GEMINI_API_KEY not set")]

    prompt = arguments["prompt"]
    thread_id = arguments.get("thread_id", "")
    system = arguments.get("system", "You are a rigorous scientific reviewer.")

    contents: list[dict] = []

    if thread_id and thread_id in threads:
        contents = [c.copy() for c in threads[thread_id]]

    contents.append({"role": "user", "parts": [{"text": prompt}]})

    try:
        response = await call_gemini(contents, system)
    except Exception as e:
        return [TextContent(type="text", text=f"Gemini API error: {e}")]

    contents.append({"role": "model", "parts": [{"text": response}]})

    if thread_id:
        threads[thread_id] = contents
    else:
        import uuid
        thread_id = str(uuid.uuid4())[:8]
        threads[thread_id] = contents

    result = json.dumps({"thread_id": thread_id, "response": response})
    return [TextContent(type="text", text=result)]


async def main():
    await run_server(server)


if __name__ == "__main__":
    asyncio.run(main())
