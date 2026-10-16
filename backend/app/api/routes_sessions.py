"""Sessions (many goals side by side), watcher ticks, the vault and the demo inbox."""
import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import store, vault, watchers
from ..db import engine
from ..events import bus
from ..models import DemoEmail, SessionRun, WatchRow

router = APIRouter(prefix="/api")


def _link(session_id: str, run_id: str, goal: str) -> None:
    with Session(engine) as s:
        if not s.get(SessionRun, run_id):
            s.add(SessionRun(run_id=run_id, session_id=session_id, goal=goal))
            s.commit()


async def link_run(session_id: str | None, run_id: str, goal: str) -> None:
    if session_id:
        await asyncio.to_thread(_link, session_id, run_id, goal)


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, after: int = 0) -> dict:
    events = await asyncio.to_thread(bus.since_session, session_id, after)
    return {"events": events, "cursor": events[-1]["seq"] if events else after}


@router.post("/sessions/{session_id}/tick")
async def tick(session_id: str) -> dict:
    """Wake this session's watchers. Called by the open browser every few seconds (a cron
    job could call it too); each watcher checks at most once per WATCH_INTERVAL_SEC."""
    return await watchers.tick(session_id)


def _watches(session_id: str) -> list[WatchRow]:
    with Session(engine) as s:
        return list(s.exec(select(WatchRow).where(WatchRow.session_id == session_id)).all())


@router.get("/sessions/{session_id}/watches")
async def list_watches(session_id: str) -> list[dict]:
    return [w.model_dump(mode="json", exclude={"cursor"}) for w in await asyncio.to_thread(_watches, session_id)]


# ---------- vault ----------


class CredentialIn(BaseModel):
    mode: str  # "imap" (real mailbox) | "demo"
    email: str | None = None
    app_password: str | None = None
    host: str | None = None


@router.post("/approvals/{approval_id}/credential")
async def provide_credential(approval_id: str, body: CredentialIn) -> dict:
    """The human answers a watch_setup card. The secret goes straight into the encrypted
    vault and the approval is marked approved; the approval itself never holds the secret."""
    a = await store.get_approval(approval_id)
    if not a or a.kind != "watch_setup":
        raise HTTPException(404, "unknown credential request")
    if a.status != "pending":
        raise HTTPException(409, "already decided")
    name = a.details.get("credential", "gmail")
    if body.mode == "demo":
        await vault.put(name, {"mode": "demo"}, "Demo inbox")
    elif body.mode == "imap":
        if not body.email or not body.app_password:
            raise HTTPException(400, "email and app password are required")
        secret = {"mode": "imap", "email": body.email.strip(),
                  "app_password": body.app_password.replace(" ", ""), "host": body.host or "imap.gmail.com"}
        await vault.put(name, secret, body.email.strip())
    else:
        raise HTTPException(400, "mode must be imap or demo")
    row = await store.decide(approval_id, "approved", "credential provided", None)
    if not row:
        raise HTTPException(409, "already decided")
    return {"ok": True, "stored": name}


@router.get("/vault")
async def vault_list() -> list[dict]:
    """Names and labels only. Values never leave the server."""
    out = []
    for n in ("gmail",):
        i = await vault.info(n)
        if i:
            out.append(i)
    return out


@router.delete("/vault/{name}")
async def vault_delete(name: str) -> dict:
    return {"deleted": await vault.delete(name)}


# ---------- demo inbox ----------

PRESETS = {
    "payment": ("billing@k-electric.example", "Payment due: your electricity bill of PKR 14,250",
                "Dear customer, your bill of PKR 14,250 is due on 25 Oct. Pay online to avoid a late fee."),
    "receipt": ("no-reply@daraz.example", "Payment received - order #48213",
                "We received your payment of PKR 289,999 for MacBook Air M3. Your order is being packed."),
    "newsletter": ("news@techdigest.example", "This week in AI: 10 tools you should try",
                   "Our weekly roundup of AI news, product launches and tutorials."),
    "personal": ("ali@example.com", "Dinner on Saturday?", "Are you free on Saturday evening? Let me know."),
}


class DemoEmailIn(BaseModel):
    preset: str | None = None
    sender: str | None = None
    subject: str | None = None
    body: str = ""


def _add_demo(m: DemoEmail) -> int:
    with Session(engine, expire_on_commit=False) as s:
        s.add(m)
        s.commit()
        return m.id


@router.post("/demo/emails")
async def add_demo_email(body: DemoEmailIn) -> dict:
    if body.preset:
        if body.preset not in PRESETS:
            raise HTTPException(400, f"preset must be one of {list(PRESETS)}")
        sender, subject, text = PRESETS[body.preset]
    elif body.sender and body.subject:
        sender, subject, text = body.sender, body.subject, body.body
    else:
        raise HTTPException(400, "give a preset or sender + subject")
    eid = await asyncio.to_thread(_add_demo, DemoEmail(sender=sender, subject=subject, body=text))
    return {"id": eid, "subject": subject}
