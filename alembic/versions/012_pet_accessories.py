"""Add pet accessories column.

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pets", sa.Column("accessories", sa.String(500), server_default="", nullable=False))


def downgrade():
    op.drop_column("pets", "accessories")
