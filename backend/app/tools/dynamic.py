"""Run approved generated tools. The DB is the registry: whatever is `active` there is what
exists, on every serverless instance, with no restart (this is the hot-load)."""
import tempfile
from pathlib import Path

from .. import store
from ..config import settings
from ..events import bus
from ..models import Event
from ..toolsmith.sandbox import run_tool

# Offline mock mode never touches the real internet: any URL returns this canned page.
MOCK_WORLD = {"": {"status": 200, "text": "<b>PKR 245,000</b> per tola (mock data)"}}


async def run_generated(name: str, args: dict, run_id: str, agent_id: str, secrets: dict | None = None) -> dict:
    row = await store.get_tool(name)
    if not row or row.status != "active":
        return {"ok": False, "error": f"tool '{name}' is not active"}

    async def ev(type_, **payload):
        await bus.publish(Event(run_id=run_id, type=type_, agent_id=agent_id, payload=payload))

    await ev("tool_call", tool=name, args=args, generated=True)
    await ev("system_flow", **{"from": "agents", "to": "sandbox"})
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "tool.py"
        f.write_text(row.code, encoding="utf-8")
        res = await run_tool(f, args, secrets or {}, row.allowed_domains,
                             mock_http=MOCK_WORLD if settings.use_mock else None)
    await store.bump_usage(name)
    await ev("tool_result", tool=name, ok=res.get("ok", False), generated=True)
    return res
