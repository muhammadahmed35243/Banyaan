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
