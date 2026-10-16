from fastapi import APIRouter, HTTPException

from .. import store

router = APIRouter(prefix="/api/tools")

BUILTIN = [
    {"name": "web_search", "description": "Search the web via SerpAPI", "risk_level": "low"},
    {"name": "fetch_url", "description": "Fetch and clean a web page", "risk_level": "low"},
    {"name": "calculate", "description": "Safe arithmetic (min/max/sum/round)", "risk_level": "low"},
    {"name": "current_time", "description": "Current UTC date and time", "risk_level": "low"},
    {"name": "send_email", "description": "Send an email (always needs human approval)", "risk_level": "high"},
]


@router.get("")
async def list_tools() -> dict:
    grown = [
        {"name": t.name, "description": t.description, "risk_level": t.risk_level, "status": t.status,
         "version": t.version, "approved_by": t.approved_by,
         "approved_at": t.approved_at.isoformat() if t.approved_at else None,
         "usage_count": t.usage_count, "allowed_domains": t.allowed_domains,
         "composed_from": t.composed_from, "code": t.code}
        for t in await store.list_tools(False) if t.status in ("active", "disabled")
    ]
    return {"builtin": [{**b, "status": "active"} for b in BUILTIN], "grown": grown,
            "started_with": len(BUILTIN), "human_approved": len(grown)}


@router.post("/{name}/disable")
async def disable(name: str) -> dict:
    if not await store.set_tool_status(name, "disabled"):
        raise HTTPException(404, "unknown tool")
    return {"ok": True}
