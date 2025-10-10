"""expand job levels and add selfmade

Revision ID: 001
Revises:
Create Date: 2025-10-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing check constraints
    op.drop_constraint('jobs_job_type_check', 'jobs', type_='check')
    op.drop_constraint('jobs_job_level_check', 'jobs', type_='check')

    # Add new check constraints with selfmade and levels 1-10
    op.create_check_constraint(
        'jobs_job_type_check',
        'jobs',
        "job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture', 'selfmade')"
    )
    op.create_check_constraint(
        'jobs_job_level_check',
        'jobs',
        'job_level BETWEEN 1 AND 10'
    )


def downgrade() -> None:
    # Drop new check constraints
    op.drop_constraint('jobs_job_type_check', 'jobs', type_='check')
    op.drop_constraint('jobs_job_level_check', 'jobs', type_='check')

    # Restore old check constraints
    op.create_check_constraint(
        'jobs_job_type_check',
        'jobs',
        "job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture')"
    )
    op.create_check_constraint(
        'jobs_job_level_check',
        'jobs',
        'job_level BETWEEN 1 AND 6'
    )
