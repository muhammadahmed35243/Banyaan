"""Read-only email connector used by watcher agents.

Two modes, chosen by the credential stored in the vault:
- "demo": reads the demo_emails table (for presentations; filled via /api/demo/emails)
- "imap": reads a real mailbox over IMAP, e.g. Gmail with an app password.
  Mailbox is opened read-only and messages are fetched with BODY.PEEK, so nothing is
  marked as read and nothing is ever sent or deleted.

The credential is decrypted only here; callers get emails, never the password."""
import asyncio
import email
import imaplib
import re
from email.header import decode_header, make_header

from sqlmodel import Session, func, select

from ..db import engine
from ..models import DemoEmail

MAX_PER_CHECK = 10


def _decode(v: str | None) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def _clean(text: str, n: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:n]


# ---------- demo inbox ----------


def _demo_latest() -> int:
    with Session(engine) as s:
        return s.exec(select(func.max(DemoEmail.id))).one() or 0


def _demo_new(cursor: int) -> tuple[list[dict], int]:
    with Session(engine) as s:
        rows = s.exec(select(DemoEmail).where(DemoEmail.id > cursor)
                      .order_by(DemoEmail.id).limit(MAX_PER_CHECK)).all()
    mails = [{"id": r.id, "from": r.sender, "subject": r.subject, "snippet": _clean(r.body)} for r in rows]
    return mails, (rows[-1].id if rows else cursor)


# ---------- real mailbox (IMAP) ----------


def _imap(secret: dict) -> imaplib.IMAP4_SSL:
    box = imaplib.IMAP4_SSL(secret.get("host") or "imap.gmail.com", timeout=20)
    box.login(secret["email"], secret["app_password"])
    box.select("INBOX", readonly=True)
    return box


def _imap_latest(secret: dict) -> int:
    box = _imap(secret)
    try:
        _, data = box.uid("search", None, "ALL")
        uids = [int(u) for u in (data[0] or b"").split()]
        return max(uids, default=0)
    finally:
        box.logout()


def _imap_new(secret: dict, cursor: int) -> tuple[list[dict], int]:
    box = _imap(secret)
    try:
        _, data = box.uid("search", None, f"UID {cursor + 1}:*")
        # "N:*" always returns the newest message, even if its UID is below N.
        uids = sorted(u for u in (int(x) for x in (data[0] or b"").split()) if u > cursor)[:MAX_PER_CHECK]
        mails = []
        for uid in uids:
            _, h = box.uid("fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            _, t = box.uid("fetch", str(uid), "(BODY.PEEK[TEXT]<0.1500>)")
            head = email.message_from_bytes(h[0][1]) if h and isinstance(h[0], tuple) else {}
            body = t[0][1].decode("utf-8", "replace") if t and isinstance(t[0], tuple) else ""
            mails.append({"id": uid, "from": _decode(head.get("From")), "subject": _decode(head.get("Subject")),
                          "snippet": _clean(body)})
        return mails, (uids[-1] if uids else cursor)
    finally:
        box.logout()


# ---------- public API ----------


async def latest_cursor(secret: dict) -> int:
    """Where to start watching: only mail that arrives from now on counts."""
    if secret.get("mode") == "imap":
        return await asyncio.to_thread(_imap_latest, secret)
    return await asyncio.to_thread(_demo_latest)


async def fetch_new(secret: dict, cursor: int) -> tuple[list[dict], int]:
    if secret.get("mode") == "imap":
        return await asyncio.to_thread(_imap_new, secret, cursor)
    return await asyncio.to_thread(_demo_new, cursor)
