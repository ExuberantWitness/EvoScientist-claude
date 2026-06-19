"""Tavily Search Client — 基于 tavily-python SDK。

用于 web 搜索，替代 langchain TavilySearchResults 工具。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TavilyClient:
    """Tavily 搜索 API 封装。"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from tavily import TavilyClient as _TavilyClient
            self._client = _TavilyClient(api_key=self.api_key)
        return self._client

    def search(
        self, query: str, max_results: int = 5, search_depth: str = "advanced"
    ) -> list[dict[str, str]]:
        """执行搜索，返回结果列表。

        Args:
            query: 搜索查询
            max_results: 最大结果数
            search_depth: "basic" 或 "advanced"

        Returns:
            [{"title": str, "url": str, "content": str}]
        """
        if not self.api_key:
            logger.warning("TavilyClient: API key not set, skipping search")
            return []

        try:
            client = self._get_client()
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
            )
            results = []
            for r in response.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                })
            logger.debug(
                "TavilyClient.search query='%s' results=%d",
                query[:50], len(results),
            )
            return results
        except Exception as e:
            logger.error("TavilyClient.search failed: %s", e)
            return []
