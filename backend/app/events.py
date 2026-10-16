import asyncio

from sqlmodel import Session, select

from .db import engine
from .models import Event, EventRow


class EventBus:
    """Persist every event. Clients read them back by polling with a sequence cursor.

    Vercel functions are stateless and cannot hold WebSockets, so the database is
    the only shared channel between whoever emits events and whoever reads them.
    """

    @staticmethod
    def _insert(event: Event) -> None:
        with Session(engine) as s:
            s.add(EventRow(**event.model_dump()))
            s.commit()

    async def publish(self, event: Event) -> None:
        # Off the event loop: a DB round-trip must never stall other agents.
        await asyncio.to_thread(self._insert, event)

    def since(self, run_id: str, after: int = 0) -> list[dict]:
        """Events with seq > after, oldest first. Each carries its `seq` cursor."""
        with Session(engine) as s:
            rows = s.exec(
                select(EventRow)
                .where(EventRow.run_id == run_id, EventRow.seq > after)
                .order_by(EventRow.seq)
            ).all()
        return [Event(**r.model_dump(exclude={"seq"})).model_dump(mode="json") | {"seq": r.seq} for r in rows]


bus = EventBus()
