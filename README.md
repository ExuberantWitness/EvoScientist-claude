# EvoScientist-Claude

*Multi-agent scientific discovery system — Claude Code native Skills + PES Controller + Claim Chain v2*

> v0.3.0 (2026-06-02) — CC v2 SQLite: temporal metadata, iteration-aware knowledge graph, dashboard undo/rollback, experiment-to-CC sync.

---

## Architecture

```
Skills (20+) ──→ PES Controller ──→ Claim Chain v2 (SQLite cc.db)
                     │                       │
                     ▼                       ▼
              Dashboard (8420)         BGE-M3 Embedding
              - Phase transitions     - Semantic search
              - Iteration mgmt        - RND evaluation
              - Undo/rollback         - Cross-iteration context
              - Decision ledger
```

**Core components:**

| Component | Purpose |
|---|---|
| **PES Controller** | Plan-Execute-Summary loop, auto-advance phases, 4-persona ideation, ELO tournament, artifact validation |
| **Claim Chain v2** | SQLite-backed knowledge graph (cc.db) — atoms, edges, embeddings, temporal metadata (iter/phase/timestamp), validates/refutes relations |
| **Dashboard** | Web UI at localhost:8420 — phase transitions, iteration management, undo jump_to_plan, decision ledger, live persona events via SSE |
| **Experiment Recorder** | Agent tool for recording results — validates transitions, writes events.jsonl, updates Algorithms/*.md, syncs to cc.db with temporal metadata |
| **BGE-M3 Socket** | Unix socket embedding service — pre-computes atom embeddings, enables O(1) semantic search |
| **Markdown Parser** | Vault → CC sync — parses frontmatter, typed relations, wiki-links, self-wiring edges |

## Quick Start

```bash
# Install skills
cp -r skills/* ~/.claude/skills/

# Run pipeline
cd EvoScientist-claude && python run_dashboard.py &
claude
> /evo-pipeline "Your research question"
```

Dashboard: `http://localhost:8420`

## Skill Map (20+ Skills)

| Skill | Phase | Purpose |
|---|---|---|
| `/evo-pipeline` | Orchestrator | Full W1-W8 end-to-end pipeline |
| `/evo-intake` | W1 | Parse proposal, extract scope |
| `/evo-planner` | W2 | Experiment plan + success signals |
| `/evo-research` | W3 | Literature survey via paper-navigator |
| `/evo-ideation` | W3.5 | Idea Tree Search + Elo tournament |
| `/evo-refine` | W3.6 | Iterative method refinement (external review) |
| `/evo-code-agent-pre` | W4 | Pre-code CC context loading |
| `/evo-code` | W4 | Implement experiment code |
| `/evo-code-agent-check` | W4 | Code quality check against plan |
| `/evo-code-agent-post` | W4 | Post-code CC sync + link |
| `/evo-debug` | W4.5 | Debug runtime failures |
| `/evo-run` | W4.7 | Execute experiments |
| `/evo-analyze` | W5 | Metrics, plots, statistical analysis |
| `/evo-claim` | W5.6 | Result-to-claim judgment gate |
| `/evo-iterate` | W5.5 | Evaluate vs success signals, loop |
| `/evo-write` | W6 | Paper-ready report |
| `/evo-review` | W7 | Cross-model review via MCP |
| `/evo-memory` | Utility | Persistent memory management |
| `/research-wiki` | Utility | Persistent knowledge base (papers/ideas/claims) |
| `/evo-evolve` | PES | Quality-diversity evolution loop |

## Claim Chain v2

SQLite is the single source of truth. JSONL is temporary (write → sync → delete).

```
atoms.jsonl (temp) → cc.db (canonical) → BGE-M3 socket → embedding column
```

**Node schema:** id, title, type, summary, content, tags, status, metadata (JSON with iter/phase/timestamps), embedding (1024-dim BGE-M3 as JSON string)

**Edge types:** extends, improves, replaces, adapts, uses_component, compares, background, implements, validates, contradicts, derives, specializes, related_to, motivates, creates, affects, addressed_by, replaced_by

**Temporal metadata:** Every atom carries `iter`, `phase`, `created_at_iso` in its metadata JSON — enabling cross-iteration knowledge filtering, rollback, and structured context injection.

## Dashboard Features

- **Phase transitions:** satisfied/unsatisfied with artifact validation gate
- **Iteration management:** jump_to_plan → creates iterations/{N}/ directory, undo via full-state snapshots (git-like)
- **CC semantics:** satisfied → tag atoms iter_complete; unsatisfied → rollback atoms
- **Decision ledger:** AutoR-inspired human decision audit trail
- **Live events:** SSE streaming for persona invocations, ELO results, pipeline steps

## Project Structure

```
EvoScientist-claude/
├── pes_controller/         # PES loop engine
│   ├── controller.py       # Main controller (W2-W8 phases)
│   ├── bootstrap.py        # Session bootstrap
│   ├── protocol.py         # State read/write, atomic operations
│   ├── elo/                # ELO tournament + RND evaluation
│   └── rubric/             # Rubric scheduler
├── claim_chain/            # Knowledge graph v2
│   ├── chain.py            # ClaimChainV2: SQLite CRUD, embeddings, compat API
│   ├── query.py            # CCQueryInterface: semantic search, graph traversal
│   ├── grounding.py        # CCGrounding: atom/relation validation
│   ├── schemas/            # Node/Edge dataclasses, taxonomy, validation
│   └── ontology/           # Domain ontology definitions
├── sdk/
│   ├── dashboard/monitor.py  # Starlette web dashboard (8420)
│   ├── memory/evo_auto_evolve.py  # PES auto-evolution loop
│   ├── search/web_search.py      # Tavily + web search
│   ├── status/fitness.py         # Fitness tracker
│   └── tools/                    # execute, search, skill_manager, think
├── plugins/
│   ├── writing/markdown_parser.py  # Vault → CC sync + self-wiring
│   ├── experimentation/agent_task.py
│   ├── reporting/event_log.py
│   └── ideation/                   # Idea generation utilities
├── tools/
│   ├── experiment_recorder.py  # Agent tool: record → CC + events + Markdown
│   ├── bge_socket_server.py    # BGE-M3 Unix socket embedding service
│   └── cc_query_tool.py        # CLI for CC query/upsert/link
├── session/                  # Session lifecycle management
├── application/              # Personas, orchestrator, evolution
├── skills/                   # 20+ Claude Code Skills (Markdown)
├── run_dashboard.py          # Dashboard entry point
├── CLAUDE.md                 # Claude Code project config
└── sessions/                 # Research sessions (gitignored)
```

## Iteration Flow

```
Iteration 0: W2 → W3 → W4 → W5 → W6
                                    │
                     ┌──────────────┼──────────────┐
                     ▼              ▼              ▼
              满意→下一阶段    不满意→重做    直接回到Plan
              (tag complete)  (rollback W6)  (tag complete)
                     │              │              │
                     └──────────────┴──────────────┘
                                    │
                                    ▼
                            Iteration 1: W2
                      (_build_cc_full_context reads iter=0 atoms)
```

All three paths produce `iteration + 1`. CC atoms from the completed iteration are tagged `iter_complete=true` (satisfied path) or `iter_rollback=true` (unsatisfied path). W2 personas receive structured CC context grouped by iteration.

## v0.3.0 Changes (2026-06-02)

**CC v2 + Temporal Metadata:**
- cc.db as single source of truth (JSONL → temp → delete)
- All atoms carry iter/phase/created_at_iso in metadata
- `tag_atoms_by_iteration`, `tag_atoms_by_phase`, `update_atom_metadata` APIs
- BGE-M3 embedding stored in nodes.embedding column

**Dashboard Iteration Management:**
- Bug fix: iteration always 0→1 (removed double-increment in satisfied handler)
- jump_to_plan: full-state v2 snapshots with undo stack
- CC semantics: tag iter_complete (satisfied) or iter_rollback (unsatisfied) on jump_to_plan
- Decision ledger: human decision audit trail

**Cross-Iteration Knowledge:**
- `_build_cc_full_context()`: reads all CC atoms grouped by iter/phase for W2 persona context
- Experiment recorder syncs to cc.db with temporal metadata
- `add_atom()` accepts optional iteration/phase params

**Experiment Recorder:**
- `_sync_experiment_to_cc()`: upserts experiment atoms with score, status, validates edges
- Reads PIPELINE_STATE.json for iter/phase injection
- Creates validates edges between experiment and proposal atoms

## Previous Versions

### v0.2.1 (2026-05-25)
- Tavily Search + Direct LLM Pipeline
- Dashboard live persona events (SSE)
- Session recovery, watchdog disabled
- ELO verification with phase dimension matching

### v0.2.0 (2026-05-02)
- Four-Layer Architecture: Claim Chain + MAP-Elites + PES Loop + vis.js Dashboard
- 15 Skills, Agent Manager 8 MCP tools

### v0.1.0 (2026-04-09)
- First release: 14 Skills + Multi-Agent MCP + 3 cross-model review bridges

## Acknowledgements

- [EvoScientist](https://github.com/EvoScientist/EvoScientist) — original multi-agent scientific discovery system
- [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) — Claude Code Skill architecture
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic)
- [LangGraph](https://github.com/langchain-ai/langgraph) — multi-agent orchestration
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol

## Citation

```bibtex
@software{evoscientist_claude_2026,
  title  = {EvoScientist-Claude: Multi-Agent Scientific Discovery for Claude Code},
  author = {EvoScientist Contributors},
  year   = {2026},
  url    = {https://github.com/EvoScientist/EvoScientist-claude},
}
```

## License

Apache 2.0
