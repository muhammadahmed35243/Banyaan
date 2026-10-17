"""Sign in with Google. The flow runs in a popup so the mission-control page (and any goal
request it is running) stays put. The token goes straight into the vault."""
import html

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import store, vault, watchers
from ..connectors import google, services

router = APIRouter(prefix="/api/auth/google")


@router.get("/config")
async def config() -> dict:
    info = await vault.info("google")
    return {"enabled": google.enabled(), "connected": info["label"] if info else None}


@router.get("/start")
async def start(request: Request, approval_id: str | None = None, service: str | None = None) -> RedirectResponse:
    """`service` (e.g. google_classroom) adds that service's read-only scopes to the sign-in."""
    if not google.enabled():
        raise HTTPException(404, "Google sign-in is not configured")
    extra = (services.KNOWN.get(service) or {}).get("scopes", []) if service else []
    base = google.public_base(request)
    state = google.sign_state({"approval_id": approval_id, "service": service, "base": base})
    return RedirectResponse(google.auth_url(state, extra, base))


def _page(ok: bool, text: str) -> HTMLResponse:
    color = "#34d399" if ok else "#f87171"
    return HTMLResponse(
        f"""<!doctype html><meta charset="utf-8"><title>Banyan</title>
<body style="background:#0f172a;color:#e2e8f0;font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center"><div style="font-size:48px">🌳</div>
<p style="color:{color};font-size:18px">{html.escape(text)}</p>
<p style="color:#64748b">You can close this window.</p></div>
<script>try{{window.opener&&window.opener.postMessage({{banyan:"google",ok:{str(ok).lower()}}},"*")}}catch(e){{}}
setTimeout(function(){{window.close()}},1800)</script></body>""")


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None,
                   error: str | None = None) -> HTMLResponse:
    if error:
        return _page(False, f"Google sign-in was cancelled ({error}).")
    data = google.verify_state(state or "")
    if not data or not code:
        return _page(False, "This sign-in link is invalid or expired. Try again.")
    try:
        # The same redirect_uri as the sign-in started with (Google requires an exact match).
        tok = google.exchange_code(code, data.get("base") or google.public_base(request))
    except Exception as e:
        return _page(False, f"Sign-in failed: {e}")
    await vault.put("google", tok, tok["email"])
    if not data.get("service"):  # a plain Google sign-in is for Gmail; a Classroom one leaves Gmail as is
        await vault.put("gmail", {"mode": "google"}, f"Gmail: {tok['email']}")  # watchers read this inbox now
    if data.get("approval_id"):
        a = await store.get_approval(data["approval_id"])
        if a and a.status == "pending" and a.kind in ("watch_setup", "connect_google", "connect_service"):
            if a.kind == "connect_service" and not await services.connected(a.details.get("service", "")):
                return _page(False, "Google did not grant the access this needs. Try again and tick every box.")
            row = await store.decide(a.id, "approved", "Google sign-in", None)
            if row and row.kind == "watch_setup":
                await watchers.resume_setup(row)
    return _page(True, f"Connected {tok['email']}.")


@router.post("/disconnect")
async def disconnect() -> dict:
    gm = await vault.info("gmail")
    await vault.delete("google")
    if gm and gm["label"].startswith("Gmail:"):
        await vault.delete("gmail")
    return {"ok": True}
