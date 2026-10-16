"""Built-in tools as plain async functions. (Phase 3 exposes the same registry via FastMCP
for hot-loading; Phase 1 workers call these directly to avoid a network hop per call.)"""
import os
import re

import httpx

SERPAPI_URL = "https://serpapi.com/search.json"
MAX_FETCH_CHARS = 6000


async def web_search(query: str) -> list[dict]:
    """Top Google results via SerpAPI: [{title, link, snippet}]."""
    key = os.environ.get("SERPAPI_API_KEY")
    if not key:
        return [{"title": "web_search unavailable", "link": "", "snippet": "SERPAPI_API_KEY not set"}]
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(SERPAPI_URL, params={"q": query, "api_key": key, "num": 5})
            r.raise_for_status()
        return [
            {"title": x.get("title", ""), "link": x.get("link", ""), "snippet": x.get("snippet", "")}
            for x in r.json().get("organic_results", [])[:5]
        ]
    except Exception as e:  # never crash a branch on an external failure
        return [{"title": "web_search failed", "link": "", "snippet": f"{type(e).__name__}"}]


async def fetch_url(url: str) -> str:
    """GET a page and return cleaned, truncated text."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "BanyanBot/0.1"})
            r.raise_for_status()
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:MAX_FETCH_CHARS]
    except Exception as e:
        return f"fetch_url failed: {type(e).__name__}"


TOOLS = {"web_search": web_search, "fetch_url": fetch_url}
