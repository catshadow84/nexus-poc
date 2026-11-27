"""add price and door code to bookings

Revision ID: e6c3a9b14d58
Revises: d5b2f8a13c47
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6c3a9b14d58"
down_revision: Union[str, None] = "d5b2f8a13c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("total_cents", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column("bookings", sa.Column("door_pin", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("door_pin_id", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("door_pin_expires", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "door_pin_expires")
    op.drop_column("bookings", "door_pin_id")
    op.drop_column("bookings", "door_pin")
    op.drop_column("bookings", "currency")
    op.drop_column("bookings", "total_cents")
