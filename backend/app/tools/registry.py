"""Built-in tools as plain async functions. (Phase 3 exposes the same registry via FastMCP
for hot-loading; Phase 1 workers call these directly to avoid a network hop per call.)"""
import json
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


async def image_search(query: str) -> list[dict]:
    """Google Images via SerpAPI: [{title, image, source}]. `image` is SerpAPI's hosted thumbnail,
    which (unlike many originals) can be shown on any page."""
    key = os.environ.get("SERPAPI_API_KEY")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(SERPAPI_URL, params={"engine": "google_images", "q": query, "api_key": key})
            r.raise_for_status()
        return [{"title": x.get("title", ""), "image": x.get("thumbnail", ""), "source": x.get("link", "")}
                for x in r.json().get("images_results", [])[:6] if x.get("thumbnail")]
    except Exception:
        return []


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
    Sends through the user's Gmail when they signed in with Google; otherwise it is a mock
    that only logs (the approval card says which)."""
    import asyncio

    from .. import approvals, store, vault
    from ..config import settings
    from ..connectors import google
    from ..events import bus
    from ..models import Event

    # Scripted/test runs never send real mail, even when a Google login is in the vault.
    g = None if settings.use_mock else await vault.info("google")
    await store.set_agent(agent_id, status="waiting_human")
    await bus.publish(Event(run_id=run_id, type="agent_status", agent_id=agent_id,
                            payload={"status": "waiting_human"}))
    if not g and google.enabled() and not settings.use_mock:
        # No mailbox yet: ask the human to sign in instead of pretending to send.
        await bus.publish(Event(run_id=run_id, type="secret_requested", agent_id=agent_id,
                                payload={"name": "google", "have": False}))
        ask = await approvals.request(run_id, agent_id, "connect_google", "Sign in with Google to send this email",
                                      {"purpose": f"Send an email to {to}", "subject": subject,
                                       "access": "Banyan will still ask before every email it sends."}, "medium")
        if ask.status == "rejected":
            return {"sent": False, "reason": "NOT SENT: the human did not connect Gmail"}
        g = await vault.info("google")
    via = f"Gmail ({g['label']})" if g and google.enabled() else "mock (nothing is sent)"
    row = await approvals.request(run_id, agent_id, "risky_action", f"Send email to {to}",
                                  {"to": to, "subject": subject, "body": body, "via": via}, "high")
    await store.set_agent(agent_id, status="thinking")
    await bus.publish(Event(run_id=run_id, type="agent_status", agent_id=agent_id,
                            payload={"status": "thinking"}))
    if row.status == "rejected":
        return {"sent": False, "reason": f"NOT SENT: rejected by the human ({row.note or 'no reason'})"}
    if row.status == "edited" and row.edited_payload:  # the human may fix the text before sending
        body = str(row.edited_payload.get("body", body))
    if g and google.enabled():
        secret = await vault.get("google")
        await bus.publish(Event(run_id=run_id, type="secret_used", agent_id=agent_id,
                                payload={"name": "google", "purpose": "send email"}))
        try:
            await asyncio.to_thread(google.send, secret, to, subject, body)
        except Exception as e:
            await bus.publish(Event(run_id=run_id, type="log", agent_id=agent_id,
                                    payload={"message": f"Gmail send failed: {e}"[:200]}))
            return {"sent": False, "reason": "Gmail send failed"}
        await bus.publish(Event(run_id=run_id, type="log", agent_id=agent_id,
                                payload={"message": f"Email sent via Gmail to {to}: {subject}"}))
        return {"sent": True}
    await bus.publish(Event(run_id=run_id, type="log", agent_id=agent_id,
                            payload={"message": f"(mock) email NOT really sent to {to}: {subject}"}))
    # Worded so the agent can't report it as delivered.
    return {"sent": False, "mock": True,
            "reason": "NOT SENT: demo mode, no Gmail connected. Tell the user it was approved but not delivered."}


async def call_service(service: str, path: str, method: str = "GET", params: dict | None = None,
                       body: dict | None = None, *, run_id: str, agent_id: str) -> str:
    """Call a connected service (Classroom, GitHub, a custom API) with the user's credential.
    Reads run freely; a write waits for a human click. The credential stays on the server."""
    from .. import approvals
    from ..connectors import services
    from ..events import bus
    from ..models import Event

    async def ev(type_: str, **payload):
        await bus.publish(Event(run_id=run_id, type=type_, agent_id=agent_id, payload=payload))

    method = (method or "GET").upper()
    await ev("tool_call", tool="call_service", args={"service": service, "method": method, "path": path})
    if method != "GET":
        s = await services.config(service) or {"label": service}
        row = await approvals.request(run_id, agent_id, "risky_action", f"{method} on {s['label']}: {path}",
                                      {"service": s["label"], "method": method, "path": path,
                                       "result": f"```json\n{json.dumps(body or {}, indent=1)[:1500]}\n```"}, "high")
        if row.status == "rejected":
            return f"NOT DONE: the human rejected this change ({row.note or 'no reason'})"
    try:
        await ev("secret_used", name=f"svc:{service}", purpose=f"{method} {path}"[:80])
        out = await services.call_text(service, method, path, params, body)
    except Exception as e:
        await ev("tool_result", tool="call_service", summary=f"error: {e}"[:200])
        return f"ERROR: {e}"
    await ev("tool_result", tool="call_service", summary=f"{len(out)} chars from {service}")
    return out


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
