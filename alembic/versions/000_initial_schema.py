"""initial schema

Revision ID: 000
Revises:
Create Date: 2025-10-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('gender', sa.String(length=10), nullable=True),
        sa.Column('balance', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('is_banned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id')
    )
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'])

    # Create jobs table with selfmade and 1-10 levels
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('job_level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('times_worked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_work_time', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.CheckConstraint(
            "job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture', 'selfmade')",
            name='jobs_job_type_check'
        ),
        sa.CheckConstraint('job_level BETWEEN 1 AND 10', name='jobs_job_level_check')
    )
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])

    # Create interpol_fines table
    op.create_table(
        'interpol_fines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interpol_id', sa.BigInteger(), nullable=False),
        sa.Column('victim_id', sa.BigInteger(), nullable=False),
        sa.Column('fine_amount', sa.Integer(), nullable=False),
        sa.Column('bonus_amount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['interpol_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['victim_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_interpol_fines_lookup', 'interpol_fines', ['interpol_id', 'victim_id', 'created_at'])

    # Create cooldowns table
    op.create_table(
        'cooldowns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'action', name='uq_user_action')
    )
    op.create_index('ix_cooldowns_user_id', 'cooldowns', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_cooldowns_user_id', table_name='cooldowns')
    op.drop_table('cooldowns')
    op.drop_index('ix_interpol_fines_lookup', table_name='interpol_fines')
    op.drop_table('interpol_fines')
    op.drop_index('ix_jobs_user_id', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_table('users')
