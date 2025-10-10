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
    op.create_table(
        'interpol_fines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interpol_id', sa.BigInteger(), nullable=False),
        sa.Column('victim_id', sa.BigInteger(), nullable=False),
        sa.Column('fine_amount', sa.Integer(), nullable=False),
        sa.Column('bonus_amount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['interpol_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['victim_id'], ['users.telegram_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_interpol_fines_victim', 'interpol_fines', ['interpol_id', 'victim_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_interpol_fines_victim')
    op.drop_table('interpol_fines')
