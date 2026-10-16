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
from .agents import CURRENT, LLM, WorkerOutput, get_llm


class HumanRejected(Exception):
    pass


@dataclass
class Ctx:
    run_id: str
    llm: LLM
    sem: asyncio.Semaphore


@dataclass
class Node:
    id: str
    parent_id: str | None
    depth: int
    goal: str
    notes: list[str] = field(default_factory=list)
    tokens: int = 0
    budget_ok: bool = False


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
                   context: str = "", plan_first: bool = False) -> str | None:
    node = Node(node_id, parent_id, depth, goal)
    role = "planner" if plan_first else "worker"
    await store.upsert_agent(AgentRow(id=node.id, run_id=ctx.run_id, parent_id=parent_id,
                                      depth=depth, role=role, goal=goal))
    await emit(ctx, "agent_spawned", node, role=role, goal=goal, depth=depth, status="queued")
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
    out: WorkerOutput = await llm_call(ctx, node, ctx.llm.work, node.goal, prompt_ctx)
    await checkpoint(ctx, node)
    if out.missing_tool:
        # Toolsmith pipeline arrives in Phase 3; until then a missing capability = low confidence.
        await emit(ctx, "log", node, message=f"Missing capability: {out.missing_tool.description}")
        out.confidence = min(out.confidence, 0.3)
    if out.needs_decomposition:
        if node.depth < settings.max_depth:
            return await _plan_and_run(ctx, node)
        await emit(ctx, "log", node, message="Max depth reached; solving directly")
        out.confidence = min(out.confidence, 0.5)
    return await _finish(ctx, node, out.result, out.confidence)


async def _plan_and_run(ctx: Ctx, node: Node) -> str:
    await set_status(ctx, node, "thinking")
    plan = await llm_call(ctx, node, ctx.llm.plan, node.goal, node.depth)
    await checkpoint(ctx, node)
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
                        ctx, f"{node.id}.{sid}", node.id, s.goal, node.depth + 1, dep_ctx))
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


async def run_goal(run_id: str, goal: str) -> str | None:
    ctx = Ctx(run_id, get_llm(), asyncio.Semaphore(settings.max_parallel_agents))
    await emit(ctx, "run_started", goal=goal, mock=type(ctx.llm).__name__ == "MockLLM")
    result = await run_node(ctx, f"{run_id}-root", None, goal, 0, plan_first=True)
    await emit(ctx, "run_finished", result=result)
    return result
