---
name: evo-pipeline
description: "Pipeline 一键启动。自动启动 Dashboard（如未运行）+ 初始化工作空间 + 输出 Dashboard URL。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write
---

# EvoScientist Pipeline — 一键启动

研究问题: **$ARGUMENTS**

项目根目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude`
工作空间目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH`

## 步骤 0: 确保 Dashboard 在运行

检查 Dashboard：

```
curl -s -o /dev/null -w '%{http_code}' http://localhost:8420/
```

如果返回不是 200，后台启动：

```
/home/exuber/anaconda3/envs/evo-agents/bin/python /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude/tools/start_dashboard.py
```

## 步骤 1: Bootstrap 工作空间

```
python /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude/tools/bootstrap.py '$ARGUMENTS' /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH
```

注意: 研究问题用单引号包裹以避免特殊字符问题。
从输出中提取 session_id 和 dashboard_url。

## 步骤 2: 展示 Dashboard URL

```
"================================================"
"Pipeline 已就绪。请在浏览器中打开:"
"  {dashboard_url}"
"后续所有操作都在 Dashboard 网页端完成。"
"================================================"
```
