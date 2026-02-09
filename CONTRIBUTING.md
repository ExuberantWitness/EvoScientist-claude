# Contributing to EvoScientist

Thank you for your interest in contributing to EvoScientist.

## Core Principles

- Less is more.
- Keep solutions simple, composable, and maintainable.
- Extend existing abstractions before introducing new paths.

## Agent-First Workflow

EvoScientist is commonly developed with AI agents as collaborators.
Before coding, make sure your agent can clearly explain:
- What this project does
- What writing/coding style this repository follows
- What constraints must not be broken

Before opening a PR, ask your agent to confirm:
- The implementation is the smallest viable change
- Existing behavior is preserved
- The feature works with both defaults and custom settings

## Architecture Guardrails

For new features:
- Prefer configuration and reuse over hardcoded special cases.
- Do not add feature-specific channels or one-off pipelines unless strictly necessary.
- Do not degrade, bypass, or complicate the main flow to support a single feature.
- Keep backward compatibility for existing CLI commands, config keys, and common workflows.

If a change requires a new path, explain why existing paths cannot be safely extended.

## Scope

Contributions are welcome for:
- Bug fixes
- New features and improvements
- Tests and CI stability
- Documentation updates

If your change is large or affects architecture, open an issue first to align on scope.

## Development Setup

Requirements:
- Python 3.11+

Install project with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the CLI locally:

```bash
python -m EvoScientist
# or
EvoSci
```

## Project Structure

Main code is under `EvoScientist/`, including:
- `cli.py` (Typer CLI)
- `EvoScientist.py` (agent wiring)
- `llm/` (model/provider logic)
- `stream/` (stream rendering/state)
- `channels/` (channel integrations)
- `skills/` (built-in skills)

Tests live in `tests/` and follow `test_*.py` naming.

## Coding Standards

- Use 4-space indentation and Python 3.11+ features.
- Add explicit type hints for public APIs when practical.
- Keep docstrings concise and focused on non-trivial behavior.
- Naming conventions:
  - `snake_case` for modules, functions, variables
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants

Run lint before opening a PR:

```bash
ruff check .
```

## Testing

Run all tests:

```bash
pytest -v
```

Guidelines:
- Add or update tests for every behavior change.
- Place tests near the affected domain (example: `EvoScientist/llm/...` -> `tests/test_llm.py`).
- Use fixtures and `unittest.mock` to isolate external services/API calls.

## Commit Message Convention

Use Conventional Commits where possible:
- `feat(llm): add provider fallback`
- `fix(stream): guard empty events`
- `test(asyncio): cover loop reuse`

## Pull Request Checklist

Please include:
- A clear summary of what changed and why
- Why this is the minimal solution (`less is more`)
- How compatibility is preserved across existing settings/workflows
- Linked issue(s), if applicable
- Validation evidence (output summary of `ruff check .` and `pytest -v`)
- Screenshots or terminal snippets for user-facing behavior changes, when applicable

Before requesting review, ensure:
- Lint passes
- Tests pass
- Main flow behavior is unchanged unless explicitly documented
- No feature-specific channel/pipeline was introduced without architectural justification
- Documentation is updated if behavior changed

## Security and Configuration

- Copy `.env.example` to create local config:

```bash
cp .env.example .env
```

- Never commit real API keys or secrets.
- Configure credentials via environment variables:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `NVIDIA_API_KEY`
  - `TAVILY_API_KEY`

## Questions

If anything is unclear, open an issue and describe:
- current behavior
- expected behavior
- reproducible context (commands/logs/environment)
