"""Sessions (many goals side by side), watcher ticks, the vault and the demo inbox."""
import asyncio

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import store, vault, watchers
from ..config import settings
from ..db import engine
from ..events import bus
from ..models import BillRow, DemoEmail, SessionRun, WatchRow

router = APIRouter(prefix="/api")


def _link(session_id: str, run_id: str, goal: str) -> None:
    with Session(engine) as s:
        if not s.get(SessionRun, run_id):
            s.add(SessionRun(run_id=run_id, session_id=session_id, goal=goal))
            s.commit()


async def link_run(session_id: str | None, run_id: str, goal: str) -> None:
    if session_id:
        await asyncio.to_thread(_link, session_id, run_id, goal)


def _sessions(limit: int) -> list[dict]:
    from sqlalchemy import func

    from ..models import AgentRow, ApprovalRow

    with Session(engine) as s:
        rows = s.exec(select(SessionRun.session_id, func.count(), func.min(SessionRun.created_at),
                             func.max(SessionRun.created_at))
                      .group_by(SessionRun.session_id)
                      .order_by(func.max(SessionRun.created_at).desc()).limit(limit)).all()
        ids = [r[0] for r in rows]
        if not ids:
            return []
        runs = s.exec(select(SessionRun).where(SessionRun.session_id.in_(ids))
                      .order_by(SessionRun.created_at)).all()
        session_of = {r.run_id: r.session_id for r in runs}
        goals: dict[str, list[str]] = {}
        for r in runs:
            goals.setdefault(r.session_id, []).append(r.goal)
        agents: dict[str, int] = {}
        for run_id, n in s.exec(select(AgentRow.run_id, func.count()).where(AgentRow.run_id.in_(session_of))
                                .group_by(AgentRow.run_id)).all():
            agents[session_of[run_id]] = agents.get(session_of[run_id], 0) + n
        pending: dict[str, int] = {}
        for run_id in s.exec(select(ApprovalRow.run_id).where(ApprovalRow.run_id.in_(session_of),
                                                                ApprovalRow.status == "pending")).all():
            pending[session_of[run_id]] = pending.get(session_of[run_id], 0) + 1
        watching: dict[str, int] = {}
        for sid in s.exec(select(WatchRow.session_id).where(WatchRow.session_id.in_(ids),
                                                               WatchRow.status == "active")).all():
            watching[sid] = watching.get(sid, 0) + 1
    return [{"id": sid, "goals": n, "first_goal": goals[sid][0], "last_goal": goals[sid][-1],
             "recent_goals": goals[sid][-3:], "agents": agents.get(sid, 0), "pending": pending.get(sid, 0),
             "watching": watching.get(sid, 0), "started_at": first.isoformat(), "last_at": last.isoformat()}
            for sid, n, first, last in rows]


@router.get("/sessions")
async def list_sessions(limit: int = 60) -> list[dict]:
    """Every session, most recent first, with a short summary for the sessions page."""
    return await asyncio.to_thread(_sessions, min(limit, 200))


@router.get("/sessions/{session_id}/memory")
async def get_memory(session_id: str) -> dict:
    from .. import memory

    return {"facts": await memory.facts(session_id)}


@router.delete("/sessions/{session_id}/memory/{index}")
async def forget_fact(session_id: str, index: int) -> dict:
    """The human can delete anything Banyan remembered."""
    from .. import memory

    return {"facts": await memory.forget(session_id, index)}


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, after: int = 0) -> dict:
    events = await asyncio.to_thread(bus.since_session, session_id, after)
    return {"events": events, "cursor": events[-1]["seq"] if events else after}


@router.post("/sessions/{session_id}/tick")
async def tick(session_id: str) -> dict:
    """Wake this session's watchers. Called by the open browser every few seconds (a cron
    job could call it too); each watcher checks at most once per WATCH_INTERVAL_SEC."""
    return await watchers.tick(session_id)


@router.api_route("/watches/tick_all", methods=["GET", "POST"])
async def tick_all(authorization: str | None = Header(default=None)) -> dict:
    """Wake every watcher, even with no browser open. Called by Vercel Cron (GET, sends
    'Authorization: Bearer $CRON_SECRET') and by the GitHub Actions schedule."""
    if not settings.cron_secret or authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(401, "bad or missing cron secret")
    return await watchers.tick(None)


def _bills(session_id: str) -> list[BillRow]:
    with Session(engine) as s:
        return list(s.exec(select(BillRow).where(BillRow.session_id == session_id)
                           .order_by(BillRow.created_at)).all())


@router.get("/sessions/{session_id}/bills")
async def list_bills(session_id: str) -> list[dict]:
    return [b.model_dump(mode="json") for b in await asyncio.to_thread(_bills, session_id)]


def _watches(session_id: str) -> list[WatchRow]:
    with Session(engine) as s:
        return list(s.exec(select(WatchRow).where(WatchRow.session_id == session_id)).all())


@router.get("/sessions/{session_id}/watches")
async def list_watches(session_id: str) -> list[dict]:
    return [w.model_dump(mode="json", exclude={"cursor"}) for w in await asyncio.to_thread(_watches, session_id)]


# ---------- vault ----------


class CredentialIn(BaseModel):
    mode: str  # "google" (after Sign in with Google) | "imap" (app password) | "demo"
    email: str | None = None
    app_password: str | None = None
    host: str | None = None
    ntfy_topic: str | None = None  # optional phone push channel


async def _save_ntfy(topic: str | None) -> None:
    if topic and topic.strip():
        await vault.put("notify", {"ntfy_topic": topic.strip()}, "ntfy phone push")


class NotifyIn(BaseModel):
    ntfy_topic: str


@router.post("/vault/notify")
async def set_notify(body: NotifyIn) -> dict:
    await _save_ntfy(body.ntfy_topic)
    return {"ok": True}


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
    elif body.mode == "google":  # reuse an existing "Sign in with Google"
        g = await vault.info("google")
        if not g:
            raise HTTPException(400, "sign in with Google first")
        await vault.put(name, {"mode": "google"}, f"Gmail: {g['label']}")
    elif body.mode == "imap":
        if not body.email or not body.app_password:
            raise HTTPException(400, "email and app password are required")
        secret = {"mode": "imap", "email": body.email.strip(),
                  "app_password": body.app_password.replace(" ", ""), "host": body.host or "imap.gmail.com"}
        await vault.put(name, secret, body.email.strip())
    else:
        raise HTTPException(400, "mode must be google, imap or demo")
    await _save_ntfy(body.ntfy_topic)
    row = await store.decide(approval_id, "approved", "credential provided", None)
    if not row:
        raise HTTPException(409, "already decided")
    await watchers.resume_setup(row)  # in case the goal's request already timed out
    return {"ok": True, "stored": name}


@router.get("/vault")
async def vault_list() -> list[dict]:
    """Names and labels only. Values never leave the server."""
    out = []
    for n in ("gmail", "google", "notify"):
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


# ---------- demo Classroom (a stand-in school account for presentations) ----------

DEMO_COURSES = [
    {"id": "c101", "name": "Data Structures (CS-201)", "section": "Fall 2026", "teacher": "Dr. Ayesha Khan"},
    {"id": "c102", "name": "Linear Algebra (MTH-231)", "section": "Fall 2026", "teacher": "Prof. Usman Ali"},
    {"id": "c103", "name": "Technical Writing (ENG-210)", "section": "Fall 2026", "teacher": "Ms. Sara Malik"},
]
# (course, title, description, due in N days)
DEMO_WORK = [
    ("c101", "Assignment 3: Binary Search Trees",
     "In Python, implement a BST class with insert(key), delete(key) (handle all three cases: leaf, one child, "
     "two children using the in-order successor) and inorder() returning a list. Then: (a) insert 50, 30, 70, "
     "20, 40, 60, 80 and give the in-order output; (b) delete 30 and give the in-order output again; "
     "(c) state the worst-case time of each operation and when it happens.", 3),
    ("c101", "Quiz 2: Hashing", "Online quiz, 20 minutes, open at 10am.", 6),
    ("c102", "Problem Set 4: Eigenvalues",
     "Show all steps. 1) Find the eigenvalues and eigenvectors of A = [[2, 0], [1, 3]]. "
     "2) Find the characteristic polynomial of B = [[1, 2], [2, 1]] and its eigenvalues. "
     "3) Prove that a square matrix and its transpose have the same eigenvalues.", 2),
    ("c103", "Essay draft: Technology and Society",
     "Write a 600-word argumentative essay: 'Should universities allow students to use AI assistants for "
     "coursework?' Take a clear position, give two arguments and one counter-argument, APA style.", 9),
]
DEMO_ANN = [
    ("c101", "Lab moved to Room 4 this Thursday."),
    ("c102", "Midterm syllabus: chapters 1-5. Past papers are on the drive."),
]
PS5 = ("Answer all questions and show every step. "
       "1) Diagonalize A = [[4, 1], [2, 3]]: find P and D with A = P D P^-1. "
       "2) Is B = [[1, 1], [0, 1]] diagonalizable? Justify. "
       "3) Using your answer to 1, compute A^5. "
       "4) Show that if A is diagonalizable and invertible, then A^-1 is diagonalizable.")
DEMO_PRESETS = {
    "assignment": ("c102", "assignment", "Problem Set 5: Diagonalization", PS5, 4),
    "announcement": ("c101", "announcement", "Class cancelled tomorrow; recorded lecture uploaded.", "", None),
    "quiz": ("c103", "assignment", "Quiz 1: Citations and referencing", "15 MCQs, opens Friday 9am.", 1),
}


def _due_obj(days: int | None) -> dict | None:
    if days is None:
        return None
    from datetime import date, timedelta

    d = date.today() + timedelta(days=days)
    return {"year": d.year, "month": d.month, "day": d.day}


def _demo_extras(course_id: str, kind: str) -> list:
    from ..models import DemoCoursework

    with Session(engine) as s:
        return list(s.exec(select(DemoCoursework).where(DemoCoursework.course_id == course_id,
                                                        DemoCoursework.kind == kind)).all())


def _demo_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")


@router.get("/demo/classroom/v1/courses")
async def demo_courses(authorization: str | None = Header(default=None)) -> dict:
    _demo_auth(authorization)
    return {"courses": [{**c, "courseState": "ACTIVE"} for c in DEMO_COURSES]}


@router.get("/demo/classroom/v1/courses/{course_id}/courseWork")
async def demo_coursework(course_id: str, authorization: str | None = Header(default=None)) -> dict:
    _demo_auth(authorization)
    base = [{"id": f"{course_id}-w{i}", "title": t, "description": d, "dueDate": _due_obj(n), "state": "PUBLISHED",
             "workType": "ASSIGNMENT"} for i, (c, t, d, n) in enumerate(DEMO_WORK) if c == course_id]
    extra = [{"id": f"x{e.id}", "title": e.title, "description": e.text,
              "dueDate": {"year": int(e.due[:4]), "month": int(e.due[5:7]), "day": int(e.due[8:10])} if e.due else None,
              "state": "PUBLISHED", "workType": "ASSIGNMENT"}
             for e in await asyncio.to_thread(_demo_extras, course_id, "assignment")]
    return {"courseWork": extra[::-1] + base}


@router.get("/demo/classroom/v1/courses/{course_id}/announcements")
async def demo_announcements(course_id: str, authorization: str | None = Header(default=None)) -> dict:
    _demo_auth(authorization)
    base = [{"id": f"{course_id}-a{i}", "text": t} for i, (c, t) in enumerate(DEMO_ANN) if c == course_id]
    extra = [{"id": f"x{e.id}", "text": e.title}
             for e in await asyncio.to_thread(_demo_extras, course_id, "announcement")]
    return {"announcements": extra[::-1] + base}


class DemoClassIn(BaseModel):
    preset: str = "assignment"


@router.post("/demo/classroom/simulate")
async def demo_classroom_simulate(body: DemoClassIn) -> dict:
    """Post a new item to the demo Classroom, as a teacher would (for presentations)."""
    from datetime import date, timedelta

    from ..models import DemoCoursework

    if body.preset not in DEMO_PRESETS:
        raise HTTPException(400, f"preset must be one of {list(DEMO_PRESETS)}")
    course, kind, title, text, days = DEMO_PRESETS[body.preset]
    due = (date.today() + timedelta(days=days)).isoformat() if days is not None else None

    def add() -> int:
        with Session(engine, expire_on_commit=False) as s:
            row = DemoCoursework(course_id=course, kind=kind, title=title, text=text, due=due)
            s.add(row)
            s.commit()
            return row.id

    return {"id": await asyncio.to_thread(add), "title": title}


class ServiceCredIn(BaseModel):
    token: str | None = None
    use_demo: bool = False  # Classroom only: use the built-in demo Classroom instead
    base_url: str | None = None  # custom services
    auth: str | None = None  # bearer | header | query
    header: str | None = None  # header (or query param) name for 'header' / 'query' auth
    label: str | None = None


@router.post("/approvals/{approval_id}/service_credential")
async def provide_service_credential(approval_id: str, body: ServiceCredIn) -> dict:
    """The human answers a connect_service card. The token goes straight into the vault."""
    from ..connectors import services

    a = await store.get_approval(approval_id)
    if not a or a.kind != "connect_service":
        raise HTTPException(404, "unknown connection request")
    if a.status != "pending":
        raise HTTPException(409, "already decided")
    service = a.details.get("service", "")
    if body.use_demo:
        await services.connect("demo_classroom", "demo")
        chosen = "demo_classroom"
    else:
        if not body.token:
            raise HTTPException(400, "a token is required")
        try:
            await services.connect(service, body.token, body.label or a.details.get("label"),
                                   body.base_url or a.details.get("base_url"), body.auth or a.details.get("auth"),
                                   body.header)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        chosen = service
    row = await store.decide(approval_id, "edited" if chosen != service else "approved", "credential provided",
                             {"service": chosen} if chosen != service else None)
    if not row:
        raise HTTPException(409, "already decided")
    return {"ok": True, "service": chosen}
