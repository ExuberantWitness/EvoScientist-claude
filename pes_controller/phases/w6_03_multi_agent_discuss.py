"""W6 结果分析 — 多 Agent 分析讨论"""
from pes_controller.base_phase import BasePhase

class W6MultiAgentDiscuss(BasePhase):
    def run(self):
        return {
            "action": "multi_agent_discuss",
            "step": "multi_agent_discuss",
            "agent_list": ["analyst", "planner", "researcher"],
            "instruction": "多Agent分析实验结果: analyst分析数据、planner评估进度、researcher对比文献。"
        }
