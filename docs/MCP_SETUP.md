# MCP Setup Guide

EvoScientist-claude uses MCP (Model Context Protocol) servers for cross-model review and notifications.

## LLM Review MCP (GPT / OpenAI-compatible)

Enables cross-model scientific review using any OpenAI-compatible API.

### Supported Providers

| Provider | Model | Base URL |
|----------|-------|----------|
| OpenAI | gpt-4o, gpt-4-turbo | https://api.openai.com/v1 |
| DeepSeek | deepseek-chat | https://api.deepseek.com/v1 |
| Kimi | moonshot-v1-32k | https://api.moonshot.cn/v1 |
| MiniMax | MiniMax-M2.7 | https://api.minimax.io/v1 |
| GLM | glm-4 | https://open.bigmodel.cn/api/paas/v4 |

### Installation

```bash
# Install dependencies
pip install -r mcp-servers/llm-review/requirements.txt

# Add to Claude Code (choose one)
# OpenAI:
claude mcp add llm-review \
  -e LLM_API_KEY=sk-xxx \
  -e LLM_MODEL=gpt-4o \
  -- python3 /path/to/mcp-servers/llm-review/server.py

# DeepSeek:
claude mcp add llm-review \
  -e LLM_API_KEY=your_key \
  -e LLM_BASE_URL=https://api.deepseek.com/v1 \
  -e LLM_MODEL=deepseek-chat \
  -- python3 /path/to/mcp-servers/llm-review/server.py

# MiniMax:
claude mcp add llm-review \
  -e LLM_API_KEY=your_key \
  -e LLM_BASE_URL=https://api.minimax.io/v1 \
  -e LLM_MODEL=MiniMax-M2.7 \
  -- python3 /path/to/mcp-servers/llm-review/server.py
```

### Usage in Skills

The `/evo-review` skill automatically uses this MCP:
```
/evo-review "final report" — REVIEWER: llm-review
```

## Gemini Review MCP

Uses Google Gemini as scientific reviewer.

### Installation

```bash
pip install -r mcp-servers/gemini-review/requirements.txt

claude mcp add gemini-review \
  -e GEMINI_API_KEY=your_key \
  -e GEMINI_REVIEW_MODEL=gemini-2.5-flash \
  -- python3 /path/to/mcp-servers/gemini-review/server.py
```

### Usage

```
/evo-review "report" — REVIEWER: gemini-review
```

## Feishu Notify MCP

Push notifications to Feishu/Lark for experiment status updates.

### Option A: Group Webhook (Simplest)

1. Create a custom bot in your Feishu group
2. Copy the webhook URL

```bash
pip install -r mcp-servers/feishu-notify/requirements.txt

claude mcp add feishu-notify \
  -e FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx \
  -- python3 /path/to/mcp-servers/feishu-notify/server.py
```

### Option B: App DM (Requires Feishu App)

1. Create a Feishu app at open.feishu.cn
2. Get app_id, app_secret, and target user's open_id

```bash
claude mcp add feishu-notify \
  -e FEISHU_APP_ID=cli_xxx \
  -e FEISHU_APP_SECRET=xxx \
  -e FEISHU_USER_ID=ou_xxx \
  -- python3 /path/to/mcp-servers/feishu-notify/server.py
```

## Verification

After adding MCPs, verify they're working:
```bash
claude mcp list
```

In Claude Code, you can test:
```
> Use the llm-review MCP to say hello
> Use the feishu-notify MCP to send a test message
```
