"""add room status and issues

Revision ID: d5b2f8a13c47
Revises: c4a1e7d92b30
Create Date: 2026-11-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b2f8a13c47'
down_revision: Union[str, Sequence[str], None] = 'c4a1e7d92b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('room_statuses',
    sa.Column('room_id', sa.String(), nullable=False),
    sa.Column('clean_state', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('updated_by', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('room_id')
    )
    op.create_table('room_issues',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('room_id', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('details', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('reported_by', sa.String(), nullable=True),
    sa.Column('updated_by', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('room_issues')
    op.drop_table('room_statuses')