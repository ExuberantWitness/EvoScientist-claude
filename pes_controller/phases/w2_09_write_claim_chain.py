"""W2 问题分析 — 写入 CC atoms (via CCGrounding gatekeeper)

This step runs AFTER elo_tournament + write_sme and writes:
  - Winning proposals → CC method atoms (gatekeeper-validated)
  - Tournament results → validates/contradicts relations
  - Experiment results → verification atoms (W5 Analyze)

Actual execution happens in sdk/dashboard/monitor.py:_do_write_claim_chain
which dispatches through CCGrounding.enrich_from_proposals() or
CCGrounding.enrich_from_experiments().
"""
from pes_controller.base_phase import BasePhase

class W2WriteClaimChain(BasePhase):
    def run(self):
        """Write ranked proposals to CC via grounding pipeline.

        Reads last_persona_proposals + last_tournament_result from state.
        Each proposal goes through OntologyGatekeeper before CC write.
        """
        proposals = self.state.get("last_persona_proposals", [])
        tournament = self.state.get("last_tournament_result", {})
        ranked = tournament.get("ranked", [])

        return {
            "proposals_pending": len(proposals),
            "ranked_count": len(ranked),
            "via": "CCGrounding gatekeeper (OntologyGatekeeper + BGE-M3 dedup)",
        }
