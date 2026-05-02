# Contributing to EvoScientist-Claude

感谢你的关注！欢迎贡献代码、文档、新 Skill 或 Bug 修复。

## 贡献方式

### 1. 新增 Skill

最受欢迎的贡献方式。每个 Skill 是一个独立的 `SKILL.md` 文件：

```bash
skills/
└── your-skill-name/
    └── SKILL.md
```

Skill 格式参考现有文件（如 `skills/evo-planner/SKILL.md`），需包含：
- YAML 头部（name, description, argument-hint, allowed-tools）
- 工作流阶段（Phase 0, 1, 2...）
- Constants 定义（可覆盖参数）
- Key Rules
- Composing with Other Skills

### 2. 改进现有 Skill

- 修复工作流中的逻辑问题
- 添加新参数/模式
- 改进提示词质量

### 3. MCP Server

- 添加新的 LLM 审稿桥接
- 改进现有 MCP server 的错误处理

### 4. Agent Manager

- 改进 `UnrestrictedBackend`
- 优化多 Agent 讨论机制
- 添加新的 MCP tools

## PR 流程

1. Fork 本仓库
2. 创建分支：`git checkout -b feature/your-feature`
3. 修改代码
4. 提交：`git commit -m "Add: your feature description"`
5. 推送：`git push origin feature/your-feature`
6. 创建 Pull Request

## 代码规范

- Python：遵循 PEP 8，使用 type hints
- SKILL.md：遵循现有格式（参考 ARIS 风格）
- 提交信息：简洁明了，使用 `Add:` / `Fix:` / `Update:` 前缀

## 问题反馈

- Bug 报告：创建 Issue，附上复现步骤
- 功能建议：创建 Issue，描述使用场景

## License

贡献的��码将遵循项目的 Apache 2.0 许可证。
