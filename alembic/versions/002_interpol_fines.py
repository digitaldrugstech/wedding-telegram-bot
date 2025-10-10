"""Add interpol_fines table

Revision ID: 002
Revises: 001
Create Date: 2025-10-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration is now a no-op since 000 already creates interpol_fines table
    # Kept for backward compatibility
    pass


def downgrade() -> None:
    pass
