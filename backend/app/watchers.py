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
from .models import AgentRow, BillRow, Event, WatchRow

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
    access = "Read-only. It never deletes or marks mail as read."
    if spec.forward_to:
        access += f" It WILL email each matching alert to {spec.forward_to} from your Gmail."
    else:
        access += " It never sends mail."
    # Everything needed to finish the setup goes in the approval, because the human may answer
    # after this request has timed out; then the request that records the decision finishes it.
    row = await approvals.request(
        ctx.run_id, node.id, "watch_setup", "A watcher wants read-only access to your inbox",
        {"service": "Gmail", "credential": CREDENTIAL, "condition": spec.condition, "access": access,
         "forward_to": spec.forward_to, "interval_sec": settings.watch_interval_sec,
         "session_id": ctx.session_id or ctx.run_id, "parent_id": parent.id,
         "has_credential": bool(existing), "credential_label": existing["label"] if existing else None},
        "medium")
    if row.status == "rejected":
        await set_status(ctx, node, "failed")
        raise HumanRejected(row.note or "inbox access denied")
    try:
        return await finish_setup(row)
    except SetupFailed as e:
        raise HumanRejected(str(e)) from e


class SetupFailed(Exception):
    pass


def _insert(w: WatchRow) -> bool:
    from sqlalchemy.exc import IntegrityError

    try:
        with Session(engine, expire_on_commit=False) as s:
            s.add(w)
            s.commit()
        return True
    except IntegrityError:
        return False


async def finish_setup(a) -> str:
    """Register the watcher of an approved watch_setup card. Idempotent: the watch's id is the
    approval's id, so the goal's request and the decision request can both call this safely."""
    import asyncio

    d = a.details
    inbox_msg = (f"A watcher is now checking your inbox for emails {d['condition']}."
                 + (f" Each match is emailed to {d['forward_to']}." if d.get("forward_to") else "")
                 + " Alerts will appear here.")
    if await asyncio.to_thread(_get, a.id):
        return inbox_msg
    agent, parent = a.agent_id, d.get("parent_id")
    secret = await vault.get(d.get("credential", CREDENTIAL))
    if not secret:
        raise SetupFailed("approved, but no credential was saved in the vault")
    await _ev(a.run_id, "secret_used", agent, parent, name=CREDENTIAL, purpose="connect to inbox")  # name only
    await store.set_agent(agent, status="running_tool")
    await _ev(a.run_id, "agent_status", agent, parent, status="running_tool")
    await _ev(a.run_id, "tool_call", agent, parent, tool="email_inbox", args={"mode": secret.get("mode")})
    try:
        cursor = await email_inbox.latest_cursor(secret)
    except Exception as e:
        await store.set_agent(agent, status="failed")
        await _ev(a.run_id, "agent_failed", agent, parent, error=f"Could not open the inbox: {e}"[:300])
        raise SetupFailed("inbox login failed") from e
    watch = WatchRow(id=a.id, session_id=d.get("session_id") or a.run_id, run_id=a.run_id, agent_id=agent,
                     condition=d["condition"], credential=d.get("credential", CREDENTIAL),
                     forward_to=d.get("forward_to"), cursor=cursor)
    if not await asyncio.to_thread(_insert, watch):
        return inbox_msg  # the other request got there first
    await store.set_agent(agent, status="watching")
    await _ev(a.run_id, "agent_status", agent, parent, status="watching")
    await _ev(a.run_id, "watch_started", agent, parent, watch_id=watch.id, condition=watch.condition,
              mode=secret.get("mode"))
    await _ev(a.run_id, "speak", agent, parent, role="watcher",
              text="I'm watching your inbox now. I'll tell you when something matches.")
    return inbox_msg.replace("your inbox", "the demo inbox") if secret.get("mode") == "demo" else inbox_msg


async def resume_setup(a) -> None:
    """Called by the requests that record a watch_setup decision. If the goal's request is still
    waiting it does the same work (idempotently); if it already timed out, this finishes the job:
    the card, the watcher and the goal's answer all update."""
    d = a.details
    await _ev(a.run_id, "human_decision", a.agent_id, approval_id=a.id, decision=a.status, note=a.note)
    parent = d.get("parent_id")
    if a.status == "rejected":
        await store.set_agent(a.agent_id, status="failed")
        await _ev(a.run_id, "agent_failed", a.agent_id, parent, error=f"Rejected by human: {a.note or 'inbox access denied'}")
        return
    try:
        msg = await finish_setup(a)
    except SetupFailed:
        return
    if parent:
        await store.set_agent(parent, status="done")
        await _ev(a.run_id, "agent_finished", parent, result=msg, confidence=0.9)
    await _ev(a.run_id, "run_finished", None, result=msg)


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


def _active(session_id: str | None) -> list[WatchRow]:
    """Active watches of one session, or of all sessions (session_id=None, used by the cron)."""
    with Session(engine, expire_on_commit=False) as s:
        q = select(WatchRow).where(WatchRow.status == "active")
        if session_id:
            q = q.where(WatchRow.session_id == session_id)
        return list(s.exec(q).all())


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


async def tick(session_id: str | None) -> dict:
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
        await _ev(w.run_id, "secret_used", w.agent_id, name=w.credential, purpose="check inbox")
        await _ev(w.run_id, "tool_call", w.agent_id, tool="email_inbox", args={"mode": secret.get("mode")})
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
                await _notify(w, mail["subject"] or "Banyan alert", m.summary + (f" ({m.amount})" if m.amount else ""))
                if w.forward_to:
                    await _forward(w, mail, m)
                if m.action in ACTIONS:
                    await _propose(w, aid, m, mail)
            if not hits:
                await _ev(w.run_id, "log", w.agent_id, message=f"{len(mails)} new email(s); none matched")
        await asyncio.to_thread(_progress, w)
    except Exception as e:  # a bad check must not kill the watcher
        await _ev(w.run_id, "log", w.agent_id, message=f"Check failed: {type(e).__name__}: {e}"[:300])
    # The watch may have been paused/stopped by a human while this check ran.
    fresh = await asyncio.to_thread(_get, w.id)
    if fresh and fresh.status == "active":
        await _ev(w.run_id, "agent_status", w.agent_id, status="watching")


# ---------- follow-up actions (proposed by the watcher, executed only after a human approves) ----------

ACTIONS = {"track_bill": "Add bill to tracker", "mark_paid": "Record payment as paid"}


async def _propose(w: WatchRow, alert_id: str, m, mail: dict) -> None:
    """Non-blocking approval: the tick ends right away; the action runs when a human decides
    (see execute_action, called by the decide endpoint)."""
    what = " · ".join(x for x in (m.payee, m.amount, f"due {m.due_date}" if m.due_date else None) if x)
    title = f"{ACTIONS[m.action]}: {what or mail['subject']}"
    details = {"action": m.action, "payee": m.payee or mail["from"], "amount": m.amount or "",
               "due_date": m.due_date, "subject": mail["subject"], "session_id": w.session_id,
               "watch_id": w.id, "result": m.summary}
    approval_id = await store.create_approval(run_id=w.run_id, agent_id=alert_id, kind="watch_action",
                                              title=title, details=details, risk="low")
    await _ev(w.run_id, "needs_human", alert_id, approval_id=approval_id, kind="watch_action", title=title,
              risk="low", details=details)


def _add_bill(b: BillRow) -> None:
    with Session(engine, expire_on_commit=False) as s:
        s.add(b)
        s.commit()


async def execute_action(approval) -> None:
    """Called after a human decides a watch_action card."""
    import asyncio

    d = approval.details | (approval.edited_payload or {})
    await _ev(approval.run_id, "human_decision", approval.agent_id, approval_id=approval.id,
              decision=approval.status, note=approval.note)
    if approval.status == "rejected":
        await _ev(approval.run_id, "log", approval.agent_id, message=f"Human declined: {approval.title}")
        return
    status = "paid" if d["action"] == "mark_paid" else "due"
    bill = BillRow(id=uuid.uuid4().hex[:12], session_id=d["session_id"], payee=d.get("payee") or "",
                   amount=d.get("amount") or "", due_date=d.get("due_date"), status=status,
                   source_subject=d.get("subject") or "")
    await asyncio.to_thread(_add_bill, bill)
    node = f"{approval.agent_id}.act"
    await _ev(approval.run_id, "agent_spawned", node, approval.agent_id, role="action",
              goal=f"{'Paid' if status == 'paid' else 'Tracked'}: {bill.payee} {bill.amount}".strip(),
              depth=99, status="done")
    await _ev(approval.run_id, "agent_finished", node, result="Added to the bills tracker", confidence=1.0)
    await _ev(approval.run_id, "bill_tracked", node, bill_id=bill.id, payee=bill.payee, amount=bill.amount,
              due_date=bill.due_date, status=status, subject=bill.source_subject)


# ---------- notifications that reach you with the tab closed ----------


async def _notify(w: WatchRow, title: str, message: str) -> None:
    """Optional phone push through ntfy.sh (configured in the vault as 'notify'). The topic name
    is the only protection on ntfy, so it's kept in the vault like a password."""
    import httpx

    cfg = await vault.get("notify")
    topic = (cfg or {}).get("ntfy_topic")
    if not topic:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://ntfy.sh/{topic}", content=message.encode(),
                             headers={"Title": title[:120].encode("ascii", "ignore").decode() or "Banyan",
                                      "Tags": "bell"})
        await _ev(w.run_id, "notified", w.agent_id, channel="ntfy", ok=r.status_code < 300)
    except Exception as e:
        await _ev(w.run_id, "log", w.agent_id, message=f"Push notification failed: {e}"[:200])


async def _forward(w: WatchRow, mail: dict, m) -> None:
    """Email the alert to the address the user named. The human consented to this standing
    rule on the setup card, so each send doesn't need its own approval. Scripted/test runs and
    setups without a Google login never send."""
    import asyncio

    from .connectors import google

    to = w.forward_to
    subject = f"Banyan alert: {mail['subject'] or 'matching email'}"
    body = (f"Your Banyan watcher found an email {w.condition}.\n\nFrom: {mail['from']}\n"
            f"Subject: {mail['subject']}\nSummary: {m.summary}" + (f"\nAmount: {m.amount}" if m.amount else ""))
    await _ev(w.run_id, "tool_call", w.agent_id, tool="send_email", args={"to": to, "subject": subject})
    g = None if settings.use_mock or not google.enabled() else await vault.get("google")
    if not g:
        await _ev(w.run_id, "log", w.agent_id, message=f"NOT SENT to {to}: no Gmail connected (sign in with Google to send)")
        return
    try:
        await _ev(w.run_id, "secret_used", w.agent_id, name="google", purpose="forward alert")
        await asyncio.to_thread(google.send, g, to, subject, body)
        await _ev(w.run_id, "tool_result", w.agent_id, tool="send_email", summary=f"Alert emailed to {to}")
    except Exception as e:
        await _ev(w.run_id, "log", w.agent_id, message=f"Forward to {to} failed: {e}"[:300])


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
