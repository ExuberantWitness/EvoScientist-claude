# Flux-* Skill Interface Contracts

## Version: 1.0.0

## Skill -> MCP Contract
Every flux-* skill MUST:
1. Read config from `skills/flux-config/review_config.json`
2. Use `mcp__llm-review__chat_session` for multi-turn review (thread_id based)
3. Use `mcp__llm-review__chat` for single-turn queries
4. Send SSE events to `http://localhost:8420/api/internal/events`
5. Read workspace_dir from `PIPELINE_STATE.json`
6. Write deliverables to workspace (not skill directory)

## PES -> Skill Contract
PES Controller invokes skills via:
```json
{"action": "invoke_skill", "skill": "/flux-paper-plan", "instruction": "<context>"}
```

## Skill -> PES Contract
Skills write deliverables. PES reads state via `verify_deliverables` step.
PRODUCT_SPECS in controller.py defines exact deliverables per phase.

## Dashboard -> PES Contract
Dashboard polls `/api/deliverables/{session_id}` for status.
User transitions via POST `/api/transition` with `action` and optional `feedback`.
