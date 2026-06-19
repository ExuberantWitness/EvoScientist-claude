# 实施规格：ARIS 论文写作 → Flux-Insight（v4 — 全量 openai SDK 迁移）

## 背景

Flux-Insight 的 W7 "论文写作" 是单阶段。ARIS 有成熟的 5 阶段论文写作流水线（plan→figure→write→compile→improve）+ 审稿循环。我们将 W7 拆分为 W7.1-W7.5 子阶段 + W8 审稿。

**根本性架构决策**：PES Controller 内部用 Python 直接调用 DeepSeek LLM（通过 `openai` Python SDK），彻底删除 Claude Code 和 Agent SDK 依赖。所有 skill 逻辑在 PES Controller 内部执行。W8 交叉评审使用 MiMo。LLM 库选择 openai SDK（Decision #27）：事实标准 API 格式，外部 skill 平台（clawhub.ai 等）可直接通过改 `base_url` 对接。

## 当前状态（2026-06-04 审计）

| 组件 | 状态 | 说明 |
|---|---|---|
| mcp-servers/llm-review/ | 已创建 | chat + chat_session 工具。**PES 不使用它**，但保留作为备用/人工工具 |
| skills/flux-config/ | 已创建 | SKILL_REGISTRY.json, review_config.json, interface_validators.py, INTERFACE_CONTRACTS.md |
| skills/flux-paper-write/templates/ | 已创建 | 24 个 LaTeX 模板文件 |
| skills/flux-shared-references/ | 已创建 | 4 个参考文件 |
| pes_controller/controller.py | 部分更新 | 新 phase 常量已加，但 transition 逻辑引用未定义的 PHASE_WRITE |
| pes_controller/stages.py | 过时 | **待删除** |
| pes_controller/__init__.py | 过时 | **待更新** |
| pes_controller/phases/*.py | 过时 | **待替换** |
| sdk/dashboard/monitor.py | 过时 | **待全面更新** |
| sdk/dashboard/watchdog.py | 过时 | **待更新** |
| 4 个 evo-*/SKILL.md | 保留 | evo-pipeline, evo-code-agent-pre/check/post |
| 17 个 evo-*/SKILL.md | **待删除** | 核心功能已在 monitor.py _do_*() 中，SKILL.md 不参与自动调度 |
| 15 个 flux-*/SKILL.md | 空目录 | **待创建**（4 persona + verify + 10 skills 作为 prompt 模板） |
| tools_legacy/ | 过时 | **待同步更新** |
| plugins/experimentation/agent_task.py | **待删除** | Agent SDK 子进程入口 |

---

## 决策记录

| # | 问题 | 决策 |
|---|---|---|
| 1 | stages.py 双源真相 | **删除 stages.py**，唯一真相源为 controller.py |
| 2 | monitor.py 更新范围 | **全量更新**：imports + 删除 AGENT_SDK_PHASES + task 映射 + JS 前端 + 硬编码字符串 + transition 逻辑 |
| 3 | phases/ 目录 | **删除旧 + 创建新** |
| 4 | transition 中 PHASE_WRITE 引用 | **直接替换为 PHASE_WRITE_PLAN** |
| 5 | SKILL.md 创建 | **重新编写**，参考 ARIS 源，加入 Flux-Insight 特有机制 |
| 6 | Legacy 文件 | **同步更新** |
| 7 | 测试 | **单元测试 + 手动 E2E** |
| 8 | PRODUCT_SPECS.required[] | **描述性文字**（skill 自检质量），deliverables[] → 程序化文件存在检查 |
| 9 | evo-review vs flux-review-loop | **flux-* 为主** |
| 10 | **LLM 调用方式** | **PES Controller 通过 SkillExecutor 调用 DeepSeek**（主体模型），W8 交叉评审用 MiMo。模型配置在 PES Controller |
| 11 | **执行架构** | **PES Controller 内部用 Python 实现 skill 逻辑**，删除 Claude Code 和 Agent SDK 依赖 |
| 12 | **SKILL.md 角色** | **prompt 模板**，PES 读取并填充变量后发送给 LLM |
| 13 | **LLM 输出格式** | **JSON 结构化输出**，包含 files[] 和 actions[] 数组 |
| 14 | **多轮对话** | **PES Controller 内部管理会话状态**（messages 列表） |
| 15 | **SSE 事件** | **PES Controller 发送**，skill 不发 |
| 16 | **_auto_next_phase** | **保留** W2-W6 自动推进；**W7.1-W8 返回 None** 要求人工选择 |
| 17 | **jump_to_write** | **改为 jump_to_write_plan** |
| 18 | **Dashboard UI** | **多方案选择**：A/B/C 方案 + D 修改意见 + E 退回 |
| 19 | **Agent SDK** | **彻底删除** |
| 20 | **agent_task.py** | **彻底删除** |
| 21 | **W7.1 执行模型** | **SkillExecutor 内部执行**（不经过 monitor.py），与 W7.2-W8 统一 |
| 22 | **W7.1 并行策略** | **4 线程并行**（ThreadPoolExecutor），4 个 Persona 同时调用 LLM |
| 23 | **Elo 维度分层** | **W7.1 研究内容审阅维度**（创新性/可行性/影响力/叙事/规格）+ **W7.5 论文写作审阅维度**（理论/声明对齐/清晰度/自含性/符号）+ **W8 混合维度** |
| 24 | **模型配置** | **DeepSeek 主体 + MiMo 仅 W8**，环境变量 DEEPSEEK_*（主体）+ MIMO_*（W8 专用） |
| 25 | **W7/W8 执行路径** | **新建 SkillExecutor 路径**，不沿用现有 monitor.py `_do_*()` 模式。与 W2-W6 的 `invoke_skill` → monitor.py 分发完全独立。理由：现有 evo-write/evo-review 的 `_do_*()` 函数是硬编码 Python，无法支持多方案选择、多轮对话等 W7.1-W8 新特性 |
| 26 | **evo-* skill 清理** | **删除 17 个不用的 evo-* skill 目录**，仅保留 4 个：evo-pipeline, evo-code-agent-pre, evo-code-agent-check, evo-code-agent-post。/evo-analyze、/evo-claim、/evo-iterate 的核心功能已在 monitor.py 的 _do_*() 函数中，SKILL.md 删除无影响 |
| 27 | **LLM 库选择** | **openai SDK**（`pip install openai`）。理由：(1) OpenAI API 格式是事实标准，外部 skill 平台（clawhub.ai 等）必然支持；(2) 改 `base_url` 即可切换 provider（DeepSeek/MiMo/任何兼容端点）；(3) 依赖极轻（1 个包），langchain 需要适配其 provider 抽象层；(4) W2-W6 用 langchain 是 AgentManager 独立路径，不受影响 |
| 28 | **外部 skill provider 集成** | LLMClient 支持动态 `base_url`，外部 skill 平台（如 clawhub.ai）暴露 OpenAI 兼容端点后，`LLMClient(base_url=skill_endpoint)` 即可对接。SkillExecutor 不关心 LLM 来源，只关心 SKILL.md + LLMClient |
| 29 | **EloTournament 重构** | **将 `_call_judge()` 从 httpx raw HTTP 改为接受 LLMClient 实例**。构造函数签名改为 `__init__(self, llm_client: LLMClient, ...)`，删除内部 httpx 调用。保持 `rank()` 为 async 不变 |
| 30 | **Dashboard UI 参考** | 参考 claude-fleet（Alpine.js + Tailwind 单文件 SPA + FastAPI SSE）。W7.1 多方案选择用卡片布局，W7.2-W8 用产物确认卡片。关键模式：SSE 推送 + Alpine.js 响应式绑定 |
| 31 | **方案 ID 映射** | 4 个 Persona 输出文件名用 persona name（`plan_novel-academic.json`），Dashboard 显示为 A/B/C/D。映射表：`{"A": "novel-academic", "B": "conservative-academic", "C": "novel-engineering", "D": "conservative-engineering"}` |
| 32 | **LLMClient 同步/异步** | **LLMClient.chat() 保持同步**（简单直接），EloTournament `_call_judge()` 用 `asyncio.to_thread(self.llm_client.chat, ...)` 包装。`_build_step()` 中调用 `await tournament.rank()` 在 async MCP tool 上下文中执行 |
| 33 | **回到W5** | 使用 `advance` action + `target_phase=PHASE_CODE`，不使用 `jump_to_plan`（那个跳到 W2） |
| 34 | **Session 机制统一** | **SkillExecutor 内部 `self.sessions` 字典**为唯一会话机制，删除独立 SessionManager 模块（A3）。多轮会话通过 `session_id` 参数传递，持久化到 `workspace/.llm_session.json` |
| 35 | **4 个方案 → 4 个选项** | 4 个 Persona 生成 4 个方案，Dashboard 显示 A/B/C/D 4 个选项（非 3 个） |

---

## 架构总览

```
┌──────────────┐     ┌──────────────────────────────────────────┐
│  Dashboard    │     │  PES Controller (Python MCP server)       │
│ localhost:8420│     │                                           │
│              │────▶│  sub_loop() → _build_step()              │
│  Starlette   │     │       ↓                                   │
│  SSE events  │     │  skill_executor.py → 读取 SKILL.md       │
│  多方案UI     │     │       ↓                                   │
│  产物侧边栏   │     │  llm_client.py → openai SDK → DeepSeek API│
│              │◀────│       ↓                                   │
│              │     │  JSON 响应解析 → files[] 写入 → actions[] 执行 │
│              │     │       ↓                                   │
│              │     │  verify_deliverables → SSE event          │
└──────────────┘     └──────────────────────────────────────────┘
```

**数据流**：
1. Dashboard 调用 PES Controller 的 sub_loop()
2. sub_loop() 调用 _build_step()，获取 skill 步骤
3. _build_step() → skill_executor.py → 读取 SKILL.md prompt → 填充变量
4. skill_executor → llm_client.py → openai.ChatCompletion.create() → DeepSeek API（W8用MiMo）
5. LLM 返回 JSON（files[] + actions[]）
6. skill_executor 解析 JSON → 写文件 → 执行命令
7. verify_deliverables 检查产物
8. PES Controller 发 SSE 事件到 Dashboard
9. Dashboard 展示多方案选项，用户选择下一步

---

## 模块 A：PES Controller 新增模块

### A1. pes_controller/llm_client.py

**职责**：封装 LLM API 调用（默认 DeepSeek，W8 可切换 MiMo）

**输入**：
- `messages: list[dict]` — 消息列表 `[{"role": "system"|"user"|"assistant", "content": str}]`
- `model: str = "deepseek-chat"` — 模型名
- `max_tokens: int = 4096` — 最大 token 数
- `temperature: float = 0.7` — 温度

**输出**：
- `content: str` — LLM 响应文本
- `usage: dict` — token 使用统计

**接口**：
```python
class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        """初始化 OpenAI 兼容客户端"""
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def chat(self, messages: list[dict], max_tokens: int = 4096,
             temperature: float = 0.7) -> tuple[str, dict]:
        """调用 LLM，返回 (content, usage)"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content
        usage = {"prompt_tokens": response.usage.prompt_tokens,
                 "completion_tokens": response.usage.completion_tokens}
        return content, usage
```

**依赖**：`openai` Python 包（`pip install openai`）
**环境变量**：
- 主体模型：`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1`, `DEEPSEEK_MODEL=deepseek-chat`
- W8 专用：`MIMO_API_KEY`, `MIMO_BASE_URL=https://api.xiaomimimo.com/v1`, `MIMO_MODEL=mimo-v2.5-pro`

**外部 skill provider 集成**（Decision #28）：
```python
# 外部 skill 平台（如 clawhub.ai）暴露 OpenAI 兼容端点
# SkillExecutor 不关心 LLM 来源，只关心 SKILL.md + LLMClient
external_client = LLMClient(
    api_key=os.environ.get("CLAWHUB_API_KEY", ""),
    base_url="https://api.clawhub.ai/v1/skills/xxx",  # 外部 skill 端点
    model="clawhub-skill-model",
)
executor = SkillExecutor(skills_dir, external_client)
```

**三库并存状态**（Decision #27 后）：

| 库 | 使用位置 | 调用方式 | 状态 |
|---|---|---|---|
| **openai SDK** | SkillExecutor (W7.1-W8) | `LLMClient.chat()` | **新建** |
| **langchain** | AgentManager (W2-W6 4-Persona) | `get_chat_model().invoke()` | **已验证，不修改** |
| **httpx raw** | EloTournament (W2-W4, W7.1) | `_call_judge()` | **待迁移到 LLMClient**（Decision #29） |

### A2. pes_controller/skill_executor.py

**职责**：读取 SKILL.md → 填充变量 → 调用 LLM → 解析 JSON 响应 → 执行操作

**输入**：
- `skill_name: str` — skill 名称（如 `"flux-paper-plan"`）
- `variables: dict` — 变量映射（如 `{"research_topic": "...", "workspace_dir": "..."}`）
- `llm_client: LLMClient` — LLM 客户端实例

**输出**：
- `result: dict` — `{"success": bool, "files_written": [...], "actions_executed": [...], "llm_response": str}`

**接口**：
```python
class SkillExecutor:
    def __init__(self, skills_dir: Path, llm_client: LLMClient):
        self.skills_dir = skills_dir  # E:\DATA\vscode\ARIS\Flux-Insight\skills
        self.llm_client = llm_client
        self.sessions: dict[str, list[dict]] = {}  # thread_id → messages

    def execute(self, skill_name: str, variables: dict,
                session_id: str | None = None) -> dict:
        """执行一个 skill"""
        # 1. 读取 SKILL.md
        skill_path = self.skills_dir / skill_name / "SKILL.md"
        prompt = self._parse_and_fill(skill_path, variables)

        # 2. 构建消息
        messages = self._build_messages(prompt, session_id)

        # 3. 调用 LLM
        content, usage = self.llm_client.chat(messages)

        # 4. 保存到会话
        self._update_session(session_id, messages, content)

        # 5. 解析 JSON 响应
        parsed = self._parse_json_response(content)

        # 6. 执行文件操作和命令
        result = self._execute_actions(parsed, variables.get("workspace_dir", "."))

        return result

    def _parse_and_fill(self, skill_path: Path, variables: dict) -> str:
        """读取 SKILL.md，替换 {{variable}} 占位符"""
        template = skill_path.read_text(encoding="utf-8")
        # 去掉 YAML frontmatter
        if template.startswith("---"):
            end = template.find("---", 3)
            template = template[end + 3:].strip()
        for key, value in variables.items():
            template = template.replace("{{" + key + "}}", str(value))
        return template

    def _parse_json_response(self, content: str) -> dict:
        """从 LLM 响应中提取 JSON"""
        # 尝试提取 ```json ... ``` 代码块
        import re
        json_match = re.search(r'```json\s*\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        # 尝试直接解析整个内容
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"files": [], "actions": [], "raw_text": content}

    def _execute_actions(self, parsed: dict, workspace_dir: str) -> dict:
        """执行文件写入和命令"""
        import subprocess
        ws = Path(workspace_dir)
        files_written = []
        actions_executed = []

        for f in parsed.get("files", []):
            path = ws / f["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f["content"], encoding="utf-8")
            files_written.append(str(path))

        for a in parsed.get("actions", []):
            result = subprocess.run(
                a["command"], shell=True, capture_output=True, text=True,
                cwd=str(ws), timeout=300,
            )
            actions_executed.append({
                "command": a["command"],
                "returncode": result.returncode,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000],
            })

        return {
            "success": True,
            "files_written": files_written,
            "actions_executed": actions_executed,
        }
```

### A3. 会话管理（内嵌在 SkillExecutor 中，Decision #34）

**不创建独立 SessionManager**。会话管理内嵌在 `SkillExecutor` 中：

```python
class SkillExecutor:
    def __init__(self, skills_dir: Path, llm_client: LLMClient):
        self.skills_dir = skills_dir
        self.llm_client = llm_client
        self.sessions: dict[str, list[dict]] = {}  # session_id → messages

    def execute(self, skill_name: str, variables: dict,
                session_id: str | None = None) -> dict:
        # 1. 读取 SKILL.md → 填充变量 → 得到 prompt
        skill_path = self.skills_dir / skill_name / "SKILL.md"
        prompt = self._parse_and_fill(skill_path, variables)

        # 2. 构建/恢复消息列表
        if session_id and session_id in self.sessions:
            messages = self.sessions[session_id].copy()
            messages.append({"role": "user", "content": prompt})
        else:
            messages = [{"role": "user", "content": prompt}]

        # 3. 调用 LLM
        content, usage = self.llm_client.chat(messages)

        # 4. 保存到会话
        if session_id:
            messages.append({"role": "assistant", "content": content})
            self.sessions[session_id] = messages
            # 持久化到文件（Decision #26）
            self._save_session_file(variables.get("workspace_dir", "."), session_id, messages)

        # 5-6. 解析 JSON → 执行操作
        parsed = self._parse_json_response(content)
        result = self._execute_actions(parsed, variables.get("workspace_dir", "."))
        result["llm_response"] = content
        return result

    def _save_session_file(self, workspace_dir: str, session_id: str, messages: list):
        """持久化会话到 workspace/.llm_session.json"""
        ws = Path(workspace_dir)
        session_file = ws / ".llm_session.json"
        import datetime
        session_data = {
            "skill_name": session_id,
            "messages": messages,
            "updated_at": datetime.datetime.now().isoformat(),
        }
        session_file.write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_session(self, workspace_dir: str, session_id: str) -> list[dict]:
        """从文件恢复会话"""
        session_file = Path(workspace_dir) / ".llm_session.json"
        if session_file.exists():
            data = json.loads(session_file.read_text(encoding="utf-8"))
            self.sessions[session_id] = data.get("messages", [])
            return self.sessions[session_id]
        return []
```

---

## 模块 B：PES Controller 修改

### B0. 调度机制全景（两种并存）

**PES Controller 存在两套 skill 调度机制**：

| 机制 | 阶段 | 执行路径 | LLM 库 | 状态 |
|---|---|---|---|---|
| **机制 1：monitor.py 分发** | W2-W6 | PES → action dict → monitor.py `_do_*()` / `AgentManager` | langchain | **已验证，不修改** |
| **机制 2：SkillExecutor 内部执行** | W7.1-W8 | PES `_build_step()` 直接执行 → `SkillExecutor` → `LLMClient` | openai SDK | **待新建** |

**机制 1 详情（W2-W6，不修改）**：
```
PES _build_step() → {"action": "invoke_personas"/"invoke_skill", "skill": "/evo-analyze", ...}
    → monitor.py _execute_step()
        → invoke_personas: AgentManager.invoke_agent() × 4 (langchain)
        → invoke_skill /evo-analyze: _do_scan_islands_rubrics() (Python)
        → invoke_skill /evo-claim: _do_write_claim_chain() (Python)
        → invoke_skill /evo-iterate: _do_island_assign() (Python)
        → invoke_skill /evo-research: _do_web_research() (Python)
```

**机制 2 详情（W7.1-W8，新建）**：
```
PES _build_step() → 内部直接调用:
    → _get_skill_executor(state) → SkillExecutor(skills_dir, llm_client)
        → executor.execute("flux-paper-plan-novel-academic", variables)
            → 读取 SKILL.md → 填充变量 → LLMClient.chat() → 解析 JSON → 写文件
    → W7.1 invoke_four_personas_paper: ThreadPoolExecutor 并行调用 4 个 persona
    → W7.1 elo_tournament_paper: 直接导入 EloTournament 类
    → W7.2-W7.4: SkillExecutor.execute() 单次调用
    → W7.5/W8: SkillExecutor.execute() 多轮调用
```

**monitor.py 对 W7.1-W8 的角色**（Decision #21）：
- **不执行** step（PES 内部完成）
- **仅展示** SSE 事件（paper_plan_options_ready, skill_completed 等）
- **转发** Transition API 请求（advance/redo/terminate）

### B1. controller.py 修改清单

**文件**：`pes_controller/controller.py`

**B1.1 Phase 常量**（~行 39-44）✅ 已更新
```
PHASE_WRITE_PLAN   = "W7.1 论文计划"
PHASE_WRITE_FIGURE = "W7.2 图表生成"
PHASE_WRITE_LATEX  = "W7.3 LaTeX写作"
PHASE_WRITE_COMPILE= "W7.4 编译"
PHASE_WRITE_IMPROVE= "W7.5 审稿修复"
PHASE_REVIEW       = "W8 审阅"
```

**B1.2 CHAIN_STEPS**（~行 79-98）需更新

W7.1 改为 4 步（4-Persona + Elo + 验证 + 展示），W7.5 改为 5 步（多轮），W8 改为 6 步（多轮）：
```python
CHAIN_STEPS = {
    PHASE_PLAN_1:   list(_PERSONA_CHAIN),
    PHASE_PLAN_2:   list(_PERSONA_CHAIN),
    PHASE_IDEATE:   list(_PERSONA_CHAIN),
    PHASE_CODE: ["generate_code_spec", "run_step_pipeline",
                 "generate_code_plan", "wait_user_code"],
    PHASE_ANALYZE: ["run_step_pipeline", "scan_islands_rubrics",
                     "multi_agent_discuss", "evolution_memory",
                     "island_assign", "refine_atoms", "write_claim_chain"],
    PHASE_WRITE_PLAN: [
        "invoke_four_personas_paper", "elo_tournament_paper",
        "verify_paper_plan_products", "present_paper_plan_options",
    ],
    PHASE_WRITE_FIGURE: ["invoke_skill_paper_figure", "verify_deliverables"],
    PHASE_WRITE_LATEX:  ["invoke_skill_paper_write", "verify_deliverables"],
    PHASE_WRITE_COMPILE:["invoke_skill_paper_compile", "verify_deliverables"],
    PHASE_WRITE_IMPROVE: [
        "invoke_skill_improve_review_1", "invoke_skill_improve_fix_1",
        "invoke_skill_improve_review_2", "invoke_skill_improve_fix_2",
        "verify_deliverables",
    ],
    PHASE_REVIEW: [
        "invoke_skill_review_round_1", "invoke_skill_review_fix_1",
        "invoke_skill_review_round_2", "invoke_skill_review_fix_2",
        "invoke_skill_review_round_3",
        "verify_deliverables",
    ],
}
```

**B1.3 TRANSITIONS**（~行 60-72）需更新

添加 W7.2-W7.5 → W7.1 的回退路径：
```python
TRANSITIONS = {
    PHASE_PLAN_1:   [PHASE_PLAN_2],
    PHASE_PLAN_2:   [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN_1, PHASE_WRITE_PLAN],
    PHASE_WRITE_PLAN:   [PHASE_WRITE_FIGURE],
    PHASE_WRITE_FIGURE: [PHASE_WRITE_LATEX, PHASE_WRITE_PLAN],
    PHASE_WRITE_LATEX:  [PHASE_WRITE_COMPILE, PHASE_WRITE_PLAN],
    PHASE_WRITE_COMPILE:[PHASE_WRITE_IMPROVE, PHASE_WRITE_PLAN],
    PHASE_WRITE_IMPROVE:[PHASE_REVIEW, PHASE_WRITE_PLAN],
    PHASE_REVIEW:   [PHASE_WRITE_PLAN, PHASE_CODE, PHASE_PLAN_1, PHASE_TERMINATED],
}
```

**B1.4 PRODUCT_SPECS**（~行 120-192）✅ 已更新

**B1.5 _build_step 中 W7.1-W8 step handlers**（~行 1368-1450）需重写

**关键决策（#21-24）**：所有 W7.1-W8 步骤由 PES Controller 内部通过 SkillExecutor 直接执行，不经过 monitor.py。W7.1 的 4-Persona 调用使用 `concurrent.futures.ThreadPoolExecutor` 并行执行。

**新增 step handlers（W7.1 专属 — SkillExecutor 内部执行 + 并行）**：
```python
elif step_name == "invoke_four_personas_paper":
    # 内部并行执行 4 个 Persona 的 SkillExecutor 调用
    # 每个 Persona 使用独立的 SKILL.md（flux-paper-plan-persona-{1-4}）
    # 使用 concurrent.futures.ThreadPoolExecutor(max_workers=4) 并行
    import concurrent.futures

    regen_context = ""
    if state.get("needs_regeneration"):
        regen_context = f"\n\n**人工审稿意见（首要修改指导）**：\n{state.get('iteration_feedback', '')}"

    executor = self._get_skill_executor(state)
    ws = Path(state.get("workspace_dir", "."))
    plans_dir = ws / "paper_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    persona_prompts = [
        ("novel-academic", "flux-paper-plan-novel-academic"),
        ("conservative-academic", "flux-paper-plan-conservative-academic"),
        ("novel-engineering", "flux-paper-plan-novel-engineering"),
        ("conservative-engineering", "flux-paper-plan-conservative-engineering"),
    ]

    def _call_persona(persona_name, skill_name):
        return persona_name, executor.execute(skill_name, {
            "research_topic": state.get("research_topic", ""),
            "workspace_dir": str(ws),
            "venue": state.get("venue", "ICLR"),
            "regen_context": regen_context,
            "persona_name": persona_name,
            "w6_discussion": state.get("analysis_discussion", ""),
            "cc_atoms": state.get("claim_chain_atoms", ""),
        })

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_call_persona, pn, sn): pn for pn, sn in persona_prompts}
        for future in concurrent.futures.as_completed(futures):
            persona_name, result = future.result()
            results[persona_name] = result
            # 保存方案到 paper_plans/
            plan_file = plans_dir / f"plan_{persona_name}.json"
            plan_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "done": False, "phase": phase, "step": step_name,
        "step_index": state.get("sub_loop_step", 0) - 1,
        "action": "personas_completed",
        "persona_count": len(results),
        "plans_dir": str(plans_dir),
    }

elif step_name == "elo_tournament_paper":
    # PES 内部导入 EloTournament 类直接执行（不走 monitor.py）
    from pes_controller.elo.tournament import EloTournament

    ws = Path(state.get("workspace_dir", "."))
    plans_dir = ws / "paper_plans"
    executor = self._get_skill_executor(state)

    # 读取 4 个方案
    proposals = []
    for pf in sorted(plans_dir.glob("plan_*.json")):
        data = json.loads(pf.read_text(encoding="utf-8"))
        proposals.append({
            "id": pf.stem.replace("plan_", ""),
            "content": data.get("llm_response", ""),
        })

    tournament = EloTournament(llm_client=executor.llm_client, phase=phase)
    rankings = await tournament.rank(proposals)  # async（Decision #29：EloTournament 保持 async）

    # 保存 Elo 结果
    (plans_dir / "elo_results.json").write_text(
        json.dumps(rankings, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "done": False, "phase": phase, "step": step_name,
        "step_index": state.get("sub_loop_step", 0) - 1,
        "action": "elo_completed",
        "rankings": rankings,
    }

elif step_name == "verify_paper_plan_products":
    # 结构检查 + LLM 审稿维度初评（PES 内部执行）
    executor = self._get_skill_executor(state)
    result = executor.execute("flux-verify-paper-plan", {
        "workspace_dir": state.get("workspace_dir", "."),
        "product_spec": json.dumps(PRODUCT_SPECS.get(phase, {}), ensure_ascii=False),
    })
    return {
        "done": False, "phase": phase, "step": step_name,
        "step_index": state.get("sub_loop_step", 0) - 1,
        "action": "verify_completed",
        "result": result,
    }

elif step_name == "present_paper_plan_options":
    # 读取 elo_results.json + review_summary.json
    # 发 SSE paper_plan_options_ready 事件
    # 设置 awaiting_decision 状态 → sub_loop 将停止推进
    ws = Path(state.get("workspace_dir", "."))
    plans_dir = ws / "paper_plans"
    elo_data = json.loads((plans_dir / "elo_results.json").read_text(encoding="utf-8"))

    # 构建 SSE 事件数据
    options = []
    for r in elo_data.get("rankings", []):
        plan_file = plans_dir / f"plan_{r['id']}.json"
        plan_data = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
        options.append({
            "id": r["id"].upper(),
            "elo_rating": r.get("elo_rating", 1500),
            "scores": r.get("scores", {}),
            "title": plan_data.get("title", ""),
            "summary": plan_data.get("llm_response", "")[:500],
        })

    self._post_to_dashboard(
        state.get("session_id", ""), "paper_plan_options_ready",
        {"phase": phase, "options": options},
    )

    # 设置 awaiting_decision → sub_loop 下次调用将返回 wait_for_decision
    state["status"] = "awaiting_decision"
    self._write_state(state)

    return {
        "done": True, "phase": phase, "step": step_name,
        "step_index": state.get("sub_loop_step", 0) - 1,
        "action": "present_options",
        "options_type": "paper_plan",
        "options": options,
    }
```

**W7.2-W7.4 step handlers（SkillExecutor 内部执行）**：
```python
elif step_name == "invoke_skill_paper_figure":
    executor = self._get_skill_executor(state)
    result = executor.execute("flux-paper-figure", {
        "workspace_dir": state.get("workspace_dir", "."),
        "paper_plan": (Path(state.get("workspace_dir", ".")) / "PAPER_PLAN.md").read_text(encoding="utf-8") if (Path(state.get("workspace_dir", ".")) / "PAPER_PLAN.md").exists() else "",
    })
    return {"done": False, "phase": phase, "step": step_name,
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "skill_completed", "result": result}

elif step_name == "invoke_skill_paper_write":
    executor = self._get_skill_executor(state)
    ws = Path(state.get("workspace_dir", "."))
    result = executor.execute("flux-paper-write", {
        "workspace_dir": state.get("workspace_dir", "."),
        "paper_plan": (ws / "PAPER_PLAN.md").read_text(encoding="utf-8") if (ws / "PAPER_PLAN.md").exists() else "",
        "figures_includes": (ws / "figures" / "latex_includes.tex").read_text(encoding="utf-8") if (ws / "figures" / "latex_includes.tex").exists() else "",
        "venue": state.get("venue", "ICLR"),
    })
    return {"done": False, "phase": phase, "step": step_name,
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "skill_completed", "result": result}

elif step_name == "invoke_skill_paper_compile":
    executor = self._get_skill_executor(state)
    result = executor.execute("flux-paper-compile", {
        "workspace_dir": state.get("workspace_dir", "."),
    })
    return {"done": False, "phase": phase, "step": step_name,
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "skill_completed", "result": result}
```

**W7.5 多轮 step handlers**：
```python
elif step_name.startswith("invoke_skill_improve_review_"):
    round_num = step_name.split("_")[-1]
    executor = self._get_skill_executor(state)
    result = executor.execute("flux-paper-improve", {
        "workspace_dir": state.get("workspace_dir", "."),
        "round": round_num,
        "mode": "review",
        "research_topic": state.get("research_topic", ""),
    })
    # 发 SSE 事件
    self._post_to_dashboard(
        state.get("session_id", ""), "paper_review_round",
        {"round": int(round_num), "result": result},
    )
    return {"done": False, "phase": phase, "step": step_name,
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "skill_completed", "result": result}

elif step_name.startswith("invoke_skill_improve_fix_"):
    round_num = step_name.split("_")[-1]
    executor = self._get_skill_executor(state)
    result = executor.execute("flux-paper-improve", {
        "workspace_dir": state.get("workspace_dir", "."),
        "round": round_num,
        "mode": "fix",
    })
    return {"done": False, "phase": phase, "step": step_name,
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "skill_completed", "result": result}
```

**W8 多轮 step handlers**（类似模式，但使用 MiMo 模型）：
```python
elif step_name.startswith("invoke_skill_review_"):
    parts = step_name.split("_")
    # invoke_skill_review_round_1 / invoke_skill_review_fix_1 / invoke_skill_review_round_3
    if "round" in parts:
        round_num = parts[-1]
        mode = "review"
    else:
        round_num = parts[-1]
        mode = "fix"
    # W8 使用 MiMo 模型
    executor = self._get_skill_executor(state, use_mimo=True)
    result = executor.execute("flux-review-loop", {
        "workspace_dir": state.get("workspace_dir", "."),
        "round": round_num,
        "mode": mode,
    })
    return {"done": False, "phase": phase, "step": step_name,
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "skill_completed", "result": result}
```

**ELO_DIMENSIONS 更新**（`pes_controller/elo/tournament.py` 行 30-58）：

**EloTournament 重构**（Decision #29）：
- **构造函数**：`__init__(self, llm_client: LLMClient, k_factor=32.0, initial_rating=1500.0, max_rounds=None, phase="W2 问题分析")`
  - 替换原来的 `judge_model: str` 参数
  - `llm_client` 复用 SkillExecutor 的 LLMClient 实例（同一 API key/endpoint）
- **`_call_judge()` 方法**：从 httpx raw HTTP 改为调用 `self.llm_client.chat()`，用 `asyncio.to_thread` 包装（Decision #32）
  ```python
  async def _call_judge(self, prompt: str, use_phase_prompt: bool = False) -> str:
      system_prompt = self._judge_prompt if use_phase_prompt else _build_judge_prompt(self.phase)
      messages = [
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": prompt},
      ]
      # LLMClient.chat() 是同步的，用 asyncio.to_thread 避免阻塞事件循环
      content, _ = await asyncio.to_thread(
          self.llm_client.chat, messages, 1500, 0.1
      )
      return content
  ```
- **`rank()` 方法**：保持 `async`，在 `_build_step()` 中用 `await` 调用（MCP tool 是 async 上下文）
- **向后兼容**：W2-W4 的 Elo 调用也需要迁移到新接口（构造时传入 LLMClient）

**分层 Elo 评分体系**（根据 ARIS 全部 review 指标梳理）：

- **W7.1 论文计划**：使用"研究内容审阅"层维度（评的是计划而非成品）
- **W7.5 审稿修复**：使用"论文写作审阅"层维度（评成品论文质量）
- **W8 审阅**：使用两层混合维度（最终综合评审）

```python
"W7.1 论文计划": {
    "dimensions": ["elo_novelty", "validity", "impact", "story_coherence", "product_satisfaction"],
    "elo_novelty": "创新性——论文核心 Claim 是否具有非显而易见性？是否开辟新研究方向？",
    "validity": "可行性——逻辑漏洞检查：问题-方法-证据链条是否合理？假设是否经过论证？",
    "impact": "影响力——研究是否可能对领域产生显著影响？贡献是否够顶会水平？",
    "story_coherence": "叙事一致性——One-Sentence Contribution 是否清晰？What/Why/So What 叙事逻辑是否连贯？缺失实验是否影响核心故事？",
    "product_satisfaction": "产物规格满足度——是否包含：工作标题、Venue、Claims-Evidence Matrix、章节结构、图表计划、引用计划？",
    "scenario": "论文规划评审 — Program Committee",
},
"W7.5 审稿修复": {
    "dimensions": ["theoretical_rigor", "claims_evidence_alignment", "writing_clarity", "self_containedness", "notation_consistency"],
    "theoretical_rigor": "理论严谨性——假设-模型匹配度，数学推导是否完整",
    "claims_evidence_alignment": "声明-证据对齐——每个声明是否有实验支撑？是否存在不合理的声明？",
    "writing_clarity": "写作清晰度——表述是否自洽、易懂？叙事弱点是否已修复？",
    "self_containedness": "自含性——定理/引理是否独立可读？",
    "notation_consistency": "符号一致性——全文符号是否统一？",
    "scenario": "论文写作质量评审 — Writing Quality Committee",
},
"W8 审阅": {
    "dimensions": ["elo_novelty", "claims_evidence_alignment", "impact", "writing_clarity", "product_satisfaction"],
    "elo_novelty": "创新性——最终论文的核心贡献是否具有非显而易见性？",
    "claims_evidence_alignment": "声明-证据对齐——所有声明是否有充分实验证据？是否存在 cherry-picked results？",
    "impact": "影响力——研究对领域的长期价值",
    "writing_clarity": "写作清晰度——全文叙事是否连贯？格式是否合规（页数、引用）？",
    "product_satisfaction": "产物完整性——是否包含所有必需产物？",
    "scenario": "最终审阅 — Program Chair",
},
```

**B1.6 verify_deliverables**（~行 1452-1473）✅ 已添加

**B1.7 _auto_next_phase — 修复但保留**（行 2341-2363）

**保留原因**：
- W2-W6 的自动推进链（Plan1→Plan2→Ideate→Code→Analyze→Plan1/WritePlan）是有效的，减少人工操作负担
- 仅在**关键成果节点**（W7.1-W8）需要人工确认

**当前问题**：
1. 行 2357 引用 `PHASE_WRITE` → 应为 `PHASE_WRITE_PLAN`
2. 行 2359 `elif phase == PHASE_WRITE:` → 删除（W7 已拆为子阶段）
3. 行 2362 `return PHASE_WRITE` → 删除（W8 后的 transition 由人工选择）

**修改方案**：
```python
def _auto_next_phase(self, phase: str, state: dict) -> str | None:
    """W2-W6 自动推进；W7.1-W8 返回 None 要求人工选择。"""
    if phase == PHASE_PLAN_1:   return PHASE_PLAN_2
    elif phase == PHASE_PLAN_2: return PHASE_IDEATE
    elif phase == PHASE_IDEATE: return PHASE_CODE
    elif phase == PHASE_CODE:   return PHASE_ANALYZE
    elif phase == PHASE_ANALYZE:
        target = self._read_success_target()
        if target is not None:
            fs = self.fitness.get_stats()
            best = fs.get("global", {}).get("max_score", 0)
            if best >= target:
                return PHASE_WRITE_PLAN  # 进入论文写作（修复：PHASE_WRITE → PHASE_WRITE_PLAN）
        return PHASE_PLAN_1  # 未达标→回到Plan-1
    # W7.1-W7.5, W8: 关键成果节点，返回 None 要求人工确认
    return None
```

**B1.8 transition_phase — 修复+扩展（行 2295-2339）**

**当前问题诊断**（为什么必须修改）：

| 问题 | 行号 | 具体代码 | 运行时后果 |
|---|---|---|---|
| NameError: PHASE_WRITE 未定义 | 2316 | `state["phase"] = PHASE_WRITE` | `unsatisfied` 在 W8 阶段触发时直接崩溃 |
| NameError: PHASE_WRITE 未定义 | 2327 | `state["phase"] = PHASE_WRITE` | `jump_to_write` 直接触发 NameError |
| NameError: PHASE_WRITE 未定义 | 2331 | `return {"to": PHASE_WRITE}` | 同上 |
| 设计缺陷: 只有4个固定action | 2295 | 无 target_phase 参数 | 无法支持 Dashboard 多方案选择 UI |
| 硬编码: jump_to_write 不兼容 | 2323-2331 | PHASE_WRITE 单一目标 | W7 拆为 5 子阶段后应跳到 W7.1 |
| unsatisfied 跳转到错误 phase | 2314-2321 | 无条件跳 PHASE_WRITE | 应改为重做当前 phase（redo） |

**修改方案**：修复 NameError + 新增 `advance`/`redo_with_review` action

```python
def transition_phase(self, action: str, target_phase: str | None = None,
                     feedback: str = "", selected_plan: str | None = None) -> dict:
    """Dashboard 调用的阶段流转方法。

    Actions:
        satisfied       — W2-W6 自动推进（调用 _auto_next_phase）
        advance         — W7.1-W8 人工选择目标 phase（必须提供 target_phase）
        redo            — 重做当前 phase（sub_loop_step 归零）
        redo_with_review— 带人工审稿意见的重做（回到当前 phase 开头）
        jump_to_plan    — 跳回 W2 问题分析
        terminate       — 终止流水线
    """
    state = self._read_state()
    phase = state["phase"]

    if action == "satisfied":
        # W2-W6 自动推进
        next_phase = self._auto_next_phase(phase, state)
        if next_phase is None:
            return {"error": f"阶段 '{phase}' 需要显式选择目标（advance action）",
                    "valid_targets": TRANSITIONS.get(phase, [])}
        state["phase"] = next_phase
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        if phase == PHASE_ANALYZE:
            state["iteration"] = state.get("iteration", 0) + 1
        self._write_state(state)
        self._post_to_dashboard(
            state.get("session_id", ""), "phase_changed",
            {"from": phase, "to": next_phase},
        )
        return {"transitioned": True, "from": phase, "to": next_phase}

    elif action == "advance":
        # W7.1-W8 人工显式选择
        if target_phase is None:
            return {"error": "advance 需要 target_phase 参数",
                    "valid_targets": TRANSITIONS.get(phase, [])}
        valid = TRANSITIONS.get(phase, [])
        if target_phase not in valid:
            return {"error": f"不允许从 '{phase}' 转到 '{target_phase}'",
                    "valid_targets": valid}
        # 处理选中的方案（W7.1 选择后写入 PAPER_PLAN.md）
        if selected_plan and phase == PHASE_WRITE_PLAN:
            self._activate_selected_plan(state, selected_plan)
        # 处理回退到 W7.1 的归档
        if target_phase == PHASE_WRITE_PLAN and phase != PHASE_WRITE_PLAN:
            self._archive_current_products(state)
            state["paper_iteration"] = state.get("paper_iteration", 0) + 1
        state["phase"] = target_phase
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        if feedback:
            state["iteration_feedback"] = feedback
        self._write_state(state)
        self._post_to_dashboard(
            state.get("session_id", ""), "phase_changed",
            {"from": phase, "to": target_phase},
        )
        return {"transitioned": True, "from": phase, "to": target_phase}

    elif action == "redo":
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        if feedback:
            state["iteration_feedback"] = feedback
        self._write_state(state)
        return {"transitioned": False, "phase": phase,
                "message": f"重做阶段 '{phase}'"}

    elif action == "redo_with_review":
        # 带人工审稿意见的重做 → 回到当前 phase 开头
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        state["needs_regeneration"] = True
        if feedback:
            state["iteration_feedback"] = feedback
        self._write_state(state)
        return {"transitioned": False, "phase": phase,
                "message": f"带审稿意见重做 '{phase}'，反馈: {feedback}"}

    elif action == "jump_to_plan":
        state["phase"] = PHASE_PLAN_1
        state["sub_loop_step"] = 0
        state["status"] = "in_progress"
        if feedback:
            state["iteration_feedback"] = feedback
        self._write_state(state)
        return {"transitioned": True, "from": phase, "to": PHASE_PLAN_1}

    elif action == "terminate":
        state["phase"] = PHASE_TERMINATED
        state["status"] = "terminated"
        self._write_state(state)
        return {"transitioned": True, "to": PHASE_TERMINATED}

    return {"error": f"Unknown action: {action}"}

def _activate_selected_plan(self, state, selected_plan: str):
    """将选中的方案写入 PAPER_PLAN.md 和 NARRATIVE_REPORT.md"""
    # 方案 ID 映射（Decision #31）
    PLAN_DISPLAY_MAP = {
        "A": "novel-academic",
        "B": "conservative-academic",
        "C": "novel-engineering",
        "D": "conservative-engineering",
    }
    persona_name = PLAN_DISPLAY_MAP.get(selected_plan.upper(), selected_plan)

    ws = Path(state.get("workspace_dir", "."))
    plans_dir = ws / "paper_plans"
    plan_file = plans_dir / f"plan_{persona_name}.json"
    if plan_file.exists():
        import json as _json
        data = _json.loads(plan_file.read_text(encoding="utf-8"))
        # 解析 LLM 响应（data 结构: {success, files_written, actions_executed, llm_response}）
        llm_raw = data.get("llm_response", "")
        # 尝试解析 LLM 返回的 JSON
        try:
            plan_data = _json.loads(llm_raw)
        except (_json.JSONDecodeError, TypeError):
            plan_data = {"method_sketch": llm_raw, "hypothesis": ""}
        # 写入 PAPER_PLAN.md
        (ws / "PAPER_PLAN.md").write_text(
            plan_data.get("method_sketch", llm_raw), encoding="utf-8")
        # 写入 NARRATIVE_REPORT.md
        (ws / "NARRATIVE_REPORT.md").write_text(
            f"# 研究叙事报告\n\n## 核心发现\n{plan_data.get('hypothesis', '')}",
            encoding="utf-8")

def _archive_current_products(self, state):
    """归档当前产物到 archive_iter_{N}/"""
    import shutil
    ws = Path(state.get("workspace_dir", "."))
    iteration = state.get("paper_iteration", 0)
    archive_dir = ws / "paper_plans" / f"archive_iter_{iteration}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in ["PAPER_PLAN.md", "NARRATIVE_REPORT.md"]:
        src = ws / f
        if src.exists():
            shutil.copy2(str(src), str(archive_dir / f))
```

**变更总结**：
- **修复** 3 处 `PHASE_WRITE` NameError
- **保留** `satisfied` action → W2-W6 自动推进
- **新增** `advance` action → W7.1-W8 人工选择目标 phase + `selected_plan` 参数
- **新增** `redo_with_review` action → 带人工审稿意见重做当前 phase
- **替换** `unsatisfied` → `redo`
- **替换** `jump_to_write` → `advance` + `target_phase=PHASE_WRITE_PLAN`
- **新增** `_activate_selected_plan` → W7.1 多方案选择后写入文件
- **新增** `_archive_current_products` → 回退时归档产物

**B1.9 _get_skill_executor 方法**（已被 B1.5 各 step handler 引用）
```python
def _get_skill_executor(self, state: dict, use_mimo: bool = False) -> SkillExecutor:
    """获取 SkillExecutor 实例。默认用 DeepSeek，W8 用 MiMo。"""
    skills_dir = Path(__file__).parent.parent / "skills"
    if use_mimo:
        llm = LLMClient(
            api_key=os.environ.get("MIMO_API_KEY", ""),
            base_url=os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"),
            model=os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
        )
    else:
        llm = LLMClient(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    return SkillExecutor(skills_dir, llm)
```

**B1.10 删除所有 PHASE_WRITE 引用**

搜索 `PHASE_WRITE` 但不是 `PHASE_WRITE_PLAN` / `PHASE_WRITE_FIGURE` 等的引用，全部替换。

### B2. 删除 stages.py

**操作**：删除 `pes_controller/stages.py`

### B3. 更新 __init__.py

```python
"""PES Controller - Pipeline Evolution System controller layer."""
from pes_controller.controller import (
    PESController,
    PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE, PHASE_CODE,
    PHASE_ANALYZE,
    PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
    PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE,
    PHASE_REVIEW, PHASE_TERMINATED,
    AUTO_ADVANCE_PHASES, PHASES,
    TRANSITIONS, CHAIN_STEPS, FOUR_PERSONA_AGENTS,
    AGENT_ROLES, PRODUCT_SPECS,
)
```

### B4. Phase 文件

**删除**：
- `pes_controller/phases/w7_01_invoke_skill_write.py`
- `pes_controller/phases/w8_01_invoke_skill_review.py`

**创建**（6 个新文件，内容见 v2 计划，此处不重复）：
- w7_01_paper_plan.py, w7_02_paper_figure.py, w7_03_paper_write.py
- w7_04_paper_compile.py, w7_05_paper_improve.py, w8_01_flux_review.py

### B5. 删除 Agent SDK 相关

**删除文件**：
- `plugins/experimentation/agent_task.py`

**从 controller.py 删除**：
- `AGENT_SDK_PHASES` 常量（不再需要区分 Agent SDK 阶段）

**从 monitor.py 删除**：
- `AGENT_SDK_PHASES` 覆写
- `_spawn_agent_task` 函数
- `_is_agent_running` 函数
- Agent SDK spawn 逻辑（~行 2495-2501）

### B6. 清理不用的 evo-* skill 目录

**保留**（4 个）：
- `skills/evo-pipeline/` — 一键启动流水线
- `skills/evo-code-agent-pre/` — W5 代码实现前置
- `skills/evo-code-agent-check/` — W5 中期检查
- `skills/evo-code-agent-post/` — W5 完成确认

**删除**（17 个 skill 目录）：
- `skills/evo-analyze/` — 核心功能已在 monitor.py `_do_scan_islands_rubrics()`
- `skills/evo-boot/`
- `skills/evo-claim/` — 核心功能已在 monitor.py `_do_write_claim_chain()`
- `skills/evo-code/`
- `skills/evo-debug/`
- `skills/evo-evolve/`
- `skills/evo-ideation/`
- `skills/evo-intake/`
- `skills/evo-iterate/` — 核心功能已在 monitor.py `_do_island_assign()`
- `skills/evo-memory/`
- `skills/evo-planner/`
- `skills/evo-refine/`
- `skills/evo-research/`
- `skills/evo-review/` — 旧 W8，被 flux-review-loop 替代
- `skills/evo-run/`
- `skills/evo-write/` — 旧 W7，被 flux-paper-* 替代
- `skills/research-wiki/`

---

## 模块 C：SKILL.md Prompt 模板

### C0. SKILL.md 格式规范

每个 SKILL.md 分为两个区域：
1. **YAML frontmatter**：元数据（name, description, argument-hint）
2. **Prompt 正文**：发送给 LLM 的 prompt 内容

**变量占位符**：`{{variable_name}}`，由 SkillExecutor 在执行时替换。

**JSON 输出格式约定**（写在每个 SKILL.md 末尾）：

```markdown
## 输出格式

你必须返回 JSON 格式：
​```json
{
  "files": [
    {"path": "相对路径", "content": "文件内容"}
  ],
  "actions": [
    {"command": "shell 命令"}
  ],
  "summary": "本次操作的简要描述"
}
​```
```

### C1-C15. 15 个 SKILL.md 文件

每个 skill 的详细工作流、输入、输出如下表：

| Skill | Phase | 输入 | 输出文件 | 多轮 |
|---|---|---|---|---|
| flux-paper-plan-novel-academic | W7.1 | research_topic, venue, regen_context | paper_plans/plan_novel-academic.json（含 title, hypothesis, method_sketch） | 否 |
| flux-paper-plan-conservative-academic | W7.1 | 同上 | paper_plans/plan_conservative-academic.json | 否 |
| flux-paper-plan-novel-engineering | W7.1 | 同上 | paper_plans/plan_novel-engineering.json | 否 |
| flux-paper-plan-conservative-engineering | W7.1 | 同上 | paper_plans/plan_conservative-engineering.json | 否 |
| flux-verify-paper-plan | W7.1 | paper_plans/*, product_spec | paper_plans/review_summary.json | 否 |
| flux-paper-figure | W7.2 | PAPER_PLAN.md, 实验数据 | figures/*.pdf, figures/latex_includes.tex, figures/gen_*.py | 否 |
| flux-paper-write | W7.3 | PAPER_PLAN.md, figures/, templates/ | paper/main.tex, paper/sections/*.tex, paper/references.bib, paper/math_commands.tex | 否 |
| flux-paper-compile | W7.4 | paper/ | paper/main.pdf | 否 |
| flux-paper-improve | W7.5 | paper/main.pdf, round, mode(review/fix) | paper/main.pdf(改进), PAPER_IMPROVEMENT_LOG.md, PAPER_IMPROVEMENT_STATE.json | **是**（2轮） |
| flux-review-loop | W8 | paper/main.pdf, PAPER_PLAN.md, round, mode(review/fix) | AUTO_REVIEW.md, REVIEW_STATE.json, CLAIMS_FROM_RESULTS.md | **是**（3轮） |
| flux-result-to-claim | 辅助 | 实验结果 | CLAIMS_FROM_RESULTS.md | 否 |
| flux-novelty-check | 辅助 | 方法描述, 相关工作 | NOVELTY_ASSESSMENT.md | 否 |
| flux-proof-writer | 辅助 | 定理/命题 | PROOF_PACKAGE.md | **是**（多轮） |
| flux-formula-derivation | 辅助 | 问题陈述 | DERIVATION.md | 否 |
| flux-paper-illustration | 辅助 | 插图描述 | figures/illustration_*.pdf | 否 |

**4 个 Persona SKILL.md 的区别**：每个 persona 的 SKILL.md 有不同的 system prompt 和评审倾向：
- `flux-paper-plan-novel-academic`：倾向理论创新，鼓励高风险高回报的新范式
- `flux-paper-plan-conservative-academic`：倾向理论严谨性，强调已有理论的扩展而非颠覆
- `flux-paper-plan-novel-engineering`：倾向工程创新，鼓励新架构/新算法
- `flux-paper-plan-conservative-engineering`：倾向工程可靠性，强调可复现性和渐进改进

每个 persona 的 SKILL.md 共享相同的输入变量（research_topic, venue, regen_context, persona_name）和输出格式（JSON: title, hypothesis, method_sketch, search_results_summary），但 prompt 中的评审倾向和关注点不同。

**每个 SKILL.md 的具体 prompt 内容**将在实施阶段参考 ARIS 源文件编写。此处定义的是**接口契约**（输入/输出/是否多轮），确保 1000 个 agent 并行开发时可正确拼接。

---

## 模块 D：Dashboard 全量更新

### D0. UI 设计参考：claude-fleet（Decision #30）

**参考项目**：[claude-fleet](https://github.com/tianyilt/claude-fleet)（Alpine.js + Tailwind 单文件 SPA + FastAPI SSE）

**可复用模式**：
| claude-fleet 模式 | Flux-Insight 对应 |
|---|---|
| 卡片式 session 列表 | W7.1 多方案选择卡片（方案A/B/C 各一张卡片） |
| triage 状态分类（working/waiting/stalled/completed） | phase 状态分类（in_progress/awaiting_decision/error/completed） |
| SSE 实时推送 + Alpine.js 响应式绑定 | `paper_plan_options_ready` 事件触发 UI 更新 |
| Timeline 视图 | W7.5/W8 审稿历史（每轮评分变化） |
| skill/memory 统计面板 | 产物侧边栏（PDF/TeX/BibTeX 预览） |
| 单文件 `static/index.html` | Flux-Insight 已有 `_PES_PIPELINE_CONTROL_HTML` 内嵌前端 |

**Flux-Insight Dashboard 技术栈**（与 claude-fleet 一致）：
- 后端：Starlette（已有）+ SSE
- 前端：Alpine.js + Tailwind CDN（已有）
- 所有前端代码内嵌在 `monitor.py` 的 `_PES_PIPELINE_CONTROL_HTML` 字符串中

**新增前端组件**（W7.1-W8）：
1. **方案选择卡片** — W7.1 多方案展示（Elo + 5维分数雷达图 + 摘要）
2. **产物确认面板** — W7.2-W7.4 产物列表 + 预览
3. **审稿历史时间线** — W7.5/W8 每轮评分变化
4. **多方案操作栏** — A/B/C 选择 + D 审稿意见 + E 退回

### D1. monitor.py 修改清单

**D1.1 Imports**（~行 27）
```python
from pes_controller import (
    PESController, PHASE_PLAN_1, PHASE_CODE,
    PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
    PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE, PHASE_REVIEW,
    PRODUCT_SPECS, TRANSITIONS,
)
```

**D1.2 删除 AGENT_SDK_PHASES**（~行 69）
删除整行，不再区分 Agent SDK 阶段。

**D1.3 删除 Agent SDK spawn 逻辑**（~行 2495-2501）
删除 `if phase in AGENT_SDK_PHASES:` 整个分支。

**D1.4 前端 JS PHASES 常量**（~行 1019-1028）
```javascript
const PHASES = [
    "W2 问题分析","W3 方案方向","W4 具体方案生成",
    "W5 代码实现","W6 结果分析",
    "W7.1 论文计划","W7.2 图表生成","W7.3 LaTeX写作",
    "W7.4 编译","W7.5 审稿修复",
    "W8 审阅","已终止"
];
const CHAIN_STEPS = {
    "W7.1 论文计划": ["invoke_four_personas_paper", "elo_tournament_paper",
                       "verify_paper_plan_products", "present_paper_plan_options"],
    "W7.2 图表生成": ["invoke_skill_paper_figure", "verify_deliverables"],
    "W7.3 LaTeX写作": ["invoke_skill_paper_write", "verify_deliverables"],
    "W7.4 编译": ["invoke_skill_paper_compile", "verify_deliverables"],
    "W7.5 审稿修复": ["invoke_skill_improve_review_1", "invoke_skill_improve_fix_1",
                       "invoke_skill_improve_review_2", "invoke_skill_improve_fix_2",
                       "verify_deliverables"],
    "W8 审阅": ["invoke_skill_review_round_1", "invoke_skill_review_fix_1",
                 "invoke_skill_review_round_2", "invoke_skill_review_fix_2",
                 "invoke_skill_review_round_3", "verify_deliverables"]
};
```

**D1.5 硬编码字符串替换**
所有 `"W7 论文写作"` → `PHASE_WRITE_PLAN`

**D1.5.1 monitor.py 对 W7.1-W8 的角色变化**（重要）

由于 Decision #21（W7.1-W8 全部通过 SkillExecutor 内部执行），monitor.py 对 W7.1-W8 的角色从"执行者"变为"展示者+转发者"：

| monitor.py 功能 | W2-W6（不变） | W7.1-W8（新） |
|---|---|---|
| `_execute_step()` 执行 step | 是（4-Persona, Elo 等） | **否**（PES 内部执行） |
| 显示 SSE 事件 | 是 | 是（paper_plan_options_ready, skill_completed 等） |
| Transition API 转发 | 是（satisfied/redo） | 是（advance/redo/redo_with_review/terminate） |
| 显示 sub_loop() 返回值 | 是 | 是（但不执行，仅展示结果） |
| AgentManager 调用 | 是（4-Persona） | **否** |

**monitor.py `_execute_step()` 需要的修改**：
- W7.1-W8 的 step 由 `sub_loop()` 内部 `_build_step()` 直接执行完毕
- `sub_loop()` 返回的 dict 已包含执行结果（`action: "personas_completed"`, `action: "skill_completed"` 等）
- monitor.py 的 `_execute_step()` 只需检查：如果返回的 action 不在已知的外部执行列表（`invoke_personas`, `multi_agent` 等）中，直接跳过执行，将结果透传给 Dashboard
- 具体实现：在 `_execute_step()` 开头加一个判断，W7.1-W8 phase 的 step 直接 `pass`（不执行），仅转发结果

**D1.6 Transition API 更新**（~行 1787）

**修改原因**：当前 API 只支持 `satisfied/unsatisfied/jump_to_write/terminate`，缺少 `advance`（W7.1-W8 人工选择）和 `redo`（重做当前 phase）。

```python
async def pes_pipeline_transition_api(request):
    body = await request.json()
    workspace_dir = body.get("workspace_dir", "")
    action = body.get("action", "")         # satisfied(W2-W6)|advance(W7-W8)|redo|jump_to_plan|terminate
    target_phase = body.get("target_phase")  # advance 时必须提供
    feedback = body.get("feedback", "")

    ctrl = PESController(state_path)
    result = ctrl.transition_phase(action, target_phase=target_phase, feedback=feedback)
    return JSONResponse(result)
```

**D1.7 新增 Dashboard 路由**
- `GET /api/deliverables/{session_id}` — 产物列表+验证状态
- `GET /api/phase-content/{session_id}/{file_path:path}` — 产物内容预览
- `GET /api/transition-options/{session_id}` — 获取当前 phase 的合法 transition 选项

**D1.8 多方案 UI**
Dashboard 根据 phase 类型决定 UI 模式：

**W2-W6（自动模式）**：
- `satisfied` → `{"action": "satisfied"}` 自动推进
- `redo` → `{"action": "redo"}` 重做当前 phase

**W7.1（多方案选择模式）**：
- 从 SSE 事件 `paper_plan_options_ready` 获取方案列表
- 每个方案渲染为卡片（标题 + Elo + 5维分数 + 摘要）
- A/B/C 按钮 → `{"action": "advance", "target_phase": "W7.2 图表生成", "selected_plan": "A/B/C"}`
- D: 审稿意见文本框 → `{"action": "redo_with_review", "feedback": "..."}`
- E: 退回重新生成 → `{"action": "redo"}`
- 回到W7.1/回到W5/回到W2 按钮 → `{"action": "advance", "target_phase": "W7.1/W5/W2"}`

**W7.2-W7.4（产物确认模式）**：
- A: 继续到下一 phase → `{"action": "advance", "target_phase": "下一个phase"}`
- B: 审稿意见 → `{"action": "redo_with_review", "feedback": "..."}`
- C: 退回重新生成 → `{"action": "redo"}`
- 回到W7.1/回到W5/回到W2 按钮

**W7.5（审稿历史模式）**：
- 同产物确认模式 + 审稿历史（每轮评分变化）
- A: 继续到 W8 → `{"action": "advance", "target_phase": "W8 审阅"}`
- B/C/回退 同上

**W8（最终审阅模式）**：
- A: 完成终止 → `{"action": "terminate"}`
- B: 回到W7.1 → `{"action": "advance", "target_phase": "W7.1 论文计划"}`
- C: 回到W5 → `{"action": "jump_to_plan"}`
- D: 审稿意见 → `{"action": "redo_with_review", "feedback": "..."}`
- 回到W2 → `{"action": "jump_to_plan"}`

### D2. watchdog.py 更新

- **删除** `AGENT_SDK_PHASES` 引用（Decision #19：彻底删除 Agent SDK）
- 更新 phase 名称匹配（W7.1-W7.5, W8）

---

## 模块 E：Legacy 同步

更新以下文件中的 PHASE_WRITE/"W7 论文写作"引用：
- `tools_legacy/pes_controller.py`
- `tools_legacy/pipeline_watchdog.py`
- `agent-manager_legacy/evo_agent_manager/dashboard.py`
- `plugins/experimentation/agent_task.py` → **删除**

---

## 模块 F：集成 + 测试

### F1. CLAUDE.md 更新

在 Skill Map 中添加 flux-* skill 列表。

### F2. evo-review/SKILL.md

添加 PES 集成说明。

### F3. 单元测试

**文件**：`tests/test_flux_skills.py`

测试类：
1. `TestPhaseConstants` — 验证所有 phase 常量、PHASES 顺序、TRANSITIONS、CHAIN_STEPS
2. `TestPhaseFiles` — 验证新 phase 文件存在、旧文件已删
3. `TestSkillFiles` — 验证 15 个 SKILL.md 存在且格式正确
4. `TestConfig` — 验证 flux-config JSON 文件有效
5. `TestMonitorImports` — 验证 monitor.py 使用新 phase 常量
6. `TestControllerTransitions` — 验证 controller.py 无旧 PHASE_WRITE 引用
7. `TestLLMClient` — 验证 LLMClient 初始化
8. `TestSkillExecutor` — 验证 SKILL.md 解析和变量填充
9. `TestSessionManager` — 验证多轮对话状态管理

### F4. 手动 E2E

1. `python -c "from pes_controller import PHASE_WRITE_PLAN; print(PHASE_WRITE_PLAN)"` → 输出 "W7.1 论文计划"
2. PES transition: W6 satisfied → 应返回合法目标列表（含 W7.1）
3. 每个skill加载测试
4. Dashboard 显示 W7.1-W7.5 阶段
5. Multi-option transition UI 工作正常

---

## 补充规格索引（第3轮讨论）

| # | 问题 | 决策 | 对应主决策 |
|---|---|---|---|
| S1 | 多轮执行模型 | **每轮一个 sub_loop 调用**，CHAIN_STEPS 中拆分 | → #21 |
| S2 | 上下文传递 | **SkillExecutor 读取文件 → 拼接 prompt** | → #22 |
| S3 | 错误处理 | **停止 + 人工介入** | — |
| S4 | 测试 LLM | **用 DeepSeek 真实调用** | → #27 |
| S5 | 多轮 CHAIN_STEPS | **每轮拆为 review+fix 两步** | → #21 |
| S6 | 会话持久化 | **单独 session 文件**（.llm_session.json） | → #34 |
| S7 | 变量定义 | **在 SKILL.md frontmatter 中声明** | — |
| S8 | JSON 强制 | **Prompt 指令 + 重试** | — |

---

## 补充规格：多轮 CHAIN_STEPS

### flux-paper-improve（W7.5）— 2 轮

```python
PHASE_WRITE_IMPROVE: [
    "invoke_skill_improve_review_1",   # 第1轮审稿
    "invoke_skill_improve_fix_1",      # 第1轮修复
    "invoke_skill_improve_review_2",   # 第2轮审稿
    "invoke_skill_improve_fix_2",      # 第2轮修复
    "verify_deliverables",
],
```

### flux-review-loop（W8）— 3 轮

```python
PHASE_REVIEW: [
    "invoke_skill_review_round_1",     # 第1轮审稿
    "invoke_skill_review_fix_1",       # 第1轮修复
    "invoke_skill_review_round_2",     # 第2轮审稿
    "invoke_skill_review_fix_2",       # 第2轮修复
    "invoke_skill_review_round_3",     # 第3轮审稿（最终）
    "verify_deliverables",
],
```

### 会话文件

**路径**：`workspace/.llm_session.json`
**格式**：
```json
{
  "skill_name": "flux-paper-improve",
  "messages": [
    {"role": "system", "content": "你是论文审稿专家..."},
    {"role": "user", "content": "审稿第1轮..."},
    {"role": "assistant", "content": "{\"files\":[...],\"actions\":[...]}"},
    {"role": "user", "content": "修复以下问题..."},
    {"role": "assistant", "content": "{\"files\":[...],\"actions\":[...]}"}
  ],
  "round": 2,
  "created_at": "2026-06-04T12:00:00",
  "updated_at": "2026-06-04T12:05:00"
}
```

---

## 补充规格：SKILL.md Frontmatter 变量声明

```yaml
---
name: flux-paper-plan
description: "生成论文大纲。"
argument-hint: [research-topic]
variables:
  - name: research_topic
    source: state.research_topic
    required: true
  - name: workspace_dir
    source: state.workspace_dir
    required: true
  - name: venue
    source: state.venue
    default: "ICLR"
  - name: narrative_report
    source: file:NARRATIVE_REPORT.md
    required: false
---
```

**变量来源类型**：
- `state.xxx` — 从 PIPELINE_STATE.json 读取
- `file:XXX` — 从 workspace 目录读取文件内容
- `default:YYY` — 默认值

---

## 补充规格：错误处理流程

```
LLM 调用失败（网络/超时/API错误）
    → 重试 1 次（间隔 5 秒）
    → 仍失败 → 设置 state.status = "error"
    → 发 SSE 事件 error
    → Dashboard 显示错误信息
    → 等待人工介入（重试/跳过/终止）

LLM 返回无效 JSON
    → 重试 1 次，附加 prompt "请返回有效 JSON"
    → 仍无效 → 同上错误处理

文件写入失败（权限/磁盘）
    → 同上错误处理

命令执行失败（latexmk 等）
    → 同上错误处理
```

---

## 补充规格：测试配置

```python
# tests/conftest.py
import os

# 测试用 DeepSeek（比 MiMo 便宜）
os.environ.setdefault("LLM_TEST_API_KEY", "")
os.environ.setdefault("LLM_TEST_BASE_URL", "https://api.deepseek.com/v1")
os.environ.setdefault("LLM_TEST_MODEL", "deepseek-chat")
```

---

## W7/W8 完整迭代流程规格

### W7.1 论文计划（多方案 + Elo + 人工选择，4步）

**核心机制**：复用 W2-W4 的 4-Persona 创意生成 + Elo 锦标赛，生成 3+ 个完整论文计划方案，LLM 初评 + 人工选择。

**CHAIN_STEPS**：
```python
PHASE_WRITE_PLAN: [
    "invoke_four_personas_paper",  # 4-Persona 生成 3+ 论文计划方案
    "elo_tournament_paper",        # Elo 锦标赛评分排名
    "verify_paper_plan_products",  # 产物验证（结构检查 + LLM 审稿维度初评）
    "present_paper_plan_options",  # 向 Dashboard 展示多方案 + 评分 + 等待人工选择
],
```

**Elo 评分维度**（新增 W7.1 专属维度，复用 `pes_controller/elo/tournament.py`）：
```python
"W7.1 论文计划": {
    "dimensions": ["elo_novelty", "validity", "impact", "story_coherence", "product_satisfaction"],
    "elo_novelty": "创新性——论文的核心Claim是否具有非显而易见性？是否提出新的理论视角或方法论创新？",
    "validity": "可行性——Claims-Evidence Matrix中的证据链是否充分？实验数据是否支撑每个Claim？",
    "impact": "影响力——研究是否可能对领域产生显著影响？成果是否可复用？",
    "story_coherence": "叙事一致性——One-Sentence Contribution 是否清晰？What/Why/So What 叙事逻辑是否连贯？",
    "product_satisfaction": "产物规格满足度——是否包含：工作标题、Venue、Claims-Evidence Matrix、章节结构、图表计划、引用计划？",
    "scenario": "论文规划评审 — Program Committee",
}
```

```
触发：Dashboard POST /api/pipeline/transition {"action":"advance","target_phase":"W7.1 论文计划"}
  ↓
PES Controller: state.phase = "W7.1 论文计划", sub_loop_step = 0
  ↓
── sub_loop #1: invoke_four_personas_paper ──
  复用 W2-W4 的 invoke_four_personas 机制：
  - 4 个 Persona（novel-academic, conservative-academic, novel-engineering, conservative-engineering）
  - 每个 Persona 独立生成一份完整论文计划（PAPER_PLAN.md 格式）
  - Prompt 注入：
    research_topic + venue + W6 讨论记录 + cc.db atoms + PRODUCT_SPECS
  - 每个 Persona 返回 JSON：
    {
      "title": "论文工作标题",
      "hypothesis": "核心假设",
      "method_sketch": "完整论文计划内容（Claims-Evidence Matrix + 章节结构 + 图表计划 + 引用计划）",
      "search_results_summary": "文献搜索摘要"
    }
  - PES 将 4 个 Persona 的输出保存为：
    workspace/paper_plans/plan_persona_1.json ~ plan_persona_4.json
  ↓
── sub_loop #2: elo_tournament_paper ──
  复用 pes_controller/elo/tournament.py 的 EloTournament：
  - 输入：4 个 Persona 方案的 method_sketch
  - Full round-robin pairwise comparison（6 场对决）
  - LLM judge（DeepSeek）使用 W7.1 专属 5 维评分
  - 输出：排名 + Elo 分 + 各维度分数
  - 保存：workspace/paper_plans/elo_results.json
  ↓
── sub_loop #3: verify_paper_plan_products ──
  结构检查 + LLM 审稿维度初评：
  1. 对每个方案执行 _STRUCTURAL_PATTERNS 检查：
     - Claims-Evidence Matrix 是否包含？
     - 章节结构是否完整？
     - 图表计划是否列出？
     - 引用计划是否包含？
  2. LLM 初步审稿评价（使用 W8 论文写作质量维度）：
     - 创新性指标 (1-10)
     - 影响力指标 (1-10)
     - 叙事一致性 (1-10)
     - 证据充分性 (1-10)
  3. 综合 Elo 排名 + LLM 审稿分数 → 最终排名
  4. 保存：workspace/paper_plans/review_summary.json
  ↓
── sub_loop #4: present_paper_plan_options ──
  PES 发 SSE 事件到 Dashboard：
  {
    "type": "paper_plan_options_ready",
    "data": {
      "phase": "W7.1 论文计划",
      "options": [
        {
          "id": "A",
          "title": "方案A: 基于xxx的...",
          "elo_rating": 1623,
          "scores": {"elo_novelty": 7.5, "validity": 8.2, "impact": 6.8, "story_coherence": 7.0, "product_satisfaction": 9.0},
          "summary": "完整论文计划摘要...",
          "content_preview": "前500字..."
        },
        {
          "id": "B", ...
        },
        {
          "id": "C", ...
        }
      ],
      "review_summary": "总体评价...",
      "actions": [
        {"id": "A", "label": "采用方案A", "action": "advance", "target_phase": "W7.2 图表生成"},
        {"id": "B", "label": "采用方案B", "action": "advance", "target_phase": "W7.2 图表生成"},
        {"id": "C", "label": "采用方案C", "action": "advance", "target_phase": "W7.2 图表生成"},
        {"id": "D", "label": "提供审稿意见，回到W7重新开始", "action": "redo_with_review"},
        {"id": "E", "label": "退回W7重新生成", "action": "redo"}
      ]
    }
  }
  ↓
Dashboard 展示：
  ┌──────────────────────────────────────────────────────┐
  │ W7.1 论文计划 — 多方案选择                            │
  │                                                      │
  │ ┌─ 方案A ─ Elo: 1623 ─────────────────────────────┐ │
  │ │ 标题: 基于xxx的...                               │ │
  │ │ 创新: ████████░░ 7.5  影响: ██████░░░░ 6.8      │ │
  │ │ 可行: █████████░ 8.2  叙事: ████████░░ 7.0      │ │
  │ │ 规格: █████████░ 9.0                              │ │
  │ │ [查看完整计划] [采用方案A]                         │ │
  │ └──────────────────────────────────────────────────┘ │
  │ ┌─ 方案B ─ Elo: 1587 ─────────────────────────────┐ │
  │ │ ...                                              │ │
  │ └──────────────────────────────────────────────────┘ │
  │ ┌─ 方案C ─ Elo: 1542 ─────────────────────────────┐ │
  │ │ ...                                              │ │
  │ └──────────────────────────────────────────────────┘ │
  │                                                      │
  │ ┌──────────────────────────────────────────────────┐ │
  │ │ D: 审稿意见（选择后回到W7重新开始下一轮迭代）     │ │
  │ │ [文本输入框]                                     │ │
  │ │ [提交审稿意见并重做]                              │ │
  │ └──────────────────────────────────────────────────┘ │
  │ [E: 退回重新生成]  [回到W5修改算法]  [回到W2重新规划] │
  └──────────────────────────────────────────────────────┘
```

**人工选择后的处理**：

1. **选择 A/B/C 方案**：
   - Dashboard POST `{"action": "advance", "target_phase": "W7.2 图表生成", "selected_plan": "A"}`
   - PES 将选中方案的完整内容写入 `workspace/PAPER_PLAN.md` 和 `workspace/NARRATIVE_REPORT.md`
   - 丢弃未选中方案（保留在 `paper_plans/` 归档目录）
   - 状态推进到 W7.2

2. **选择 D（审稿意见）**：
   - Dashboard POST `{"action": "redo_with_review", "feedback": "人工审稿意见内容"}`
   - PES 设置 `state.iteration_feedback = 人工审稿意见`
   - PES 设置 `state.needs_regeneration = True`
   - **回到 W7.1 开头的下一轮迭代**（sub_loop_step 归零）
   - 4-Persona 在下一轮看到人工审稿意见作为首要修改指导
   - 人工评价被注入到 invoke_four_personas_paper 的 regen_context 参数中

3. **选择 E（退回重新生成）**：
   - Dashboard POST `{"action": "redo"}`
   - 不带反馈，直接重新运行 W7.1

**transition_phase 新增 `redo_with_review` action**：
```python
elif action == "redo_with_review":
    # 带人工审稿意见的重做 → 回到当前 phase 开头
    state["sub_loop_step"] = 0
    state["status"] = "in_progress"
    state["needs_regeneration"] = True
    if feedback:
        state["iteration_feedback"] = feedback
    self._write_state(state)
    return {"transitioned": False, "phase": phase,
            "message": f"带审稿意见重做 '{phase}'，反馈: {feedback}"}
```

**接口规格**：
- invoke_four_personas_paper 输入：`{research_topic, workspace_dir, venue, w6_discussion, cc_atoms, regen_context}`
- invoke_four_personas_paper 输出：`4 个 JSON 方案` → 保存为 `paper_plans/plan_persona_{1-4}.json`
- elo_tournament_paper 输入：`4 个方案的 method_sketch`
- elo_tournament_paper 输出：`{rankings: [{id, elo_rating, scores}], matchups: [...]}`
- verify_paper_plan_products 输入：`4 个方案 + Elo 结果`
- verify_paper_plan_products 输出：`{verified: bool, per_plan: [{id, structural_ok, llm_scores}]}`
- present_paper_plan_options 输出：`SSE 事件` → Dashboard 渲染

---

### W7.2 图表生成（单轮，2步 + 人工确认）

```
触发：Dashboard POST {"action":"advance","target_phase":"W7.2 图表生成","selected_plan":"A"}
  ↓
── sub_loop #1: invoke_skill_paper_figure ──
SkillExecutor.execute("flux-paper-figure", variables)
  变量：workspace_dir, paper_plan（来自选中的方案）, experiment_data
  ↓
LLM 返回 JSON → 写入 figures/ + 执行 gen_*.py
  ↓
── sub_loop #2: verify_deliverables ──
  检查：figures/, figures/latex_includes.tex
  ↓
Dashboard 展示（W7.2-W7.4 统一 UI 模式）：
  ┌──────────────────────────────────────────────────────┐
  │ W7.2 图表生成 — 已完成                               │
  │                                                      │
  │ 产物:                                                │
  │  ✅ figures/fig1.pdf (23 KB) [预览]                  │
  │  ✅ figures/fig2.pdf (18 KB) [预览]                  │
  │  ✅ figures/latex_includes.tex (2.1 KB)              │
  │                                                      │
  │ A: 继续到 W7.3 LaTeX写作                             │
  │ B: 审稿意见（选择后回到W7重新开始）                   │
  │    [文本输入框] [提交]                                │
  │ C: 退回重新生成                                      │
  │ [回到W7.1重新规划] [回到W5] [回到W2]                 │
  └──────────────────────────────────────────────────────┘
```

---

### W7.3 LaTeX写作（单轮，2步 + 人工确认）

```
触发：Dashboard POST {"action":"advance","target_phase":"W7.3 LaTeX写作"}
  ↓
── sub_loop #1: invoke_skill_paper_write ──
SkillExecutor.execute("flux-paper-write", variables)
  变量：workspace_dir, paper_plan, figures_includes, template_content, venue
  ↓
LLM 返回 JSON → 写入 paper/ 目录下所有文件
  ↓
── sub_loop #2: verify_deliverables ──
  检查：paper/main.tex, paper/sections/, paper/references.bib, paper/math_commands.tex
  ↓
Dashboard 展示（同 W7.2 UI 模式）：
  A: 继续到 W7.4 编译
  B: 审稿意见（回到W7重新开始）
  C: 退回重新生成
  [回到W7.1重新规划] [回到W5] [回到W2]
```

---

### W7.4 编译（单轮，2步 + 人工确认）

```
触发：Dashboard POST {"action":"advance","target_phase":"W7.4 编译"}
  ↓
── sub_loop #1: invoke_skill_paper_compile ──
  执行 latexmk 编译 → 生成 paper/main.pdf
  ↓
── sub_loop #2: verify_deliverables ──
  检查：paper/main.pdf 存在且 > 100KB
  ↓
Dashboard 展示（同 W7.2 UI 模式 + PDF 预览）：
  A: 继续到 W7.5 审稿修复
  B: 审稿意见（回到W7重新开始）
  C: 退回重新生成
  [回到W7.1重新规划] [回到W5] [回到W2]
```

---

### W7.5 审稿修复（多轮，5步 + 人工确认）

```
触发：Dashboard POST {"action":"advance","target_phase":"W7.5 审稿修复"}
  ↓
PES: state.phase = "W7.5 审稿修复"

── sub_loop #1: invoke_skill_improve_review_1 ──
  LLM 审稿第1轮 → 评分 + 问题列表 → PAPER_IMPROVEMENT_LOG.md
  发 SSE: {"type":"paper_review_round","data":{"round":1,"score":6,"verdict":"revise"}}
  ↓
── sub_loop #2: invoke_skill_improve_fix_1 ──
  LLM 修复问题 → 更新 .tex → 编译 → paper/main_round1.pdf
  ↓
── sub_loop #3: invoke_skill_improve_review_2 ──
  LLM 审稿第2轮 → 更新评分
  ↓
── sub_loop #4: invoke_skill_improve_fix_2 ──
  LLM 修复 → 编译 → paper/main_round2.pdf → paper/main.pdf
  写 PAPER_IMPROVEMENT_STATE.json {"status":"completed","rounds":2,"final_score":8}
  ↓
── sub_loop #5: verify_deliverables ──
  检查：paper/main.pdf, PAPER_IMPROVEMENT_LOG.md, PAPER_IMPROVEMENT_STATE.json
  ↓
Dashboard 展示（同 W7.2 UI 模式 + 审稿历史）：
  ┌──────────────────────────────────────────────────────┐
  │ W7.5 审稿修复 — 已完成（2轮）                        │
  │                                                      │
  │ 审稿历史:                                            │
  │  Round 1: Score 6/10 → 修复 → Round 2: Score 8/10   │
  │                                                      │
  │ 产物:                                                │
  │  ✅ paper/main.pdf (324 KB) [预览PDF]                │
  │  ✅ PAPER_IMPROVEMENT_LOG.md [查看]                  │
  │                                                      │
  │ A: 继续到 W8 审阅                                    │
  │ B: 审稿意见（选择后回到W7重新开始）                   │
  │    [文本输入框] [提交]                                │
  │ C: 退回重新修复                                      │
  │ [回到W7.1重新规划] [回到W5] [回到W2]                 │
  └──────────────────────────────────────────────────────┘
```

---

### W8 审阅（多轮，6步 + 人工确认）

```
触发：Dashboard POST {"action":"advance","target_phase":"W8 审阅"}
  ↓

── sub_loop #1-2: review_round_1 + fix_1 ──
  LLM 审稿 + 修复
  ↓
── sub_loop #3-4: review_round_2 + fix_2 ──
  LLM 审稿 + 修复
  ↓
── sub_loop #5: invoke_skill_review_round_3 ──
  最终审稿 → CLAIMS_FROM_RESULTS.md → REVIEW_STATE.json → AUTO_REVIEW.md
  ↓
── sub_loop #6: verify_deliverables ──
  检查：AUTO_REVIEW.md, REVIEW_STATE.json, CLAIMS_FROM_RESULTS.md
  ↓
Dashboard 展示（W8 专属 UI）：
  ┌──────────────────────────────────────────────────────┐
  │ W8 审阅 — 已完成（3轮）                              │
  │                                                      │
  │ 最终评分: 8/10                                       │
  │ 审稿报告: AUTO_REVIEW.md [查看]                      │
  │                                                      │
  │ A: 完成终止                                          │
  │ B: 回到 W7.1 重新规划论文                            │
  │ C: 回到 W5 修改算法                                  │
  │ D: 审稿意见（选择后回到W7重新开始）                   │
  │    [文本输入框] [提交]                                │
  │ [回到W2重新规划]                                     │
  └──────────────────────────────────────────────────────┘
```

---

### 回退机制规格

**所有 W7/W8 阶段通用的回退按钮**：

| 按钮 | Action | 效果 |
|---|---|---|
| 回到W7.1重新规划 | `{"action": "advance", "target_phase": "W7.1 论文计划"}` | 保留当前产物归档，从W7.1重新开始新一轮迭代 |
| 回到W5修改算法 | `{"action": "advance", "target_phase": "W5 代码实现"}` | 跳回 W5（Decision #33：用 advance，不用 jump_to_plan） |
| 回到W2重新规划 | `{"action": "jump_to_plan"}` | 跳回 W2 问题分析 |
| 审稿意见+重做 | `{"action": "redo_with_review", "feedback": "..."}` | 回到当前 phase 开头，带人工反馈 |

**TRANSITIONS 更新**（添加 W7/W8 任意阶段→W7.1 的回退路径）：

```python
TRANSITIONS = {
    PHASE_PLAN_1:   [PHASE_PLAN_2],
    PHASE_PLAN_2:   [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN_1, PHASE_WRITE_PLAN],
    # W7.1-W7.5: 每个都可以向前一步 或 回到W7.1
    PHASE_WRITE_PLAN:   [PHASE_WRITE_FIGURE],
    PHASE_WRITE_FIGURE: [PHASE_WRITE_LATEX, PHASE_WRITE_PLAN],
    PHASE_WRITE_LATEX:  [PHASE_WRITE_COMPILE, PHASE_WRITE_PLAN],
    PHASE_WRITE_COMPILE:[PHASE_WRITE_IMPROVE, PHASE_WRITE_PLAN],
    PHASE_WRITE_IMPROVE:[PHASE_REVIEW, PHASE_WRITE_PLAN],
    PHASE_REVIEW:   [PHASE_WRITE_PLAN, PHASE_CODE, PHASE_PLAN_1, PHASE_TERMINATED],
}
```

**回退时的产物归档**：
- 当从 W7.2+ 回到 W7.1 时，当前产物移动到 `paper_plans/archive_iter_{N}/`
- `state.paper_iteration` 自增
- 新一轮 4-Persona 看到归档产物作为 `regen_context`

---

## 执行顺序

**开发策略：同步开发**（核心 + Dashboard 一起推进）。

### 阶段 1：基础模块（无依赖，可并行）

| 并行轨道 | 任务 | 产物 |
|---|---|---|
| **轨道 A** | 创建 `llm_client.py` + `skill_executor.py` + `session_manager.py` | 3 个新文件 |
| **轨道 B** | 重构 `elo/tournament.py`（Decision #29：接受 LLMClient） | 1 个修改文件 |
| **轨道 C** | 删除 17 个 evo-* skill 目录 + agent_task.py | 文件删除 |
| **轨道 D** | 删除 `stages.py` + 更新 `__init__.py` | 文件删除/修改 |

**验证**：
- `python -c "from pes_controller.llm_client import LLMClient; print('OK')"`
- `python -c "from pes_controller.tavily_client import TavilyClient; print('OK')"`
- `python -c "from pes_controller.skill_executor import SkillExecutor; print('OK')"`
- `python -c "from pes_controller.elo.tournament import EloTournament; print('OK')"`

### 阶段 2：controller.py 核心修改（依赖阶段 1）

| 任务 | 详情 |
|---|---|
| 修复 PHASE_WRITE NameError | 3 处引用替换为 PHASE_WRITE_PLAN（行 2316/2327/2331） |
| 删除 AGENT_SDK_PHASES | 行 57-58 + 行 2357/2359/2362 |
| 更新 CHAIN_STEPS | W7.1-W8 新步骤定义 |
| 更新 TRANSITIONS | W7.2-W7.5 → W7.1 回退路径 |
| 重写 `_build_step` W7.1-W8 handlers | SkillExecutor 内部执行（Decision #21-22） |
| 重写 `transition_phase` | 新增 advance/redo/redo_with_review（Decision #18） |
| 重写 `_auto_next_phase` | W7.1-W8 返回 None（Decision #16） |

**验证**：
- `python -c "from pes_controller import PHASE_WRITE_PLAN; print(PHASE_WRITE_PLAN)"`
- `python -c "from pes_controller import TRANSITIONS; print(PHASE_WRITE_PLAN in TRANSITIONS)"`
- Phase 常量无 NameError

### 阶段 3：SKILL.md + Dashboard（可并行，依赖阶段 2）

| 并行轨道 | 任务 |
|---|---|
| **轨道 E** | 创建 15 个 flux-* SKILL.md prompt 模板 |
| **轨道 F** | Dashboard 全量更新（monitor.py：imports + 删除 Agent SDK + SSE handler + 多方案 UI + Transition API） |
| **轨道 G** | watchdog.py 更新 |

**验证**：
- 每个 SKILL.md 格式正确（YAML frontmatter + prompt body）
- Dashboard 显示 W7.1-W7.5 阶段
- Transition API 支持 advance/redo/redo_with_review

### 阶段 4：Legacy + 测试（依赖阶段 3）

| 任务 | 详情 |
|---|---|
| Legacy 同步 | 更新 tools_legacy/ 中 PHASE_WRITE 引用 |
| 单元测试 | TestPhaseConstants, TestSkillFiles, TestLLMClient, TestSkillExecutor 等 |
| E2E 测试 | DeepSeek 真实调用，完整 W7.1-W8 流程 |

**三库并存状态（最终）**：

| 库 | 使用位置 | 说明 |
|---|---|---|
| openai SDK | SkillExecutor (W7.1-W8) + EloTournament (W2-W4, W7.1) | **统一到 LLMClient** |
| langchain | AgentManager (W2-W6 4-Persona) | **不修改**，独立路径 |
| httpx raw | **已迁移到 LLMClient** | 删除 tournament.py 中的 httpx 调用 |

---

## v4 补充：全量 openai SDK 迁移 + 架构统一

> 本节记录 v4 新增决策和模块变更，覆盖 v3 中"保持分裂"的部分。

### v4 覆盖 v3 决策清单

以下 v3 决策被 v4 **明确推翻**（以 v4 为准）：

| v3 决策 | v3 内容 | v4 覆盖 | v4 内容 |
|---|---|---|---|
| #25 W7/W8 执行路径 | 双机制（monitor.py 执行 W2-W6，controller.py 执行 W7-W8） | **#40** | 统一机制：controller.py 执行所有 phase，monitor.py 纯展示 |
| #27 LLM 库选择 | openai SDK 仅用于 W7-W8，W2-W6 保持 langchain | **#36** | 全换 openai SDK，删除 langchain |
| B0 调度机制全景 | 两种并存机制 | **#40** | 一种统一机制：SkillExecutor |
| D1.5.1 monitor.py 角色 | W7.1-W8 不执行，W2-W6 仍执行 | **#40** | 所有 phase 都不执行，纯展示 |
| A2 SkillExecutor 构造 | `(skills_dir, llm_client)` | **G2** | `(skills_dir, llm_client, tavily_client)` |
| A3 SessionManager | 独立模块 | **#34** | 内嵌在 SkillExecutor 中 |
| D0 Dashboard 前端 | 内嵌在 `_PES_PIPELINE_CONTROL_HTML` | **#41** | 分离为 `static/index.html` |

**未覆盖的 v3 内容仍然有效**：所有 W7.1-W8 的详细流程规格（CHAIN_STEPS、TRANSITIONS、SKILL.md 列表、回退机制等）。

### v4 决策记录

| # | 问题 | 决策 |
|---|---|---|
| 36 | **LLM 库统一** | **全换 openai SDK**：W2-W6 AgentManager + W7-W8 SkillExecutor + EloTournament 统一使用 LLMClient（openai SDK）。删除 langchain 依赖 |
| 37 | **W2-W4 4-Persona 执行** | **也换 SkillExecutor**：W2-W4 的 persona 调用从 AgentManager.invoke_agent() 迁移到 SkillExecutor.execute("w2-persona-xxx") |
| 38 | **Tavily 搜索** | **tavily-python SDK**：替换 langchain 的 TavilySearchResults 工具 |
| 39 | **LLMClient 实例** | **PESController 集中创建，依赖注入**：Controller 创建 LLMClient + TavilyClient + SkillExecutor，通过参数传递 |
| 40 | **monitor.py 角色** | **纯展示层**：所有 step 执行移到 controller.py，monitor.py 只负责 SSE 展示 + Transition API 转发 + 产物侧边栏 |
| 41 | **Dashboard 前端** | **分离为 static/index.html**：从 monitor.py 内嵌 HTML 分离为独立前端文件 |
| 42 | **Skill 执行模型** | **侧重内部执行**：外部 skill 转本地 SKILL.md 文件后执行 |
| 43 | **AgentManager** | **彻底删除**：功能由 SkillExecutor + TavilyClient 完全替代 |
| 44 | **langchain 依赖** | **彻底删除**：不再有任何组件依赖 langchain |
| 45 | **W6 _do_*() 函数** | **移到 controller.py** 或独立 utility 模块。其中 discuss() → SkillExecutor，web_research() → TavilyClient + SkillExecutor |

### v4 目标架构

```
┌─ PESController (唯一执行者) ──────────────────────────────────────┐
│                                                                     │
│  初始化时创建:                                                       │
│    self.llm_client = LLMClient(deepseek_config)                     │
│    self.tavily_client = TavilyClient(tavily_api_key)                │
│    self.executor = SkillExecutor(skills_dir, llm_client, tavily)    │
│                                                                     │
│  sub_loop() → _build_step() → 统一执行所有 step                     │
│                                                                     │
│  ┌─ W2-W4 (改造) ──────────────────────────────────────────────┐   │
│  │  invoke_four_personas:                                       │   │
│  │    ThreadPoolExecutor(4) → executor.execute("w2-persona-xxx")│   │
│  │    每个 persona: TavilyClient.search() → 搜索结果注入 variables│   │
│  │  elo_tournament: EloTournament(self.llm_client).rank()       │   │
│  │  multi_agent_discuss: executor.execute("w2-discuss", ...)    │   │
│  │  evolution_memory / island_assign: 纯 Python（保留原有逻辑）  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ W5-W6 (改造) ──────────────────────────────────────────────┐   │
│  │  W5 代码实现: 现有代码逻辑（Python），不涉及 LLM             │   │
│  │  W6 scan_islands_rubrics: 纯 Python + executor.execute()     │   │
│  │  W6 write_claim_chain: 纯 Python（cc.db 操作）               │   │
│  │  W6 island_assign: 纯 Python（IslandManager + CellGrid）     │   │
│  │  W6 web_research: TavilyClient.search() + executor.execute() │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ W7.1-W8 (新建，见 v3 详细规格) ────────────────────────────┐   │
│  │  完全同 v3 计划，无变更                                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  SSE 事件 → _post_to_dashboard()                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─ monitor.py (纯展示层) ──────────────────────────────────────────┐
│                                                                     │
│  职责（仅 3 项）:                                                   │
│    1. SSE 事件展示（实时推送 step 进度、产物更新）                    │
│    2. Transition API 转发（satisfied/advance/redo/terminate）         │
│    3. 产物侧边栏（文件列表、预览、验证状态）                          │
│                                                                     │
│  不执行任何 step，不创建 LLMClient，不调用 LLM                       │
│  前端: static/index.html（Alpine.js + Tailwind）                     │
└─────────────────────────────────────────────────────────────────────┘

┌─ 待删除 ──────────────────────────────────────────────────────────┐
│  session/manager.py (AgentManager)                                   │
│  session/llm/models.py (get_chat_model)                              │
│  pes_controller/stages.py                                            │
│  plugins/experimentation/agent_task.py                               │
│  17 个 evo-* skill 目录                                              │
│  langchain 依赖（requirements.txt 中移除）                           │
│  monitor.py 中 _execute_step() 和 _do_*() 函数                      │
│  monitor.py 中 _PES_PIPELINE_CONTROL_HTML 内嵌字符串                 │
└─────────────────────────────────────────────────────────────────────┘
```

### v4 新增/修改模块

#### G1. pes_controller/tavily_client.py（新建）

```python
class TavilyClient:
    """封装 Tavily 搜索 API（tavily-python SDK）"""
    def __init__(self, api_key: str):
        from tavily import TavilyClient as _TavilyClient
        self.client = _TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        results = self.client.search(query, max_results=max_results)
        return [{"title": r["title"], "url": r["url"],
                 "content": r["content"]} for r in results]
```

**依赖**：`pip install tavily-python`
**环境变量**：`TAVILY_API_KEY`

#### G2. SkillExecutor 扩展（修改 A2）

SkillExecutor 新增 `tavily_client` 参数和搜索预处理能力：

```python
class SkillExecutor:
    def __init__(self, skills_dir: Path, llm_client: LLMClient,
                 tavily_client: TavilyClient | None = None):
        self.skills_dir = skills_dir
        self.llm_client = llm_client
        self.tavily_client = tavily_client
        self.sessions: dict[str, list[dict]] = {}

    def execute(self, skill_name: str, variables: dict,
                session_id: str | None = None,
                pre_search: str | None = None) -> dict:
        """执行一个 skill。pre_search 时先执行 Tavily 搜索再注入变量。"""
        # 可选：搜索预处理
        if pre_search and self.tavily_client:
            search_results = self.tavily_client.search(pre_search)
            variables["search_results"] = json.dumps(search_results, ensure_ascii=False)

        # ... 后续逻辑同 v3 A2 ...
```

#### G3. W2-W4 Persona SKILL.md（新建 4 个）

| Skill | Phase | 输入 | 输出 |
|---|---|---|---|
| w2-persona-novel-academic | W2-W4 | research_topic, search_results, workspace_dir, persona_name | persona_proposal JSON |
| w2-persona-conservative-academic | W2-W4 | 同上 | 同上 |
| w2-persona-novel-engineering | W2-W4 | 同上 | 同上 |
| w2-persona-conservative-engineering | W2-W4 | 同上 | 同上 |

与 W7.1 的 flux-paper-plan-* 的区别：
- W2-W4 persona SKILL.md：侧重**研究方案生成**（假设、方法、实验设计）
- W7.1 persona SKILL.md：侧重**论文计划生成**（Claims-Evidence Matrix、章节结构、图表计划）
- 共享相同的 4-Persona 分类（novel/conservative × academic/engineering）

#### G4. W6 辅助 SKILL.md（新建 2-3 个）

| Skill | Step | 输入 | 输出 |
|---|---|---|---|
| w6-discuss | multi_agent_discuss | code_results, persona_proposals | discussion_summary JSON |
| w6-research | web_research | research_topic | research_notes JSON |

#### G5. controller.py _build_step 统一化

**W2-W4 step handlers 改造**（替换原有 invoke_four_personas → monitor.py 分发）：

```python
elif step_name == "invoke_four_personas":
    # v3: 返回 action dict 给 monitor.py 执行
    # v4: 内部直接执行（与 W7.1 invoke_four_personas_paper 统一模式）
    import concurrent.futures
    executor = self.executor  # self.executor 在 __init__ 中创建
    ws = Path(state.get("workspace_dir", "."))

    persona_prompts = [
        ("novel-academic", "w2-persona-novel-academic"),
        ("conservative-academic", "w2-persona-conservative-academic"),
        ("novel-engineering", "w2-persona-novel-engineering"),
        ("conservative-engineering", "w2-persona-conservative-engineering"),
    ]

    research_topic = state.get("research_topic", "")

    def _call_persona(persona_name, skill_name):
        return persona_name, executor.execute(
            skill_name,
            variables={"research_topic": research_topic, "workspace_dir": str(ws),
                       "persona_name": persona_name},
            pre_search=research_topic,  # 先执行 Tavily 搜索
        )

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_call_persona, pn, sn): pn for pn, sn in persona_prompts}
        for future in concurrent.futures.as_completed(futures):
            persona_name, result = future.result()
            results[persona_name] = result

    # 保存结果
    proposals_dir = ws / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    for pn, r in results.items():
        (proposals_dir / f"proposal_{pn}.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"done": False, "phase": phase, "step": step_name,
            "action": "personas_completed", "persona_count": len(results)}
```

**W6 step handlers 改造**（从 monitor.py _do_*() 迁移）：

```python
elif step_name == "scan_islands_rubrics":
    # 原 monitor.py _do_scan_islands_rubrics() 的纯 Python 逻辑
    # 但 discuss() 部分替换为 SkillExecutor 调用
    ...

elif step_name == "write_claim_chain":
    # 原 monitor.py _do_write_claim_chain() 的纯 Python 逻辑
    # 直接搬移，不涉及 LLM
    ...

elif step_name == "island_assign":
    # 原 monitor.py _do_island_assign() 的纯 Python 逻辑
    # 直接搬移
    ...

elif step_name == "web_research":
    # TavilyClient.search() + SkillExecutor.execute("w6-research", ...)
    ...
```

#### G6. monitor.py 重构

**删除的内容**：
- `_PES_PIPELINE_CONTROL_HTML` 内嵌字符串 → 替换为 `static/index.html` 文件
- `_execute_step()` 函数 → 执行逻辑已移到 controller.py
- `_do_scan_islands_rubrics()`, `_do_write_claim_chain()`, `_do_island_assign()`, `_do_web_research()` → 移到 controller.py
- `AgentManager` 实例化和所有引用
- `AGENT_SDK_PHASES`

**保留的内容**：
- SSE 事件推送（`_sse_generator`, `/api/sse/{session_id}` 端点）
- Transition API（`/api/pipeline/transition` 端点）
- 新增产物路由（`/api/deliverables/{session_id}`, `/api/phase-content/{session_id}/{file_path}`）
- StaticFiles 中间件（提供 `static/index.html`）

**新增的内容**：
- `StaticFiles` 中间件提供分离的前端
- W7.1-W8 SSE 事件处理器（`paper_plan_options_ready`, `skill_completed`, `paper_review_round` 等）

**新的 monitor.py 结构**：
```python
# sdk/dashboard/monitor.py

# ── 路由 ──
# GET  /                        → static/index.html
# GET  /api/sse/{session_id}    → SSE 事件流
# POST /api/pipeline/transition → Transition API
# GET  /api/deliverables/{sid}  → 产物列表
# GET  /api/phase-content/{sid}/{path} → 产物内容
# GET  /api/transition-options/{sid}   → 合法 transition

# ── SSE 事件处理 ──
# controller.py 通过 MCP 调用 _post_to_dashboard()
# → monitor.py 转发为 SSE 事件到前端

# ── 无执行逻辑 ──
# 所有 step 执行在 controller.py 中完成
```

#### G7. static/index.html（新建）

**技术栈**：Alpine.js + Tailwind CDN（与 claude-fleet 一致）

**结构**：
```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body x-data="pipelineApp()">
    <!-- Phase 进度条 -->
    <!-- Step 进度条 -->
    <!-- SSE 事件日志 -->
    <!-- 产物侧边栏 -->
    <!-- W7.1 多方案选择卡片（条件渲染） -->
    <!-- W7.2-W8 产物确认面板（条件渲染） -->
    <!-- Transition 操作按钮 -->
</body>
<script>
function pipelineApp() {
    return {
        phase: '',
        step: '',
        events: [],
        options: [],  // W7.1 多方案
        deliverables: [],
        // SSE 连接
        init() {
            const es = new EventSource('/api/sse/' + this.sessionId);
            es.onmessage = (e) => this.handleEvent(JSON.parse(e.data));
        },
        handleEvent(event) { ... },
        async transition(action, params) { ... },
    }
}
</script>
</html>
</html>
```

### v4 删除清单

| 文件/目录 | 操作 | 替代 |
|---|---|---|
| `session/manager.py` | 删除 | SkillExecutor + TavilyClient |
| `session/llm/models.py` | 删除 | LLMClient (openai SDK) |
| `pes_controller/stages.py` | 删除 | controller.py 唯一真相源 |
| `plugins/experimentation/agent_task.py` | 删除 | 无替代（Agent SDK 已废弃） |
| `langchain` 依赖 | 从 requirements.txt 移除 | openai SDK |
| `monitor.py` 中 `_execute_step()` | 删除 | controller.py _build_step() |
| `monitor.py` 中 `_do_*()` 函数 | 删除 | 移到 controller.py |
| `monitor.py` 中 `_PES_PIPELINE_CONTROL_HTML` | 删除 | static/index.html |
| `monitor.py` 中 `AgentManager` 引用 | 删除 | 无替代 |
| 17 个 `evo-*` skill 目录 | 删除 | SkillExecutor 用 SKILL.md |
| `controller.py` 中 `AGENT_SDK_PHASES` | 删除 | 无替代 |
| `watchdog.py` 中 `AGENT_SDK_PHASES` | 删除 | 无替代 |

### v4 新增文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `pes_controller/llm_client.py` | 新建 | LLMClient (openai SDK) |
| `pes_controller/tavily_client.py` | 新建 | TavilyClient (tavily-python SDK) |
| `pes_controller/skill_executor.py` | 新建 | SkillExecutor（含会话管理） |
| `sdk/dashboard/static/index.html` | 新建 | 分离前端（Alpine.js + Tailwind） |
| `skills/w2-persona-novel-academic/SKILL.md` | 新建 | W2-W4 persona prompt |
| `skills/w2-persona-conservative-academic/SKILL.md` | 新建 | W2-W4 persona prompt |
| `skills/w2-persona-novel-engineering/SKILL.md` | 新建 | W2-W4 persona prompt |
| `skills/w2-persona-conservative-engineering/SKILL.md` | 新建 | W2-W4 persona prompt |
| `skills/w6-discuss/SKILL.md` | 新建 | W6 多智能体讨论 prompt |
| `skills/w6-research/SKILL.md` | 新建 | W6 文献调研 prompt |
| 15 个 `flux-*` SKILL.md | 新建 | W7-W8 论文写作 prompt（见 v3 C1-C15） |

### v4 执行顺序（重写）

**一步到位，按依赖顺序执行**：

#### 阶段 1：基础模块（无依赖，可并行）

| 轨道 | 任务 | 产物 |
|---|---|---|
| A | 创建 `llm_client.py` | LLMClient (openai SDK) |
| B | 创建 `tavily_client.py` | TavilyClient (tavily-python SDK) |
| C | 创建 `skill_executor.py`（含会话管理） | SkillExecutor |
| D | 重构 `elo/tournament.py`：接受 LLMClient | EloTournament |
| E | 删除 `stages.py` + 17 个 evo-* skill 目录 + `agent_task.py` | 清理 |

#### 阶段 2：controller.py 全量重写（依赖阶段 1）

| 任务 | 详情 |
|---|---|
| 添加 LLMClient/TavilyClient/SkillExecutor 初始化 | `__init__` 中创建并保存 |
| 修复 PHASE_WRITE NameError | 3 处替换为 PHASE_WRITE_PLAN |
| 删除 AGENT_SDK_PHASES | 行 57-58 |
| 更新 CHAIN_STEPS + TRANSITIONS | W7.1-W8 新步骤 + 回退路径 |
| 重写 W2-W4 step handlers | invoke_four_personas → SkillExecutor 并行 |
| 重写 W6 step handlers | _do_*() 逻辑搬移 + discuss/research → SkillExecutor |
| 重写 W7.1-W8 step handlers | 完全同 v3 B1.5 |
| 重写 transition_phase | advance/redo/redo_with_review |
| 重写 _auto_next_phase | W7.1-W8 返回 None |

#### 阶段 3：monitor.py 重构 + 前端（依赖阶段 2）

| 轨道 | 任务 |
|---|---|
| F | monitor.py 重构：删除执行逻辑，保留 SSE + API 路由 |
| G | 创建 `static/index.html` 分离前端 |
| H | watchdog.py 更新：删除 AGENT_SDK_PHASES |

#### 阶段 4：SKILL.md + 测试（依赖阶段 3）

| 轨道 | 任务 |
|---|---|
| I | 创建 4 个 W2-W4 persona SKILL.md |
| J | 创建 2 个 W6 辅助 SKILL.md |
| K | 创建 15 个 W7-W8 flux-* SKILL.md |
| L | 删除 AgentManager + get_chat_model + langchain 依赖 |

#### 阶段 5：Legacy + 测试

| 任务 |
|---|
| 更新 tools_legacy/ 中 PHASE_WRITE 引用 |
| 单元测试（TestLLMClient, TestSkillExecutor, TestPhaseConstants 等） |
| E2E 测试（DeepSeek 真实调用，完整 W2-W8 流程） |
| `pip uninstall langchain langchain-core` 验证无残留引用 |

### v4 验证清单

```bash
# 1. 模块导入验证
python -c "from pes_controller.llm_client import LLMClient; print('LLMClient OK')"
python -c "from pes_controller.tavily_client import TavilyClient; print('TavilyClient OK')"
python -c "from pes_controller.skill_executor import SkillExecutor; print('SkillExecutor OK'"
python -c "from pes_controller.elo.tournament import EloTournament; print('EloTournament OK'"

# 2. Phase 常量验证
python -c "from pes_controller import PHASE_WRITE_PLAN, TRANSITIONS, CHAIN_STEPS; print('Constants OK')"

# 3. 无 langchain 残留
python -c "import pes_controller; print('No langchain' if 'langchain' not in str(dir(pes_controller)) else 'WARNING: langchain found')"

# 4. 无 PHASE_WRITE 引用
grep -r "PHASE_WRITE[^_]" pes_controller/ --include="*.py" || echo "OK: no stale PHASE_WRITE"

# 5. Dashboard 启动
python sdk/dashboard/monitor.py
# 打开 http://localhost:8420 → 应显示分离的前端

# 6. E2E: W2 4-Persona → Elo → Transition
python -c "
from pes_controller import PESController
ctrl = PESController('test_state.json')
result = ctrl.sub_loop()
print(result)
"

# 7. LLM 真实调用测试
python -c "
from pes_controller.llm_client import LLMClient
client = LLMClient(api_key='...', base_url='https://api.deepseek.com/v1', model='deepseek-chat')
content, usage = client.chat([{'role':'user','content':'Say hello'}])
print(f'Response: {content[:100]}, Tokens: {usage}')
"
```

---

## v5 补充：架构优雅化（10k star 标杆）

> v5 在 v4 基础上进一步优化：统一执行入口、Phase Handler 注册制、dataclass 类型化、persona 复用。

### v5 决策记录

| # | 问题 | 决策 |
|---|---|---|
| 46 | **统一执行入口** | **所有 step 都走 SkillExecutor**，纯 Python 步骤通过 SKILL.md `handler` 字段指定 Python 函数 |
| 47 | **Phase Handler 注册制** | 每个 phase 一个 handler 文件（`phases/w*_handler.py`），实现 `build_step()` 方法。controller.py 只做调度（~200 行） |
| 48 | **dataclass 类型化** | 所有模块间数据契约用 `@dataclass` 定义 |
| 49 | **Persona 复用** | 4 个 persona SKILL.md 文件，通过 `{{phase}}` 参数区分 W2 vs W7.1 行为（4 个文件而非 8 个） |
| 50 | **SKILL.md 双模式** | `execution: llm`（调 LLM）和 `execution: python`（调 Python 函数） |

### v5 最终目录结构

```
pes_controller/
├── __init__.py                    # 导出 phase 常量 + TRANSITIONS + PESController
├── types.py                       # dataclass 类型定义（NEW）
├── llm_client.py                  # LLMClient (openai SDK)（NEW）
├── tavily_client.py               # TavilyClient (tavily-python SDK)（NEW）
├── skill_executor.py              # SkillExecutor — 唯一执行入口（NEW）
├── controller.py                  # 轻量调度器（REWRITE to ~200 lines）
├── phases/                        # Phase Handler 注册制（NEW directory）
│   ├── __init__.py                # 自动注册所有 handler
│   ├── base.py                    # BasePhaseHandler(ABC)
│   ├── w2_handler.py              # W2 问题分析
│   ├── w3_handler.py              # W3 方案方向
│   ├── w4_handler.py              # W4 具体方案生成
│   ├── w5_handler.py              # W5 代码实现
│   ├── w6_handler.py              # W6 结果分析
│   ├── w7_1_handler.py            # W7.1 论文计划
│   ├── w7_2_handler.py            # W7.2 图表生成
│   ├── w7_3_handler.py            # W7.3 LaTeX写作
│   ├── w7_4_handler.py            # W7.4 编译
│   ├── w7_5_handler.py            # W7.5 审稿修复
│   └── w8_handler.py              # W8 审阅
├── elo/
│   └── tournament.py              # EloTournament（MODIFY: accept LLMClient）
└── protocol.py                    # 原子读写协议（KEEP）

skills/
├── persona-novel-academic/SKILL.md        # 共享 persona（phase 参数区分）
├── persona-conservative-academic/SKILL.md
├── persona-novel-engineering/SKILL.md
├── persona-conservative-engineering/SKILL.md
├── w6-scan-islands/SKILL.md               # execution: python
├── w6-write-claim-chain/SKILL.md          # execution: python
├── w6-island-assign/SKILL.md              # execution: python
├── w6-web-research/SKILL.md               # execution: llm
├── w6-discuss/SKILL.md                    # execution: llm
├── flux-verify-paper-plan/SKILL.md        # execution: llm
├── flux-paper-figure/SKILL.md
├── flux-paper-write/SKILL.md
├── flux-paper-compile/SKILL.md
├── flux-paper-improve/SKILL.md
├── flux-review-loop/SKILL.md
├── flux-result-to-claim/SKILL.md          # 辅助
├── flux-novelty-check/SKILL.md            # 辅助
├── flux-proof-writer/SKILL.md             # 辅助
├── flux-formula-derivation/SKILL.md       # 辅助
└── flux-paper-illustration/SKILL.md       # 辅助

sdk/dashboard/
├── monitor.py                     # 纯展示层（REWRITE: SSE + API routes only）
└── static/
    └── index.html                 # 分离前端（NEW: Alpine.js + Tailwind）
```

### v5 核心模块接口

#### types.py

```python
@dataclass
class StepResult:
    done: bool
    phase: str
    step: str
    step_index: int
    action: str
    data: dict = field(default_factory=dict)

@dataclass
class SkillResult:
    success: bool
    files_written: list[str] = field(default_factory=list)
    actions_executed: list[dict] = field(default_factory=list)
    llm_response: str = ""

@dataclass
class TransitionResult:
    transitioned: bool
    from_phase: str = ""
    to_phase: str = ""
    error: str = ""
    valid_targets: list[str] = field(default_factory=list)

@dataclass
class SSEEvent:
    type: str
    data: dict
    phase: str = ""

@dataclass
class SkillConfig:
    name: str
    execution: str = "llm"   # "llm" | "python"
    handler: str = ""         # Python 函数路径（execution=python 时）
    description: str = ""
    variables: list[dict] = field(default_factory=list)
```

#### phases/base.py

```python
class BasePhaseHandler(ABC):
    chain_steps: list[str] = []

    def __init__(self, executor: SkillExecutor, llm_client: LLMClient,
                 tavily_client: TavilyClient, state: dict):
        self.executor = executor
        self.llm_client = llm_client
        self.tavily_client = tavily_client
        self.state = state

    @abstractmethod
    def build_step(self, step_name: str) -> StepResult: ...
```

#### controller.py（重写为~200行调度器）

```python
class PESController:
    def __init__(self, state_path: str):
        self.llm_client = LLMClient(...)
        self.tavily_client = TavilyClient(...)
        self.executor = SkillExecutor(skills_dir, self.llm_client, self.tavily_client)
        self._handlers = {phase: get_handler(phase) for phase in PHASES}

    def sub_loop(self) -> StepResult:
        state = self._read_state()
        phase, step_index = state["phase"], state.get("sub_loop_step", 0)
        steps = CHAIN_STEPS.get(phase, [])
        if step_index >= len(steps):
            return StepResult(done=True, ...)
        handler = self._handlers[phase](self.executor, self.llm_client, self.tavily_client, state)
        return handler.build_step(steps[step_index])

    def transition_phase(self, action, target_phase=None, feedback="",
                         selected_plan=None) -> TransitionResult: ...
```

#### skill_executor.py（双模式执行）

```python
class SkillExecutor:
    def execute(self, skill_name, variables, session_id=None, pre_search=None) -> SkillResult:
        config, prompt = self._parse_skill(skill_name)
        if pre_search and self.tavily_client:
            variables["search_results"] = json.dumps(self.tavily_client.search(pre_search))
        if config.execution == "python":
            return self._execute_python(config, variables)
        else:
            return self._execute_llm(config, prompt, variables, session_id)
```

### v5 并行开发分配

| 开发者组 | 负责 | 依赖 |
|---|---|---|
| **核心组** | types.py, llm_client.py, tavily_client.py, skill_executor.py | 无 |
| **调度组** | controller.py, phases/base.py, phases/__init__.py | 核心组 |
| **W2-W4 组** | w2/w3/w4_handler.py + persona SKILL.md | 调度组 |
| **W5 组** | w5_handler.py | 调度组 |
| **W6 组** | w6_handler.py + w6-* SKILL.md + Python handler 函数 | 调度组 |
| **W7.1 组** | w7_1_handler.py + EloTournament 重构 + verify skill | 调度组 |
| **W7.2-4 组** | w7_2~w7_4 handler + flux-paper-* SKILL.md | 调度组 |
| **W7.5 组** | w7_5_handler.py + flux-paper-improve SKILL.md | 调度组 |
| **W8 组** | w8_handler.py + flux-review-loop SKILL.md | 调度组 |
| **Dashboard 组** | monitor.py 重写 + static/index.html | 调度组 |
| **清理组** | 删除 AgentManager/langchain/stages.py 等 | 全部 |

### v5 执行顺序

```
阶段 0: types.py + 常量
    ↓
阶段 1: llm_client + tavily_client + skill_executor + base.py
    ↓
阶段 2: controller.py 重写 + phases/__init__.py
    ↓ ┌───────────────────────────────────────────┐
阶段 3: │ 并行（互不依赖）：                         │
        │   W2-W4 handlers + persona skills         │
        │   W5 handler                               │
        │   W6 handler + w6 skills + Python handlers │
        │   W7.1 handler + Elo + verify skill        │
        │   W7.2-4 handlers + flux skills            │
        │   W7.5 handler + improve skill             │
        │   W8 handler + review skill                │
        │   Dashboard monitor.py + index.html        │
        └───────────────────────────────────────────┘
    ↓
阶段 4: 集成测试 + 删除旧代码 + Legacy 同步
```
