---
name: flux-pipeline
description: "Pipeline 一键启动。清理旧进程 → GitHub搜索baseline → 用户确认 → Bootstrap → 启动 Dashboard。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write, Skill, AskUserQuestion
---

# Flux-Insight Pipeline — 一键启动

研究问题: **$ARGUMENTS**

## 路径约定

本 SKILL 使用以下变量。Claude Code 执行时自动解析为实际路径：

| 变量 | 含义 | 自动发现方式 |
|------|------|-------------|
| `PROJECT_ROOT` | Flux-Insight 项目根目录 | 搜索包含 `CLAUDE.md` + `run_dashboard.py` 的目录 |
| `WORKSPACE_ROOT` | 工作空间根目录 | `PROJECT_ROOT` 的父目录 |
| `SKILLS_ROOT` | Claude Code Skills 目录 | `~/.claude/skills` |
| `PYTHON_BIN` | Python (需 BGE-M3/FlagEmbedding) | `python3` 或 conda env，见步骤 0 |

**在开始前，先执行以下发现命令，后续所有代码块使用这些 shell 变量：**

```bash
# 自动发现 PROJECT_ROOT (从当前目录向上搜索)
_find_project_root() {
    local d="$1"
    while [ "$d" != "/" ]; do
        if [ -f "$d/CLAUDE.md" ] && [ -f "$d/run_dashboard.py" ]; then
            echo "$d"
            return 0
        fi
        d=$(dirname "$d")
    done
    # Fallback: search home directory (max depth 6)
    find "$HOME" -maxdepth 6 -name "run_dashboard.py" -path "*/Flux-Insight/*" 2>/dev/null | head -1 | xargs dirname 2>/dev/null
}
PROJECT_ROOT=$(_find_project_root "$(pwd)")
WORKSPACE_ROOT=$(dirname "$PROJECT_ROOT")

echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "WORKSPACE_ROOT=$WORKSPACE_ROOT"
```

## 步骤 0: 清理旧进程 + 残留数据

杀掉旧 Dashboard，清理残留状态：

```bash
pkill -f "run_dashboard" 2>/dev/null; sleep 2
```

```bash
python3 -c "
import json
from pathlib import Path

ws = Path('$WORKSPACE_ROOT')
sp = ws / 'PIPELINE_STATE.json'
s = {}
if sp.exists():
    s = json.loads(sp.read_text())
    for key in ['agent_heartbeat', 'agent_report', 'approval_request',
                'approval_response', 'active_task', 'command',
                'code_phase_status', 'code_results', 'code_session_dir']:
        s.pop(key, None)
    sp.write_text(json.dumps(s, indent=2, ensure_ascii=False))
    print('PIPELINE_STATE.json cleaned')
else:
    print('No PIPELINE_STATE.json, skipping')

sdir = ws / '.evo_sessions'
if sdir.exists():
    current_sid = s.get('session_id', '')
    for f in sdir.glob('*.json'):
        if f.stem != current_sid:
            f.unlink()
    print('.evo_sessions cleaned')

rpath = Path('$PROJECT_ROOT') / 'agent-manager/.evo_session_registry.json'
if rpath.exists():
    registry = json.loads(rpath.read_text())
    valid = {sid: wspath for sid, wspath in registry.items()
             if (Path(wspath) / '.evo_sessions' / f'{sid}.json').exists()}
    if len(valid) != len(registry):
        rpath.write_text(json.dumps(valid, indent=2))
        print(f'Registry cleaned: {len(registry)} -> {len(valid)}')
    else:
        print('Registry clean')
"
```

## 步骤 0.5: 选择 Embedding 服务

**先检测当前环境可用的 embedding 方案，然后让用户选择。**

```bash
# 检测 BGE-M3 是否可用
python3 -c "import FlagEmbedding; print('BGE_M3_AVAILABLE=true')" 2>/dev/null || echo "BGE_M3_AVAILABLE=false"
```

然后调用 `AskUserQuestion`，问题：「Pipeline 需要 Embedding 服务（用于语义搜索、去重、创新性评估）。请选择 Embedding 方案：」

选项：
1. **本地 BGE-M3**（推荐，免费，需 `pip install FlagEmbedding`，推荐 GPU）— 仅当 BGE_M3_AVAILABLE=true 时显示
2. **DeepSeek Chat API 语义指纹**（使用现有 DEEPSEEK_API_KEY，无需本地模型，64 维语义向量）
3. **自定义 API**（OpenAI / OpenRouter / 本地 Ollama 等兼容 OpenAI /v1/embeddings 的端点）

根据用户选择，写入环境变量到 `$WORKSPACE_ROOT/.env.embedding`：

```bash
# 如果用户选了 DeepSeek Chat API 语义指纹
echo 'EMBEDDING_PROVIDER=llm' > "$WORKSPACE_ROOT/.env.embedding"
echo 'EMBEDDING_API_KEY='"$DEEPSEEK_API_KEY" >> "$WORKSPACE_ROOT/.env.embedding"
echo 'EMBEDDING_BASE_URL='"$DEEPSEEK_BASE_URL" >> "$WORKSPACE_ROOT/.env.embedding"
echo 'EMBEDDING_MODEL='"${EMBEDDING_MODEL:-deepseek-chat}" >> "$WORKSPACE_ROOT/.env.embedding"

# 如果用户选了 BGE-M3
echo 'EMBEDDING_PROVIDER=bge_m3' > "$WORKSPACE_ROOT/.env.embedding"

# 如果用户选了自定义 API（需要用户提供 API_KEY, BASE_URL, MODEL）
echo 'EMBEDDING_PROVIDER=api' > "$WORKSPACE_ROOT/.env.embedding"
echo 'EMBEDDING_API_KEY=<用户提供的key>' >> "$WORKSPACE_ROOT/.env.embedding"
echo 'EMBEDDING_BASE_URL=<用户提供的url>' >> "$WORKSPACE_ROOT/.env.embedding"
echo 'EMBEDDING_MODEL=<用户提供的model>' >> "$WORKSPACE_ROOT/.env.embedding"
```

然后验证 embedding 可用：

```bash
# 加载配置并测试
export $(cat "$WORKSPACE_ROOT/.env.embedding" | xargs) && cd "$PROJECT_ROOT" && python3 -c "
import sys
sys.path.insert(0, '.')
from pes_controller.embedding_provider import get_embedding_provider
p = get_embedding_provider()
if p is None:
    print('ERROR: No embedding provider available')
    sys.exit(1)
vecs = p.encode(['test embedding'])
print(f'OK: provider={p.name}, dim={vecs.shape[1]}')
"
```

如果测试失败，提示用户：
- 检查 API Key 是否正确
- 推荐使用 BGE-M3（本地）或 DeepSeek Chat API 语义指纹（无需本地模型）
- 重新选择或手动配置 EMBEDDING_BASE_URL 和 EMBEDDING_MODEL

## 步骤 1: GitHub 搜索 Baseline + 用户确认

**重要**: GitHub API 不支持中文搜索。必须从 `$ARGUMENTS` 中提取英文关键词后再搜索。
先用低门槛搜索获取候选，再用高门槛二次筛选。

使用 NVM Node v22 直接调用 github-search 脚本：

```bash
# 第一步: 宽搜索（低门槛，从$ARGUMENTS提取英文关键词填入<query>）
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use v22.22.2 && cd "$SKILLS_ROOT/github-search" && node scripts/github-search.mjs "<query>" --language python --min-stars 10 --limit 15 2>&1
```

根据研究领域补充多角度搜索：

```bash
# 搜索算法实现
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use v22.22.2 && cd "$SKILLS_ROOT/github-search" && node scripts/github-search.mjs "<query>" --language python --min-stars 10 --limit 15 2>&1

# 搜索框架和库
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use v22.22.2 && cd "$SKILLS_ROOT/github-search" && node scripts/github-search.mjs "<query>" --language python --min-stars 50 --limit 10 2>&1
```

如果 GitHub API 返回 0 结果（非 rate limit），执行 LLM 驱动的查询重试:

1. 调用 LLM 分析为什么搜索失败（关键词太长？太具体？中文术语？语言不匹配？）
2. LLM 生成 2-3 个重新表述的查询（将中文翻译为英文、简化关键词、使用更广泛的领域术语）
3. 使用重新表述的查询重试 GitHub 搜索
4. 最多循环 3 轮，直到找到结果或所有查询变体都已用尽
5. 只有在所有 LLM 生成的查询都失败时，才报告失败并要求用户手动输入基线

LLM 重试分析 prompt 模板:
```
GitHub API returned 0 results for query: '{query}'. Research topic: '{topic}'.
Analyze why this search likely failed (too specific? language mismatch? wrong technical terms?)
Then generate 2-3 alternative search queries that are more likely to return results.
Output as JSON: {"analysis":"...", "reformulated_queries":["query1","query2","query3"]}
```

从返回的仓库列表中提取方法名候选，按类别分组：
- **算法**: 名称/描述中含算法缩写（如 SAC, TD3, PPO, DDPG, BERT, GPT, LSTM 等）或方法名
- **框架**: 名称含 framework, library, platform, toolkit, suite
- **Benchmark**: 名称含 benchmark, environment, dataset, corpus

然后调用 `AskUserQuestion` 让用户确认：

- 第一个问题：展示发现的算法类 baseline（top-5），让用户勾选确认哪些是公认的基线方法，并提供"手动输入"选项
- 第二个问题：展示发现的框架/库（top-3），让用户勾选或跳过
- 第三个问题：展示发现的 benchmark（top-3），让用户勾选或跳过
- 第四个问题：「是否需要先测试某个 baseline 的可用性？」选项: "不需要，直接进入 Pipeline" / "需要测试（请说明哪个 baseline repo URL 或名称）"

## 步骤 1.5: Baseline 可行性测试（可选）

**仅当步骤 1 第四个问题用户选择了"需要测试"时执行。**

对用户指定的每个 baseline repo，依次执行以下测试流程：

### 1.5.1 Clone + 环境探测

```bash
BASELINE_TEST_DIR="$WORKSPACE_ROOT/baseline_tests"
mkdir -p "$BASELINE_TEST_DIR"

# Clone baseline repo（替换 <REPO_URL> 为用户指定的 URL）
cd "$BASELINE_TEST_DIR" && git clone --depth 1 <REPO_URL> 2>&1 | tail -3
BASELINE_DIR="$BASELINE_TEST_DIR/$(ls "$BASELINE_TEST_DIR" | tail -1)"
echo "Cloned to: $BASELINE_DIR"
```

### 1.5.2 读取 README + 生成测试脚本

读取 baseline repo 的 README.md / README.rst，提取：
- 安装命令（pip install / setup.py / requirements.txt）
- 示例用法（example usage / quick start）
- 入口脚本（train.py / main.py / run.py）
- 配置要求（Python 版本、依赖库、GPU 需求）

然后生成一个 `test_baseline.py` 测试脚本：

```bash
python3 -c "
import os, sys
from pathlib import Path

baseline_dir = Path('$BASELINE_DIR')
readme = ''
for name in ['README.md', 'README.rst', 'README.txt', 'README']:
    p = baseline_dir / name
    if p.exists():
        readme = p.read_text(encoding='utf-8', errors='ignore')[:5000]
        break

# 检测依赖文件
deps_info = []
for dep_file in ['requirements.txt', 'setup.py', 'setup.cfg', 'pyproject.toml', 'environment.yml']:
    if (baseline_dir / dep_file).exists():
        deps_info.append(dep_file)
        content = (baseline_dir / dep_file).read_text(encoding='utf-8', errors='ignore')[:2000]
        print(f'=== {dep_file} ===')
        print(content)

# 检测入口脚本
entry_points = []
for ep in ['train.py', 'main.py', 'run.py', 'test.py', 'evaluate.py', 'demo.py', 'example.py']:
    if (baseline_dir / ep).exists():
        entry_points.append(ep)
    # 也检查子目录
    for sub in ['scripts', 'examples', 'tools', 'bin']:
        sub_ep = baseline_dir / sub / ep
        if sub_ep.exists():
            entry_points.append(f'{sub}/{ep}')

print(f'\n=== README (first 3000 chars) ===')
print(readme[:3000])
print(f'\n=== Detected deps files: {deps_info} ===')
print(f'=== Detected entry points: {entry_points} ===')
"
```

### 1.5.3 安装依赖 + 运行快速测试

根据探测结果，安装依赖并运行一个快速验证（短 episode / 小数据集 / dry-run）：

```bash
cd "$BASELINE_DIR"

# 安装依赖
if [ -f requirements.txt ]; then
    pip install -r requirements.txt 2>&1 | tail -5
fi
if [ -f setup.py ]; then
    pip install -e . 2>&1 | tail -5
fi

# 运行快速测试（dry-run / 1 episode / --help）
# 根据具体 baseline 调整命令：
#   如果是 RL 算法：通常 python train.py --env <env> --num-steps 1000 --eval-interval 500
#   如果是 ML 库：通常 python -m pytest tests/ -x --timeout=30 或 python example.py
#   优先查找 --help 输出确定可用参数
python3 -c "
import subprocess, sys
from pathlib import Path

bd = Path('$BASELINE_DIR')
# 尝试找到入口并运行 --help
for ep in ['train.py', 'main.py', 'run.py', 'demo.py']:
    ep_path = bd / ep
    if ep_path.exists():
        # 先试 --help
        r = subprocess.run([sys.executable, str(ep_path), '--help'],
                          capture_output=True, text=True, timeout=15)
        help_text = r.stdout[:2000] if r.returncode == 0 else ''
        if help_text:
            print(f'=== {ep} --help ===')
            print(help_text[:2000])
        break
"
```

**然后用 AskUserQuestion 向用户展示测试结果并确认**：

- 展示内容：clone 是否成功、依赖是否安装、入口脚本是否可运行、--help 输出摘要
- 问题：「Baseline 测试结果如何？」选项:
  - "测试通过，可以复现" 
  - "依赖安装失败（说明错误）"
  - "运行报错（说明错误）"
  - "跳过测试，继续 Pipeline"

### 1.5.4 记录测试结果

无论测试是否通过，将结果记录到工作空间：

```bash
python3 -c "
import json
from pathlib import Path
from datetime import datetime

test_dir = Path('$BASELINE_TEST_DIR')
result = {
    'baseline': '$(basename $BASELINE_DIR)',
    'timestamp': datetime.now().isoformat(),
    'status': 'passed',  # passed / failed / skipped
    'entry_points': [],  # 从 1.5.2 检测结果填入
    'deps_installed': True,
    'notes': '',  # 用户反馈
}
(test_dir / 'baseline_test_result.json').write_text(
    json.dumps(result, indent=2, ensure_ascii=False))
print('Test result saved')
"
```

**测试完成后，无论通过与否，都继续执行步骤 2（Bootstrap）。** 测试失败的 baseline 会在后续 W2 分析阶段被标记为"不可用"。

## 步骤 2: Bootstrap 工作空间

```bash
cd "$PROJECT_ROOT" && PYTHONPATH=. python3 pes_controller/bootstrap.py '$ARGUMENTS' "$WORKSPACE_ROOT"
```

从输出中提取 `session_id`、`session_dir`。

## 步骤 3: 写入确认的 Baseline (到 cc.db) + 触发 Embedding

```bash
python3 -c "
import json, sys
from pathlib import Path

sys.path.insert(0, '$PROJECT_ROOT')
from claim_chain.chain import ClaimChainV2

sd = Path('{session_dir}')
sp = sd / 'PIPELINE_STATE.json'
state = json.loads(sp.read_text())

# 写入用户确认的 baseline
state['confirmed_baselines'] = {
    'algorithms': [...],      # 从步骤1的 AskUserQuestion 结果
    'frameworks': [...],
    'benchmarks': [...],
    'user_added': [...],
}

# 写入 CC atoms 到 cc.db (canonical store)
idx = sd / '_index'
idx.mkdir(parents=True, exist_ok=True)
cc = ClaimChainV2(idx / 'cc.db')

written = 0
for cat, items in state['confirmed_baselines'].items():
    for item in items:
        if cat == 'user_added':
            source = 'user_provided'
        else:
            source = 'github_search'
        cc.add_atom(
            type='fact',
            title=item,
            content=json.dumps({'source': source, 'category': cat, 'method': item}, ensure_ascii=False),
            tags=['baseline', 'user-confirmed', cat],
            evidence_level='verified',
            metadata={'source': source, 'category': cat},
        )
        written += 1

cc.close()
sp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(f'Written {written} baseline atoms to cc.db')
"
```

## 步骤 3.5: 计算 Baseline Embeddings

**使用步骤 0.5 中选择的 Embedding 服务直接计算（无需 socket server）。**

```bash
# 加载用户在步骤 0.5 选择的 embedding 配置
if [ -f "$WORKSPACE_ROOT/.env.embedding" ]; then
    export $(cat "$WORKSPACE_ROOT/.env.embedding" | grep -v '^#' | xargs)
fi

cd "$PROJECT_ROOT" && python3 -c "
import sys, os
sys.path.insert(0, '.')
from pes_controller.embedding_provider import get_embedding_provider
from tools_legacy.cc_query_tool import _ensure_embeddings_provider

cc_db_path = '{session_dir}/_index/cc.db'
count = _ensure_embeddings_provider(cc_db_path)
if count >= 0:
    print(f'Embeddings computed: {count} atoms')
else:
    print('WARNING: No embedding provider available, embeddings will be computed later')
"
```

## 步骤 3.6: 启动 Dashboard + 展示管控指引

**根据当前操作系统选择启动方式**：

### Linux/macOS

```bash
cd "$PROJECT_ROOT" && PYTHON_BIN="${PYTHON_BIN:-python3}" && "$PYTHON_BIN" run_dashboard.py 2>&1 &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:8420/ 2>/dev/null || echo "Dashboard starting..."
```

### Windows

```powershell
cd "$PROJECT_ROOT"
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "run_dashboard.py"
Start-Sleep -Seconds 3
Invoke-WebRequest -Uri "http://localhost:8420/" -UseBasicParsing -TimeoutSec 5 | Select-Object -ExpandProperty StatusCode
```

如果端口 8420 被占用，先结束旧进程：

```powershell
Get-NetTCPConnection -LocalPort 8420 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-Sleep -Seconds 2
```

**必须向用户展示以下管控指引**（直接输出给用户，不要放在代码块里）：

---

Pipeline 已就绪。**请打开浏览器访问 Dashboard 进行全程管控**：

**http://localhost:8420**

### Dashboard 操作流程

1. **首页** — 点击你的 session 进入 Pipeline 控制页
2. **W1 Intake** — GitHub baseline 搜索结果展示，确认后点击「满意，继续」
3. **点击「执行步骤」** — 逐步推进 W2 → W3 → ... → W8
4. **W2-W6 阶段** — 每步完成后点击「满意，继续」自动推进
5. **W7.1 论文计划** — 4 个方案 + Elo 排名展示，选择 A/B/C/D 后继续
6. **W7.2-W7.5 论文写作** — 查看生成产物（LaTeX、PDF），确认后推进
7. **W8 最终审阅** — 3 轮 review+fix，审阅完成后终止

### 关键操作

| 按钮 | 含义 |
|------|------|
| 满意，继续 | 自动推进到下一阶段 |
| 退回重做 | 重新运行当前阶段 |
| 审稿意见 + 重做 | 带人工反馈重新运行 |
| 回到 W7.1 | 重新规划论文（保留归档） |
| 回到 W5 | 回到代码阶段修改算法 |
| 回到 W2 | 回到问题分析重新规划 |

**所有后续操作都通过 Dashboard 完成，无需在 Claude Code 中手动执行 pipeline 步骤。**

---
