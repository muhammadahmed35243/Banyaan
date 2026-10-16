"""Standing agents ("watchers"): goals like "any time I get a payment email, tell me".

A watcher is created by the Planner, asks the human for mailbox access (the credential goes
straight into the vault, never to the LLM), then stays in the tree as a `watching` node
after its goal's request has ended. Serverless can't keep a process alive, so the watcher
lives in the DB and is woken by short `tick` requests (sent by the open browser every few
seconds; a cron job could call the same endpoint). Each tick reads only NEW mail, lets the
LLM judge it against the rule, and raises alerts. Other goals keep running in parallel."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update
from sqlmodel import Session, select

from . import approvals, store, vault
from .config import settings
from .connectors import email_inbox
from .db import engine
from .events import bus
from .models import AgentRow, Event, WatchRow

CREDENTIAL = "gmail"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _ev(run_id: str, type_: str, agent_id: str | None, parent_id: str | None = None, **payload) -> None:
    await bus.publish(Event(run_id=run_id, type=type_, agent_id=agent_id, parent_id=parent_id, payload=payload))


# ---------- creation (runs inside the goal's request) ----------


async def start(ctx, parent, spec) -> str:
    """Spawn the watcher under `parent`, get consent + credential, register it. Returns a
    message for the parent; raises HumanRejected / Pruned like any branch."""
    from .orchestrator.runner import HumanRejected, Node, emit, set_status

    node = Node(f"{parent.id}.watch", parent.id, parent.depth + 1,
                f"Watch my inbox for emails {spec.condition}", role="watcher")
    await store.upsert_agent(AgentRow(id=node.id, run_id=ctx.run_id, parent_id=parent.id,
                                      depth=node.depth, role="watcher", goal=node.goal))
    await emit(ctx, "agent_spawned", node, role="watcher", goal=node.goal, depth=node.depth, status="queued")

    existing = await vault.info(CREDENTIAL)
    await set_status(ctx, node, "waiting_human")
    await emit(ctx, "secret_requested", node, name=CREDENTIAL, have=bool(existing))
    row = await approvals.request(
        ctx.run_id, node.id, "watch_setup", "A watcher wants read-only access to your inbox",
        {"service": "Gmail", "credential": CREDENTIAL, "condition": spec.condition,
         "access": "Read-only. It never sends, deletes or marks mail as read.",
         "interval_sec": settings.watch_interval_sec,
         "has_credential": bool(existing), "credential_label": existing["label"] if existing else None},
        "medium")
    if row.status == "rejected":
        await set_status(ctx, node, "failed")
        raise HumanRejected(row.note or "inbox access denied")

    secret = await vault.get(CREDENTIAL)
    if not secret:
        raise RuntimeError("approved, but no credential was saved in the vault")
    await emit(ctx, "secret_used", node, name=CREDENTIAL, purpose="connect to inbox")  # name only, never the value
    await set_status(ctx, node, "running_tool")
    await emit(ctx, "tool_call", node, tool="email_inbox", args={"mode": secret.get("mode")})
    try:
        cursor = await email_inbox.latest_cursor(secret)
    except Exception as e:
        await store.set_agent(node.id, status="failed")
        await emit(ctx, "agent_failed", node, error=f"Could not open the inbox: {e}"[:300])
        raise HumanRejected("inbox login failed") from e

    watch = WatchRow(id=uuid.uuid4().hex[:12], session_id=ctx.session_id or ctx.run_id, run_id=ctx.run_id,
                     agent_id=node.id, condition=spec.condition, credential=CREDENTIAL, cursor=cursor)
    with Session(engine, expire_on_commit=False) as s:
        s.add(watch)
        s.commit()
    await store.set_agent(node.id, status="watching")
    await emit(ctx, "agent_status", node, status="watching")
    await emit(ctx, "watch_started", node, watch_id=watch.id, condition=spec.condition, mode=secret.get("mode"))
    await emit(ctx, "speak", node, role="watcher", text="I'm watching your inbox now. I'll tell you when something matches.")
    inbox = "the demo inbox" if secret.get("mode") == "demo" else "your inbox"
    return f"A watcher is now checking {inbox} for emails {spec.condition}. Alerts will appear here."


# ---------- ticks (each one is a short request) ----------


def _claim(watch_id: str) -> bool:
    """Atomically take this watch for one check, so two tabs / instances never double-check."""
    cutoff = _utcnow() - timedelta(seconds=settings.watch_interval_sec)
    with Session(engine) as s:
        res = s.execute(update(WatchRow)
                     .where(WatchRow.id == watch_id, WatchRow.status == "active",
                            or_(WatchRow.last_tick_at.is_(None), WatchRow.last_tick_at < cutoff))
                     .values(last_tick_at=_utcnow()))
        s.commit()
        return res.rowcount == 1


def _active(session_id: str) -> list[WatchRow]:
    with Session(engine, expire_on_commit=False) as s:
        return list(s.exec(select(WatchRow).where(WatchRow.session_id == session_id,
                                                  WatchRow.status == "active")).all())


def _save(w: WatchRow) -> None:
    with Session(engine, expire_on_commit=False) as s:
        s.merge(w)
        s.commit()


def _progress(w: WatchRow) -> None:
    """Store a check's progress without touching status (a human may have paused meanwhile)."""
    with Session(engine) as s:
        s.execute(update(WatchRow).where(WatchRow.id == w.id)
                  .values(cursor=w.cursor, checks=w.checks, alerts=w.alerts))
        s.commit()


async def tick(session_id: str) -> dict:
    import asyncio

    checked = 0
    for w in await asyncio.to_thread(_active, session_id):
        if not await asyncio.to_thread(_claim, w.id):
            continue
        agent = await store.get_agent(w.agent_id)
        if agent and agent.control == "prune":  # e.g. a human pruned the parent planner
            await stop(w, "pruned")
            continue
        await _check(w)
        checked += 1
    return {"checked": checked}


async def _check(w: WatchRow) -> None:
    import asyncio

    from .orchestrator.agents import CURRENT, get_llm

    await _ev(w.run_id, "agent_status", w.agent_id, status="running_tool")
    try:
        secret = await vault.get(w.credential)
        if not secret:
            await _ev(w.run_id, "log", w.agent_id, message="Credential was removed from the vault; stopping")
            await stop(w, "failed")
            return
        mails, w.cursor = await email_inbox.fetch_new(secret, w.cursor)
        w.checks += 1
        if mails:
            await _ev(w.run_id, "tool_result", w.agent_id, tool="email_inbox", summary=f"{len(mails)} new email(s)")
            await _ev(w.run_id, "agent_status", w.agent_id, status="thinking")
            CURRENT.set((w.run_id, w.agent_id))
            res, tokens = await get_llm().classify_emails(w.condition, mails)
            hits = [m for m in res.matches if 0 <= m.index < len(mails)]
            for m in hits:
                mail = mails[m.index]
                w.alerts += 1
                aid = f"{w.agent_id}.a{w.alerts}"
                await _ev(w.run_id, "agent_spawned", aid, w.agent_id, role="alert",
                          goal=mail["subject"] or "(no subject)", depth=99, status="done")
                await _ev(w.run_id, "agent_finished", aid, result=f"From {mail['from']}: {m.summary}", confidence=1.0)
                await _ev(w.run_id, "alert", w.agent_id, watch_id=w.id, alert_id=aid, sender=mail["from"],
                          subject=mail["subject"], summary=m.summary, amount=m.amount)
                await _ev(w.run_id, "speak", w.agent_id, role="watcher",
                          text=f"Payment alert: {m.summary}" if "pay" in w.condition else f"Alert: {m.summary}")
            if not hits:
                await _ev(w.run_id, "log", w.agent_id, message=f"{len(mails)} new email(s); none matched")
        await asyncio.to_thread(_progress, w)
    except Exception as e:  # a bad check must not kill the watcher
        await _ev(w.run_id, "log", w.agent_id, message=f"Check failed: {type(e).__name__}: {e}"[:300])
    # The watch may have been paused/stopped by a human while this check ran.
    fresh = await asyncio.to_thread(_get, w.id)
    if fresh and fresh.status == "active":
        await _ev(w.run_id, "agent_status", w.agent_id, status="watching")


def _get(watch_id: str) -> WatchRow | None:
    with Session(engine, expire_on_commit=False) as s:
        return s.get(WatchRow, watch_id)


def _by_agent(agent_id: str) -> WatchRow | None:
    with Session(engine, expire_on_commit=False) as s:
        return s.exec(select(WatchRow).where(WatchRow.agent_id == agent_id)).first()


async def stop(w: WatchRow, status: str = "pruned") -> None:
    import asyncio

    w.status = "stopped"
    await asyncio.to_thread(_save, w)
    await store.set_agent(w.agent_id, status=status)
    await _ev(w.run_id, "agent_status", w.agent_id, status=status)
    await _ev(w.run_id, "watch_stopped", w.agent_id, watch_id=w.id)


async def control(agent_id: str, action: str) -> bool:
    """Human controls on a watcher node (no coroutine is running for it, so act directly).
    Returns False if this agent is not a watcher."""
    import asyncio

    w = await asyncio.to_thread(_by_agent, agent_id)
    if not w or w.status == "stopped":
        return False
    if action == "prune":
        await stop(w)
    elif action == "pause":
        w.status = "paused"
        await asyncio.to_thread(_save, w)
        await store.set_agent(agent_id, status="paused")
        await _ev(w.run_id, "agent_status", agent_id, status="paused")
    elif action == "resume":
        w.status = "active"
        await asyncio.to_thread(_save, w)
        await store.set_agent(agent_id, status="watching")
        await _ev(w.run_id, "agent_status", agent_id, status="watching")
    else:
        return False
    return True
