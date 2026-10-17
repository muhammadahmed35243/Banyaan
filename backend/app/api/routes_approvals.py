from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import store, vault, watchers

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
    if current.details.get("blocked") and body.decision != "rejected":
        raise HTTPException(400, "this build was blocked by the security checks and can only be rejected")
    if current.kind == "watch_setup" and body.decision != "rejected" and not await vault.info(current.details.get("credential", "gmail")):
        raise HTTPException(400, "provide a credential (or choose the demo inbox) to approve this")
    if current.kind == "connect_service" and body.decision != "rejected":
        from ..connectors import services

        if not await services.connected(current.details.get("service", "")):
            raise HTTPException(400, "connect the service first (sign in, or paste a token)")
    if current.kind == "connect_google" and body.decision != "rejected" and not await vault.info("google"):
        raise HTTPException(400, "sign in with Google first")
    if current.risk == "high" and body.decision != "rejected" and not body.confirm:
        raise HTTPException(400, "high-risk approvals require confirm=true from a UI click")
    row = await store.decide(approval_id, body.decision, body.note, body.edited_payload)
    if not row:
        raise HTTPException(409, "already decided")
    if row.kind == "watch_action":  # nobody is waiting on this one: run the approved action now
        await watchers.execute_action(row)
    if row.kind == "flow_edit":  # also non-blocking: apply the approved change now
        await watchers.apply_flow_edit(row)
    if row.kind == "watch_setup":  # finish it here too, in case the goal's request timed out
        await watchers.resume_setup(row)
    return _out(row)
