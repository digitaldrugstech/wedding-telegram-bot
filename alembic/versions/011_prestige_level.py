"""Add prestige_level column to users.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"


def upgrade():
    op.add_column("users", sa.Column("prestige_level", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "prestige_level")
