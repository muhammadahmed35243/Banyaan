"""Google sign-in (OAuth 2.0 web flow) + the Gmail API.

The refresh token lives only in the vault (secret 'google'); access tokens are minted on
the server per use and cached briefly in memory. No agent or LLM ever sees either."""
import base64
import hashlib
import hmac
import json
import time
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx

from ..config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = ["openid", "email", "https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.send"]
STATE_TTL = 600


def enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    return settings.backend_url.rstrip("/") + "/api/auth/google/callback"


# ---------- state: signed, short-lived, so a callback can't be forged or replayed later ----------

def _key() -> bytes:
    return hashlib.sha256(("oauth-state:" + (settings.vault_key or settings.database_url)).encode()).digest()


def sign_state(data: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps({**data, "ts": int(time.time())}).encode()).decode()
    sig = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_state(state: str) -> dict | None:
    try:
        body, sig = state.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()):
            return None
        data = json.loads(base64.urlsafe_b64decode(body))
        return data if time.time() - data["ts"] < STATE_TTL else None
    except Exception:
        return None


def auth_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state,
    })


def exchange_code(code: str) -> dict:
    """-> {refresh_token, email}"""
    r = httpx.post(TOKEN_URL, data={
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code"}, timeout=20)
    r.raise_for_status()
    tok = r.json()
    if not tok.get("refresh_token"):
        raise RuntimeError("Google returned no refresh token")
    # The id_token comes straight from Google over TLS, so reading its payload is enough here.
    payload = tok["id_token"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    _cache[tok["refresh_token"]] = (tok["access_token"], time.time() + tok.get("expires_in", 3600) - 60)
    return {"refresh_token": tok["refresh_token"], "email": claims.get("email", "")}


# ---------- access tokens + Gmail ----------

_cache: dict[str, tuple[str, float]] = {}


def access_token(secret: dict) -> str:
    rt = secret["refresh_token"]
    tok, exp = _cache.get(rt, ("", 0))
    if time.time() < exp:
        return tok
    r = httpx.post(TOKEN_URL, data={
        "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "refresh_token": rt, "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Google token refresh failed ({r.status_code}); sign in again")
    data = r.json()
    _cache[rt] = (data["access_token"], time.time() + data.get("expires_in", 3600) - 60)
    return data["access_token"]


def _get(secret: dict, path: str, params=None) -> dict:
    r = httpx.get(GMAIL + path, params=params, headers={"Authorization": f"Bearer {access_token(secret)}"}, timeout=20)
    r.raise_for_status()
    return r.json()


def new_messages(secret: dict, after_ts: int, limit: int = 10) -> list[dict]:
    """Inbox messages that arrived after `after_ts` (unix seconds), oldest first:
    [{id, ts, from, subject, snippet}]"""
    ids = _get(secret, "/messages", [("q", f"in:inbox after:{after_ts}"), ("maxResults", limit)]).get("messages", [])
    out = []
    for m in ids:
        msg = _get(secret, f"/messages/{m['id']}", [("format", "metadata"), ("metadataHeaders", "From"),
                                                    ("metadataHeaders", "Subject")])
        h = {x["name"].lower(): x["value"] for x in msg.get("payload", {}).get("headers", [])}
        ts = int(msg.get("internalDate", "0")) // 1000
        if ts > after_ts:
            out.append({"id": ts, "from": h.get("from", ""), "subject": h.get("subject", ""),
                        "snippet": msg.get("snippet", "")})
    return sorted(out, key=lambda x: x["id"])


def send(secret: dict, to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = httpx.post(GMAIL + "/messages/send", json={"raw": raw},
                   headers={"Authorization": f"Bearer {access_token(secret)}"}, timeout=20)
    r.raise_for_status()
    return r.json().get("id", "")
