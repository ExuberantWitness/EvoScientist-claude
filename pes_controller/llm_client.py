"""LLM Client — 基于 openai SDK 的 LLM 调用封装。

支持任何 OpenAI 兼容 API（DeepSeek, MiMo, clawhub.ai 等）。
通过改 base_url 即可切换 provider。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI SDK 封装。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        import os
        from openai import OpenAI
        os.environ.setdefault("NO_PROXY", "*")
        os.environ.setdefault("no_proxy", "*")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.base_url = base_url

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> tuple[str, dict[str, int]]:
        """调用 LLM，返回 (content, usage)。

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": str}]
            max_tokens: 最大生成 token 数
            temperature: 采样温度

        Returns:
            (content_text, {"prompt_tokens": int, "completion_tokens": int})
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        }
        logger.debug(
            "LLMClient.chat model=%s tokens=%s", self.model, usage
        )
        return content, usage

    def chat_with_retry(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_retries: int = 2,
    ) -> tuple[str, dict[str, int]]:
        """带重试的 LLM 调用。网络/超时错误最多重试 max_retries 次。"""
        import time

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                return self.chat(messages, max_tokens, temperature)
            except Exception as e:
                last_error = e
                logger.warning(
                    "LLMClient.chat failed (attempt %d/%d): %s",
                    attempt, max_retries, e,
                )
                if attempt < max_retries:
                    time.sleep(attempt * 3)

        raise RuntimeError(
            f"LLM 调用连续失败 {max_retries} 次: {last_error}"
        ) from last_error
