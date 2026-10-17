"""Connected services: the call_service gateway, the connect card, and a watcher that polls
a service (demo Classroom) and alerts on new items. Scripted Planner, throwaway SQLite."""
import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "s.db")
os.environ["MOCK_LLM"] = "true"
os.environ["BACKEND_URL"] = "http://testserver"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import store, vault, watchers  # noqa: E402
from app.config import settings  # noqa: E402
from app.connectors import services  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import EventRow, WatchRow  # noqa: E402
from app.orchestrator.runner import run_goal  # noqa: E402

pytestmark = pytest.mark.skipif("s.db" not in settings.database_url,
                                reason="needs the throwaway sqlite DB; run this file on its own")


def _types(run_id: str) -> list[str]:
    with Session(engine) as s:
        return [e.type for e in s.exec(select(EventRow).where(EventRow.run_id == run_id)).all()]


def test_connect_call_and_watch_a_service():
    async def go():
        init_db()
        services._transport = httpx.ASGITransport(app=app)  # the demo Classroom is served by this app
        api = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")

        # 1) Not connected: a goal that needs Classroom asks with a connect card; the human picks demo.
        task = asyncio.create_task(run_goal("r1", "what assignments are due in my classroom?", "s1"))
        card = None
        for _ in range(50):
            await asyncio.sleep(0.2)
            pend = [a for a in await store.list_approvals("pending") if a.kind == "connect_service"]
            if pend:
                card = pend[0]
                break
        assert card and card.details["service"] == "google_classroom" and card.details["demo"]
        # Approving without connecting anything is refused.
        r = await api.post(f"/api/approvals/{card.id}/decide", json={"decision": "approved"})
        assert r.status_code == 400
        r = await api.post(f"/api/approvals/{card.id}/service_credential", json={"use_demo": True})
        assert r.json() == {"ok": True, "service": "demo_classroom"}
        assert await asyncio.wait_for(task, 30)
        assert await services.connected("demo_classroom")

        # 2) The gateway: reads work, other hosts are refused, the token never shows in output.
        out = await services.call_text("demo_classroom", "GET", "/v1/courses")
        assert "Data Structures" in out and "demo" not in out.lower().replace("demo_", "")
        for bad in ("https://evil.example/x", "/../../secrets"):
            with pytest.raises(ValueError):
                await services.call("demo_classroom", "GET", bad)
        with pytest.raises(ValueError):
            await services.connect("myapi", "tok", base_url="http://insecure.example")

        # 3) A watcher on the service: first snapshot raises nothing; a new assignment alerts.
        msg = await run_goal("r2", "any time a new assignment is posted in my classroom, tell me", "s1")
        assert "Right now there are" in msg
        with Session(engine) as s:
            w = s.exec(select(WatchRow).where(WatchRow.source == "service")).one()
        assert w.service == "demo_classroom" and len(w.seen) >= 6
        await api.post("/api/demo/classroom/simulate", json={"preset": "assignment"})
        with Session(engine) as s:  # pretend the 5-minute interval has passed
            row = s.get(WatchRow, w.id)
            row.last_tick_at = None
            s.add(row)
            s.commit()
        assert (await watchers.tick("s1"))["checked"] == 1
        assert "alert" in _types("r2")
        # Nothing new on the next check.
        with Session(engine) as s:
            row = s.get(WatchRow, w.id)
            row.last_tick_at = None
            s.add(row)
            s.commit()
        before = _types("r2").count("alert")
        await watchers.tick("s1")
        assert _types("r2").count("alert") == before

        # 4) A write would need a human: the registry asks before any non-GET call.
        assert await vault.info("svc:demo_classroom")
        await api.aclose()

    asyncio.run(go())
