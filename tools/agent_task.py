"""Agent SDK 子进程入口 — 用于 W4 Code / W6 Write / W7 Review。

Dashboard spawn 本脚本作为独立子进程，Agent SDK 在其中运行。
Agent 通过 SDK 自定义工具 report_progress / request_approval 与 Dashboard 通信。

用法:
    python tools/agent_task.py --task code --workspace /path/ws --session-id sess_xxx
    python tools/agent_task.py --task write --workspace /path/ws --session-id sess_xxx
    python tools/agent_task.py --task review --workspace /path/ws --session-id sess_xxx
"""

import argparse
import json
import os
import sys
import time
import threading
import uuid
from pathlib import Path

# Add tools/ to path so we can import pipeline_protocol
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from pipeline_protocol import (
    atomic_read, atomic_write,
    agent_write_heartbeat, agent_write_approval_request,
    agent_wait_approval, agent_write_report,
)


# ── Task configurations ──

TASK_CONFIGS = {
    "code": {
        "phase": "W4 Code",
        "description": "基于实验计划和Claim Chain，实现实验代码",
        "system_prompt": (
            "你是一个强化学习实验代码专家。你的任务是：\n"
            "1. 阅读 workspace 中的 plan.md 和 claim_chain/ 目录\n"
            "2. 基于计划实现可运行的实验代码，输出到 artifacts/ 目录\n"
            "3. 代码必须可复现，包含训练脚本和评估脚本\n"
            "4. 完成后调用 request_approval 工具等待用户确认\n"
            "5. 始终先调用 report_progress 汇报当前进度"
        ),
    },
    "write": {
        "phase": "W6 Write",
        "description": "基于所有实验结果撰写论文报告",
        "system_prompt": (
            "你是一个科学论文写作专家。你的任务是：\n"
            "1. 阅读 workspace 中的所有实验结果和分析报告\n"
            "2. 撰写一份完整的论文级 Markdown 报告\n"
            "3. 包含: 摘要、引言、方法、实验、结果分析、结论\n"
            "4. 不编造任何数据或引用\n"
            "5. 完成后调用 request_approval 工具等待用户确认"
        ),
    },
    "review": {
        "phase": "W7 Review",
        "description": "审阅论文报告，提出修改建议",
        "system_prompt": (
            "你是一个严格的科学论文审稿人。你的任务是：\n"
            "1. 阅读 workspace 中的论文报告\n"
            "2. 从方法正确性、实验充分性、结论可靠性三个维度评审\n"
            "3. 给出具体的修改建议和打分 (1-10)\n"
            "4. 完成后调用 request_approval 工具等待用户确认"
        ),
    },
}


# ── Agent context builder ──

def _build_context(workspace: Path, task: str) -> str:
    """从 workspace 目录读取上下文信息构建 agent 的初始 prompt。"""
    parts = []
    config = TASK_CONFIGS[task]

    # plan.md
    plan_path = workspace / "plan.md"
    if plan_path.exists():
        parts.append(f"## 实验计划\n{plan_path.read_text(encoding='utf-8')[:5000]}")

    # Claim Chain
    cc_dir = workspace / "claim_chain"
    if cc_dir.exists():
        atoms_path = cc_dir / "atoms.jsonl"
        if atoms_path.exists():
            parts.append(f"## Claim Chain 原子\n{atoms_path.read_text(encoding='utf-8')[:3000]}")

    # Research notes
    rn_path = workspace / "research_notes.md"
    if rn_path.exists():
        parts.append(f"## 文献调研笔记\n{rn_path.read_text(encoding='utf-8')[:3000]}")

    # Experiment results
    results_dir = workspace / "results"
    if results_dir.exists():
        summaries = list(results_dir.rglob("summary.json"))
        if summaries:
            for s in summaries[:3]:
                try:
                    data = json.loads(s.read_text(encoding='utf-8'))
                    parts.append(f"## 实验结果 ({s.parent.name})\n{json.dumps(data, indent=2)[:2000]}")
                except Exception:
                    pass

    # Existing report (for review task)
    report_path = workspace / "final_report.md"
    if report_path.exists():
        parts.append(f"## 论文报告\n{report_path.read_text(encoding='utf-8')[:8000]}")

    # Experiment log
    log_path = workspace / "experiment_log.md"
    if log_path.exists():
        parts.append(f"## 实验日志\n{log_path.read_text(encoding='utf-8')[:3000]}")

    context = "\n\n".join(parts) if parts else "(空工作空间，请从零开始)"
    return f"{config['system_prompt']}\n\n工作空间: {workspace}\n\n{context}"


# ── Heartbeat thread ──

_done = False
_current_step = "initializing"
_state_path = None


def _heartbeat_loop():
    """独立心跳线程：每 60 秒写一次 agent_heartbeat。"""
    global _done
    while not _done:
        time.sleep(60)
        if _done:
            break
        try:
            agent_write_heartbeat(_state_path, _current_step)
        except Exception:
            pass  # 心跳失败不中断主流程


# ── SDK Custom Tools (in-process, via @tool decorator) ──

# 注意: 这些工具在 Agent SDK 子进程中运行。
# 它们通过 pipeline_protocol 与 Dashboard 共享的 PIPELINE_STATE.json 通信。
# 写权限硬约束: 工具函数只能写 AGENT_FIELDS，不能写 DASHBOARD_FIELDS。


def make_report_progress():
    """创建 report_progress 工具（闭包捕获 state_path）。"""
    from claude_agent_sdk import tool

    @tool("report_progress", "汇报当前进度到Dashboard", {"step": str, "result": str})
    async def report_progress(args):
        global _current_step
        _current_step = args["step"]
        try:
            agent_write_report(_state_path, args["step"], args["result"])
            return {"content": [{"type": "text", "text": f"进度已汇报: {args['step']} — {args['result']}"}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"汇报失败: {e}"}]}
    return report_progress


def make_request_approval():
    """创建 request_approval 工具（闭包捕获 state_path）。"""
    from claude_agent_sdk import tool

    @tool("request_approval", "请求Dashboard审批当前阶段结果",
          {"phase": str, "summary": str, "files": list})
    async def request_approval(args):
        global _current_step
        _current_step = f"awaiting_approval:{args['phase']}"
        try:
            apr_id = agent_write_approval_request(
                _state_path,
                args["phase"],
                args["summary"],
                args.get("files", []),
            )
            # 阻塞等待 Dashboard 批复
            response = agent_wait_approval(_state_path, apr_id, timeout=1800)
            _current_step = f"approved:{args['phase']}"
            return {"content": [{"type": "text", "text": json.dumps(response, ensure_ascii=False)}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"审批请求失败: {e}"}]}
    return request_approval


# ── Main ──

def main():
    global _state_path, _done, _current_step

    parser = argparse.ArgumentParser(description="Agent SDK Task Runner")
    parser.add_argument("--task", required=True, choices=["code", "write", "review"])
    parser.add_argument("--workspace", required=True, help="工作空间目录")
    parser.add_argument("--session-id", default="", help="Session ID")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    _state_path = workspace / "PIPELINE_STATE.json"

    if not _state_path.exists():
        print(f"ERROR: PIPELINE_STATE.json not found at {_state_path}", file=sys.stderr)
        sys.exit(1)

    config = TASK_CONFIGS[args.task]
    print(f"[Agent Task] {config['phase']}: {config['description']}")
    print(f"[Agent Task] Workspace: {workspace}")
    print(f"[Agent Task] PID: {os.getpid()}")

    # 启动心跳线程
    _current_step = "starting"
    hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb_thread.start()

    # 写初始心跳
    agent_write_heartbeat(_state_path, _current_step)
    agent_write_report(_state_path, "agent_started", f"task={args.task}")

    # 构建上下文
    context = _build_context(workspace, args.task)

    try:
        from claude_agent_sdk import (
            tool, create_sdk_mcp_server,
            ClaudeAgentOptions, ClaudeSDKClient, query,
        )

        # 创建 SDK 自定义工具 (in-process MCP server)
        tools = [make_report_progress(), make_request_approval()]
        sdk_mcp = create_sdk_mcp_server(
            name="pipeline-tools",
            version="1.0.0",
            tools=tools,
        )

        options = ClaudeAgentOptions(
            mcp_servers={"pipeline": sdk_mcp},
            allowed_tools=[
                "mcp__pipeline__report_progress",
                "mcp__pipeline__request_approval",
                "Bash", "Read", "Write", "Edit", "Grep", "Glob",
            ],
            system_prompt=config["system_prompt"],
            permission_mode="bypassPermissions",
            cwd=str(workspace),
        )

        # 运行 agent
        import asyncio
        async def _run():
            _current_step = "agent_running"
            agent_write_report(_state_path, "agent_running", f"开始执行 {config['phase']}")

            async with ClaudeSDKClient(options=options) as client:
                await client.query(f"请执行 {config['phase']} 任务:\n\n{context}")
                async for msg in client.receive_response():
                    # 流式输出，agent 在工作中
                    # 具体的进度汇报由 agent 主动调 report_progress 完成
                    pass

            _current_step = "completed"
            agent_write_report(_state_path, "agent_completed", f"{config['phase']} 完成")
            print(f"[Agent Task] {config['phase']} 完成。")

        asyncio.run(_run())

    except ImportError:
        print("[Agent Task] claude-agent-sdk 未安装。使用降级模式。", file=sys.stderr)
        print("[Agent Task] 在降级模式下，agent 无法实际执行 LLM 工作。", file=sys.stderr)
        print("[Agent Task] 安装: pip install claude-agent-sdk", file=sys.stderr)

        # 降级模式：模拟 agent 运行（用于测试架构）
        _current_step = "degraded_mode"
        agent_write_report(_state_path, "degraded_mode",
                           f"SDK未安装，降级模式。任务: {config['phase']}")

        # 模拟审批请求
        apr_id = agent_write_approval_request(
            _state_path, config['phase'],
            f"(降级模式) {config['description']}",
            [],
        )
        print(f"[Agent Task] 审批请求已写入: {apr_id}，等待 Dashboard 批复...")

        response = agent_wait_approval(_state_path, apr_id, timeout=300)
        print(f"[Agent Task] 收到批复: {response}")

    finally:
        _done = True
        hb_thread.join(timeout=5)
        print(f"[Agent Task] 子进程退出。")


if __name__ == "__main__":
    main()
