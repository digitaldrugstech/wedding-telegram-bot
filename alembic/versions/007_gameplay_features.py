"""gameplay features

Revision ID: 007
Revises: 006
Create Date: 2025-01-21

Adds gameplay features: quests, pets, duels, mining, wheel of fortune.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create quests table
    op.create_table(
        "quests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quest_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.CheckConstraint("quest_type IN ('work', 'casino', 'transfer', 'marriage', 'pet')", name="quests_type_check"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create user_quests table
    op.create_table(
        "user_quests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("quest_id", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quest_id"], ["quests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "quest_id", name="uq_user_quest"),
    )

    # Create pets table
    op.create_table(
        "pets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pet_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("hunger", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("happiness", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("last_fed_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_played_at", sa.DateTime(), nullable=True),
        sa.Column("is_alive", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("pet_type IN ('cat', 'dog', 'dragon')", name="pets_type_check"),
        sa.CheckConstraint("hunger BETWEEN 0 AND 100", name="pets_hunger_check"),
        sa.CheckConstraint("happiness BETWEEN 0 AND 100", name="pets_happiness_check"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="pets_user_id_key"),
    )

    # Create duels table
    op.create_table(
        "duels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenger_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_id", sa.BigInteger(), nullable=False),
        sa.Column("bet_amount", sa.BigInteger(), nullable=False),
        sa.Column("winner_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["challenger_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opponent_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["winner_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("duels")
    op.drop_table("pets")
    op.drop_table("user_quests")
    op.drop_table("quests")
