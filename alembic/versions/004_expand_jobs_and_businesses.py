"""expand jobs and businesses

Revision ID: 004
Revises: 003
Create Date: 2025-10-15

Adds 12 new job types and 8 new business types for 3x content.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


# All 18 job types
NEW_JOB_TYPES = [
    'interpol', 'banker', 'infrastructure', 'court', 'culture', 'selfmade',  # original 6
    'medic', 'teacher', 'journalist', 'transport', 'security', 'chef',  # new 6
    'artist', 'scientist', 'programmer', 'lawyer', 'athlete', 'streamer'  # new 6
]


def upgrade() -> None:
    # Drop old job_type constraint and create new one with all types
    op.drop_constraint('jobs_job_type_check', 'jobs', type_='check')
    op.create_check_constraint(
        'jobs_job_type_check',
        'jobs',
        f"job_type IN ({', '.join(repr(jt) for jt in NEW_JOB_TYPES)})"
    )

    # Drop old business_type constraint (1-4) and create new one (1-12)
    op.drop_constraint('businesses_business_type_check', 'businesses', type_='check')
    op.create_check_constraint(
        'businesses_business_type_check',
        'businesses',
        'business_type BETWEEN 1 AND 12'
    )


def downgrade() -> None:
    # Restore original constraints
    # Note: This will fail if any data uses new types
    op.drop_constraint('businesses_business_type_check', 'businesses', type_='check')
    op.create_check_constraint(
        'businesses_business_type_check',
        'businesses',
        'business_type BETWEEN 1 AND 4'
    )

    op.drop_constraint('jobs_job_type_check', 'jobs', type_='check')
    op.create_check_constraint(
        'jobs_job_type_check',
        'jobs',
        "job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture', 'selfmade')"
    )
