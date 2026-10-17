"""Session memory: what a later goal in the same session knows.

Three parts, all rebuilt from the DB on each goal (serverless keeps nothing in RAM):
- facts the user stated ("my budget is 15k") that the Planner chose to remember,
- the recent conversation (goals and answers),
- the flows still running (watchers) with their ids, so "pause it" / "also include salary
  emails" can edit them, plus the bills tracker."""
import asyncio
from datetime import datetime, timezone

from sqlmodel import Session, select

from .db import engine
from .events import bus
from .models import BillRow, Event, EventRow, SessionMemory, SessionRun, WatchRow

MAX_FACTS = 30


def _get(session_id: str) -> list[str]:
    with Session(engine) as s:
        row = s.get(SessionMemory, session_id)
        return list(row.facts) if row else []


def _set(session_id: str, facts: list[str]) -> None:
    with Session(engine) as s:
        row = s.get(SessionMemory, session_id) or SessionMemory(session_id=session_id)
        row.facts = facts[-MAX_FACTS:]
        row.updated_at = datetime.now(timezone.utc)
        s.add(row)
        s.commit()


async def facts(session_id: str) -> list[str]:
    return await asyncio.to_thread(_get, session_id)


async def remember(session_id: str, run_id: str, new: list[str]) -> list[str]:
    """Add facts (a fact about the same thing replaces the older one only if identical text;
    the Planner is told to restate updated facts in full, e.g. 'Budget: under 10k PKR')."""
    current = await facts(session_id)
    added = False
    for f in (x.strip() for x in new):
        if f and f.lower() not in {c.lower() for c in current}:
            # Same topic ("Budget: ...") replaces the old value.
            key = f.split(":", 1)[0].lower() if ":" in f[:40] else None
            if key:
                current = [c for c in current if not (":" in c[:40] and c.split(":", 1)[0].lower() == key)]
            current.append(f)
            added = True
    if added:
        await asyncio.to_thread(_set, session_id, current)
        await bus.publish(Event(run_id=run_id, type="memory_updated", payload={"facts": current[-MAX_FACTS:]}))
    return current


def _last_run(session_id: str) -> str | None:
    with Session(engine) as s:
        r = s.exec(select(SessionRun).where(SessionRun.session_id == session_id)
                   .order_by(SessionRun.created_at.desc())).first()
        return r.run_id if r else None


async def forget(session_id: str, index: int) -> list[str]:
    current = await facts(session_id)
    if 0 <= index < len(current):
        current.pop(index)
        await asyncio.to_thread(_set, session_id, current)
        run_id = await asyncio.to_thread(_last_run, session_id)
        if run_id:  # an event, so every open tab (and a later replay) sees the deletion
            await bus.publish(Event(run_id=run_id, type="memory_updated", payload={"facts": current}))
    return current


def _context(session_id: str, run_id: str, limit: int) -> str:
    with Session(engine) as s:
        mem = s.get(SessionMemory, session_id)
        runs = s.exec(select(SessionRun).where(SessionRun.session_id == session_id, SessionRun.run_id != run_id)
                      .order_by(SessionRun.created_at.desc()).limit(limit)).all()
        convo = []
        for r in reversed(runs):
            fin = s.exec(select(EventRow).where(EventRow.run_id == r.run_id, EventRow.type == "run_finished")).first()
            answer = (fin.payload.get("result") or "(no answer)") if fin else "(still running)"
            convo.append(f"- User: {r.goal}\n  Banyan: {answer[:700]}")
        watches = s.exec(select(WatchRow).where(WatchRow.session_id == session_id,
                                                WatchRow.status != "stopped")).all()
        bills = s.exec(select(BillRow).where(BillRow.session_id == session_id)).all()
    parts = []
    if mem and mem.facts:
        parts.append("Facts the user told you (use them):\n" + "\n".join(f"- {f}" for f in mem.facts))
    if convo:
        parts.append("Conversation so far:\n" + "\n".join(convo))
    if watches:
        parts.append("Flows still running in this session (edit them by id with flow_edits):\n" + "\n".join(
            (f"- id={w.id} watcher [{w.status}] on {w.service}: new items {w.condition}" if w.source == "service"
             else f"- id={w.id} watcher [{w.status}]: emails {w.condition}")
            + (f"; forwards alerts to {w.forward_to}" if w.forward_to else "")
            + f"; {w.checks} checks, {w.alerts} alerts" for w in watches))
    if bills:
        parts.append("Bills tracker:\n" + "\n".join(
            f"- {b.payee} {b.amount} {b.status}" + (f" due {b.due_date}" if b.due_date else "") for b in bills))
    return "\n\n".join(parts)


async def context(session_id: str, run_id: str, limit: int = 6) -> str:
    from .connectors import services

    ctx = await asyncio.to_thread(_context, session_id, run_id, limit)
    conn = await services.connected_list()
    if conn:
        ctx += ("\n\n" if ctx else "") + "Connected services (the user's own accounts, readable now):\n" + "\n".join(
            f"- {c['service']}: {c['label']}" for c in conn)
    return ctx
