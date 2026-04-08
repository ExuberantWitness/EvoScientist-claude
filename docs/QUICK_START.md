# Quick Start

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- (Optional) Python 3.11+ for MCP servers

## Installation

### 1. Install Skills

```bash
git clone https://github.com/EvoScientist/EvoScientist-claude.git
cp -r EvoScientist-claude/skills/* ~/.claude/skills/
```

### 2. (Optional) Set Up Cross-Model Review MCP

For GPT/OpenAI-compatible review:
```bash
pip install -r EvoScientist-claude/mcp-servers/llm-review/requirements.txt
claude mcp add llm-review -e LLM_API_KEY=your_key -- python3 ~/.claude/mcp-servers/llm-review/server.py
```

For Gemini review:
```bash
pip install -r EvoScientist-claude/mcp-servers/gemini-review/requirements.txt
claude mcp add gemini-review -e GEMINI_API_KEY=your_key -- python3 ~/.claude/mcp-servers/gemini-review/server.py
```

### 3. (Optional) Set Up Feishu Notifications

```bash
pip install -r EvoScientist-claude/mcp-servers/feishu-notify/requirements.txt
claude mcp add feishu-notify -e FEISHU_WEBHOOK_URL=your_url -- python3 ~/.claude/mcp-servers/feishu-notify/server.py
```

## Usage

### Full Pipeline (Autonomous)
```
claude
> /evo-pipeline "Investigate whether knowledge distillation from GPT-4 improves BERT performance on low-resource NER"
```

### Full Pipeline (Interactive)
```
> /evo-pipeline "Your research question" — AUTO_PROCEED: false
```

### Individual Skills
```
> /evo-intake "proposal text"
> /evo-planner "optimize transformer inference speed"
> /evo-research "knowledge distillation methods 2025"
> /evo-ideation "low-resource NER improvements"
> /evo-code "implement Stage 1 baseline"
> /evo-run "Stage 1"
> /evo-debug "RuntimeError: CUDA out of memory"
> /evo-analyze "artifacts/"
> /evo-iterate
> /evo-write "final report"
> /evo-review "final report" — REVIEWER: llm-review
> /evo-memory init
> /evo-memory update
```

### Parameter Override
All skills support inline parameter overrides:
```
> /evo-pipeline "goal" — AUTO_PROCEED: true, SKIP_RESEARCH: true, CODE_MODE: effort
> /evo-review "report" — MAX_ROUNDS: 5, DIFFICULTY: hard
> /evo-code "task" — PREFLIGHT: false
```
