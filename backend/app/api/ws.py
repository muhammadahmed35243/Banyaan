from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..events import bus

router = APIRouter()


@router.websocket("/ws/{run_id}")
async def run_ws(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    # Subscribe first, then read history, so no event falls in the gap.
    # Events present in both are de-duplicated by id.
    q = bus.subscribe(run_id)
    try:
        sent: set[str] = set()
        for ev in bus.history(run_id):
            sent.add(ev.id)
            await ws.send_text(ev.model_dump_json())
        while True:
            ev = await q.get()
            if ev.id in sent:
                continue
            await ws.send_text(ev.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(run_id, q)
