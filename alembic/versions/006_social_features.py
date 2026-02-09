"""social features

Revision ID: 006
Revises: 005
Create Date: 2025-01-21

Adds social features: friendships, reputation, achievements, rating.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add reputation field to users table
    op.add_column("users", sa.Column("reputation", sa.Integer(), nullable=False, server_default="0"))

    # Create friendships table
    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user1_id", sa.BigInteger(), nullable=False),
        sa.Column("user2_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'accepted')", name="friendships_status_check"),
        sa.ForeignKeyConstraint(["user1_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user2_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user1_id", "user2_id", name="uq_friendship"),
    )

    # Create reputation_logs table
    op.create_table(
        "reputation_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.BigInteger(), nullable=False),
        sa.Column("to_user_id", sa.BigInteger(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("value IN (-1, 1)", name="reputation_logs_value_check"),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create achievements table
    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("emoji", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="achievements_code_key"),
    )

    # Create user_achievements table
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("achievement_id", sa.Integer(), nullable=False),
        sa.Column("earned_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["achievement_id"], ["achievements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("reputation_logs")
    op.drop_table("friendships")

    # Drop column from users
    op.drop_column("users", "reputation")
