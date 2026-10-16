import asyncio
from collections import defaultdict

from sqlmodel import Session, select

from .db import engine
from .models import Event, EventRow


class EventBus:
    """Persist every event, then fan it out to live subscribers of that run."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)

    async def publish(self, event: Event) -> None:
        with Session(engine) as s:
            s.add(EventRow(**event.model_dump()))
            s.commit()
        for q in list(self._subs[event.run_id]):
            q.put_nowait(event)

    def history(self, run_id: str) -> list[Event]:
        with Session(engine) as s:
            rows = s.exec(
                select(EventRow).where(EventRow.run_id == run_id).order_by(EventRow.seq)
            ).all()
        return [Event(**r.model_dump(exclude={"seq"})) for r in rows]

    def subscribe(self, run_id: str) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue[Event]) -> None:
        self._subs[run_id].discard(q)


bus = EventBus()
