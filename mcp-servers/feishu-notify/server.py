#!/usr/bin/env python3
"""
Feishu Notify MCP Server — Push notifications to Feishu/Lark.

Environment variables:
  FEISHU_APP_ID       — Feishu app ID (required)
  FEISHU_APP_SECRET   — Feishu app secret (required)
  FEISHU_USER_ID      — Target user open_id for DM (optional)
  FEISHU_WEBHOOK_URL  — Group chat webhook URL (optional, alternative to app)

Install:
  pip install -r requirements.txt
  claude mcp add feishu-notify -- python3 /path/to/server.py
"""

import os
import sys
import json
import asyncio
import time
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

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
USER_ID = os.environ.get("FEISHU_USER_ID", "")
WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
TIMEOUT = int(os.environ.get("FEISHU_TIMEOUT", "30"))

FEISHU_BASE = "https://open.feishu.cn/open-apis"

_token_cache: dict[str, Any] = {"token": "", "expires": 0}

server = Server("feishu-notify")


async def get_tenant_token() -> str:
    """Get or refresh Feishu tenant access token."""
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expires"] = time.time() + data.get("expire", 7200) - 60
        return _token_cache["token"]


async def send_message(content: str, title: str = "EvoScientist") -> str:
    """Send a message card to Feishu."""
    if WEBHOOK_URL:
        return await send_webhook(content, title)
    return await send_dm(content, title)


async def send_webhook(content: str, title: str) -> str:
    """Send via group webhook (no auth needed)."""
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        },
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(WEBHOOK_URL, json=card)
        resp.raise_for_status()
        return resp.json().get("msg", "sent")


async def send_dm(content: str, title: str) -> str:
    """Send DM via Feishu API (requires app auth)."""
    token = await get_tenant_token()
    headers = {"Authorization": f"Bearer {token}"}

    msg = {
        "receive_id": USER_ID,
        "msg_type": "interactive",
        "content": json.dumps({
            "type": "template",
            "data": {
                "template_id": "",
                "template_variable": {},
            },
        }),
    }

    # Fallback to text if card is complex
    msg = {
        "receive_id": USER_ID,
        "msg_type": "text",
        "content": json.dumps({"text": f"**{title}**\n\n{content}"}),
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id",
            headers=headers,
            json=msg,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("message_id", "sent")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="notify",
            description="Send a notification to Feishu/Lark.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Notification message (Markdown supported)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Notification title (default: EvoScientist)",
                    },
                },
                "required": ["message"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "notify":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    if not (WEBHOOK_URL or (APP_ID and APP_SECRET and USER_ID)):
        return [TextContent(
            type="text",
            text="Error: Set FEISHU_WEBHOOK_URL or (FEISHU_APP_ID + FEISHU_APP_SECRET + FEISHU_USER_ID)",
        )]

    message = arguments["message"]
    title = arguments.get("title", "EvoScientist")

    try:
        result = await send_message(message, title)
        return [TextContent(type="text", text=f"Sent: {result}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Feishu error: {e}")]


async def main():
    await run_server(server)


if __name__ == "__main__":
    asyncio.run(main())
