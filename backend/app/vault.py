"""Secrets vault: Fernet-encrypted rows in the DB.

The LLM never sees a secret: values are only decrypted inside connectors on the server
(e.g. the email connector logging in over IMAP) and are never written to events,
approval details or prompts. Every use is counted."""
import asyncio
import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session

from .config import settings
from .db import engine
from .models import SecretRow


def _fernet() -> Fernet:
    # VAULT_KEY should be set in production. The fallback (derived from the DB URL) keeps
    # local dev working, but anyone holding the DB URL could then decrypt.
    seed = settings.vault_key or f"banyan-dev:{settings.database_url}"
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))


def _put(name: str, value: dict, label: str) -> None:
    token = _fernet().encrypt(json.dumps(value).encode()).decode()
    with Session(engine, expire_on_commit=False) as s:
        s.merge(SecretRow(name=name, ciphertext=token, label=label))
        s.commit()


def _get(name: str) -> dict | None:
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(SecretRow, name)
        if not row:
            return None
        row.use_count += 1
        row.last_used_at = datetime.now(timezone.utc)
        s.add(row)
        s.commit()
        try:
            return json.loads(_fernet().decrypt(row.ciphertext.encode()))
        except InvalidToken:  # saved under a different VAULT_KEY: unusable, so drop it
            s.delete(row)
            s.commit()
            return None


def _info(name: str) -> dict | None:
    """Non-secret metadata only (safe for the UI)."""
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(SecretRow, name)
        return None if not row else {"name": row.name, "label": row.label, "use_count": row.use_count}


def _delete(name: str) -> bool:
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(SecretRow, name)
        if not row:
            return False
        s.delete(row)
        s.commit()
        return True


def _list_prefix(prefix: str) -> list[dict]:
    from sqlmodel import select

    with Session(engine) as s:
        rows = s.exec(select(SecretRow).where(SecretRow.name.startswith(prefix))).all()
        return [{"name": r.name, "label": r.label, "use_count": r.use_count} for r in rows]


put = lambda n, v, label="": asyncio.to_thread(_put, n, v, label)  # noqa: E731
list_prefix = lambda p: asyncio.to_thread(_list_prefix, p)  # noqa: E731
get = lambda n: asyncio.to_thread(_get, n)  # noqa: E731
info = lambda n: asyncio.to_thread(_info, n)  # noqa: E731
delete = lambda n: asyncio.to_thread(_delete, n)  # noqa: E731
