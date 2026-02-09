"""Expand quest types to include fish, duel, rob, bounty, gang, daily.

Revision ID: 015
Revises: 014
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"


def upgrade():
    # Find and drop ALL check constraints on quests table related to type
    # Constraint names vary: could be "quests_quest_type_check", "quests_type_check", etc.
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'quests'::regclass AND contype = 'c' AND conname LIKE '%type%'"
        )
    )
    for row in result:
        op.drop_constraint(row[0], "quests", type_="check")

    # Add new constraint with expanded types
    op.create_check_constraint(
        "quests_quest_type_check",
        "quests",
        "quest_type IN ('work', 'casino', 'transfer', 'marriage', 'pet', 'fish', 'duel', 'rob', 'bounty', 'gang', 'daily')",
    )


def downgrade():
    op.drop_constraint("quests_quest_type_check", "quests", type_="check")
    op.create_check_constraint(
        "quests_quest_type_check",
        "quests",
        "quest_type IN ('work', 'casino', 'transfer', 'marriage', 'pet')",
    )
