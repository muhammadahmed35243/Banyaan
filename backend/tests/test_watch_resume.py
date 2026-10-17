"""A watcher whose goal request timed out before the human answered must still start
when the human approves (the decision request finishes the setup), exactly once."""
import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["MOCK_LLM"] = "true"  # mock mode: never sends mail

import pytest  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import store, vault, watchers  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import AgentRow, EventRow, WatchRow  # noqa: E402

# Never touch a real database: if config was loaded earlier (other tests), skip.
pytestmark = pytest.mark.skipif(not settings.database_url.startswith("sqlite:///") or "t.db" not in settings.database_url,
                                reason="needs the throwaway sqlite DB; run this file on its own")


def test_late_approval_starts_watcher_once():
    async def go():
        init_db()
        await vault.put("gmail", {"mode": "demo"}, "Demo inbox")
        await store.upsert_agent(AgentRow(id="r-root", run_id="r", depth=0, role="planner", goal="g"))
        await store.upsert_agent(AgentRow(id="r-root.watch", run_id="r", parent_id="r-root", depth=1,
                                          role="watcher", goal="watch"))
        # The goal's request created this card, then died (nobody is polling it any more).
        aid = await store.create_approval(
            run_id="r", agent_id="r-root.watch", kind="watch_setup", title="t", risk="medium",
            details={"credential": "gmail", "condition": "about a payment", "forward_to": "me@x.com",
                     "session_id": "s1", "parent_id": "r-root"})
        row = await store.decide(aid, "approved", "late", None)
        await watchers.resume_setup(row)
        await watchers.resume_setup(row)  # a second request (or the revived goal) must not duplicate
        assert "emailed to me@x.com" in await watchers.finish_setup(row)

        with Session(engine) as s:
            watches = s.exec(select(WatchRow)).all()
            types = [e.type for e in s.exec(select(EventRow).where(EventRow.run_id == "r")).all()]
        assert len(watches) == 1 and watches[0].forward_to == "me@x.com" and watches[0].session_id == "s1"
        assert types.count("watch_started") == 1
        assert "human_decision" in types and "run_finished" in types
        assert (await store.get_agent("r-root.watch")).status == "watching"

    asyncio.run(go())
