import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel

EventType = Literal[
    "run_started", "run_finished",
    "agent_spawned", "agent_status", "agent_thought", "agent_finished", "agent_failed",
    "tool_call", "tool_result",
    "needs_human", "human_decision",
    "toolsmith_stage",
    "tool_loaded", "tool_unloaded",
    "secret_requested", "secret_used",
    "budget_warning", "speak",
    "system_flow",
    "alert", "watch_started", "watch_stopped", "bill_tracked", "notified",
    "memory_updated", "flow_updated",
    "log",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    type: EventType
    agent_id: str | None = None
    parent_id: str | None = None
    ts: datetime = Field(default_factory=_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventRow(SQLModel, table=True):
    __tablename__ = "events"

    seq: int | None = SQLField(default=None, primary_key=True)  # insertion order for replay
    id: str = SQLField(unique=True, index=True)
    run_id: str = SQLField(index=True)
    type: str
    agent_id: str | None = None
    parent_id: str | None = None
    ts: datetime
    payload: dict = SQLField(default_factory=dict, sa_column=Column(JSON))


class AgentRow(SQLModel, table=True):
    """Live control state for an agent node. Serverless instances share no memory, so the
    orchestrator and the control API talk through this table."""

    __tablename__ = "agents"

    id: str = SQLField(primary_key=True)  # globally unique (run-prefixed)
    run_id: str = SQLField(index=True)
    parent_id: str | None = None
    depth: int = 0
    role: str = "worker"
    goal: str = ""
    status: str = "queued"
    control: str = "none"  # none | pause | prune | redirect
    control_text: str | None = None  # new goal for redirect, or injected note
    tokens_used: int = 0


class ApprovalRow(SQLModel, table=True):
    __tablename__ = "approvals"

    id: str = SQLField(primary_key=True)
    run_id: str = SQLField(index=True)
    agent_id: str | None = None
    kind: str  # new_tool | secret_access | risky_action | low_confidence | budget
    title: str
    details: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    risk: str = "low"
    status: str = "pending"  # pending | approved | rejected | edited
    decided_by: str | None = None
    decided_at: datetime | None = None
    note: str | None = None
    edited_payload: dict | None = SQLField(default=None, sa_column=Column(JSON))
    created_at: datetime = SQLField(default_factory=_now)


class ToolRow(SQLModel, table=True):
    """A human-approved generated tool. Code lives in the DB (serverless has no durable disk);
    the sandbox materialises it to a temp file per call. The table is the source of truth
    for 'which tools exist', so a newly approved tool is live on every instance at once."""

    __tablename__ = "tools"

    name: str = SQLField(primary_key=True)
    version: int = 1
    description: str = ""
    input_schema: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    secrets_required: list = SQLField(default_factory=list, sa_column=Column(JSON))
    allowed_domains: list = SQLField(default_factory=list, sa_column=Column(JSON))
    risk_level: str = "low"
    status: str = "active"  # active | rejected | disabled
    approved_by: str | None = None
    approved_at: datetime | None = None
    composed_from: list = SQLField(default_factory=list, sa_column=Column(JSON))
    usage_count: int = 0
    code: str = ""
    tests: dict = SQLField(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = SQLField(default_factory=_now)


class SessionRun(SQLModel, table=True):
    """A session is one mission-control screen: many goals (runs) side by side."""

    __tablename__ = "session_runs"

    run_id: str = SQLField(primary_key=True)
    session_id: str = SQLField(index=True)
    goal: str = ""
    created_at: datetime = SQLField(default_factory=_now)


class SecretRow(SQLModel, table=True):
    """The vault. Values are encrypted at rest and never placed in events, approvals or
    prompts; only connectors on the server decrypt them."""

    __tablename__ = "secrets"

    name: str = SQLField(primary_key=True)  # e.g. "gmail"
    ciphertext: str
    label: str = ""  # non-secret description shown in the UI (e.g. the email address)
    use_count: int = 0
    last_used_at: datetime | None = None
    created_at: datetime = SQLField(default_factory=_now)


class WatchRow(SQLModel, table=True):
    """A standing agent: a rule that keeps running after its goal's request has ended.
    Serverless cannot keep a process alive, so each check is a short 'tick' request."""

    __tablename__ = "watches"

    id: str = SQLField(primary_key=True)
    session_id: str = SQLField(index=True)
    run_id: str
    agent_id: str  # the watcher node in the tree
    source: str = "email"
    condition: str = ""  # natural-language rule, e.g. "related to a payment"
    credential: str = "gmail"
    forward_to: str | None = None  # also email each alert here (consented on the setup card)
    service: str | None = None  # source "service": which connected service it polls (e.g. google_classroom)
    request: str | None = None  # for a custom service: the GET path to poll
    seen: list | None = SQLField(default=None, sa_column=Column(JSON))  # ids already reported
    interval_sec: int | None = None  # per-watch check interval (APIs are polled less often than mail)
    cursor: int = 0  # last email id / IMAP UID already examined
    status: str = "active"  # active | paused | stopped
    checks: int = 0
    alerts: int = 0
    last_tick_at: datetime | None = None
    created_at: datetime = SQLField(default_factory=_now)


class BillRow(SQLModel, table=True):
    """The bills tracker a watcher fills, one human-approved entry at a time."""

    __tablename__ = "bills"

    id: str = SQLField(primary_key=True)
    session_id: str = SQLField(index=True)
    payee: str = ""
    amount: str = ""
    due_date: str | None = None
    status: str = "due"  # due | paid
    source_subject: str = ""
    created_at: datetime = SQLField(default_factory=_now)


class DemoEmail(SQLModel, table=True):
    """The demo inbox, so a watcher can be shown live without a real mailbox."""

    __tablename__ = "demo_emails"

    id: int | None = SQLField(default=None, primary_key=True)
    sender: str
    subject: str
    body: str = ""
    created_at: datetime = SQLField(default_factory=_now)


class SessionMemory(SQLModel, table=True):
    """Durable facts the user told Banyan in a session ("my budget is 15k", "my email is ..."),
    shown to every later goal of that session. The human can delete any of them."""

    __tablename__ = "session_memory"

    session_id: str = SQLField(primary_key=True)
    facts: list = SQLField(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime = SQLField(default_factory=_now)


class DemoCoursework(SQLModel, table=True):
    """Extra items in the built-in demo Classroom ("Simulate" adds them during a presentation)."""

    __tablename__ = "demo_coursework"

    id: int | None = SQLField(default=None, primary_key=True)
    course_id: str
    kind: str = "assignment"  # assignment | announcement
    title: str
    text: str = ""
    due: str | None = None  # YYYY-MM-DD
    created_at: datetime = SQLField(default_factory=_now)
