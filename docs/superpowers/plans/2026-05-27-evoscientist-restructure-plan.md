# EvoScientist 项目重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 tools/ + agent-manager/ 双目录重构为7层架构（L1~L7），消除 God Class，接入未集成模块。

**Architecture:** 自底向上7层 — claim_chain(底层文件系统) → sdk(底层驱动) → pes_controller(操作系统) → session(线程管理) → application(应用) → plugins(应用插件) → 外置session。每层一个顶级目录，文件按职责归属。

**Tech Stack:** Python 3.11+, SQLite, BGE-M3, MiMo API, LangChain, Starlette, DeepAgents

---

## File Structure Map

创建的新目录结构（7个顶级目录 + old/）：

```
EvoScientist-claude/
├── claim_chain/       # L1: schemas/, ontology/, chain.py, grounding.py, query.py, codegraph.py, cell_island.py, negative_archive.py, api.py, decomposer.py
├── sdk/               # L2: server.py, dashboard.py, web_process.py, local_process.py, skill_maintainer.py, literature/, status/, mcp/, middleware/
├── pes_controller/    # L3: base_phase.py, controller.py, protocol.py, bootstrap.py, pipeline_bridge.py, watchdog.py, stages.py, elo/, rubric/, phases/
├── session/           # L4: session.py, chunk.py, compress.py, lineage.py, manager.py, factory.py, backend.py, registry.py, event_bus.py, utils.py, llm/, config/, stream/, paths.py, runtime_utils.py
├── application/       # L5: orchestrator.py, prompts.py, personas/, meta/, evolution/, memory/, skill_manager.py, think.py
├── plugins/           # L6: ideation/, experimentation/, research/, validation/, writing/, reporting/, pipeline/, grounding/
├── old/               # 归档: claim_chain(v1), pes_cli, gbrain, evolve_grid, backends, sessions, onboard, skill-creator/, stream/display, stream/formatter, stream/diff_format, restart_dashboard, start_dashboard_standalone, start_dashboard, audit_agent_methods
└── tests/             # 按层分散: test_L1/, test_L3/, etc.
```

---

### Task 1: Phase 1 — 创建目录骨架

**Files:**
- Create: 7个层目录 + old/ + 所有子目录

- [ ] **Step 1: 创建所有顶级目录**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
mkdir -p claim_chain/schemas claim_chain/ontology
mkdir -p sdk/dashboard sdk/search sdk/literature sdk/memory sdk/status sdk/mcp sdk/tools sdk/middleware
mkdir -p pes_controller/elo pes_controller/rubric pes_controller/phases
mkdir -p session/llm session/config session/stream
mkdir -p application/personas application/meta application/evolution application/middleware application/memory
mkdir -p plugins/ideation plugins/experimentation plugins/research plugins/validation plugins/writing plugins/reporting plugins/pipeline plugins/grounding
mkdir -p old
mkdir -p tests/test_L1 tests/test_L3 tests/test_sdk
```

- [ ] **Step 2: 创建所有 __init__.py**

```bash
# 为所有新目录创建空的 __init__.py
for d in $(find claim_chain sdk pes_controller session application plugins -type d); do
    touch "$d/__init__.py"
done
touch old/__init__.py
```

- [ ] **Step 3: 验证目录结构**

```bash
find . -maxdepth 1 -type d | sort
# 应包含: application/ claim_chain/ old/ pes_controller/ plugins/ sdk/ session/ tests/
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: create 7-layer directory skeleton for project restructure"
```

---

### Task 2: Phase 1 — 归档不用的文件到 old/

**Files:**
- Move: 16个文件/目录 → old/

- [ ] **Step 1: 归档 tools/ 中的死代码**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
mv tools/claim_chain.py old/                    # v1 JSONL, 替换为v2
mv tools/pes_cli.py old/                         # 功能已合并
mv tools/gbrain_maintenance.py old/              # 零调用
mv tools/evolve_grid.py old/                     # 与cell_grid重叠
mv tools/start_dashboard.py old/                 # 功能已整合到sdk/dashboard
```

- [ ] **Step 2: 归档 evoscientist_core 中未使用的文件**

```bash
mv agent-manager/evoscientist_core/EvoScientist/backends.py old/
mv agent-manager/evoscientist_core/EvoScientist/sessions.py old/
mv agent-manager/evoscientist_core/EvoScientist/config/onboard.py old/
mv agent-manager/evoscientist_core/EvoScientist/skills old/skill-creator
mv agent-manager/evoscientist_core/EvoScientist/stream/display.py old/
mv agent-manager/evoscientist_core/EvoScientist/stream/formatter.py old/
mv agent-manager/evoscientist_core/EvoScientist/stream/diff_format.py old/
```

- [ ] **Step 3: 归档开发辅助脚本**

```bash
mv agent-manager/restart_dashboard.py old/
mv agent-manager/start_dashboard_standalone.py old/
mv scripts/audit_agent_methods.py old/
```

- [ ] **Step 4: 归档旧的 sessions 目录**

```bash
# 移到外层统一管理
mv sessions old/sessions_legacy 2>/dev/null || echo "sessions already in AUTORESEARCH/sessions/"
```

- [ ] **Step 5: 验证 old/ 包含16项**

```bash
ls old/ | wc -l
# 应 >= 14
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: archive 16 unused files to old/"
```

---

### Task 3: Phase 2 — 移动 L1 Claim Chain 文件

**Files:**
- Move: schemas/, ontology_schema_alignment, claim_chain_v2, cc_grounding, cc_query_interface, codegraph_cc, negative_archive, cell_grid, island_manager

- [ ] **Step 1: 移动 schemas/**

```bash
cp schemas/atom.py claim_chain/schemas/atom.py
cp schemas/__init__.py claim_chain/schemas/__init__.py
```

- [ ] **Step 2: 移动 tools/ 中的 L1 文件**

```bash
cp tools/taxonomy.py claim_chain/schemas/taxonomy.py
cp tools/models.py claim_chain/schemas/models.py
cp tools/validation.py claim_chain/schemas/validation.py
cp tools/ontology_schema_alignment.py claim_chain/ontology/alignment.py
cp tools/claim_chain_v2.py claim_chain/chain.py
cp tools/cc_grounding.py claim_chain/grounding.py
cp tools/cc_query_interface.py claim_chain/query.py
cp tools/codegraph_cc.py claim_chain/codegraph.py
cp tools/negative_archive.py claim_chain/negative_archive.py
cp tools/cell_grid.py claim_chain/cell_grid.py
cp tools/island_manager.py claim_chain/island_manager.py
```

- [ ] **Step 3: 验证 L1 文件就位**

```bash
ls claim_chain/
# chain.py  codegraph.py  grounding.py  negative_archive.py  query.py  cell_grid.py  island_manager.py
# ontology/  schemas/
ls claim_chain/schemas/
# atom.py  taxonomy.py  models.py  validation.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: move L1 Claim Chain files to claim_chain/"
```

---

### Task 4: Phase 2 — 移动 L2 SDK 文件

**Files:**
- Move: server, dashboard, web_tools, lit_ingest, mineru_literature, memory, evo_auto_evolve, fitness, mcp/*, tools/*, middleware/*

- [ ] **Step 1: 移动 agent-manager 文件到 sdk/**

```bash
cp agent-manager/evo_agent_manager/server.py sdk/server.py
cp agent-manager/evo_agent_manager/dashboard.py sdk/dashboard/monitor.py
cp agent-manager/evo_agent_manager/frontend.py sdk/dashboard/frontend.py
cp agent-manager/evo_agent_manager/web_tools.py sdk/search/web_search.py
cp agent-manager/evo_agent_manager/pipeline_bridge.py sdk/pipeline_bridge.py
```

- [ ] **Step 2: 移动 tools/ 中的 L2 文件**

```bash
cp tools/lit_ingest.py sdk/literature/ingest.py
cp tools/mineru_literature.py sdk/literature/mineru.py
```

- [ ] **Step 3: 移动 evolution memory + fitness**

```bash
cp agent-manager/evo_agent_manager/evolution/memory.py sdk/memory/memory.py
cp tools/evo_auto_evolve.py sdk/memory/evo_auto_evolve.py
cp agent-manager/evo_agent_manager/evolution/fitness.py sdk/status/fitness.py
```

- [ ] **Step 4: 移动 evoscientist_core 的 mcp/ + tools/**

```bash
cp agent-manager/evoscientist_core/EvoScientist/mcp/client.py sdk/mcp/client.py
cp agent-manager/evoscientist_core/EvoScientist/mcp/registry.py sdk/mcp/registry.py
cp agent-manager/evoscientist_core/EvoScientist/tools/execute.py sdk/tools/execute.py
cp agent-manager/evoscientist_core/EvoScientist/tools/search.py sdk/tools/search.py
cp agent-manager/evoscientist_core/EvoScientist/tools/skill_manager.py sdk/tools/skill_manager.py
cp agent-manager/evoscientist_core/EvoScientist/tools/think.py sdk/tools/think.py
```

- [ ] **Step 5: 移动 middleware 到 sdk/**

```bash
cp agent-manager/evoscientist_core/EvoScientist/middleware/context_editing.py sdk/middleware/context_editing.py
cp agent-manager/evoscientist_core/EvoScientist/middleware/context_overflow.py sdk/middleware/context_overflow.py
cp agent-manager/evoscientist_core/EvoScientist/middleware/tool_error_handler.py sdk/middleware/tool_error_handler.py
cp agent-manager/evoscientist_core/EvoScientist/middleware/tool_selector.py sdk/middleware/tool_selector.py
cp agent-manager/evoscientist_core/EvoScientist/middleware/memory.py sdk/middleware/memory.py
cp agent-manager/evoscientist_core/EvoScientist/middleware/ask_user.py sdk/middleware/ask_user.py
cp agent-manager/evoscientist_core/EvoScientist/middleware/utils.py sdk/middleware/middleware_utils.py
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: move L2 SDK files to sdk/"
```

---

### Task 5: Phase 2 — 移动 L3 PES Controller 文件

**Files:**
- Move: pes_controller, pipeline_protocol, pipeline_stages, bootstrap, pipeline_bridge, elo, rnd_evaluator, rubric_novelty, rubric_scheduler, pipeline_watchdog

- [ ] **Step 1: 移动核心管线文件**

```bash
cp tools/pes_controller.py pes_controller/controller.py
cp tools/pipeline_protocol.py pes_controller/protocol.py
cp tools/pipeline_stages.py pes_controller/stages.py
cp tools/bootstrap.py pes_controller/bootstrap.py
cp tools/pipeline_watchdog.py pes_controller/watchdog.py
```

- [ ] **Step 2: 移动 ELO + Rubric**

```bash
cp agent-manager/evo_agent_manager/evolution/elo.py pes_controller/elo/tournament.py
cp tools/rnd_evaluator.py pes_controller/elo/neighborhood.py
cp tools/rubric_novelty.py pes_controller/rubric/novelty.py
cp tools/rubric_scheduler.py pes_controller/rubric/scheduler.py
```

- [ ] **Step 3: pipeline_bridge 移动到 L3**

```bash
# 已在 sdk/pipeline_bridge.py, 移动到 pes_controller/
mv sdk/pipeline_bridge.py pes_controller/pipeline_bridge.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: move L3 PES Controller files to pes_controller/"
```

---

### Task 6: Phase 2 — 移动 L4 Session 文件

**Files:**
- Move: manager, agent_factory, backend, registry, event_bus, utils, llm/*, config/settings, stream/*, paths, EvoScientist/utils

- [ ] **Step 1: 移动 agent-manager session 文件**

```bash
cp agent-manager/evo_agent_manager/manager.py session/manager.py
cp agent-manager/evo_agent_manager/agent_factory.py session/factory.py
cp agent-manager/evo_agent_manager/backend.py session/backend.py
cp agent-manager/evo_agent_manager/registry.py session/registry.py
cp agent-manager/evo_agent_manager/event_bus.py session/event_bus.py
cp agent-manager/evo_agent_manager/utils.py session/utils.py
```

- [ ] **Step 2: 移动 evoscientist_core llm/config/stream**

```bash
cp agent-manager/evoscientist_core/EvoScientist/llm/models.py session/llm/models.py
cp agent-manager/evoscientist_core/EvoScientist/llm/patches.py session/llm/patches.py
cp agent-manager/evoscientist_core/EvoScientist/config/settings.py session/config/settings.py
cp agent-manager/evoscientist_core/EvoScientist/stream/events.py session/stream/events.py
cp agent-manager/evoscientist_core/EvoScientist/stream/state.py session/stream/state.py
cp agent-manager/evoscientist_core/EvoScientist/stream/emitter.py session/stream/emitter.py
cp agent-manager/evoscientist_core/EvoScientist/stream/tracker.py session/stream/tracker.py
cp agent-manager/evoscientist_core/EvoScientist/stream/utils.py session/stream/stream_utils.py
cp agent-manager/evoscientist_core/EvoScientist/paths.py session/paths.py
cp agent-manager/evoscientist_core/EvoScientist/utils.py session/runtime_utils.py
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: move L4 Session files to session/"
```

---

### Task 7: Phase 2 — 移动 L5 Application 文件

**Files:**
- Move: EvoScientist.py, prompts, evolution/*, meta_agent, skill_manager, think

- [ ] **Step 1: 移动 orchestrator + prompts**

```bash
cp agent-manager/evoscientist_core/EvoScientist/EvoScientist.py application/orchestrator.py
cp agent-manager/evoscientist_core/EvoScientist/prompts.py application/prompts.py
```

- [ ] **Step 2: 移动 evolution/ 子模块**

```bash
cp agent-manager/evo_agent_manager/evolution/meta_agent.py application/meta/meta_agent.py
cp agent-manager/evo_agent_manager/evolution/strategy.py application/evolution/strategy.py
cp agent-manager/evo_agent_manager/evolution/validator.py application/evolution/validator.py
cp agent-manager/evo_agent_manager/evolution/trigger.py application/evolution/trigger.py
cp agent-manager/evo_agent_manager/evolution/scoring.py application/evolution/scoring.py
cp agent-manager/evo_agent_manager/evolution/pipeline.py application/evolution/pipeline.py
cp agent-manager/evo_agent_manager/evolution/tree_search.py application/evolution/tree_search.py
```

- [ ] **Step 3: 移动 skill_manager + think (从 L2 移入 L5)**

```bash
mv sdk/tools/skill_manager.py application/skill_manager.py
mv sdk/tools/think.py application/think.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: move L5 Application files to application/"
```

---

### Task 8: Phase 2 — 移动 L6 Plugins 文件

**Files:**
- Move: structure_mapping, plan_templates, domain_presets, experiment_recorder, agent_task, trainer_contract, research_wiki, markdown_parser, verify_atom, verify_plan, cleanup, event_log, vault_manager, skills/*

- [ ] **Step 1: 移动 ideation/ 工具**

```bash
cp tools/structure_mapping_engine.py plugins/ideation/structure_mapping.py
cp tools/plan_templates.py plugins/ideation/plan_templates.py
cp tools/domain_presets.py plugins/ideation/domain_presets.py
```

- [ ] **Step 2: 移动 experimentation/ 工具**

```bash
cp tools/experiment_recorder.py plugins/experimentation/recorder.py
cp tools/agent_task.py plugins/experimentation/agent_task.py
cp tools/trainer_contract.py plugins/experimentation/trainer_contract.py
```

- [ ] **Step 3: 移动 writing/ 工具**

```bash
cp tools/research_wiki.py plugins/writing/research_wiki.py
cp tools/markdown_parser.py plugins/writing/markdown_parser.py
```

- [ ] **Step 4: 移动 validation/ + reporting/ 工具**

```bash
cp tools/verify_atom.py plugins/validation/verify_atom.py
cp tools/verify_plan.py plugins/validation/verify_plan.py
cp tools/cleanup_polluted_files.py plugins/validation/cleanup.py
cp tools/event_log.py plugins/reporting/event_log.py
cp tools/vault_manager.py plugins/reporting/vault_manager.py
```

- [ ] **Step 5: 移动 skills/ SKILL.md 到对应 L6 子目录**

```bash
# experimentation skills
cp skills/evo-code/SKILL.md plugins/experimentation/skills/evo-code.md
cp skills/evo-code-agent-pre/SKILL.md plugins/experimentation/skills/evo-code-agent-pre.md
cp skills/evo-code-agent-check/SKILL.md plugins/experimentation/skills/evo-code-agent-check.md
cp skills/evo-code-agent-post/SKILL.md plugins/experimentation/skills/evo-code-agent-post.md
cp skills/evo-run/SKILL.md plugins/experimentation/skills/evo-run.md
cp skills/evo-debug/SKILL.md plugins/experimentation/skills/evo-debug.md
# validation skills
cp skills/evo-claim/SKILL.md plugins/validation/skills/evo-claim.md
cp skills/evo-review/SKILL.md plugins/validation/skills/evo-review.md
# writing skills
cp skills/evo-write/SKILL.md plugins/writing/skills/evo-write.md
# reporting skills
cp skills/evo-analyze/SKILL.md plugins/reporting/skills/evo-analyze.md
# pipeline skills
cp skills/evo-pipeline/SKILL.md plugins/pipeline/skills/evo-pipeline.md
cp skills/evo-boot/SKILL.md plugins/pipeline/skills/evo-boot.md
cp skills/evo-iterate/SKILL.md plugins/pipeline/skills/evo-iterate.md
cp skills/evo-memory/SKILL.md plugins/pipeline/skills/evo-memory.md
cp skills/evo-evolve/SKILL.md plugins/pipeline/skills/evo-evolve.md
# research skills
cp skills/evo-research/SKILL.md plugins/research/skills/evo-research.md
cp skills/evo-ideation/SKILL.md plugins/research/skills/evo-ideation.md
cp skills/evo-intake/SKILL.md plugins/research/skills/evo-intake.md
cp skills/evo-planner/SKILL.md plugins/research/skills/evo-planner.md
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: move L6 Plugin files to plugins/"
```

---

### Task 9: Phase 2 — 删除空的旧目录

**Files:**
- Delete: tools/, agent-manager/, evoscientist_core/, schemas/, scripts/, skills/ (空目录，文件已全部移走)

- [ ] **Step 1: 确认旧目录为空**

```bash
# 确认只剩残留文件
ls tools/ 2>/dev/null && echo "WARNING: tools/ not empty" || echo "tools/ ready to delete"
ls agent-manager/evo_agent_manager/ 2>/dev/null && echo "WARNING: agent-manager/ not empty" || echo "agent-manager/ ready to delete"
```

- [ ] **Step 2: 删除空目录**

```bash
rm -rf tools/ agent-manager/ schemas/ scripts/ skills/ 2>/dev/null
# 保留 tests/ 目录
```

- [ ] **Step 3: 验证项目结构**

```bash
ls -d */ | sort
# application/  claim_chain/  docs/  old/  pes_controller/  plugins/  sdk/  session/  tests/
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove empty old directories (tools/, agent-manager/, etc.)"
```

---

### Task 10: Phase 3 — 更新 L1 Claim Chain import 路径

- [ ] **Step 1: 更新 chain.py (原 claim_chain_v2) 的内部 import**

```python
# claim_chain/chain.py
# 原: from tools.taxonomy import ...
# 新: from claim_chain.schemas.taxonomy import ...
# 原: from tools.models import ...
# 新: from claim_chain.schemas.models import ...
```

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
sed -i 's/from tools\.taxonomy/from claim_chain.schemas.taxonomy/g' claim_chain/chain.py
sed -i 's/from tools\.models/from claim_chain.schemas.models/g' claim_chain/chain.py
sed -i 's/from taxonomy/from claim_chain.schemas.taxonomy/g' claim_chain/chain.py
sed -i 's/from models/from claim_chain.schemas.models/g' claim_chain/chain.py
sed -i 's/from validation/from claim_chain.schemas.validation/g' claim_chain/chain.py
```

- [ ] **Step 2: 更新 grounding.py 的 import**

```bash
sed -i 's/from codegraph_cc/from claim_chain.codegraph/g' claim_chain/grounding.py
sed -i 's/from ontology_schema_alignment/from claim_chain.ontology.alignment/g' claim_chain/grounding.py
```

- [ ] **Step 3: 更新 query.py 的 import**

```bash
sed -i 's/from ontology_schema_alignment/from claim_chain.ontology.alignment/g' claim_chain/query.py
```

- [ ] **Step 4: 更新 cell_grid.py 和 island_manager.py 的 import**

```bash
sed -i 's/from tools\.claim_chain/from claim_chain.chain/g' claim_chain/cell_grid.py claim_chain/island_manager.py 2>/dev/null
sed -i 's/from claim_chain/from claim_chain.chain/g' claim_chain/cell_grid.py claim_chain/island_manager.py 2>/dev/null
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: update L1 Claim Chain import paths"
```

---

### Task 11: Phase 3 — 更新 L3 PES Controller import 路径

- [ ] **Step 1: 更新 controller.py (原 pes_controller.py) 的 import**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
# 核心import替换
sed -i 's/from claim_chain import/from claim_chain.chain import/g' pes_controller/controller.py
sed -i 's/from cell_grid import/from claim_chain.cell_grid import/g' pes_controller/controller.py
sed -i 's/from island_manager import/from claim_chain.island_manager import/g' pes_controller/controller.py
sed -i 's/from rubric_scheduler import/from pes_controller.rubric.scheduler import/g' pes_controller/controller.py
sed -i 's/from fitness_tracker import/from pes_controller.elo.neighborhood import/g' pes_controller/controller.py
sed -i 's/from pipeline_protocol import/from pes_controller.protocol import/g' pes_controller/controller.py
sed -i 's/from rnd_evaluator import/from pes_controller.elo.neighborhood import/g' pes_controller/controller.py
sed -i 's/from cc_query_interface import/from claim_chain.query import/g' pes_controller/controller.py
sed -i 's/from structure_mapping_engine import/from plugins.ideation.structure_mapping import/g' pes_controller/controller.py
sed -i 's/from domain_presets import/from plugins.ideation.domain_presets import/g' pes_controller/controller.py
sed -i 's/from plan_templates import/from plugins.ideation.plan_templates import/g' pes_controller/controller.py
# ELO import
sed -i "s/from evo_agent_manager.evolution.elo import/from pes_controller.elo.tournament import/g" pes_controller/controller.py
```

- [ ] **Step 2: 更新 protocol.py 的 import**

```bash
sed -i 's/from taxonomy/from claim_chain.schemas.taxonomy/g' pes_controller/protocol.py
```

- [ ] **Step 3: 更新 watchdog.py 的 import**

```bash
sed -i 's/from pes_controller import/from pes_controller.controller import/g' pes_controller/watchdog.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update L3 PES Controller import paths"
```

---

### Task 12: Phase 3 — 更新 L2 SDK + L4 Session + L5 Application import 路径

- [ ] **Step 1: 更新 sdk/dashboard/monitor.py 的 import**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
sed -i 's/from pipeline_protocol import/from pes_controller.protocol import/g' sdk/dashboard/monitor.py
sed -i 's/from pes_controller import/from pes_controller.controller import/g' sdk/dashboard/monitor.py
sed -i "s/from evo_agent_manager.evolution.elo import/from pes_controller.elo.tournament import/g" sdk/dashboard/monitor.py
sed -i 's/from \.frontend import/from sdk.dashboard.frontend import/g' sdk/dashboard/monitor.py
```

- [ ] **Step 2: 更新 session/manager.py 的 import**

```bash
sed -i 's/from \.event_bus import/from session.event_bus import/g' session/manager.py
sed -i 's/from \.utils import/from session.utils import/g' session/manager.py
sed -i 's/from \.agent_factory import/from session.factory import/g' session/manager.py
sed -i 's/from \.evolution\.memory import/from sdk.memory.memory import/g' session/manager.py
sed -i 's/from \.evolution\.fitness import/from sdk.status.fitness import/g' session/manager.py
sed -i 's/from \.evolution\.elo import/from pes_controller.elo.tournament import/g' session/manager.py
sed -i 's/from EvoScientist\.stream\.events import/from session.stream.events import/g' session/manager.py
sed -i 's/from EvoScientist\.stream\.state import/from session.stream.state import/g' session/manager.py
sed -i 's/from EvoScientist\.config\.settings import/from session.config.settings import/g' session/manager.py
sed -i 's/from EvoScientist\.llm\.models import/from session.llm.models import/g' session/manager.py
```

- [ ] **Step 3: 更新 session/factory.py 的 import**

```bash
sed -i 's/from EvoScientist\.config\.settings import/from session.config.settings import/g' session/factory.py
sed -i 's/from EvoScientist\.llm\.models import/from session.llm.models import/g' session/factory.py
sed -i 's/from EvoScientist\.prompts import/from application.prompts import/g' session/factory.py
sed -i 's/from EvoScientist\.utils import/from session.runtime_utils import/g' session/factory.py
sed -i 's/from EvoScientist\.tools import/from sdk.tools/g' session/factory.py
sed -i 's/from EvoScientist\.middleware\.context_editing import/from sdk.middleware.context_editing import/g' session/factory.py
sed -i 's/from EvoScientist\.middleware\.context_overflow import/from sdk.middleware.context_overflow import/g' session/factory.py
sed -i 's/from EvoScientist\.middleware\.tool_error_handler import/from sdk.middleware.tool_error_handler import/g' session/factory.py
sed -i 's/from EvoScientist\.middleware\.tool_selector import/from sdk.middleware.tool_selector import/g' session/factory.py
sed -i 's/from EvoScientist\.middleware\.memory import/from sdk.middleware.memory import/g' session/factory.py
```

- [ ] **Step 4: 更新 sdk/server.py 的 import**

```bash
sed -i 's/from \.manager import/from session.manager import/g' sdk/server.py
sed -i 's/from \.evolution\.fitness import/from sdk.status.fitness import/g' sdk/server.py
sed -i 's/from \.evolution\.strategy import/from application.evolution.strategy import/g' sdk/server.py
sed -i 's/from \.evolution\.meta_agent import/from application.meta.meta_agent import/g' sdk/server.py
sed -i 's/from \.evolution\.validator import/from application.evolution.validator import/g' sdk/server.py
sed -i 's/from \.evolution\.trigger import/from application.evolution.trigger import/g' sdk/server.py
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: update L2/L4/L5 import paths"
```

---

### Task 13: Phase 3 — 更新 L6 Plugins import + 最终验证

- [ ] **Step 1: 更新 plugins/ 内部 import**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
sed -i 's/from tools\.event_log import/from plugins.reporting.event_log import/g' plugins/experimentation/recorder.py
sed -i 's/from tools\.vault_manager import/from plugins.reporting.vault_manager import/g' plugins/experimentation/recorder.py
sed -i 's/from event_log import/from plugins.reporting.event_log import/g' plugins/experimentation/recorder.py
sed -i 's/from vault_manager import/from plugins.reporting.vault_manager import/g' plugins/experimentation/recorder.py
sed -i 's/from markdown_parser import/from plugins.writing.markdown_parser import/g' plugins/reporting/event_log.py
sed -i 's/from pipeline_protocol import/from pes_controller.protocol import/g' plugins/experimentation/agent_task.py
sed -i 's/from tools\.trainer_contract import/from plugins.experimentation.trainer_contract import/g' plugins/validation/verify_atom.py
sed -i 's/from schemas\.atom/from claim_chain.schemas.atom/g' plugins/validation/verify_atom.py
```

- [ ] **Step 2: 验证所有 import 可用 — 执行 dry-run 导入测试**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
python3 -c "
import sys
sys.path.insert(0, '.')
# 测试 L1
from claim_chain.schemas.taxonomy import AtomType, RelationType
from claim_chain.schemas.atom import RefinedAtom
print('L1 imports OK')
# 测试 L3
from pes_controller.protocol import atomic_read, atomic_write
from pes_controller.stages import PHASES, TRANSITIONS
print('L3 imports OK')
# 测试 L2
from sdk.status.fitness import FitnessTracker
print('L2 imports OK')
"
```

- [ ] **Step 3: 修复任何失败的 import（迭代修复，每个失败一个 commit）**

```bash
# 根据上一步的输出，逐文件修复
# 每次修复后 git commit
```

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "refactor: update L6 Plugin import paths, all imports verified"
```

---

### Task 14: Phase 4 — Session 统一到 L7

- [ ] **Step 1: 更新 session 存储路径配置**

```python
# session/paths.py 或相关配置中
# SESSIONS_DIR = AUTORESEARCH/sessions/ (EvoScientist-claude 外)
# 更新 .evo_session_registry.json 指向新路径
```

- [ ] **Step 2: 迁移 sessions/ 数据**

```bash
# 已在 AUTORESEARCH/sessions/ (L7), 旧 EvoScientist-claude/sessions/ 已归档到 old/
# 验证 L7 路径可访问
ls /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/sessions/sess_e2e_1779844413/PIPELINE_STATE.json
```

- [ ] **Step 3: 更新 CLAUDE.md 中的路径引用**

```bash
# 更新 CLAUDE.md 中的 session 路径
sed -i 's|EvoScientist-claude/sessions/|AUTORESEARCH/sessions/|g' CLAUDE.md
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: unify session storage to L7 AUTORESEARCH/sessions/"
```

---

### Task 15: Phase 5 — 创建 L1 api.py 和 decomposer.py (接入未集成模块)

- [ ] **Step 1: 创建 claim_chain/api.py — L1 统一门面**

```python
# claim_chain/api.py
from pathlib import Path
from claim_chain.chain import ClaimChain
from claim_chain.ontology.alignment import OntologyGatekeeper
from claim_chain.grounding import CCGrounding
from claim_chain.query import CCQueryInterface
from claim_chain.decomposer import Decomposer

class ClaimChainAPI:
    def __init__(self, workspace_dir: Path):
        db_path = workspace_dir / "_index" / "cc.db"
        self.chain = ClaimChain(db_path)
        self.ontology = OntologyGatekeeper()
        self.grounding = CCGrounding()
        self.query_iface = CCQueryInterface(self.chain)
        self.decomposer = Decomposer()

    def ingest_code(self, code_dir: Path, algo_names: list[str] | None = None):
        atoms = self.grounding.enrich_from_codegraph(code_dir)
        validated = self.ontology.validate(atoms)
        result = {"atoms_added": 0, "relations_added": 0, "atom_ids": []}
        for atom in validated:
            a = self.chain.add_atom(**atom)
            result["atom_ids"].append(a.id)
            result["atoms_added"] += 1
        return result

    def ingest_paper(self, paper_path: Path, metadata: dict | None = None):
        atoms = self.grounding.enrich_from_literature(paper_path.read_text())
        # ... similar
        return {"atoms_added": 0, "relations_added": 0}

    def query(self, spec: dict):
        return self.query_iface.query(spec)

    def decompose(self, content: str, strategy: str = "component"):
        return self.decomposer.decompose(content, strategy)
```

- [ ] **Step 2: 创建 claim_chain/decomposer.py**

```python
# claim_chain/decomposer.py
class Decomposer:
    def decompose(self, content: str, strategy: str = "component", depth: int = 3, breadth: int = 10):
        """将内容分解为 CC atoms。strategy: component|mechanism|argument_chain"""
        pass  # 待实现: BGE-M3粗筛 + LLM细提取
```

- [ ] **Step 3: 创建 pes_controller/rubric/format_verifier.py**

```python
# pes_controller/rubric/format_verifier.py
from openai import AsyncOpenAI

class FormatVerifier:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key="sk-cr1e299iw09nn2bt9a2vvu39sxwp18bfzf4vgzn25r1mldns",
            base_url="https://api.xiaomimimo.com/v1",
        )

    async def verify(self, proposal_text: str, product_spec: dict):
        """MiMo LLM 逐字段格式校验"""
        pass  # 待实现

    async def reformat(self, proposal_text: str, product_spec: dict, hints: list[str]):
        """MiMo LLM 格式重组"""
        pass  # 待实现
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: create L1 api.py, decomposer.py, L3 format_verifier.py"
```

---

### Task 16: Phase 5 — 创建 L4 Session OpenRath-style 模块

- [ ] **Step 1: 创建 session/session.py**

```python
# session/session.py
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Session:
    session_id: str
    workspace_dir: str
    chunks: list = field(default_factory=list)
    lineage_graph: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def fork(self) -> "Session":
        pass

    def merge(self, other: "Session") -> "Session":
        pass
```

- [ ] **Step 2: 创建 session/chunk.py, compress.py, lineage.py**

```python
# 从 OpenRath 参考实现
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: create L4 Session OpenRath-style modules (session/chunk/compress/lineage)"
```

---

### Task 17: Phase 6 — 拆分 controller.py 的 phase step 文件

- [ ] **Step 1: 创建 pes_controller/base_phase.py**

```python
# pes_controller/base_phase.py
class BasePhase:
    def __init__(self, state: dict, session):
        self.state = state
        self.session = session

    def run(self):
        chain = self.get_chain()
        for step_name in chain:
            step_method = getattr(self, step_name, None)
            if step_method:
                result = step_method()
                yield result

    def invoke_personas(self): raise NotImplementedError
    def evaluate_novelty(self): raise NotImplementedError
    def elo_tournament(self): raise NotImplementedError
    def verify_products(self): raise NotImplementedError
    def evolution_memory(self): raise NotImplementedError
    def write_claim_chain(self): raise NotImplementedError

    def build_cc_context(self): ...
    def build_experiment_feedback(self): ...
    def build_regeneration_feedback(self): ...
```

- [ ] **Step 2: 创建 W2 phase step 文件 (示例: w2_01_set_style.py)**

```python
# pes_controller/phases/w2_01_set_style.py
from pes_controller.base_phase import BasePhase

class W2SetStyle(BasePhase):
    def run(self):
        return {
            "focus": "问题分析",
            "depth": "到网络组件/loss项级别",
            "perspective": "批判性分析",
            "constraints": ["具体而非笼统", "必须有因果链"]
        }
```

- [ ] **Step 3: 为每个 phase 创建所有 step 文件 (39个文件)**

按 spec 中的文件列表逐一创建，每个文件继承 base_phase 或对应的父类。

- [ ] **Step 4: 更新 controller.py 使用新的 phase step 文件**

```python
# pes_controller/controller.py
def sub_loop(self):
    phase = state["phase"]
    step_idx = state["sub_loop_step"]
    chain = CHAIN_STEPS[phase]
    step_name = chain[step_idx]
    # 动态导入: pes_controller.phases.{phase_id}_{step_index:02d}_{step_name}
    module_name = f"pes_controller.phases.{phase_id}_{step_idx:02d}_{step_name}"
    module = importlib.import_module(module_name)
    ...
```

- [ ] **Step 5: 验证 + Commit**

```bash
git add -A
git commit -m "feat: Phase 6 - split controller into base_phase + 39 phase step files"
```

---

### Task 18: 最终验证 — 运行 E2E 管线测试

- [ ] **Step 1: 运行 W2 E2E 测试验证重构后的管线**

```bash
cd /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude
python3 -c "
import sys; sys.path.insert(0, '.')
# 测试完整的 import 链
from claim_chain.api import ClaimChainAPI
from pes_controller.controller import PESController
from pes_controller.protocol import atomic_read, atomic_write
from session.manager import AgentManager
print('All core imports OK')
"
```

- [ ] **Step 2: 运行现有测试**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -20
```

- [ ] **Step 3: 运行完整的 W2.3 E2E 测试**

```bash
# 使用之前验证过的 /tmp/run_w23.py (更新import路径后)
python3 /tmp/run_w23.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify E2E pipeline works after restructure"
```
