"""Add titles and shop columns to users.

Revision ID: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"


def upgrade():
    op.add_column("users", sa.Column("active_title", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("purchased_titles", sa.String(1000), nullable=False, server_default=""))


def downgrade():
    op.drop_column("users", "purchased_titles")
    op.drop_column("users", "active_title")
