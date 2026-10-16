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


async def send_email(to: str, subject: str, body: str, *, run_id: str, agent_id: str) -> dict:
    """RISKY / irreversible: always pauses this branch for a human click first.
    Mock for now: logs instead of sending (real Gmail send comes with Phase 4)."""
    from .. import approvals, store
    from ..events import bus
    from ..models import Event

    await store.set_agent(agent_id, status="waiting_human")
    await bus.publish(Event(run_id=run_id, type="agent_status", agent_id=agent_id,
                            payload={"status": "waiting_human"}))
    row = await approvals.request(run_id, agent_id, "risky_action", f"Send email to {to}",
                                  {"to": to, "subject": subject, "body": body}, "high")
    await store.set_agent(agent_id, status="thinking")
    await bus.publish(Event(run_id=run_id, type="agent_status", agent_id=agent_id,
                            payload={"status": "thinking"}))
    if row.status == "rejected":
        return {"sent": False, "reason": row.note or "rejected by human"}
    await bus.publish(Event(run_id=run_id, type="log", agent_id=agent_id,
                            payload={"message": f"(mock) email sent to {to}: {subject}"}))
    return {"sent": True, "mock": True}


def calculate(expression: str) -> str:
    """Safely evaluate arithmetic: + - * / ** %, parentheses, and min/max/sum/round/abs."""
    import ast
    import operator as op

    ops = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
           ast.Pow: op.pow, ast.Mod: op.mod, ast.USub: op.neg, ast.UAdd: op.pos}
    funcs = {"min": min, "max": max, "sum": lambda *a: sum(a), "round": round, "abs": abs}

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs and not n.keywords:
            return funcs[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsupported expression")

    try:
        if len(expression) > 300:
            return "calculate failed: expression too long"
        return str(ev(ast.parse(expression, mode="eval").body))
    except Exception as e:
        return f"calculate failed: {type(e).__name__}"


def current_time() -> str:
    """Current UTC date and time (ISO 8601)."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TOOLS = {"web_search": web_search, "fetch_url": fetch_url}
