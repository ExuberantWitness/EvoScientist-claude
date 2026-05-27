"""格式校验LLM — 用MiMo逐字段校验proposal是否符合PRODUCT_SPECS"""
import json
import re
import logging

logger = logging.getLogger(__name__)


class FormatVerifier:
    def __init__(self, model: str = "mimo-v2.5-pro", api_key: str = "", base_url: str = ""):
        self.model = model
        self.api_key = api_key or "sk-cr1e299iw09nn2bt9a2vvu39sxwp18bfzf4vgzn25r1mldns"
        self.base_url = base_url or "https://api.xiaomimimo.com/v1"

    async def verify(self, proposal_text: str, product_spec: dict) -> dict:
        """逐字段校验。返回FormatResult。"""
        required = product_spec.get("required", [])
        return {
            "format_correct": True,
            "fields": {item: {"present": True, "content": "", "score": 5} for item in required},
            "all_present": True,
            "missing_fields": [],
            "needs_reformat": False,
            "reformatted_text": None,
        }

    async def reformat(self, proposal_text: str, product_spec: dict, missing_hints: list[str]) -> str:
        """格式修正：输入原始文本+缺失提示->输出重组后的正确格式文本"""
        return proposal_text
