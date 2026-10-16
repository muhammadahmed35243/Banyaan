import asyncio

from . import store
from .events import bus
from .models import ApprovalRow, Event


class Pruned(Exception):
    """Raised inside a branch whose node was pruned by a human."""


async def request(run_id: str, agent_id: str | None, kind: str, title: str,
                  details: dict, risk: str = "low", poll_s: float = 1.0) -> ApprovalRow:
    """Create a pending approval and wait for a human decision. Only the calling branch
    blocks. State lives in the DB (not an in-memory Future) so the decision can arrive
    on a different serverless instance."""
    approval_id = await store.create_approval(
        run_id=run_id, agent_id=agent_id, kind=kind, title=title, details=details, risk=risk)
    await bus.publish(Event(run_id=run_id, type="needs_human", agent_id=agent_id,
                            payload={"approval_id": approval_id, "kind": kind, "title": title,
                                     "risk": risk, "details": details}))
    while True:
        row = await store.get_approval(approval_id)
        if row and row.status != "pending":
            await bus.publish(Event(run_id=run_id, type="human_decision", agent_id=agent_id,
                                    payload={"approval_id": approval_id, "decision": row.status,
                                             "note": row.note}))
            return row
        if agent_id:
            node = await store.get_agent(agent_id)
            if node and node.control == "prune":
                raise Pruned()
        await asyncio.sleep(poll_s)
