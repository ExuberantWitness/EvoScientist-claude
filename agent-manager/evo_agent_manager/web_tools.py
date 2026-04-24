"""Web search tool for agents without Tavily API dependency.

Uses httpx + a search engine API (DuckDuckGo) for zero-config web search.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# We use langchain's tool decorator for compatibility
try:
    from langchain_core.tools import tool
except ImportError:
    # Fallback: create a simple callable
    def tool(name=None, description=""):
        def decorator(func):
            func.name = name or func.__name__
            func.description = description
            return func
        return decorator


@tool
def web_search(query: str) -> str:
    """Search the web for information. Returns top results with titles, URLs, and snippets. Use for finding papers, legal cases, news, and factual information. No API key needed — uses DuckDuckGo HTML API."""
    import httpx

    results = []
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            # DuckDuckGo HTML API
            resp = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "us-en"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; EvoScientist/1.0)"},
            )
            html = resp.text

            # Parse results from HTML (simple regex-based)
            import re
            titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</[at]', html, re.DOTALL)
            urls = re.findall(r'uddg=([^&"]+)', html)

            for i in range(min(len(titles), 8)):
                title = re.sub(r'<[^>]+>', '', titles[i]).strip()
                snippet = re.sub(r'<[^>]+>', '', snippets[i].strip()) if i < len(snippets) else ""
                url = urls[i] if i < len(urls) else ""
                if title:
                    results.append({"title": title, "url": url, "snippet": snippet[:200]})

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return json.dumps({"error": str(e), "results": []})

    if not results:
        return json.dumps({"query": query, "results": [], "note": "No results found. Try a different query."})

    return json.dumps({"query": query, "count": len(results), "results": results}, ensure_ascii=False)


@tool
def web_fetch(url: str) -> str:
    """Fetch and extract text content from a URL. Returns the page content as text (max 5000 chars). Use for reading articles, papers, or legal documents."""
    import httpx

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EvoScientist/1.0)"})
            resp.raise_for_status()
            text = resp.text

            # Simple HTML to text
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            if len(text) > 5000:
                text = text[:5000] + "... [truncated]"

            return text
    except Exception as e:
        return f"Error fetching {url}: {e}"
