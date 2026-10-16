from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import store

router = APIRouter(prefix="/api/approvals")


def _out(a) -> dict:
    return {"id": a.id, "run_id": a.run_id, "agent_id": a.agent_id, "kind": a.kind, "title": a.title,
            "details": a.details, "risk": a.risk, "status": a.status, "note": a.note,
            "created_at": a.created_at.isoformat()}


@router.get("")
async def list_approvals(status: str | None = None, run_id: str | None = None) -> list[dict]:
    return [_out(a) for a in await store.list_approvals(status, run_id)]


class DecideIn(BaseModel):
    decision: str  # approved | rejected | edited
    note: str | None = None
    confirm: bool = False  # high-risk approvals need an explicit UI click
    edited_payload: dict | None = None


@router.post("/{approval_id}/decide")
async def decide(approval_id: str, body: DecideIn) -> dict:
    if body.decision not in ("approved", "rejected", "edited"):
        raise HTTPException(400, "decision must be approved, rejected or edited")
    if body.decision == "rejected" and not body.note:
        raise HTTPException(400, "a note is required when rejecting")
    current = await store.get_approval(approval_id)
    if not current:
        raise HTTPException(404, "unknown approval")
    if current.risk == "high" and body.decision != "rejected" and not body.confirm:
        raise HTTPException(400, "high-risk approvals require confirm=true from a UI click")
    row = await store.decide(approval_id, body.decision, body.note, body.edited_payload)
    if not row:
        raise HTTPException(409, "already decided")
    return _out(row)
