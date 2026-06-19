"""W7.1 论文计划 Handler — 4-Persona 生成 + Elo 评分 + 产物验证 + 多方案展示。

Steps:
  1. invoke_four_personas_paper  — 4 Persona 并行生成论文计划
  2. elo_tournament_paper        — Elo 锦标赛评分排名
  3. verify_paper_plan_products  — 结构检查 + LLM 审稿维度初评
  4. present_paper_plan_options  — SSE 推送多方案 + 等待人工选择
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W7.1 论文计划"

PERSONA_SKILLS = [
    ("novel-academic", "persona-novel-academic"),
    ("conservative-academic", "persona-conservative-academic"),
    ("novel-engineering", "persona-novel-engineering"),
    ("conservative-engineering", "persona-conservative-engineering"),
]


@register_handler(PHASE)
class W7_1Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = [
        "invoke_four_personas_paper",
        "elo_tournament_paper",
        "verify_paper_plan_products",
        "present_paper_plan_options",
    ]

    def build_step(self, step_name: str) -> StepResult:
        dispatch = {
            "invoke_four_personas_paper": self._step_invoke_personas,
            "elo_tournament_paper": self._step_elo_tournament,
            "verify_paper_plan_products": self._step_verify,
            "present_paper_plan_options": self._step_present,
        }
        handler = dispatch.get(step_name)
        if handler is None:
            return StepResult(done=True, phase=PHASE, step=step_name,
                              step_index=self._step_index(), action="error",
                              data={"message": f"Unknown step: {step_name}"})
        return handler()

    # ── Step 1: 4-Persona 并行生成 ──

    def _step_invoke_personas(self) -> StepResult:
        ws = self._ws()
        plans_dir = ws / "paper_plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        regen_context = ""
        if self.state.get("needs_regeneration"):
            regen_context = (
                f"\n\n**人工审稿意见（首要修改指导）**：\n"
                f"{self.state.get('iteration_feedback', '')}"
            )

        variables_template = {
            "research_topic": self._research_topic(),
            "workspace_dir": str(ws),
            "venue": self._venue(),
            "regen_context": regen_context,
            "phase": PHASE,
            "w6_discussion": self.state.get("analysis_discussion", ""),
            "cc_atoms": self.state.get("claim_chain_atoms", ""),
        }

        def _call_persona(persona_name: str, skill_name: str):
            variables = {**variables_template, "persona_name": persona_name}
            return persona_name, self.executor.execute(
                skill_name, variables, pre_search=self._research_topic(),
            )

        results: dict[str, dict] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_call_persona, pn, sn): pn
                for pn, sn in PERSONA_SKILLS
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    persona_name, result = future.result()
                    results[persona_name] = {
                        "llm_response": result.llm_response,
                        "files_written": result.files_written,
                        "actions_executed": result.actions_executed,
                    }
                    plan_file = plans_dir / f"plan_{persona_name}.json"
                    plan_file.write_text(
                        json.dumps(results[persona_name], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.error("Persona call failed: %s", e)

        return StepResult(
            done=False, phase=PHASE, step="invoke_four_personas_paper",
            step_index=self._step_index(), action="personas_completed",
            data={"persona_count": len(results), "plans_dir": str(plans_dir)},
        )

    # ── Step 2: Elo 锦标赛 ──

    def _step_elo_tournament(self) -> StepResult:
        from pes_controller.elo.tournament import EloTournament

        ws = self._ws()
        plans_dir = ws / "paper_plans"

        proposals = []
        for pf in sorted(plans_dir.glob("plan_*.json")):
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                proposals.append({
                    "id": pf.stem.replace("plan_", ""),
                    "title": data.get("llm_response", "")[:200],
                    "content": data.get("llm_response", ""),
                })
            except Exception as e:
                logger.warning("Failed to load plan %s: %s", pf, e)

        if len(proposals) < 2:
            logger.warning("Not enough proposals for Elo (%d), skipping", len(proposals))
            return StepResult(
                done=False, phase=PHASE, step="elo_tournament_paper",
                step_index=self._step_index(), action="elo_skipped",
                data={"reason": "less_than_2_proposals"},
            )

        tournament = EloTournament(
            llm_client=self.llm_client,
            phase=PHASE,
        )
        # EloTournament.rank() is async; handler runs in sync context.
        # Use asyncio.run() if no loop, or asyncio.get_event_loop().run_until_complete()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import threading
            rankings = None
            exc = None

            def _run():
                nonlocal rankings, exc
                try:
                    rankings = asyncio.run(tournament.rank(proposals))
                except Exception as e:
                    exc = e

            t = threading.Thread(target=_run)
            t.start()
            t.join(timeout=300)
            if exc:
                raise exc
        else:
            rankings = asyncio.run(tournament.rank(proposals))

        elo_file = plans_dir / "elo_results.json"
        elo_file.write_text(
            json.dumps({"rankings": rankings}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return StepResult(
            done=False, phase=PHASE, step="elo_tournament_paper",
            step_index=self._step_index(), action="elo_completed",
            data={"rankings": rankings},
        )

    # ── Step 3: 产物验证 ──

    def _step_verify(self) -> StepResult:
        result = self.executor.execute("flux-verify-paper-plan", {
            "workspace_dir": str(self._ws()),
            "product_spec": json.dumps(
                {"required": ["NARRATIVE_REPORT.md", "PAPER_PLAN.md"],
                 "deliverables": ["NARRATIVE_REPORT.md", "PAPER_PLAN.md"]},
                ensure_ascii=False,
            ),
        })

        return StepResult(
            done=False, phase=PHASE, step="verify_paper_plan_products",
            step_index=self._step_index(), action="verify_completed",
            data={"success": result.success, "llm_response": result.llm_response},
        )

    # ── Step 4: 多方案展示 + 等待人工选择 ──

    def _step_present(self) -> StepResult:
        ws = self._ws()
        plans_dir = ws / "paper_plans"

        # Read Elo results
        elo_path = plans_dir / "elo_results.json"
        if not elo_path.exists():
            return StepResult(
                done=True, phase=PHASE, step="present_paper_plan_options",
                step_index=self._step_index(), action="error",
                data={"message": "elo_results.json not found"},
            )

        elo_data = json.loads(elo_path.read_text(encoding="utf-8"))
        rankings = elo_data.get("rankings", [])

        options = []
        for r in rankings:
            plan_id = r.get("id", "")
            plan_file = plans_dir / f"plan_{plan_id}.json"
            plan_data = {}
            if plan_file.exists():
                try:
                    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass

            llm_raw = plan_data.get("llm_response", "")
            title = self._extract_title(llm_raw)

            options.append({
                "id": plan_id,
                "display": self._plan_display_id(plan_id),
                "elo_rating": r.get("elo_rating", 1500),
                "scores": r.get("scores", {}),
                "title": title,
                "summary": llm_raw[:500],
            })

        # SSE event to Dashboard
        self._post_to_dashboard(
            self._session_id(), "paper_plan_options_ready",
            {"phase": PHASE, "options": options},
        )

        # Set awaiting_decision → sub_loop will stop advancing
        self.state["status"] = "awaiting_decision"
        self._write_state(self.state)

        return StepResult(
            done=True, phase=PHASE, step="present_paper_plan_options",
            step_index=self._step_index(), action="present_options",
            data={"options_type": "paper_plan", "options": options},
        )

    # ── Helpers ──

    @staticmethod
    def _plan_display_id(plan_id: str) -> str:
        DISPLAY_MAP = {
            "novel-academic": "A",
            "conservative-academic": "B",
            "novel-engineering": "C",
            "conservative-engineering": "D",
        }
        return DISPLAY_MAP.get(plan_id, plan_id)

    @staticmethod
    def _extract_title(llm_response: str) -> str:
        try:
            parsed = json.loads(llm_response)
            return parsed.get("title", "")[:100]
        except (json.JSONDecodeError, TypeError):
            for line in llm_response.split("\n"):
                line = line.strip()
                if line.startswith("#"):
                    return line.lstrip("#").strip()[:100]
            return llm_response[:80]

    def _post_to_dashboard(self, session_id: str, event_type: str, data: dict):
        import urllib.request
        try:
            payload = json.dumps({
                "session_id": session_id,
                "type": event_type,
                "data": data,
            }).encode()
            req = urllib.request.Request(
                "http://localhost:8420/api/internal/events",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.debug("Dashboard SSE post failed: %s", e)

    def _write_state(self, state: dict):
        from pes_controller.protocol import atomic_write
        ws = self._ws()
        state_path = ws / "PIPELINE_STATE.json"
        import time
        state["timestamp"] = time.time()
        atomic_write(state_path, state)
