import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from ..events import bus
from ..models import Event

router = APIRouter(prefix="/api/debug")

async def _fake_run(run_id: str) -> None:
    async def emit(type_, agent_id=None, parent_id=None, **payload):
        # Prefix ids with the run so several fake runs can share one session's screen.
        pre = lambda i: f"{run_id}-{i}" if i else None  # noqa: E731
        await bus.publish(
            Event(run_id=run_id, type=type_, agent_id=pre(agent_id), parent_id=pre(parent_id), payload=payload)
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


class ToolsmithDemoIn(BaseModel):
    run_id: str
    session_id: str | None = None
    sneaky: bool = False  # the Builder writes a tool that exfiltrates data: it must get blocked


@router.post("/toolsmith_demo")
async def toolsmith_demo(body: ToolsmithDemoIn) -> dict:
    """Stage-reliable Toolsmith demo: the scripted model asks for a gold-price tool, so the
    full Builder -> Tester -> Critic -> human -> hot-load loop runs every time (a real model
    is rightly reluctant to build tools it doesn't need). The tool targets the reserved
    goldprice.example.pk domain, so real agents never use it."""
    from .. import store
    from ..orchestrator.agents import MockLLM
    from ..orchestrator.runner import run_goal
    from .routes_sessions import link_run

    if (t := await store.get_tool("gold_price_pkr")) and t.status == "active":
        await store.set_tool_status("gold_price_pkr", "disabled")  # rebuild it live, as v+1
    goal = "What is the gold price per tola in PKR?" + (" (sneaky)" if body.sneaky else "")
    await link_run(body.session_id, body.run_id, goal)
    result = await run_goal(body.run_id, goal, body.session_id, llm=MockLLM())
    return {"run_id": body.run_id, "result": result}


@router.post("/fake_run/{run_id}")
async def fake_run(run_id: str, session_id: str | None = None) -> dict:
    """Plays the scripted run inside this request (~10s). The client picks the run_id and
    polls for events meanwhile; serverless has no background tasks."""
    from .routes_sessions import link_run

    await link_run(session_id, run_id, "Fake run")
    await _fake_run(run_id)
    return {"run_id": run_id}
