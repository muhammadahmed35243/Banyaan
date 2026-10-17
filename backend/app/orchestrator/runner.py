"""Recursive, parallel orchestrator (plain asyncio).

All coordination with humans (pause / prune / redirect / approvals) goes through the DB
(see store.py), because on serverless the control API and the running orchestrator are
different processes. Branches check their control flag between steps (`checkpoint`) and
while waiting on the LLM (`guarded`, which cancels the call on prune)."""
import asyncio
from dataclasses import dataclass, field

from .. import approvals, store
from ..approvals import Pruned
from ..config import settings
from ..events import bus
from ..models import AgentRow, Event
from ..toolsmith import pipeline as toolsmith
from .agents import CURRENT, LLM, WorkerOutput, get_llm


BUILTIN_TOOL_NAMES = ["web_search", "fetch_url", "image_search", "calculate", "current_time", "send_email"]


class HumanRejected(Exception):
    pass


@dataclass
class Ctx:
    run_id: str
    llm: LLM
    sem: asyncio.Semaphore
    session_id: str | None = None
    history: str = ""  # earlier goals + answers in this session (the session's memory)


@dataclass
class Node:
    id: str
    parent_id: str | None
    depth: int
    goal: str
    notes: list[str] = field(default_factory=list)
    tokens: int = 0
    budget_ok: bool = False
    role: str = "researcher"


async def emit(ctx: Ctx, type_: str, node: Node | None = None, **payload) -> None:
    await bus.publish(Event(run_id=ctx.run_id, type=type_, agent_id=node.id if node else None,
                            parent_id=node.parent_id if node else None, payload=payload))


async def set_status(ctx: Ctx, node: Node, status: str, **extra) -> None:
    await store.set_agent(node.id, status=status)
    await emit(ctx, "agent_status", node, status=status, **extra)


# ---------- human controls ----------


async def checkpoint(ctx: Ctx, node: Node) -> None:
    """Called between steps: honour prune / pause / redirect / inject set by a human."""
    row = await store.get_agent(node.id)
    if not row:
        return
    if row.control == "prune":
        raise Pruned()
    if row.control == "pause":
        await set_status(ctx, node, "paused")
        while True:
            await asyncio.sleep(1.0)
            row = await store.get_agent(node.id)
            if row.control == "prune":
                raise Pruned()
            if row.control != "pause":
                await set_status(ctx, node, "thinking")
                break
    if row and row.control == "redirect" and row.control_text:
        node.goal = row.control_text
        await store.set_agent(node.id, control="none", goal=node.goal)
        await emit(ctx, "agent_status", node, status="thinking", goal=node.goal, redirected=True)
    elif row and row.control == "inject" and row.control_text:
        node.notes.append(row.control_text)
        await store.set_agent(node.id, control="none")
        await emit(ctx, "log", node, message=f"Human note added: {row.control_text}")


async def guarded(node: Node, coro):
    """Await `coro` but cancel it promptly if the node gets pruned meanwhile."""
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=1.0)
            if done:
                return task.result()
            row = await store.get_agent(node.id)
            if row and row.control == "prune":
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise Pruned()
    except asyncio.CancelledError:
        task.cancel()
        raise


async def llm_call(ctx: Ctx, node: Node, fn, *args):
    """Run one LLM step: parallelism-gated, prune-aware, token-accounted, budget-checked."""
    CURRENT.set((ctx.run_id, node.id))
    async with ctx.sem:
        out, tokens = await guarded(node, fn(*args))
    node.tokens += tokens
    await store.set_agent(node.id, tokens_used=node.tokens)
    await emit(ctx, "agent_status", node, status="thinking", tokens=node.tokens)
    if node.tokens > settings.branch_token_budget and not node.budget_ok:
        await emit(ctx, "budget_warning", node, tokens=node.tokens, budget=settings.branch_token_budget)
        await set_status(ctx, node, "waiting_human")
        row = await approvals.request(
            ctx.run_id, node.id, "budget", f"Branch over token budget ({node.tokens})",
            {"goal": node.goal, "tokens": node.tokens, "budget": settings.branch_token_budget}, "medium")
        if row.status == "rejected":
            raise HumanRejected(row.note or "budget exceeded")
        node.budget_ok = True
        await set_status(ctx, node, "thinking")
    return out


# ---------- the recursive solver ----------


async def run_node(ctx: Ctx, node_id: str, parent_id: str | None, goal: str, depth: int,
                   context: str = "", plan_first: bool = False, role: str = "researcher",
                   depends_on: list[str] | None = None) -> str | None:
    node = Node(node_id, parent_id, depth, goal, role="planner" if plan_first else role)
    role = node.role
    await store.upsert_agent(AgentRow(id=node.id, run_id=ctx.run_id, parent_id=parent_id,
                                      depth=depth, role=role, goal=goal))
    await emit(ctx, "agent_spawned", node, role=role, goal=goal, depth=depth, status="queued",
               depends_on=depends_on or [])
    try:
        return await _solve(ctx, node, context, plan_first)
    except Pruned:
        await set_status(ctx, node, "pruned")
        return None
    except HumanRejected as e:
        await store.set_agent(node.id, status="failed")
        await emit(ctx, "agent_failed", node, error=f"Rejected by human: {e}")
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:  # a failing branch must never take the run down
        await store.set_agent(node.id, status="failed")
        await emit(ctx, "agent_failed", node, error=f"{type(e).__name__}: {e}"[:300])
        return None


async def _solve(ctx: Ctx, node: Node, context: str, plan_first: bool) -> str:
    await checkpoint(ctx, node)
    if plan_first:
        return await _plan_and_run(ctx, node)
    await set_status(ctx, node, "thinking")
    prompt_ctx = "\n".join([context, *node.notes]).strip()
    out: WorkerOutput = await llm_call(ctx, node, ctx.llm.work, node.goal, prompt_ctx, node.role)
    await checkpoint(ctx, node)
    if out.missing_tool:
        # The worker lacks a capability: grow one. Build -> test -> critique -> human -> hot-load.
        await emit(ctx, "log", node, message=f"Missing capability: {out.missing_tool.description}")
        existing = [*BUILTIN_TOOL_NAMES, *[t.name for t in await store.list_tools(True)]]
        need = await llm_call(ctx, node, ctx.llm.justify_tool, out.missing_tool.description, existing)
        if not need.needed:
            # Not worth a build + a human review: send the worker back to the tools it has.
            await emit(ctx, "log", node, message=f"No new tool needed: {need.reason}")
            node.notes.append("A new tool is NOT needed. Use web_search / fetch_url / calculate. "
                              f"({need.reason})")
            prompt_ctx = "\n".join([context, *node.notes]).strip()
            out = await llm_call(ctx, node, ctx.llm.work, node.goal, prompt_ctx, node.role)
            out.missing_tool = None
            tool = None
        else:
            await set_status(ctx, node, "running_tool")
            tool = await toolsmith.build_tool(ctx.run_id, node.id, out.missing_tool, ctx.llm)
        await checkpoint(ctx, node)
        if tool:
            await set_status(ctx, node, "thinking")
            out = await llm_call(ctx, node, ctx.llm.work, node.goal, prompt_ctx, node.role)  # retry with the new tool
        elif need.needed:
            await emit(ctx, "log", node, message="Capability denied; continuing without it")
            out.confidence = min(out.confidence, 0.3)
    if out.needs_decomposition:
        if node.depth < settings.max_depth:
            return await _plan_and_run(ctx, node)
        await emit(ctx, "log", node, message="Max depth reached; solving directly")
        out.confidence = min(out.confidence, 0.5)
    return await _finish(ctx, node, out.result, out.confidence)


async def _plan_and_run(ctx: Ctx, node: Node) -> str:
    await set_status(ctx, node, "thinking")
    plan = await llm_call(ctx, node, ctx.llm.plan, node.goal, node.depth, ctx.history if node.depth == 0 else "")
    await checkpoint(ctx, node)
    if plan.standing_watch and node.depth == 0:
        # A standing goal ("whenever X, tell me"): spawn a long-lived watcher agent.
        from .. import watchers

        await set_status(ctx, node, "running_tool")
        return await _finish(ctx, node, await watchers.start(ctx, node, plan.standing_watch), 0.9)
    if plan.direct_answer or not plan.subtasks:
        return await _finish(ctx, node, plan.direct_answer or "No subtasks produced", 0.8)

    subs = {s.id: s for s in plan.subtasks[:5]}
    results: dict[str, str | None] = {}
    running: dict[asyncio.Task, str] = {}
    started: set[str] = set()
    try:
        while len(results) < len(subs):
            for sid, s in subs.items():
                deps = [d for d in s.depends_on if d in subs and d != sid]
                if sid not in started and all(d in results for d in deps):
                    dep_ctx = "\n".join(f"{d}: {results[d]}" for d in deps if results[d])
                    t = asyncio.create_task(run_node(
                        ctx, f"{node.id}.{sid}", node.id, s.goal, node.depth + 1, dep_ctx, role=s.role,
                        depends_on=[f"{node.id}.{d}" for d in deps]))
                    running[t] = sid
                    started.add(sid)
            if not running:  # unsatisfiable (cyclic) dependencies
                for sid in subs:
                    results.setdefault(sid, None)
                break
            done, _ = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                results[running.pop(t)] = t.result()
    finally:
        for t in running:
            t.cancel()

    await checkpoint(ctx, node)
    good = {sid: r for sid, r in results.items() if r}
    if not good:
        raise RuntimeError("all subtasks failed or were pruned")
    if len(subs) == 1:  # nothing to merge: don't spend a model call (or a node) on it
        return await _finish(ctx, node, next(iter(good.values())), 0.8)
    out: WorkerOutput = await llm_call(ctx, node, ctx.llm.synthesize, node.goal, good)
    return await _finish(ctx, node, out.result, out.confidence)


async def _finish(ctx: Ctx, node: Node, result: str, confidence: float) -> str:
    await checkpoint(ctx, node)
    if confidence < settings.confidence_threshold:
        await set_status(ctx, node, "waiting_human")
        row = await approvals.request(
            ctx.run_id, node.id, "low_confidence", f"Low confidence ({confidence:.0%}): {node.goal}",
            {"goal": node.goal, "result": result, "confidence": confidence}, "medium")
        if row.status == "rejected":
            raise HumanRejected(row.note or "answer rejected")
        if row.status == "edited" and row.edited_payload:
            result = str(row.edited_payload.get("result", result))
    await store.set_agent(node.id, status="done")
    await emit(ctx, "agent_finished", node, result=result, confidence=confidence, tokens=node.tokens)
    return result


def _session_history(session_id: str, run_id: str, limit: int = 5) -> str:
    """The last few goals and answers of this session, so follow-ups ('and under 15 lac?') work."""
    from sqlmodel import Session, select

    from ..db import engine
    from ..models import EventRow, SessionRun

    with Session(engine) as s:
        runs = s.exec(select(SessionRun).where(SessionRun.session_id == session_id, SessionRun.run_id != run_id)
                      .order_by(SessionRun.created_at.desc()).limit(limit)).all()
        lines = []
        for r in reversed(runs):
            fin = s.exec(select(EventRow).where(EventRow.run_id == r.run_id, EventRow.type == "run_finished")).first()
            answer = (fin.payload.get("result") or "") if fin else "(still running)"
            lines.append(f"- User: {r.goal}\n  Banyan: {answer[:600]}")
    return "\n".join(lines)


async def run_goal(run_id: str, goal: str, session_id: str | None = None, llm: LLM | None = None) -> str | None:
    history = await asyncio.to_thread(_session_history, session_id, run_id) if session_id else ""
    ctx = Ctx(run_id, llm or get_llm(), asyncio.Semaphore(settings.max_parallel_agents), session_id, history)
    await emit(ctx, "run_started", goal=goal, mock=type(ctx.llm).__name__ == "MockLLM")
    try:
        result = await asyncio.wait_for(run_node(ctx, f"{run_id}-root", None, goal, 0, plan_first=True),
                                        settings.run_time_budget_sec)
    except asyncio.TimeoutError:
        result = await _time_up(ctx)
        if result is None:
            return None  # a watcher is waiting for inbox access; its decision finishes the goal
    await emit(ctx, "run_finished", result=result)
    return result


async def _time_up(ctx: Ctx) -> str | None:
    """The goal hit the server's time limit (often: a card waited too long for a human).
    Close what is still open and answer with whatever finished, instead of hanging forever."""
    pending = await store.list_approvals("pending", ctx.run_id)
    if any(a.kind == "watch_setup" for a in pending):
        return None
    for a in pending:  # nobody waits on these any more
        await store.decide(a.id, "rejected", "timed out: nobody answered in time", None)
        await emit(ctx, "human_decision", None, approval_id=a.id, decision="rejected", note="timed out")
    done: list[str] = []
    for row in await store.run_agents(ctx.run_id):
        node = Node(row.id, row.parent_id, row.depth, row.goal, role=row.role)
        if row.status in ("done", "failed", "pruned", "watching"):
            continue
        await store.set_agent(row.id, status="failed")
        await emit(ctx, "agent_failed", node, error="Stopped: the server time limit was reached")
    for e in await asyncio.to_thread(bus.since, ctx.run_id):
        if e["type"] == "agent_finished" and e["payload"].get("result") and e["agent_id"] != f"{ctx.run_id}-root":
            done.append(str(e["payload"]["result"]))
    head = "**⏱ Time limit reached before everything finished.**"
    if not done:
        return head + " Nothing finished in time. Try a smaller goal, or answer approval cards sooner."
    return head + " Here is what did finish:\n\n" + "\n\n---\n\n".join(done[-4:])
