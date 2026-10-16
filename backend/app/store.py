"""Async wrappers over the sync DB for agent state + approvals (run in threads so the
orchestrator's event loop is never blocked by network round-trips to Postgres)."""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, select

from .db import engine
from .models import AgentRow, ApprovalRow


def _run(fn, *a, **kw):
    return asyncio.to_thread(fn, *a, **kw)


def _upsert_agent(row: AgentRow) -> None:
    with Session(engine, expire_on_commit=False) as s:
        s.merge(row)
        s.commit()


def _get_agent(agent_id: str) -> AgentRow | None:
    with Session(engine, expire_on_commit=False) as s:
        return s.get(AgentRow, agent_id)


def _set_agent(agent_id: str, **fields) -> None:
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(AgentRow, agent_id)
        if row:
            for k, v in fields.items():
                setattr(row, k, v)
            s.add(row)
            s.commit()


def _run_agents(run_id: str) -> list[AgentRow]:
    with Session(engine, expire_on_commit=False) as s:
        return list(s.exec(select(AgentRow).where(AgentRow.run_id == run_id)).all())


def _create_approval(**fields) -> str:
    row = ApprovalRow(id=uuid.uuid4().hex[:12], **fields)
    with Session(engine, expire_on_commit=False) as s:
        s.add(row)
        s.commit()
    return row.id


def _get_approval(approval_id: str) -> ApprovalRow | None:
    with Session(engine, expire_on_commit=False) as s:
        return s.get(ApprovalRow, approval_id)


def _list_approvals(status: str | None, run_id: str | None) -> list[ApprovalRow]:
    with Session(engine, expire_on_commit=False) as s:
        q = select(ApprovalRow)
        if status:
            q = q.where(ApprovalRow.status == status)
        if run_id:
            q = q.where(ApprovalRow.run_id == run_id)
        return list(s.exec(q.order_by(ApprovalRow.created_at)).all())


def _decide(approval_id: str, status: str, note: str | None, edited: dict | None) -> ApprovalRow | None:
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(ApprovalRow, approval_id)
        if not row or row.status != "pending":
            return None
        row.status, row.note, row.edited_payload = status, note, edited
        row.decided_by, row.decided_at = "human", datetime.now(timezone.utc)
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


upsert_agent = lambda row: _run(_upsert_agent, row)  # noqa: E731
get_agent = lambda i: _run(_get_agent, i)  # noqa: E731
set_agent = lambda i, **f: _run(_set_agent, i, **f)  # noqa: E731
run_agents = lambda r: _run(_run_agents, r)  # noqa: E731
create_approval = lambda **f: _run(_create_approval, **f)  # noqa: E731
get_approval = lambda i: _run(_get_approval, i)  # noqa: E731
list_approvals = lambda s=None, r=None: _run(_list_approvals, s, r)  # noqa: E731
decide = lambda i, st, note=None, edited=None: _run(_decide, i, st, note, edited)  # noqa: E731


# ---------- generated tools ----------
from .models import ToolRow  # noqa: E402


def _save_tool(row: ToolRow) -> None:
    with Session(engine, expire_on_commit=False) as s:
        old = s.get(ToolRow, row.name)
        if old:
            row.version = old.version + 1
            row.usage_count = old.usage_count
        s.merge(row)
        s.commit()


def _list_tools(only_active: bool) -> list[ToolRow]:
    with Session(engine, expire_on_commit=False) as s:
        q = select(ToolRow)
        if only_active:
            q = q.where(ToolRow.status == "active")
        return list(s.exec(q.order_by(ToolRow.created_at)).all())


def _get_tool(name: str) -> ToolRow | None:
    with Session(engine, expire_on_commit=False) as s:
        return s.get(ToolRow, name)


def _bump_usage(name: str) -> None:
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(ToolRow, name)
        if row:
            row.usage_count += 1
            s.add(row)
            s.commit()


def _set_tool_status(name: str, status: str) -> bool:
    with Session(engine, expire_on_commit=False) as s:
        row = s.get(ToolRow, name)
        if not row:
            return False
        row.status = status
        s.add(row)
        s.commit()
        return True


save_tool = lambda r: _run(_save_tool, r)  # noqa: E731
list_tools = lambda only_active=True: _run(_list_tools, only_active)  # noqa: E731
get_tool = lambda n: _run(_get_tool, n)  # noqa: E731
bump_usage = lambda n: _run(_bump_usage, n)  # noqa: E731
set_tool_status = lambda n, s: _run(_set_tool_status, n, s)  # noqa: E731
