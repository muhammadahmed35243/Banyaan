from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import store
from ..events import bus
from ..models import Event
from ..orchestrator.runner import run_goal

router = APIRouter(prefix="/api")


class GoalIn(BaseModel):
    goal: str
    run_id: str  # chosen by the client so it can poll events while this request runs


@router.post("/goals")
async def create_goal(body: GoalIn) -> dict:
    """Runs the whole goal inside this request (serverless has no background tasks);
    the browser follows progress by polling /api/runs/{run_id}/events."""
    result = await run_goal(body.run_id, body.goal)
    return {"run_id": body.run_id, "result": result}


class ControlIn(BaseModel):
    action: str  # pause | resume | prune | redirect | inject
    text: str | None = None


@router.post("/agents/{agent_id}/control")
async def control_agent(agent_id: str, body: ControlIn) -> dict:
    row = await store.get_agent(agent_id)
    if not row:
        raise HTTPException(404, "unknown agent")
    if row.control == "prune":
        return {"ok": True, "note": "already pruned"}
    if body.action in ("redirect", "inject") and not body.text:
        raise HTTPException(400, "text required")

    if body.action == "prune":  # cancel the whole subtree
        agents = await store.run_agents(row.run_id)
        ids, frontier = {agent_id}, [agent_id]
        while frontier:
            cur = frontier.pop()
            for a in agents:
                if a.parent_id == cur and a.id not in ids:
                    ids.add(a.id)
                    frontier.append(a.id)
        for i in ids:
            await store.set_agent(i, control="prune")
    elif body.action == "pause":
        await store.set_agent(agent_id, control="pause")
    elif body.action == "resume":
        if row.control == "pause":
            await store.set_agent(agent_id, control="none")
    elif body.action in ("redirect", "inject"):
        await store.set_agent(agent_id, control=body.action, control_text=body.text)
    else:
        raise HTTPException(400, "unknown action")
    await bus.publish(Event(run_id=row.run_id, type="log", agent_id=agent_id,
                            payload={"message": f"Human: {body.action}"
                                     + (f" - {body.text}" if body.text else "")}))
    return {"ok": True}
