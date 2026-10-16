import asyncio
import uuid

from fastapi import APIRouter

from ..events import bus
from ..models import Event

router = APIRouter(prefix="/api/debug")

# Held so background tasks are not garbage collected mid-run.
_tasks: set[asyncio.Task] = set()


async def _fake_run(run_id: str) -> None:
    async def emit(type_, agent_id=None, parent_id=None, **payload):
        await bus.publish(
            Event(run_id=run_id, type=type_, agent_id=agent_id, parent_id=parent_id, payload=payload)
        )

    async def spawn(aid, parent, role, goal, depth):
        await emit("agent_spawned", aid, parent, role=role, goal=goal, depth=depth, status="queued")

    async def status(aid, st, **extra):
        await emit("agent_status", aid, status=st, **extra)

    async def finish(aid, result, confidence):
        await emit("agent_finished", aid, result=result, confidence=confidence)

    await emit("run_started", goal="Compare the price of a MacBook Air at 3 Pakistani stores")
    await spawn("root", None, "planner", "Compare MacBook Air prices at 3 stores", 0)
    await status("root", "thinking")
    await asyncio.sleep(1.2)

    stores = [("a", "Daraz"), ("b", "PriceOye"), ("c", "Mega.pk")]
    for k, name in stores:
        await spawn(f"w{k}", "root", "worker", f"Find price on {name}", 1)
        await asyncio.sleep(0.3)
    await status("root", "running_tool")

    async def branch(k, name):
        aid = f"w{k}"
        await status(aid, "thinking")
        await asyncio.sleep(1.0)
        await status(aid, "running_tool", tool="web_search")
        await asyncio.sleep(1.5)
        if k == "a":  # this branch decomposes further and then waits for a human
            await spawn("wa1", aid, "worker", "Check Daraz seller ratings", 2)
            await status("wa1", "thinking")
            await asyncio.sleep(1.0)
            await status("wa1", "waiting_human")
            await asyncio.sleep(2.0)
            await finish("wa1", "Top sellers rated 4.5+", 0.8)
        if k == "c":
            await emit("agent_failed", aid, error="Site timed out")
            return
        await finish(aid, f"{name}: PKR 3xx,xxx", 0.85)

    await asyncio.gather(*(branch(k, n) for k, n in stores))
    await finish("root", "Cheapest: PriceOye", 0.8)
    await emit("run_finished")


@router.post("/fake_run")
async def fake_run() -> dict:
    run_id = uuid.uuid4().hex[:12]
    t = asyncio.create_task(_fake_run(run_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return {"run_id": run_id}
