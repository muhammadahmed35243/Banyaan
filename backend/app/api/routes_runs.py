from fastapi import APIRouter

from ..events import bus

router = APIRouter(prefix="/api/runs")


@router.get("/{run_id}/events")
def run_events(run_id: str, after: int = 0) -> dict:
    """Polling replacement for the WebSocket: pass the last seq you saw (0 = replay all)."""
    events = bus.since(run_id, after)
    return {"events": events, "cursor": events[-1]["seq"] if events else after}
