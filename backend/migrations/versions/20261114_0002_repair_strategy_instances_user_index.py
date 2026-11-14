"""repair strategy_instances.user_id index

Databases adopted at the baseline (made by create_all before Alembic) may lack this
index: the dev DB lost it when strategy_instances was rebuilt to make the risk columns
nullable (2026-07-11). Fresh databases already have it from 0001, so create only if
missing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""
from __future__ import annotations

from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_strategy_instances_user_id', 'strategy_instances', ['user_id'],
        unique=False, if_not_exists=True,
    )


def downgrade() -> None:
    pass   # 0001 owns this index; a downgrade to 0001 must keep it.
