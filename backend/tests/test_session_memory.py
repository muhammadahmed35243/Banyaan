"""Session memory and editing running flows by asking (scripted Planner, throwaway SQLite)."""
import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "m.db")
os.environ["MOCK_LLM"] = "true"

import pytest  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app import memory, store, vault, watchers  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import AgentRow, WatchRow  # noqa: E402
from app.orchestrator.runner import run_goal  # noqa: E402

pytestmark = pytest.mark.skipif("m.db" not in settings.database_url,
                                reason="needs the throwaway sqlite DB; run this file on its own")


def _watch(wid: str) -> WatchRow:
    with Session(engine) as s:
        return s.get(WatchRow, wid)


def test_memory_and_flow_edits():
    async def go():
        init_db()
        sid = "sess1"
        await vault.put("gmail", {"mode": "demo"}, "Demo inbox")
        # A running watcher in this session (as if set up earlier).
        await store.upsert_agent(AgentRow(id="w-root", run_id="w", depth=0, role="planner", goal="g"))
        await store.upsert_agent(AgentRow(id="w-root.watch", run_id="w", parent_id="w-root", depth=1,
                                          role="watcher", goal="watch"))
        aid = await store.create_approval(run_id="w", agent_id="w-root.watch", kind="watch_setup", title="t",
                                          details={"credential": "gmail", "condition": "about a payment",
                                                   "session_id": sid, "parent_id": "w-root"})
        await watchers.finish_setup(await store.decide(aid, "approved", None, None))

        # 1) A fact is remembered and shows up in the next goal's context.
        await run_goal("r1", "my budget is 15k PKR", sid)
        assert await memory.facts(sid) == ["Budget: 15k pkr"]
        ctx = await memory.context(sid, "next")
        assert "Budget: 15k pkr" in ctx and f"id={aid} watcher [active]" in ctx

        # 2) "pause it" / "resume it" edit the running flow.
        assert "Paused" in await run_goal("r2", "pause the payment watcher", sid)
        assert _watch(aid).status == "paused"
        assert "Resumed" in await run_goal("r3", "resume it", sid)
        assert _watch(aid).status == "active"

        # 3) Changing the rule applies at once.
        out = await run_goal("r4", "also include salary emails", sid)
        assert "salary emails" in _watch(aid).condition and "now looks for" in out

        # 4) Adding email forwarding gives the flow a new power: it waits for a human.
        out = await run_goal("r5", "forward these alerts to me@x.com", sid)
        assert "needs your OK" in out and _watch(aid).forward_to is None
        card = [a for a in await store.list_approvals("pending") if a.kind == "flow_edit"][0]
        await watchers.apply_flow_edit(await store.decide(card.id, "approved", None, None))
        assert _watch(aid).forward_to == "me@x.com"

        # 5) Stop, and the human can delete a remembered fact.
        assert "Stopped" in await run_goal("r6", "stop the watcher", sid)
        assert _watch(aid).status == "stopped"
        assert await memory.forget(sid, 0) == []

    asyncio.run(go())
