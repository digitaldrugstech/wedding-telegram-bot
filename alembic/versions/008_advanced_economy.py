"""advanced economy features

Revision ID: 008
Revises: 007
Create Date: 2025-01-21

Adds advanced economy features: investments, stock exchange, auctions, tax system, insurance.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create investments table
    op.create_table(
        "investments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("return_percentage", sa.Integer(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completes_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create stocks table
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("last_updated", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company"),
    )

    # Create user_stocks table
    op.create_table(
        "user_stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("company", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "company", name="uq_user_company"),
    )

    # Create auctions table
    op.create_table(
        "auctions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.BigInteger(), nullable=False),
        sa.Column("item", sa.String(length=50), nullable=False),
        sa.Column("start_price", sa.BigInteger(), nullable=False),
        sa.Column("current_price", sa.BigInteger(), nullable=False),
        sa.Column("current_winner_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("item IN ('vip_status', 'double_salary', 'lucky_charm')"),
        sa.ForeignKeyConstraint(["creator_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_winner_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create auction_bids table
    op.create_table(
        "auction_bids",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auction_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["auction_id"], ["auctions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create tax_payments table
    op.create_table(
        "tax_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("balance_at_time", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create insurances table
    op.create_table(
        "insurances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("purchased_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("insurances")
    op.drop_table("tax_payments")
    op.drop_table("auction_bids")
    op.drop_table("auctions")
    op.drop_table("user_stocks")
    op.drop_table("stocks")
    op.drop_table("investments")
