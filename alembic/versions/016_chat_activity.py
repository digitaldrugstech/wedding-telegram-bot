"""Add chat_activity table to track bot usage per chat.

Revision ID: 016
Revises: 015
"""

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"


def upgrade():
    op.create_table(
        "chat_activity",
        sa.Column("chat_id", sa.BigInteger, primary_key=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("chat_type", sa.String(20), nullable=False, server_default="group"),
        sa.Column("command_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("user_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("chat_activity")
