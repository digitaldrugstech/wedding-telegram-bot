"""economy features

Revision ID: 005
Revises: 004
Create Date: 2025-01-21

Adds economy features: loans, transfers, rob, daily rewards, lottery.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add daily reward fields to users table
    op.add_column("users", sa.Column("daily_streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_daily_at", sa.DateTime(), nullable=True))

    # Create loans table
    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("interest_rate", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("penalty_charged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create lotteries table
    op.create_table(
        "lotteries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("jackpot", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("winner_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["winner_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create lottery_tickets table
    op.create_table(
        "lottery_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lottery_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purchased_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lottery_id"], ["lotteries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("lottery_tickets")
    op.drop_table("lotteries")
    op.drop_table("loans")

    # Drop columns from users
    op.drop_column("users", "last_daily_at")
    op.drop_column("users", "daily_streak")
