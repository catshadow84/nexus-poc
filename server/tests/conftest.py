import itertools

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server import booking_service, devices, state
from server.booking_service import RESERVED
from server.db import Base
from server.models import Booking, Guest


@pytest_asyncio.fixture
async def session(tmp_path):
    """A fresh, empty SQLite database in a temp folder for every test."""
    db_file = (tmp_path / "test.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def published(monkeypatch):
    """Replace the MQTT bus with a fake that records what would have been sent."""
    sent = []

    async def fake_publish(topic, payload):
        sent.append((topic, payload))

    monkeypatch.setattr(booking_service.bus, "publish", fake_publish)
    state._stores.clear()
    devices._registries.clear()
    return sent


@pytest.fixture
def make_booking(session):
    """Returns a function that creates a guest plus a RESERVED booking."""
    counter = itertools.count(1)

    async def _make(room_id="room1", preferences=None):
        n = next(counter)
        guest = Guest(
            name=f"Guest {n}",
            email=f"guest{n}@example.com",
            preferences=preferences or {},
        )
        session.add(guest)
        await session.commit()
        booking = Booking(guest_id=guest.id, room_id=room_id, status=RESERVED)
        session.add(booking)
        await session.commit()
        return booking

    return _make