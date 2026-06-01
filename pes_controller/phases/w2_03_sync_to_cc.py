"""W2 问题分析 — 将文献搜索结果同步到CC (via CCGrounding gatekeeper)

This step runs AFTER invoke_four_personas and syncs:
  1. Persona search results → CC (via grounding pipeline)
  2. Persona proposals → CC method atoms (gatekeeper-validated)

Actual execution happens in sdk/dashboard/monitor.py:_do_sync_to_cc
which is dispatched by sub_loop with action="sync_to_cc".
"""
from pes_controller.base_phase import BasePhase

class W2SyncToCC(BasePhase):
    def run(self):
        """Sync search results + proposals to CC via grounding pipeline.

        For W2/W3: proposals contain search_results_summary → literature atoms
        For W4: codegraph structure → component atoms
        For W6: experiment results → verification atoms
        """
        # Actual sync happens via _do_sync_to_cc in monitor.py
        # This is the declarative interface for the phase step
        proposals = self.state.get("last_persona_proposals", [])
        return {
            "atoms_synced": len(proposals),
            "source": "persona_proposals",
            "via": "CCGrounding gatekeeper",
        }
