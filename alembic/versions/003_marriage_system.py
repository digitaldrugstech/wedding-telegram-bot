"""marriage system

Revision ID: 003
Revises: 002
Create Date: 2025-10-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create marriages table
    op.create_table(
        'marriages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('partner1_id', sa.BigInteger(), nullable=False),
        sa.Column('partner2_id', sa.BigInteger(), nullable=False),
        sa.Column('family_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('love_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_love_at', sa.DateTime(), nullable=True),
        sa.Column('last_date_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['partner1_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['partner2_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('partner1_id', 'partner2_id', name='uq_partners')
    )
    op.create_index('ix_marriages_partner1_id', 'marriages', ['partner1_id'])
    op.create_index('ix_marriages_partner2_id', 'marriages', ['partner2_id'])
    op.create_index('ix_marriages_is_active', 'marriages', ['is_active'])

    # Create family_members table
    op.create_table(
        'family_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('marriage_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['marriage_id'], ['marriages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('marriage_id', 'user_id', name='uq_marriage_user')
    )
    op.create_index('ix_family_members_marriage_id', 'family_members', ['marriage_id'])
    op.create_index('ix_family_members_user_id', 'family_members', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_family_members_user_id', table_name='family_members')
    op.drop_index('ix_family_members_marriage_id', table_name='family_members')
    op.drop_table('family_members')

    op.drop_index('ix_marriages_is_active', table_name='marriages')
    op.drop_index('ix_marriages_partner2_id', table_name='marriages')
    op.drop_index('ix_marriages_partner1_id', table_name='marriages')
    op.drop_table('marriages')
