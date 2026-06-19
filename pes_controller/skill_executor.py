"""Skill Executor — 统一执行入口。

所有 step 都通过 SkillExecutor.execute() 执行。
支持两种模式：
  - execution: llm   → 读 SKILL.md prompt → 填充变量 → 调 LLM → 解析 JSON → 写文件
  - execution: python → 动态加载 Python 函数并调用
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from pes_controller.types import SkillConfig, SkillResult

logger = logging.getLogger(__name__)


class SkillExecutor:
    """唯一执行入口。"""

    def __init__(
        self,
        skills_dir: Path,
        llm_client: Any,        # LLMClient
        tavily_client: Any = None,  # TavilyClient | None
    ):
        self.skills_dir = skills_dir
        self.llm_client = llm_client
        self.tavily_client = tavily_client
        self.sessions: dict[str, list[dict]] = {}

    def execute(
        self,
        skill_name: str,
        variables: dict[str, Any],
        session_id: str | None = None,
        pre_search: str | None = None,
    ) -> SkillResult:
        """执行一个 skill。

        Args:
            skill_name: skill 目录名（如 "persona-novel-academic"）
            variables: 模板变量映射
            session_id: 多轮对话 ID（None 表示单次调用）
            pre_search: 可选搜索查询（调 Tavily 后注入 search_results 变量）

        Returns:
            SkillResult
        """
        # 1. 解析 SKILL.md
        config, prompt = self._parse_skill(skill_name)
        logger.info(
            "SkillExecutor.execute skill=%s execution=%s",
            skill_name, config.execution,
        )

        # 2. 可选 Tavily 搜索
        if pre_search and self.tavily_client:
            results = self.tavily_client.search(pre_search)
            variables["search_results"] = json.dumps(
                results, ensure_ascii=False
            )

        # 3. 根据执行模式分发
        if config.execution == "python":
            return self._execute_python(config, variables)

        return self._execute_llm(config, prompt, variables, session_id)

    # ── LLM 模式 ──

    def _execute_llm(
        self,
        config: SkillConfig,
        prompt: str,
        variables: dict[str, Any],
        session_id: str | None,
    ) -> SkillResult:
        """execution: llm — 填充变量 → 调 LLM → 解析 JSON → 执行操作。"""
        # 填充变量
        filled = self._fill_template(prompt, variables)

        # 构建消息
        if session_id and session_id in self.sessions:
            messages = self.sessions[session_id].copy()
            messages.append({"role": "user", "content": filled})
        else:
            messages = [{"role": "user", "content": filled}]

        # 调用 LLM（带重试）
        content, usage = self.llm_client.chat_with_retry(messages)

        logger.debug(
            "SkillExecutor LLM response length=%d tokens=%s",
            len(content), usage,
        )

        # 保存会话
        if session_id:
            messages.append({"role": "assistant", "content": content})
            self.sessions[session_id] = messages

        # 解析 JSON
        parsed = self._parse_json_response(content)

        # 执行文件/命令操作
        actions_result = self._execute_actions(
            parsed, variables.get("workspace_dir", ".")
        )

        return SkillResult(
            success=True,
            files_written=actions_result.get("files_written", []),
            actions_executed=actions_result.get("actions_executed", []),
            llm_response=content,
            raw_content=content,
        )

    # ── Python 模式 ──

    def _execute_python(
        self, config: SkillConfig, variables: dict[str, Any]
    ) -> SkillResult:
        """execution: python — 动态加载并调用 Python 函数。"""
        if not config.handler:
            return SkillResult(
                success=False,
                llm_response="Error: execution=python but no handler specified",
            )

        try:
            module_path, func_name = config.handler.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler_fn = getattr(module, func_name)
            result = handler_fn(variables)

            if isinstance(result, SkillResult):
                return result

            # 兼容返回 dict 的 handler
            return SkillResult(
                success=result.get("success", True),
                files_written=result.get("files_written", []),
                actions_executed=result.get("actions_executed", []),
                llm_response=result.get("message", ""),
            )
        except Exception as e:
            logger.error(
                "SkillExecutor Python handler failed: %s.%s: %s",
                config.handler, e,
            )
            return SkillResult(success=False, llm_response=f"Handler error: {e}")

    # ── SKILL.md 解析 ──

    def _parse_skill(self, skill_name: str) -> tuple[SkillConfig, str]:
        """解析 SKILL.md 的 YAML frontmatter + prompt body。"""
        path = self.skills_dir / skill_name / "SKILL.md"
        if not path.exists():
            logger.warning("SKILL.md not found: %s", path)
            return SkillConfig(name=skill_name), ""

        raw = path.read_text(encoding="utf-8")
        config = SkillConfig(name=skill_name)
        prompt = raw

        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                yaml_text = raw[3:end].strip()
                try:
                    import yaml
                    meta = yaml.safe_load(yaml_text) or {}
                except ImportError:
                    meta = self._parse_yaml_fallback(yaml_text)

                config.execution = meta.get("execution", "llm")
                config.handler = meta.get("handler", "")
                config.description = meta.get("description", "")
                config.variables = meta.get("variables", [])
                prompt = raw[end + 3:].strip()

        return config, prompt

    def _parse_yaml_fallback(self, text: str) -> dict:
        """简单 YAML 解析 fallback（无 pyyaml 依赖时使用）。"""
        result = {}
        for line in text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip().strip('"').strip("'")
        return result

    # ── 模板填充 ──

    def _fill_template(self, template: str, variables: dict[str, Any]) -> str:
        """替换 {{variable}} 占位符。"""
        for key, value in variables.items():
            template = template.replace("{{" + key + "}}", str(value))

        # 处理 {{#if condition}} ... {{#endif}} 条件块
        template = self._process_conditionals(template, variables)
        return template

    def _process_conditionals(
        self, template: str, variables: dict[str, Any]
    ) -> str:
        """处理 {{#if var == value}} ... {{#endif}} 条件块。"""
        pattern = r'\{\{#if\s+(\w+)\s*==\s*"([^"]+)"\}\}(.*?)\{\{#endif\}\}'
        while True:
            match = re.search(pattern, template, re.DOTALL)
            if not match:
                break
            var_name, expected, body = match.groups()
            actual = str(variables.get(var_name, ""))
            replacement = body if actual == expected else ""
            template = template[:match.start()] + replacement + template[match.end():]
        return template

    # ── JSON 解析 ──

    def _parse_json_response(self, content: str) -> dict:
        """从 LLM 响应中提取 JSON。"""
        # 尝试 ```json ... ``` 代码块
        json_match = re.search(
            r'```json\s*\n(.*?)\n```', content, re.DOTALL
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 返回原始文本
        return {"files": [], "actions": [], "raw_text": content}

    # ── 文件/命令操作 ──

    def _execute_actions(
        self, parsed: dict, workspace_dir: str
    ) -> dict[str, Any]:
        """执行文件写入和命令。"""
        ws = Path(workspace_dir)
        files_written: list[str] = []
        actions_executed: list[dict] = []

        for f in parsed.get("files", []):
            path = ws / f["path"]
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f["content"], encoding="utf-8")
                files_written.append(str(path))
            except Exception as e:
                logger.error("File write failed %s: %s", path, e)
                actions_executed.append({
                    "type": "file_write_error",
                    "path": str(path),
                    "error": str(e),
                })

        for a in parsed.get("actions", []):
            # Handle both dict {"command": "..."} and plain string formats
            if isinstance(a, str):
                cmd = a
            elif isinstance(a, dict):
                cmd = a.get("command", "")
            else:
                continue
            if not cmd:
                continue
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    cwd=str(ws), timeout=300,
                )
                actions_executed.append({
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout": result.stdout[:1000],
                    "stderr": result.stderr[:1000],
                })
            except subprocess.TimeoutExpired:
                actions_executed.append({
                    "command": cmd,
                    "returncode": -1,
                    "error": "Timeout (300s)",
                })
            except Exception as e:
                actions_executed.append({
                    "command": cmd,
                    "returncode": -1,
                    "error": str(e),
                })

        return {
            "files_written": files_written,
            "actions_executed": actions_executed,
        }
