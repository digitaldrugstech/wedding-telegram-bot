"""Add business upgrade levels and investment bank.

Revision ID: 018
Revises: 017
"""

import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"


def upgrade():
    # Business upgrade level (1-3)
    op.add_column("businesses", sa.Column("upgrade_level", sa.Integer, server_default="1", nullable=False))

    # Investment bank deposits
    op.create_table(
        "bank_deposits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("deposited_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("last_interest_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("withdrawn_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_bank_deposits_user_active", "bank_deposits", ["user_id", "is_active"])


def downgrade():
    op.drop_index("ix_bank_deposits_user_active")
    op.drop_table("bank_deposits")
    op.drop_column("businesses", "upgrade_level")
