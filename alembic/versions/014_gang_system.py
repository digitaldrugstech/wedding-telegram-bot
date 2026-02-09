"""Add gang/clan system.

Revision ID: 014
Revises: 013
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"


def upgrade():
    op.create_table(
        "gangs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(30), unique=True, nullable=False),
        sa.Column("leader_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("bank", sa.BigInteger, server_default="0", nullable=False),
        sa.Column("level", sa.Integer, server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "gang_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gang_id", sa.Integer, sa.ForeignKey("gangs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("role", sa.String(20), server_default="member", nullable=False),
        sa.Column("joined_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("gang_members")
    op.drop_table("gangs")
