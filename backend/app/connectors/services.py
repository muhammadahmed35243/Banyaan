"""Connected services: any HTTP API an agent may call on the user's behalf.

One gateway, `call`, does every request. It
- only talks to the service's own base URL (no other host, no redirects off it),
- adds the credential from the vault on the server: agents and the LLM never see it,
- allows reads (GET) freely; anything that changes data (POST/PUT/PATCH/DELETE) needs a
  human approval first (see tools.registry.call_service),
- returns trimmed JSON so a big API response can't flood the model.

Known services carry their auth style and a few useful paths for the agents; any other REST
API can be connected as a "custom" service with a token."""
import json
from urllib.parse import urlparse

import httpx

from .. import vault
from ..config import settings

CLASSROOM_SCOPES = ["https://www.googleapis.com/auth/classroom.courses.readonly",
                    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
                    "https://www.googleapis.com/auth/classroom.announcements.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

KNOWN: dict[str, dict] = {
    "google_classroom": {
        "label": "Google Classroom", "base_url": "https://classroom.googleapis.com", "auth": "google",
        "scopes": CLASSROOM_SCOPES,
        "paths": "GET /v1/courses?courseStates=ACTIVE (your classes) · "
                 "GET /v1/courses/{courseId}/courseWork?orderBy=updateTime desc (assignments, with dueDate) · "
                 "GET /v1/courses/{courseId}/announcements · "
                 "GET /v1/courses/{courseId}/courseWork/-/studentSubmissions (your submission states)",
    },
    "google_calendar": {
        "label": "Google Calendar", "base_url": "https://www.googleapis.com/calendar/v3", "auth": "google",
        "scopes": CALENDAR_SCOPES,
        "paths": "GET /calendars/primary/events?timeMin=<RFC3339>&singleEvents=true&orderBy=startTime",
    },
    "github": {
        "label": "GitHub", "base_url": "https://api.github.com", "auth": "bearer",
        "paths": "GET /user/repos?sort=updated · GET /repos/{owner}/{repo}/issues · GET /notifications",
    },
    "shopify": {
        # Every store has its own address, so the human gives it on the connect card.
        "label": "Shopify", "base_url": "", "auth": "header", "header": "X-Shopify-Access-Token",
        "base_hint": "https://YOUR-STORE.myshopify.com/admin/api/2025-01",
        "token_hint": "Admin API access token (Settings → Apps → Develop apps → your app → API credentials)",
        "paths": "GET /shop.json · GET /products.json?limit=50&fields=id,title,status,variants,product_type,vendor "
                 "(variants carry price and inventory_quantity) · GET /orders.json?status=any&limit=50 · "
                 "GET /products/count.json",
    },
    # A built-in stand-in with fake classes, so the whole flow can be shown on stage without a
    # real school account. It is served by this backend (see routes_sessions /api/demo/classroom).
    "demo_classroom": {
        "label": "Demo Classroom", "base_url": "", "auth": "bearer",
        "paths": "GET /v1/courses · GET /v1/courses/{courseId}/courseWork · GET /v1/courses/{courseId}/announcements",
    },
}
MAX_CHARS = 6000
_transport = None  # tests route requests into the app in-process (httpx.ASGITransport)


def _vault_name(service: str) -> str:
    return f"svc:{service}"


def spec(service: str, custom: dict | None = None) -> dict | None:
    s = KNOWN.get(service)
    if s and service == "demo_classroom":
        s = {**s, "base_url": settings.backend_url.rstrip("/") + "/api/demo/classroom"}
    return s or custom


async def config(service: str) -> dict | None:
    """The service's spec, including a custom one stored with its credential."""
    if service in KNOWN and (KNOWN[service]["base_url"] or service == "demo_classroom"):
        return spec(service)
    if service in KNOWN:  # known API, per-account address (e.g. a Shopify store)
        stored = await vault.get(_vault_name(service))
        return {**KNOWN[service], "base_url": stored.get("base_url", "")} if stored else dict(KNOWN[service])
    stored = await vault.get(_vault_name(service))
    return {k: stored[k] for k in ("label", "base_url", "auth", "header", "paths") if k in stored} if stored else None


async def connected(service: str) -> bool:
    s = await config(service)
    if not s:
        return False
    if s["auth"] == "google":
        g = await vault.get("google")
        return bool(g) and set(s.get("scopes", [])) <= set(g.get("scopes", []))
    return bool(await vault.info(_vault_name(service)))


async def connect(service: str, token: str, label: str | None = None, base_url: str | None = None,
                  auth: str | None = None, header: str | None = None) -> str:
    """Store a token credential (bearer / header / query) for a known or custom service."""
    s = dict(spec(service) or {})
    if s and not s.get("base_url"):  # known API whose address differs per account (Shopify store)
        if not base_url or urlparse(base_url).scheme != "https":
            raise ValueError(f"{s['label']} needs your https address, e.g. {s.get('base_hint', '')}")
        s["base_url"] = base_url.rstrip("/")
    if not s:  # custom service: the human supplies where it lives and how it authenticates
        if not base_url or urlparse(base_url).scheme != "https":
            raise ValueError("a custom service needs an https base URL")
        s = {"label": label or service, "base_url": base_url.rstrip("/"), "auth": auth or "bearer",
             "header": header, "paths": ""}
    if s.get("auth") == "google":
        raise ValueError("this service uses Sign in with Google")
    await vault.put(_vault_name(service), {**s, "token": token.strip()}, s["label"])
    return s["label"]


async def connected_list() -> list[dict]:
    out = []
    for name in KNOWN:
        if await connected(name):
            out.append({"service": name, "label": KNOWN[name]["label"], "paths": KNOWN[name]["paths"]})
    for info in await vault.list_prefix("svc:"):
        name = info["name"][4:]
        if name not in KNOWN:
            c = await config(name)
            out.append({"service": name, "label": c["label"], "paths": c.get("paths", "")})
    return out


def _trim(data) -> str:
    text = json.dumps(data, ensure_ascii=False)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + " …(truncated; ask for fewer items with pageSize/per_page)"


async def call(service: str, method: str, path: str, params: dict | None = None, body: dict | None = None):
    """-> parsed JSON. Raises on errors with a message an agent can act on."""
    s = await config(service)
    if not s:
        raise ValueError(f"unknown service '{service}'. Connected: {[c['service'] for c in await connected_list()]}")
    if not await connected(service):
        raise PermissionError(f"{s['label']} is not connected yet; the human must connect it first")
    base = s["base_url"].rstrip("/")
    url = base + "/" + path.lstrip("/")
    if urlparse(url).netloc != urlparse(base).netloc or ".." in path or "://" in path or path.startswith("//"):
        raise ValueError("path must stay on the service's own host")
    headers = {"Accept": "application/json", "User-Agent": "Banyan"}
    params = dict(params or {})
    if s["auth"] == "google":
        from . import google

        import asyncio
        headers["Authorization"] = "Bearer " + await asyncio.to_thread(google.access_token, await vault.get("google"))
    else:
        token = (await vault.get(_vault_name(service)))["token"]
        if s["auth"] == "header":
            headers[s.get("header") or "X-API-Key"] = token
        elif s["auth"] == "query":
            params[s.get("header") or "api_key"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, transport=_transport) as c:
        r = await c.request(method.upper(), url, params=params, json=body, headers=headers)
    if r.status_code >= 400:
        raise RuntimeError(f"{s['label']} answered {r.status_code}: {r.text[:300]}")
    try:
        return r.json()
    except ValueError:
        return {"text": r.text[:MAX_CHARS]}


def _due(cw: dict) -> str | None:
    d = cw.get("dueDate")
    return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}" if d and "year" in d else cw.get("due")


def _largest_list(data):
    """For an unknown API: the biggest list of objects anywhere in the response."""
    best: list = []
    stack = [data]
    while stack:
        x = stack.pop()
        if isinstance(x, list):
            if len(x) > len(best) and all(isinstance(i, dict) for i in x):
                best = x
            stack.extend(x)
        elif isinstance(x, dict):
            stack.extend(x.values())
    return best


async def snapshot(service: str, request: str | None = None) -> list[dict]:
    """Everything currently there, as [{id, kind, title, where, due, text}]. A watcher diffs two
    snapshots to find new items. Known services get a proper walk (Classroom: every active
    course's assignments and announcements); custom ones poll one GET path."""
    if service in ("google_classroom", "demo_classroom"):
        courses = (await call(service, "GET", "/v1/courses", {"courseStates": "ACTIVE", "pageSize": 15})).get("courses", [])
        items = []
        for c in courses[:10]:
            work = await call(service, "GET", f"/v1/courses/{c['id']}/courseWork", {"pageSize": 20})
            for w in work.get("courseWork", []):
                items.append({"id": f"cw:{w['id']}", "kind": "assignment", "title": w.get("title", ""),
                              "where": c.get("name", ""), "due": _due(w),
                              "text": (w.get("description") or "")[:300]})
            ann = await call(service, "GET", f"/v1/courses/{c['id']}/announcements", {"pageSize": 10})
            for a in ann.get("announcements", []):
                items.append({"id": f"an:{a['id']}", "kind": "announcement", "title": (a.get("text") or "")[:80],
                              "where": c.get("name", ""), "due": None, "text": (a.get("text") or "")[:300]})
        return items
    if service == "github":
        notes = await call(service, "GET", "/notifications", {"all": "false"})
        return [{"id": f"gh:{n['id']}", "kind": n.get("subject", {}).get("type", "notification"),
                 "title": n.get("subject", {}).get("title", ""), "where": n.get("repository", {}).get("full_name", ""),
                 "due": None, "text": n.get("reason", "")} for n in notes]
    if not request:
        raise ValueError("a custom service watcher needs a GET path to poll")
    rows = _largest_list(await call(service, "GET", request))
    out = []
    for r in rows[:200]:
        rid = r.get("id") or r.get("uuid") or r.get("key") or json.dumps(r, sort_keys=True)[:200]
        title = r.get("title") or r.get("name") or r.get("subject") or str(rid)
        out.append({"id": f"x:{rid}", "kind": "item", "title": str(title)[:120], "where": service, "due": None,
                    "text": json.dumps(r, ensure_ascii=False)[:300]})
    return out


async def call_text(service: str, method: str, path: str, params: dict | None = None, body: dict | None = None) -> str:
    return _trim(await call(service, method, path, params, body))
