# EvoScientist 项目重构 Spec v6

## 架构分层

```
L1 claim_chain/     — CC工厂: 内容→CC atoms, CC→子图查询
L2 sdk/             — 底层驱动: MCP/Dashboard/Web Process/Local Process/Skill维护
L3 pes_controller/  — 操作系统: 每个Phase一个文件夹(含base+steps) + 顶层基类 + ELO/Rubric
L4 session/         — 线程管理: OpenRath-style Session (Chunk+Lineage+Compress)
L5 application/     — 应用: Persona/Meta/Evolution/Middleware
L6 plugins/         — 应用插件: Python工具 + SKILL.md
L7 AUTORESEARCH/sessions/ — 外置Session
```

---

## Layer 1: claim_chain/

### api.py
- **职责**: L1统一门面。上层唯一入口。
- **输入**: ingest(source, source_type, depth, breadth) / query(QuerySpec) / decompose(content, strategy)
- **输出**: IngestResult {atoms_added, relations_added, atom_ids} / Subgraph {atoms, relations, gaps} / DecomposeResult
- **交互**: 编排内部所有模块。depth控制分解细粒度(函数级/文件级/项目级)，breadth控制覆盖广度。

### decomposer.py
- **职责**: 内容→CC分解引擎。将代码/论文/文本拆分为离散atoms+relations。支持多种策略: component(按组件拆)、mechanism(按机制拆)、argument_chain(按论证链拆)。
- **输入**: 原始内容 + strategy + depth + breadth
- **输出**: 未对齐的原始 atoms + relations 列表
- **交互**: api.py调用。产出→ontology对齐→chain写入。

### chain.py
- **职责**: CC CRUD引擎。不是薄壳子——SQLite存储+事务(commit/rollback)+演化链追溯(get_evolution_chain)+UNIQUE约束去重+级联deactivate。
- **输入**: add_atom(type,title,content,tags,metadata) / add_relation(src,tgt,type,evidence) / get_atoms(filters) / get_relations(filters) / deactivate(id) / get_evolution_chain(seed_id,depth)
- **输出**: Atom对象列表 / Relation对象列表 / 演化链 / 操作状态
- **交互**: api.py调用。使用schemas/做类型校验。被ontology验证。

### schemas/atom.py
- **职责**: Atom和Relation的Pydantic数据模型。定义CC的基本数据单元——Atom(类型/标题/JSON内容/标签/证据级别/元数据/创建时间/是否激活)，Relation(源ID/目标ID/类型/证据JSON/元数据)。
- **输入**: 原始dict → model_validate()
- **输出**: 验证后的Atom/Relation对象 或 ValidationError
- **交互**: chain.py写入前校验。ontology对齐时校验。decomposer产出时构建。

### schemas/taxonomy.py
- **职责**: 类型系统枚举定义。AtomType(fact|method|component|hypothesis|experiment)。RelationType(implements|depends_on|specializes|validates|contradicts|baseline_for|motivates)。BottleneckCategory(14种瓶颈类型)。EdgeType。
- **输入**: 无(纯定义模块)
- **输出**: Enum类 + 类型检查辅助函数(is_valid_atom_type, is_valid_relation_type)
- **交互**: 被所有模块引用做类型判断。

### ontology/alignment.py
- **职责**: Ontology维护中心。合并了原validation.py+negative_archive.py的功能。包含: 类型校验(必填字段/基数规则)、BGE-M3去重、合并方案生成+执行、三层对齐检查(code↔theory↔argument)、失败atom归档(记录失败案例供反模式few-shot学习)。
- **输入**: atoms列表 / relations列表 / 失败atom信息
- **输出**: ValidationReport {errors: [{atom_id, field, issue}]} / MergePlan {groups: [[atom_ids]]} / 失败归档确认
- **交互**: api.py在每次ingest/decompose后调用。

### grounding.py
- **职责**: 信息→结构化提取管线。BGE-M3粗筛候选→LLM细提取实体+关系→ontology对齐。支持3个时机: Intake基线代码解析后、文献调研完成后、实验完成后。
- **输入**: code_dir / paper_text / experiment_results + source_type
- **输出**: 提取的atoms+relations (已对齐)
- **交互**: api.py的ingest_*()内部调用。使用codegraph.py解析代码。使用ontology对齐。

### query.py
- **职责**: CC语义查询。BGE-M3嵌入→语义搜索→邻居遍历(可控深度)→gap检测(孤儿atom/缺失关系类型)。
- **输入**: QuerySpec {keywords, atom_id, neighbor_depth(1-5), breadth(top_k), filters: {type, tags}}
- **输出**: Subgraph {atoms: [...], relations: [...], gaps: [{type, description}]}
- **交互**: api.py的query()调用。

### codegraph.py
- **职责**: CodeGraph SQLite DB→CC 转换。直接读取codegraph.db→提取AST节点+边→提取源代码片段→rule-based mechanism tag→构建CC atoms。
- **输入**: code_dir (必须含.codegraph/codegraph.db)
- **输出**: {filename: {nodes, edges}} / CC atoms列表 / mechanism_summary
- **交互**: grounding.py调用。可被L2 sdk直接import。

### cell_island.py
- **职责**: 算法代码变体统一管理。合并原cell_grid+island_manager。Cell索引(多维行为索引+异常检测)+Island集群(变体分配+合并候选检测)。
- **输入**: algo_name + metadata / 集群操作请求
- **输出**: Cell查询结果 / Island分配 / 合并建议 / 异常报告
- **交互**: api.py内部使用。

---

## Layer 2: sdk/

### server.py
- **职责**: MCP Server stdio入口。注册所有MCP tool(7个管线tool+搜索tool+文献tool+记忆tool)，处理JSON-RPC请求。
- **输入**: stdin MCP请求
- **输出**: stdout MCP响应
- **交互**: 调用L4 session/manager.py管理Agent。调用L3 pes_controller/处理管线步骤。

### dashboard.py
- **职责**: Web Dashboard。合并原monitor.py+frontend.py。HTTP API(管线状态/session状态/CC状态/SSE事件推送)+内联HTML。聚焦HTTP基础SDK和L3 session可视化。
- **输入**: HTTP请求 (GET/POST 多个endpoint)
- **输出**: JSON响应 / SSE事件流 / HTML页面
- **交互**: 调用L3 pes_controller获取管线状态。调用L4 session获取Agent状态。使用内联HTML模板渲染。

### web_process.py
- **职责**: 所有网络相关工具的统一模块。巨大且完整:
  - Tavily API搜索(学术+通用)
  - GitHub仓库搜索(github-search skill封装)
  - arXiv预印本搜索+下载
  - Semantic Scholar已发表论文搜索(含引用数/venue/TLDR)
  - DuckDuckGo无API兜底搜索
  - Web Fetch(URL→文本提取,HTML→Markdown)
  - 统一结果格式: {source, results: [{title, url, snippet, metadata}]}
- **输入**: query + source_type(tavily|github|arxiv|semantic_scholar|web) + max_results
- **输出**: 统一格式搜索结果
- **交互**: 被L5 application的persona agent通过MCP tool调用。整合了原tools/search.py功能。

### local_process.py
- **职责**: 本地文件处理统一模块:
  - PDF→Markdown提取
  - MinerU文献结构化提取
  - 文件格式转换(Markdown/LaTeX/JSON互转)
  - 代码文件解析(AST提取/依赖分析)
  - 本地文件夹批量提取(指定路径→递归处理→输出结构化数据)
- **输入**: 文件路径或文件夹路径 + 处理类型
- **输出**: 结构化提取结果
- **交互**: 被L6 plugins/literature调用。被L1 decomposer调用做预处理。

### skill_maintainer.py
- **职责**: 管线核心skill的维护管理。专门维护evo-pipeline/evo-code-agent-pre/evo-code-agent-check/evo-code-agent-post等管线流程skill。管理skill的注册、版本、更新。
- **输入**: skill更新请求 / skill状态查询
- **输出**: skill状态 / 更新确认
- **交互**: 被L3 pes_controller/bootstrap调用。管理L6 plugins/中的skill文件。

### literature/ingest.py
- **职责**: 信息摄入管线。支持两种模式:
  - 远程搜索模式: 通过web_process搜索→下载→提取
  - 本地文件夹模式: 指定路径→递归扫描→直接提取(不需要搜索步骤)
  - 统一产出: literature_manifest.jsonl + literature/*.md
- **输入**: session_dir + (搜索关键词 或 本地文件夹路径) + 摄入模式
- **输出**: literature_manifest.jsonl / literature/*.md 文件
- **交互**: 调用web_process.py(远程)或local_process.py(本地)。CLI独立运行。

### literature/mineru.py
- **职责**: MinerU文献子管道。Ingest→Index→Wiki→Retrieve→Deep Read 5阶段。当前为stub，留待后续实现。
- **输入**: paper Markdown文件
- **输出**: 结构化文献数据
- **交互**: 被literature/ingest.py在PDF提取后调用。

### status/fitness.py
- **职责**: 跨run性能追踪。记录每次实验分数，检测趋势(上升/下降/稳定)，提供统计(最佳/最差/均值/方差)。
- **输入**: score + task_id + dimensions dict + metadata
- **输出**: fitness历史 / 趋势分析 {direction, streak, best_ever, current}
- **交互**: 被L3 pes_controller在实验完成后调用。写入session/memory/fitness_history.jsonl。

### mcp/client.py
- **职责**: MCP客户端。加载MCP配置，连接外部MCP server，获取可用tool列表。
- **输入**: MCP配置 (JSON文件路径或dict)
- **输出**: MCP tool列表 [(name, schema)]
- **交互**: 被L5 application/orchestrator.py在构建Agent图时调用。

### mcp/registry.py
- **职责**: MCP server注册表。marketplace index管理——获取/解析/缓存。
- **输入**: marketplace URL
- **输出**: 可用MCP server列表 [{name, description, install_cmd}]
- **交互**: 被mcp/client.py使用。

---



### middleware/ (从L5移入 — Agent运行时中间件)

#### middleware/context_editing.py
- **职责**: 上下文编辑中间件。自动注入项目context(CLAUDE.md/目录结构/当前session状态)到agent对话开头。
- **输入**: agent消息列表
- **输出**: 增强后的消息列表(前置context)
- **交互**: L4 session/factory.py在构建agent时安装。

#### middleware/context_overflow.py
- **职责**: 上下文溢出处理。捕获provider-specific context limit错误->映射为标准ContextOverflowError->触发compress。
- **输入**: 异常对象
- **输出**: 标准错误 + compress信号
- **交互**: L4 session/factory.py安装。

#### middleware/tool_error_handler.py
- **职责**: 工具错误处理。捕获tool执行异常->转换为友好ToolMessage(含错误信息和修复建议)。
- **输入**: tool异常
- **输出**: ToolMessage(错误)
- **交互**: L4 session/factory.py安装。

#### middleware/tool_selector.py
- **职责**: 工具选择中间件。根据当前上下文智能筛选可用工具列表。
- **输入**: 全部工具列表 + 当前上下文
- **输出**: 筛选后的工具列表
- **交互**: L4 session/factory.py安装。

#### middleware/memory.py
- **职责**: Agent记忆中间件。自动提取对话重要信息->存入长期记忆->下次召回。
- **输入**: 对话消息 / 记忆查询
- **输出**: 提取的记忆 / 召回的上下文
- **交互**: L4 session/factory.py安装。

#### middleware/ask_user.py
- **职责**: 用户交互中间件。Agent主动提问->暂停执行->等待回复。
- **输入**: 问题定义
- **输出**: 用户回复
- **交互**: L4 session/factory.py安装。

#### middleware/middleware_utils.py
- **职责**: 中间件共享工具函数。
- **交互**: 被各middleware模块使用。

## Layer 3: pes_controller/

**定位**: 管线操作系统。
命名规范: `{phase_id}_{step_index:02d}_{step_name}.py`。
ELO和Rubric属于L3(评价体系是管线操作系统的一部分)。

```
pes_controller/
├── base_phase.py
├── controller.py
├── protocol.py
├── bootstrap.py
├── pipeline_bridge.py
├── watchdog.py
├── stages.py
├── elo/
│   ├── tournament.py       # 5维ELO pairwise (L3核心)
│   └── neighborhood.py     # RND邻域评价 (L3核心)
├── rubric/
│   ├── novelty.py          # LLM rubric精筛 (L3核心)
│   ├── scheduler.py        # Rubric调度 (L3核心)
│   └── format_verifier.py  # 格式校验LLM (L3核心)
└── phases/
    ├── w2_01_set_style.py              # W2 问题分析
    ├── w2_02_search_literature.py
    ├── w2_03_sync_to_cc.py
    ├── w2_04_generate_proposal.py
    ├── w2_05_evaluate_novelty.py
    ├── w2_06_elo_tournament.py
    ├── w2_07_verify_products.py
    ├── w2_08_evolution_memory.py
    ├── w2_09_write_claim_chain.py
    ├── w3_01_set_style.py              # W3 方案方向
    ├── w3_02_search_literature.py
    ├── w3_03_sync_to_cc.py
    ├── w3_04_generate_proposal.py
    ├── w3_05_evaluate_novelty.py
    ├── w3_06_elo_tournament.py
    ├── w3_07_verify_products.py
    ├── w3_08_evolution_memory.py
    ├── w3_09_write_claim_chain.py
    ├── w4_01_set_style.py              # W4 具体方案生成
    ├── w4_02_search_literature.py
    ├── w4_03_sync_to_cc.py
    ├── w4_04_generate_proposal.py
    ├── w4_05_evaluate_novelty.py
    ├── w4_06_elo_tournament.py
    ├── w4_07_verify_products.py
    ├── w4_08_evolution_memory.py
    ├── w4_09_write_claim_chain.py
    ├── w5_01_generate_code_spec.py      # W5 代码实现 (spec-first)
    ├── w5_02_run_step_pipeline.py
    ├── w5_03_generate_code_plan.py
    ├── w5_04_wait_user_code.py
    ├── w6_01_run_step_pipeline.py      # W6 结果分析
    ├── w6_02_scan_islands_rubrics.py
    ├── w6_03_multi_agent_discuss.py
    ├── w6_04_evolution_memory.py
    ├── w6_05_island_assign.py
    ├── w6_06_refine_atoms.py
    ├── w6_07_write_claim_chain.py
    ├── w7_01_invoke_skill_write.py     # W7 论文写作
    └── w8_01_invoke_skill_review.py    # W8 审阅
``````

删除的Phase:
- W2.3 检索策略 (persona已在各phase自主检索，不需要单独检索策略阶段)
- W3 文献调研 (persona已在各phase自主检索，不需要单独文献调研阶段)
- 所有write_sme步骤 (不再需要SME上下文传递机制)

W4 具体方案生成 (原 W3.5 创意生成)

---

### 通用模块

#### base_phase.py
- **职责**: 所有Step的最终祖先。定义每个step的默认实现框架+钩子方法(build_cc_context/build_experiment_feedback/build_regeneration_feedback)+sub_loop_step管理。
- **输入**: PIPELINE_STATE / session / step_name
- **输出**: step action dict (给Dashboard执行)
- **交互**: 所有phases/*.py继承。调用L1/L2/L4/L5模块。

#### controller.py
- **职责**: 管线顶层状态机。管理phase流转(TRANSITIONS规则)，按CHAIN_STEPS动态导入对应step类并依次执行。
- **输入**: PIPELINE_STATE / sub_loop()调用
- **输出**: step action JSON
- **交互**: 被L2 sdk/dashboard.py调用。动态导入phases/中的step模块。

#### protocol.py
- **职责**: PIPELINE_STATE.json原子读写。atomic_read(文件锁+损坏恢复)/atomic_write(备份+原子替换)/dashboard_write。
- **输入**: state dict / 文件路径
- **输出**: 读出的state / 写入确认
- **交互**: controller.py和L2 sdk/dashboard.py使用。

#### bootstrap.py
- **职责**: 管线一键初始化。创建session目录树->运行Intake(CodeGraph索引baseline->CC atoms)->写初始PIPELINE_STATE->启动Dashboard。
- **输入**: research_topic / workspace_dir
- **输出**: session路径 / Dashboard URL
- **交互**: 调用L1 api.py做Intake。调用L2 sdk/dashboard.py。

#### pipeline_bridge.py
- **职责**: AgentManager<->Pipeline Unix Socket桥接。传递管线事件到Dashboard SSE，传递审批请求到AgentManager。
- **输入**: 管线事件 / 审批请求
- **输出**: Dashboard事件 / 审批响应
- **交互**: 连接L4 session/manager.py和L2 sdk/dashboard.py。

#### watchdog.py
- **职责**: 管线健康监控。规则检测: stale sessions/ELO异常/CC异常/fitness stagnation。
- **输入**: PIPELINE_STATE / CC状态 / fitness历史
- **输出**: 异常报告 [{type, severity, detail, suggestion}]
- **交互**: controller.py启动。读取PIPELINE_STATE和L1 CC。

#### stages.py
- **职责**: 阶段定义中心。Phase枚举(W2/W3/W4/W5/W6/W7/W8/TERMINATED)+TRANSITIONS流转规则+CHAIN_STEPS链条+PRODUCT_SPECS产物规格+AUTO_ADVANCE_PHASES。
- **输入**: 无(配置定义)
- **输出**: Phase常量/流转规则/步骤链/产物规格
- **交互**: controller.py和base_phase.py引用。

---

### W2 问题分析 (9个step)

Persona调用拆分为4个独立step: 确定风格->自主上网查阅文献->结果同步CC->生成方案。

#### w2_01_set_style.py
- **职责**: 确定研究风格和视角。根据phase类型(W2=问题分析)配置persona的思考风格—分析深度/批判性/关注什么(难点识别vs方案提出vs实现细节)。不调用LLM，仅配置。
- **输入**: phase标识 / persona agent列表
- **输出**: style_config {focus, depth, perspective, constraints}
- **交互**: 继承base_phase。产出供后续step使用。

#### w2_02_search_literature.py
- **职责**: 自主上网查阅文献。每个persona独立搜索—使用web_process(Tavily/GitHub/arXiv/Semantic Scholar)搜索与W2相关的理论难点、Actor-Critic方法局限、Hopper-v4控制挑战等。搜索侧重="方向搜索"。
- **输入**: PIPELINE_STATE (research_topic) / style_config
- **输出**: search_results [{source, title, url, snippet, key_insight}] 每个persona独立产出
- **交互**: 继承base_phase。调用L2 sdk/web_process.py做搜索。

#### w2_03_sync_to_cc.py
- **职责**: 将查阅到的文献结果同步到Claim Chain。提取文献的关键结论->BGE-M3+LLM grounding->ontology对齐->写入CC(fact atom+literature tag+关联relation)。让CC积累最新的文献知识。
- **输入**: search_results列表
- **输出**: CC写入确认 {atoms_added, relations_added}
- **交互**: 继承base_phase。调用L1 claim_chain/api.py的ingest方法。

#### w2_04_generate_proposal.py
- **职责**: 生成W2方案。构建persona_topic: research_topic + W2 product_spec(具体难点到组件/loss项级别+因果分析+baseline为何无法解决) + CC上下文(含刚同步的文献) + JSON输出格式。4 persona各自独立产出proposal。
- **输入**: PIPELINE_STATE (含research_topic/CC上下文/iteration)
- **输出**: 4个proposal [{title, hypothesis, method_sketch, source_agent}]
- **交互**: 继承base_phase。调用L5 application/personas/。读取L1 CC。

#### w2_05_evaluate_novelty.py
- **职责**: 新颖性评价。Stage1: BGE-M3 RND(计算proposal与KB邻居密度,percentile_rank,P=100,Q=50)。Stage2: LLM 5维rubric精筛(problem/method/experiment/theory/essential novelty),与baseline描述(SAC/TD3/PPO/DDPG/A2C)对比。合并得rubric_novelty。
- **输入**: proposals列表 / RND KB路径
- **输出**: proposals(增加rubric_novelty/rnd_coarse/rnd_fine),写入PIPELINE_STATE
- **交互**: 继承base_phase。调用L3 elo/neighborhood.py和L3 rubric/novelty.py。

#### w2_06_elo_tournament.py
- **职责**: ELO锦标赛排序。5维pairwise comparison->LLM judge逐对比较(elo_novelty+validity+impact+reliability+product_satisfaction)->更新ELO rating(K=32)->计算各维度平均分。同时合并pre-computed的rubric_novelty为rubric_novelty_scored(作为第6个参考维度，不参与ELO pairwise但展示在最终排名中)。scenario参数控制LLM judge的评审场景描述(W2="导师组会-问题讨论环节")。
- **输入**: proposals(带rubric_novelty) / phase标识
- **输出**: ranked proposals(带elo_rating/dimension_scores/rubric_novelty_scored/product_satisfaction)
- **交互**: 继承base_phase。调用L3 elo/tournament.py。

#### w2_07_verify_products.py
- **职责**: 产物格式校验(3层)。Layer1: product_satisfaction阈值(>=4.0)。Layer2: structural_check关键词。Layer3: FormatVerifier LLM(MiMo)逐字段提取校验。两条路径: 信息缺失->写评语(保留上下文); 格式乱->自动重组->递归(最多2次)。
- **输入**: ranked proposals / W2 product_spec
- **输出**: verdict + 逐字段反馈 + 可能的reformatted_text
- **交互**: 继承base_phase。调用L3 rubric/format_verifier.py。

#### w2_08_evolution_memory.py
- **职责**: 记录W2排名到进化记忆(IDE类型)。存储top directions+prior failures+best strategies。
- **输入**: tournament result
- **输出**: 写入确认
- **交互**: 继承base_phase。调用L2 sdk/memory/memory.py。

#### w2_09_write_claim_chain.py
- **职责**: 将W2验证通过的proposal写入CC。创建method atom(proposal+ideation+rank_N tag)+关联relation。
- **输入**: ranked proposals
- **输出**: CC写入确认 {atoms_added, relations_added, atom_ids}
- **交互**: 继承base_phase。调用L1 claim_chain/api.py。

---

### W3 方案方向 (9个step)

与W2共享03/05/06/07/08/09步骤(继承w2对应文件)。仅01/02/04定制。

#### w3_01_set_style.py
- **职责**: W3的风格配置。focus="方案方向"—persona侧重提出解决路径而非识别问题。
- **输入**: phase标识
- **输出**: style_config
- **交互**: 继承w2_01_set_style, override配置。

#### w3_02_search_literature.py
- **职责**: W3的自主文献搜索。搜索侧重="方向搜索"—搜索针对已识别难点的可能解决方向、跨领域灵感。
- **输入**: PIPELINE_STATE / style_config
- **输出**: search_results
- **交互**: 继承w2_02_search_literature, override搜索query构建。

#### w3_03_sync_to_cc.py
- **职责**: 同w2_03。将W3搜索到的文献同步到CC。
- **输入/输出/交互**: 继承w2_03_sync_to_cc。

#### w3_04_generate_proposal.py
- **职责**: W3的方案生成。product_spec(方向描述+针对哪些难点+技术路径概要+与baseline区分点)+注入W2的CC上下文(前序phase写入的难点分析)。
- **输入**: PIPELINE_STATE (含CC上下文)
- **输出**: 4个proposal
- **交互**: 继承w2_04_generate_proposal, override build_topic()。

#### w3_05_evaluate_novelty.py ~ w3_09_write_claim_chain.py
- **交互**: 均继承w2对应文件。w3_06传入scenario="导师组会-方向讨论环节"。

---

### W4 具体方案生成 (9个step)

原"创意生成"。与W2共享03/05/06/07/08/09步骤。

#### w4_01_set_style.py
- **职责**: W4的风格配置。focus="实现细节"—persona侧重伪代码级实现和架构设计。
- **交互**: 继承w2_01_set_style, override配置。

#### w4_02_search_literature.py
- **职责**: W4的自主文献搜索。搜索侧重="实现细节搜索"—搜索伪代码实现、架构设计、损失函数设计、计算优化。
- **交互**: 继承w2_02_search_literature, override搜索query。

#### w4_03_sync_to_cc.py
- **交互**: 继承w2_03_sync_to_cc。

#### w4_04_generate_proposal.py
- **职责**: W4的方案生成。product_spec(伪代码1-2段清晰变量名+架构改动ADD/MODIFY/REMOVE+损失函数签名fn_name(args)->Tensor+计算开销估计)+注入W3的CC上下文。
- **交互**: 继承w2_04_generate_proposal, override build_topic()。

#### w4_05_evaluate_novelty.py ~ w4_09_write_claim_chain.py
- **交互**: 均继承w2对应文件。w4_06传入scenario="软件开发-专家评审团"。

---

### W5 代码实现 (4个step)

Spec-first: 先生成BuildSpec → 管线分析 → 写入CC → 精炼atoms → 生成实现计划 → 等待用户代码。

#### w5_01_generate_code_spec.py
- **职责**: 从CC winner proposal + baseline机制对比提取结构化BuildSpec (ComponentChange/LossSpec/Hyperparams)。保存为build_spec.json。用户审批后进入代码实现。
- **输入**: PIPELINE_STATE + CC状态
- **输出**: build_spec.json
- **交互**: 继承base_phase。调用pes_controller/build_spec.py。

#### w5_02_run_step_pipeline.py
- **职责**: STEP管线分析。5阶段: CLI->Indexing->Decomposer(概念基元+结构映射+反事实嫁接)->Recomposer(重组方案)->Evaluator(三公理过滤伪创新)。
- **输入**: PIPELINE_STATE (含CC状态)
- **输出**: context_bundle {proposals, primitives, mappings, evaluation}
- **交互**: 继承base_phase(override run逻辑)。读取L1 CC(只读)。

#### w5_03_write_claim_chain.py
- **职责**: W5代码阶段写入CC (复用W2实现)。非实验数据写入，代码结构同步。
- **输入**: PIPELINE_STATE
- **输出**: atoms写入确认
- **交互**: 继承W2WriteClaimChain。

#### w5_04_refine_atoms.py
- **职责**: CC atoms翻译为具体算法规格。对每个method+proposal atom生成refined_proposal JSON。
- **输入**: CC atoms列表
- **输出**: refined_proposals/*.json
- **交互**: 继承base_phase。调用L1 api.py读写。

#### w5_05_generate_code_plan.py
- **职责**: 生成implementation_plan.md。从CC/plan提取交付物清单->渲染->写入iterations/N/。
- **输入**: PIPELINE_STATE + CC状态 + build_spec.json
- **输出**: implementation_plan.md路径
- **交互**: 继承base_phase。调用L6 plugins/ideation/plan_templates.py。

#### w5_06_wait_user_code.py
- **职责**: 等待用户在Claude Code中完成代码实现。轮询code_phase_status=="completed"。
- **输入**: PIPELINE_STATE
- **输出**: 等待中/完成信号
- **交互**: 继承base_phase。读写PIPELINE_STATE。

---

### W6 结果分析 (7个step)

管线分析 → Island/Rubric扫描 → 多Agent讨论 → 进化记忆 → Island分配 → 精炼atoms → 写入CC。

#### w6_01_run_step_pipeline.py
- **职责**: STEP管线分析(W5版本)。侧重实验结果分析: 读取实验数据->性能对比->统计检验。
- **输入**: PIPELINE_STATE (含code_results)
- **输出**: 分析结果context_bundle
- **交互**: 继承base_phase(override run逻辑)。

#### w6_02_scan_islands_rubrics.py
- **职责**: Island/Rubric扫描。扫描CC中同条件下算法变体->检测异常性能差异->触发Rubric对比。
- **输入**: CC状态 + 实验结果
- **输出**: Island异常报告 / Rubric触发信号
- **交互**: 继承base_phase。调用L1 cell_island.py和L3 rubric/scheduler.py。

#### w6_03_multi_agent_discuss.py
- **职责**: 多Agent汇总讨论。analyst+planner+researcher各自独立推理->汇总共识。注入CC迭代上下文。
- **输入**: PIPELINE_STATE + 分析结果 + CC迭代上下文
- **输出**: 讨论结论
- **交互**: 继承base_phase。调用L5 application通过MCP discuss。

#### w6_04_evolution_memory.py
- **职责**: 记录W6分析结论到进化记忆(ESE类型—实验记忆)。
- **输入**: W6分析结果
- **输出**: 写入确认
- **交互**: 继承base_phase。调用L2 sdk/memory/memory.py。

#### w6_05_island_assign.py
- **职责**: 变体入岛分配+检测Island合并候选。
- **输入**: CC状态 + 新实验结果
- **输出**: Island分配 [{algo_id, island_id}] / 合并建议
- **交互**: 继承base_phase。调用L1 cell_island.py。

#### w6_06_refine_atoms.py
- **职责**: CC atoms翻译为具体算法规格。对每个method+proposal atom生成refined_proposal JSON(含core_method_body/architecture_changes/loss_function_signature等)。实验反馈后精炼。
- **输入**: CC atoms列表 + 实验结果
- **输出**: refined_proposals/*.json
- **交互**: 继承base_phase。调用L1 api.py读写。

#### w6_07_write_claim_chain.py
- **职责**: 将W6实验结果+Island分配+refined规格写入CC。创建experiment atom+validates/contradicts relation。
- **输入**: W6分析结果 + Island分配 + refined atoms
- **输出**: CC写入确认
- **交互**: 继承base_phase。调用L1 claim_chain/api.py。

---

### W7 论文写作

#### w7_01_invoke_skill_write.py
- **职责**: 调用/evo-write skill。基于全部CC状态+实验结果->生成论文markdown。不编造结果，包含负结果和局限性。
- **输入**: PIPELINE_STATE + CC状态
- **输出**: final_report.md路径
- **交互**: 继承base_phase。调用L6 plugins/writing/的skill。

---

### W8 审阅

#### w8_01_invoke_skill_review.py
- **职责**: 调用/evo-review skill。外部LLM审阅论文->评分<7/10则回到W6，否则通过。
- **输入**: 论文路径 + 审阅标准(target>=7/10)
- **输出**: 审阅意见 + 评分 + pass/fail
- **交互**: 继承base_phase。调用L6 plugins/validation/的skill。失败时设置phase="W6 Write"。

---

### ELO + Rubric (属于L3)

#### elo/tournament.py
- **职责**: 5维ELO pairwise评分。EloTournament类: rank(proposals)->生成所有matchup->LLM judge逐对比较(_compare)->更新ELO rating(K=32)->计算各维度平均分。5维: elo_novelty+validity+impact+reliability+product_satisfaction。verify_and_judge_regeneration()做3层校验。
- **输入**: proposals列表 / phase字符串
- **输出**: ranked proposals(带elo_rating+dimension_scores)
- **交互**: 被各phase的elo_tournament step调用。

#### elo/neighborhood.py
- **职责**: RND评价。BGE-M3嵌入+compute_rnd(ND=mean cosine to Q=50 nearest, RND=percentile_rank in P=100)。值越高=越稀疏=越新颖。
- **输入**: 文本列表 / KB路径
- **输出**: [{novelty_coarse, nearest_neighbors}]
- **交互**: 被各phase的evaluate_novelty step调用。

#### rubric/novelty.py
- **职责**: LLM 5维rubric精筛。与BASELINE_DESCRIPTIONS对比->返回novelty_score(0-1)+各维度分+解释。合并公式: rubric_novelty=0.5*rnd_coarse+0.5*fine。
- **输入**: proposals + RND结果 + baseline描述
- **输出**: proposals(增加rubric_novelty/rnd_coarse/rnd_fine)
- **交互**: 被各phase的evaluate_novelty step调用。

#### rubric/scheduler.py
- **职责**: Rubric调度器。管理多维度评分时机+触发条件。
- **交互**: 被controller.py和w5_02调用。

#### rubric/format_verifier.py
- **职责**: 格式校验LLM(MiMo)。verify()->FormatResult{format_correct,fields:{present,content,score},missing_fields,reformatted_text}。reformat()->重组文本。最多递归2次。
- **输入**: proposal text + product_spec
- **输出**: FormatResult
- **交互**: 被各phase的verify_products step调用。

---

## Layer 4: session/

### session.py
- **职责**: Session核心数据结构(OpenRath-style)。Session不是消息列表——是结构化Chunk序列+Lineage图+Metadata。支持fork/merge/detach操作。每个Session有唯一ID+创建时间+workspace关联+parent指针+LineageGraph。
- **输入**: 初始prompt / 持久化数据
- **输出**: Session对象
- **交互**: manager.py创建和管理。持久化到disk via persistence。

### chunk.py
- **职责**: Session数据单元。定义ChunkKind(user_text|assistant_turn|system_text|tool_feedback|pipeline_event)、ChunkRow(id+kind+content+timestamp+metadata)、ChunkTable(有序集合)。提供chunk_table_to_messages()转换给LangGraph消费。
- **输入**: 文本/tool结果/管线事件
- **输出**: Chunk对象 / LangGraph messages列表
- **交互**: session.py使用。compress.py读取。

### compress.py
- **职责**: Session上下文压缩。当chunks总token数超出限制→自动将最旧N个chunks压缩为一个摘要chunk(LLM摘要)→保持上下文在限制内。
- **输入**: Session + max_tokens
- **输出**: 压缩后的Session (旧chunks→摘要chunk)
- **交互**: manager.py在每次agent调用前检查并调用。

### lineage.py
- **职责**: Session谱系追踪。记录fork关系(parent→child)、merge关系(branch_a+branch_b→merged)、每个session由哪个role/branch/tool_call/workspace产生。支持ancestors_bfs/descendants_dfs查询。
- **输入**: session event (fork/merge/create)
- **输出**: LineageGraph更新 / 谱系查询结果
- **交互**: session.py的fork/merge操作调用。dashboard可视化session关系。

### manager.py
- **职责**: AgentSession生命周期管理。创建session(分配ID+初始化chunks+LLM配置)→恢复session(从disk加载)→运行agent(调用factory创建agent→执行→收集chunks)→销毁session。每次调用前检查是否需要compress。
- **输入**: workspace_dir / model / provider / session_id(恢复时)
- **输出**: Session对象 / agent响应 / 状态查询结果
- **交互**: 中心协调器。使用session/chunk/compress/lineage/factory/llm/stream所有子模块。

### factory.py
- **职责**: Agent创建工厂。根据配置(workspace/model/provider/role_models)构建带sub-agent/tool/middleware的完整LangGraph Agent实例。解析persona定义→注入system prompt→注册tools→安装middleware→编译agent图。
- **输入**: workspace_dir / model / provider / role_models
- **输出**: 可执行的Agent实例(LangGraph CompiledGraph)
- **交互**: manager.py调用。使用llm/models获取LLM。使用L5 application/prompts+middleware。使用L2 sdk/tools(通过MCP)。

### backend.py
- **职责**: DeepAgents后端集成。提供文件系统后端(读写workspace文件)+复合后端(组合多个backend)。
- **输入**: workspace配置
- **输出**: Backend实例(实现read/write/list接口)
- **交互**: factory.py在构建agent时使用。

### registry.py
- **职责**: Agent注册表。RSPL协议——注册agent元数据(名称/能力/状态)→查询可用agent→更新agent状态。
- **输入**: agent元数据 / 查询请求
- **输出**: 注册确认 / agent列表
- **交互**: manager.py在创建session时注册。

### event_bus.py
- **职责**: 进程内事件总线。异步fan-out——发布事件→所有订阅者收到。用于Dashboard SSE推送。
- **输入**: 事件dict (type + data)
- **输出**: 广播到所有订阅者
- **交互**: manager.py发布事件。L2 sdk/dashboard.py订阅。

### utils.py
- **职责**: Session层通用工具。generate_session_id(唯一ID生成)/now_iso(ISO时间戳)/truncate(文本截断)。
- **输入**: 工具参数
- **输出**: 工具结果
- **交互**: manager.py和其他模块使用。

### llm/models.py
- **职责**: LLM模型统一配置。支持多provider(Anthropic/OpenAI/DeepSeek/SiliconFlow/OpenRouter/Zhipu/Volcengine/DashScope/Moonshot/NVIDIA/Ollama)。get_chat_model(model, provider, **kwargs)→LangChain ChatModel。自动处理provider-specific配置(thinking/reasoning/base_url/api_key)。
- **输入**: model名称 / provider名称 / 额外配置
- **输出**: LangChain ChatModel实例
- **交互**: factory.py和manager.py调用。

### llm/patches.py
- **职责**: Provider兼容性补丁。修复第三方provider的list content→string转换、reasoning_details→content合并等问题。
- **输入**: ChatModel实例
- **输出**: patched ChatModel
- **交互**: llm/models.py在创建模型后调用。

### config/settings.py
- **职责**: Agent配置管理。读取环境变量(EVOSCIENTIST_*)+配置文件→合并优先级→应用有效配置。get_effective_config()/apply_config_to_env()。
- **输入**: 配置查询 / 环境变量
- **输出**: 有效配置dict / 环境变量更新
- **交互**: factory.py和manager.py调用。

### stream/events.py
- **职责**: SSE事件流生成器。将Agent的LangGraph执行事件(tool_call/tool_result/agent_message/error)→转换为Dashboard可消费的SSE事件→yield。
- **输入**: Agent stream (LangGraph event stream)
- **输出**: SSE事件yield (Server-Sent Events格式)
- **交互**: manager.py在运行agent时调用。使用emitter/tracker/utils。

### stream/state.py
- **职责**: 流状态追踪。管理SubAgentState(每个sub-agent的当前状态)/StreamState(整体流状态)/TODO统计(完成/进行中/待开始)。
- **输入**: 流事件
- **输出**: 状态快照 / TODO统计
- **交互**: stream/events.py使用。

### stream/emitter.py
- **职责**: 标准化事件创建器。创建StreamEvent(带type/timestamp/data的标准事件对象)。
- **输入**: 事件数据
- **输出**: StreamEvent对象
- **交互**: stream/events.py使用。

### stream/tracker.py
- **职责**: 工具调用追踪器。增量JSON解析tool_call参数→追踪每个tool call的完整生命周期(开始→参数累积→完成→结果)。
- **输入**: tool_call chunks
- **输出**: ToolCallInfo对象
- **交互**: stream/events.py使用。

### stream/stream_utils.py
- **职责**: 流工具函数集。文本截断/格式化/状态符号(✅/❌/⏳)/计数/tree输出。
- **输入**: 文本/数据/状态
- **输出**: 格式化结果
- **交互**: stream/events.py使用。

### paths.py
- **职责**: EvoScientist运行时路径解析。从环境变量读取→提供WORKSPACE_ROOT/RUNS_DIR/MEMORY_DIR/USER_SKILLS_DIR/MEDIA_DIR等路径。
- **输入**: 环境变量
- **输出**: Path对象
- **交互**: L5 application/middleware/memory.py和L4 session/manager.py使用。

### runtime_utils.py
- **职责**: EvoScientist通用工具函数。load_subagents(加载sub-agent定义)/其他工具函数。
- **输入**: sub-agent配置路径
- **输出**: sub-agent定义列表
- **交互**: factory.py使用。

---

## Layer 5: application/

### orchestrator.py
- **职责**: Agent图构建器。定义主Agent+sub-agent的LangGraph工作流——节点(sub-agent调用/工具调用/反思)、边(顺序/条件/并行)、状态管理。create_agent_graph()→CompiledGraph。
- **输入**: 工具列表 / 系统提示词 / 中间件列表 / sub-agent定义
- **输出**: 可执行的CompiledGraph
- **交互**: L4 session/factory.py调用。使用prompts.py和middleware/。

### prompts.py
- **职责**: Persona提示词模板。定义各persona的系统提示词——RESEARCHER_INSTRUCTIONS/get_system_prompt(persona_name)。每个persona有不同的研究视角和输出风格。
- **输入**: persona名称
- **输出**: 系统提示词字符串
- **交互**: L4 session/factory.py在创建agent时调用。

### personas/novel_academic.py
- **职责**: novel-academic persona。学术创新型——偏好探索新颖理论方向，引用文献，重视科学严谨性。
- **输入**: 研究topic + persona配置
- **输出**: persona agent定义(名称/系统提示词/工具列表/模型偏好)
- **交互**: L3 pes_controller/steps/invoke_personas.py调用。

### personas/conservative_academic.py
- **职责**: conservative-academic persona。保守学术型——偏好已有理论延伸，重视可复现性，谨慎创新。

### personas/novel_engineering.py
- **职责**: novel-engineering persona。创新工程型——偏好实现新颖架构，重视计算效率和可部署性。

### personas/conservative_engineering.py
- **职责**: conservative-engineering persona。保守工程型——偏好成熟技术栈，重视稳定性和向后兼容。

### meta/meta_agent.py
- **职责**: Meta进化Agent。LLM驱动的自我改进——分析fitness趋势→发现改进机会→提案新策略→提交给validator验证。
- **输入**: CC状态 / fitness历史 / 当前策略
- **输出**: 新策略提案 {strategy_change, rationale, expected_impact}
- **交互**: 被L2 sdk/memory/evo_auto_evolve.py调用。调用evolution/validator验证。

### evolution/strategy.py
- **职责**: 可进化策略文件管理。管理策略的完整生命周期——创建→激活→归档→rollback。支持版本追踪和差异比较。
- **输入**: strategy变更请求 / 版本号
- **输出**: 策略状态 / 版本历史
- **交互**: meta/meta_agent.py和pipeline.py使用。

### evolution/validator.py
- **职责**: 进化验证器。对新策略做安全验证——检查regression(fitness不能下降)→检查约束(不能违反核心规则)→自动rollback on failure。
- **输入**: 新策略 + fitness变化
- **输出**: validation result {pass/rollback, reason}
- **交互**: meta/meta_agent.py和pipeline.py使用。

### evolution/trigger.py
- **职责**: Meta-cognition触发器。分析fitness趋势+时间窗口→判断是否触发self-improvement。避免过早优化和过晚停滞。
- **输入**: fitness历史 / 时间窗口 / 触发条件
- **输出**: 触发信号 {should_evolve: bool, reason}
- **交互**: evo_auto_evolve.py使用。

### evolution/scoring.py
- **职责**: LLM文章质量评分。评估进化产生的文章/策略的质量分数。
- **输入**: 文章文本 / 评分标准
- **输出**: 质量分数 + 维度分解
- **交互**: pipeline.py使用。

### evolution/pipeline.py
- **职责**: 进化管线编排。3阶段: Plan(分析CC+fitness→规划进化方向)→Research(调研可行性)→Ideate(生成具体策略变更)。含自动distillation。
- **输入**: CC状态 / 进化记忆 / 触发信号
- **输出**: 进化后的策略变更
- **交互**: 调用evolution/下其他模块。被evo_auto_evolve.py调用。

### evolution/tree_search.py
- **职责**: Idea Tree Search。K路并行探索——从根idea出发→生成子idea→ELO评分→剪枝→保留最优K路→继续探索。用CC做idea grounding。
- **输入**: 根idea / 探索参数(K/深度/剪枝阈值)
- **输出**: 最优idea路径
- **交互**: 调用L3 elo/tournament.py做ELO剪枝。与L1 CC交互做idea验证。

### memory/evo_auto_evolve.py
- **职责**: 自动进化引擎(从L2移入)。Island GA + MAP-Elites驱动的自主实验循环——读取CC→生成变体→提交实验→收集fitness→进化策略。
- **输入**: CC状态 / fitness历史 / 进化参数
- **输出**: 进化建议 / 策略变更 / 实验提案
- **交互**: 读取L1 CC。调用evolution/pipeline。属于应用层逻辑。

### skill_manager.py
- **职责**: Skill管理工具(从L2移入)。Agent可调用的tool——安装/卸载/列出skill。LangChain @tool封装。
- **输入**: skill名称 / 操作类型
- **输出**: 操作结果
- **交互**: 被L5 application的Agent通过tool接口调用。

### think.py
- **职责**: 反思工具(从L2移入)。Agent用于结构化决策——暂停→分析当前状态→评估选项→做出决策。LangChain @tool封装。
- **输入**: 思考内容(自由文本)
- **输出**: 结构化决策
- **交互**: 被L5 application的Agent通过tool接口调用。

### middleware/middleware_utils.py
- **职责**: 中间件共享工具函数。disable_thinking等。
- **输入**: 工具参数
- **输出**: 工具结果
- **交互**: 被各middleware模块使用。

---

## Layer 6: plugins/

按功能阶段组织。每个子目录包含Python工具+对应阶段的Claude Code SKILL.md。

- **ideation/** — structure_mapping.py + plan_templates.py + domain_presets.py + skills(evo-planner/evo-ideation/evo-intake/idea-creator)
- **experimentation/** — recorder.py + agent_task.py + trainer_contract.py + skills(evo-code*/evo-run/evo-debug/run-experiment)
- **research/** — skills(evo-research/research-lit/arxiv/semantic-scholar)
- **validation/** — verify_atom.py + verify_plan.py + cleanup.py + skills(evo-claim/evo-review/result-to-claim)
- **writing/** — research_wiki.py + markdown_parser.py + skills(evo-write/paper-*)
- **reporting/** — event_log.py + vault_manager.py + skills(evo-analyze/analyze-results)
- **pipeline/** — skills(evo-pipeline/evo-boot/evo-iterate/evo-memory/evo-evolve)
- **grounding/** — literature_search.py (placeholder, 待W3接入)

---

## Layer 7: AUTORESEARCH/sessions/
所有管线运行时数据统一存储位置。在EvoScientist-claude项目目录外。

---

## old/ 归档清单 (16项, 同v5)

## 实施阶段 (6 Phase, 同v5)
