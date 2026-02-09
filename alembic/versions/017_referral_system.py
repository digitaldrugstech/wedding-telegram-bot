"""Add referral system for viral growth.

Revision ID: 017
Revises: 016
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"


def upgrade():
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("referrer_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "referred_id",
            sa.BigInteger,
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("referred_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("active_days", sa.Integer, server_default="0", nullable=False),
        sa.Column("last_active_date", sa.String(10), nullable=True),
        sa.Column("reward_given", sa.Boolean, server_default="false", nullable=False),
        sa.Column("reward_given_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])


def downgrade():
    op.drop_index("ix_referrals_referrer_id")
    op.drop_table("referrals")
