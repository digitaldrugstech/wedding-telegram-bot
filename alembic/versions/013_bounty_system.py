"""Add bounty system.

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"


def upgrade():
    op.create_table(
        "bounties",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("placer_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("collected_by_id", sa.BigInteger, sa.ForeignKey("users.telegram_id"), nullable=True),
        sa.Column("collected_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_bounties_target_active", "bounties", ["target_id", "is_active"])


def downgrade():
    op.drop_index("ix_bounties_target_active", table_name="bounties")
    op.drop_table("bounties")
