from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="guest")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), nullable=False)
    room_id: Mapped[str] = mapped_column(String, default="room1")
    status: Mapped[str] = mapped_column(String, default="RESERVED")

    planned_check_in: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_check_in: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guest: Mapped[Guest] = relationship(back_populates="bookings")