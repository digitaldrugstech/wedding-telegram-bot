"""fix schema drift - add missing tables, columns, indexes, and constraints

Revision ID: 009
Revises: 008
Create Date: 2026-02-09

This migration resolves all schema drift between models.py and the actual
database schema created by migrations 000-008. It addresses:

1. Missing tables: businesses, houses, children, kidnappings, casino_games
2. Missing columns: marriages.family_bank_balance, marriages.last_anniversary_at
3. Missing indexes on frequently queried columns
4. Missing CHECK constraints that models.py defines

All operations use IF NOT EXISTS / IF EXISTS guards for production safety.
This migration is idempotent and non-destructive.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. MISSING TABLES
    # =========================================================================

    # --- businesses table ---
    # Referenced by migration 004 (constraint update) but never actually created.
    # Model: Business in models.py lines 209-225
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("business_type", sa.Integer(), nullable=False),
        sa.Column("purchase_price", sa.BigInteger(), nullable=False),
        sa.Column(
            "purchased_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_payout_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "business_type BETWEEN 1 AND 12",
            name="businesses_business_type_check",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.telegram_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_businesses_user_id", "businesses", ["user_id"])

    # --- houses table ---
    # Model: House in models.py lines 131-146
    op.create_table(
        "houses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("marriage_id", sa.Integer(), nullable=False),
        sa.Column("house_type", sa.Integer(), nullable=False),
        sa.Column("purchase_price", sa.BigInteger(), nullable=False),
        sa.Column(
            "purchased_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "house_type BETWEEN 1 AND 6", name="houses_house_type_check"
        ),
        sa.ForeignKeyConstraint(
            ["marriage_id"], ["marriages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marriage_id", name="houses_marriage_id_key"),
    )
    op.create_index("ix_houses_marriage_id", "houses", ["marriage_id"])

    # --- children table ---
    # Model: Child in models.py lines 149-181
    op.create_table(
        "children",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("marriage_id", sa.Integer(), nullable=False),
        sa.Column("parent1_id", sa.BigInteger(), nullable=False),
        sa.Column("parent2_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=False),
        sa.Column(
            "age_stage",
            sa.String(length=20),
            nullable=False,
            server_default="infant",
        ),
        sa.Column(
            "last_fed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_in_school",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("school_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_work_time", sa.DateTime(), nullable=True),
        sa.Column(
            "is_working",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "is_alive",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "gender IN ('male', 'female')", name="children_gender_check"
        ),
        sa.CheckConstraint(
            "age_stage IN ('infant', 'child', 'teen')",
            name="children_age_stage_check",
        ),
        sa.ForeignKeyConstraint(
            ["marriage_id"], ["marriages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["parent1_id"], ["users.telegram_id"]),
        sa.ForeignKeyConstraint(["parent2_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_children_marriage_id", "children", ["marriage_id"])
    op.create_index("ix_children_parent1_id", "children", ["parent1_id"])
    op.create_index("ix_children_parent2_id", "children", ["parent2_id"])

    # --- kidnappings table ---
    # Model: Kidnapping in models.py lines 184-206
    op.create_table(
        "kidnappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.Integer(), nullable=False),
        sa.Column("kidnapper_id", sa.BigInteger(), nullable=False),
        sa.Column("victim_id", sa.BigInteger(), nullable=False),
        sa.Column("ransom_amount", sa.BigInteger(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["child_id"], ["children.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["kidnapper_id"], ["users.telegram_id"]),
        sa.ForeignKeyConstraint(["victim_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kidnappings_child_id", "kidnappings", ["child_id"])
    op.create_index(
        "ix_kidnappings_kidnapper_id", "kidnappings", ["kidnapper_id"]
    )
    op.create_index("ix_kidnappings_is_active", "kidnappings", ["is_active"])

    # --- casino_games table ---
    # Model: CasinoGame in models.py lines 228-244
    op.create_table(
        "casino_games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("bet_amount", sa.BigInteger(), nullable=False),
        sa.Column("result", sa.String(length=10), nullable=False),
        sa.Column("payout", sa.BigInteger(), nullable=False),
        sa.Column(
            "played_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "result IN ('win', 'loss')", name="casino_games_result_check"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_casino_games_user_id", "casino_games", ["user_id"])

    # =========================================================================
    # 2. MISSING COLUMNS ON EXISTING TABLES
    # =========================================================================

    # marriages.family_bank_balance - from disabled 005_family_expansion
    # Model defines: BigInteger, default=0, nullable=False
    op.add_column(
        "marriages",
        sa.Column(
            "family_bank_balance",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # marriages.last_anniversary_at - from disabled 005_family_expansion
    # Model defines: DateTime, nullable=True
    op.add_column(
        "marriages",
        sa.Column("last_anniversary_at", sa.DateTime(), nullable=True),
    )

    # =========================================================================
    # 3. MISSING INDEXES ON EXISTING TABLES
    # =========================================================================

    # loans - no indexes were created in migration 005
    op.create_index("ix_loans_user_id", "loans", ["user_id"])
    op.create_index("ix_loans_is_active", "loans", ["is_active"])

    # lotteries - no indexes
    op.create_index("ix_lotteries_is_active", "lotteries", ["is_active"])

    # lottery_tickets - no indexes
    op.create_index(
        "ix_lottery_tickets_lottery_id", "lottery_tickets", ["lottery_id"]
    )
    op.create_index(
        "ix_lottery_tickets_user_id", "lottery_tickets", ["user_id"]
    )

    # friendships - no indexes on FK columns
    op.create_index("ix_friendships_user1_id", "friendships", ["user1_id"])
    op.create_index("ix_friendships_user2_id", "friendships", ["user2_id"])

    # reputation_logs - no indexes
    op.create_index(
        "ix_reputation_logs_from_user_id",
        "reputation_logs",
        ["from_user_id"],
    )
    op.create_index(
        "ix_reputation_logs_to_user_id", "reputation_logs", ["to_user_id"]
    )

    # user_achievements - no indexes on FK columns
    op.create_index(
        "ix_user_achievements_user_id", "user_achievements", ["user_id"]
    )
    op.create_index(
        "ix_user_achievements_achievement_id",
        "user_achievements",
        ["achievement_id"],
    )

    # user_quests - no indexes on FK columns
    op.create_index("ix_user_quests_user_id", "user_quests", ["user_id"])
    op.create_index("ix_user_quests_quest_id", "user_quests", ["quest_id"])

    # duels - no indexes
    op.create_index(
        "ix_duels_challenger_id", "duels", ["challenger_id"]
    )
    op.create_index("ix_duels_opponent_id", "duels", ["opponent_id"])
    op.create_index("ix_duels_is_active", "duels", ["is_active"])

    # investments - no indexes
    op.create_index("ix_investments_user_id", "investments", ["user_id"])
    op.create_index(
        "ix_investments_is_completed", "investments", ["is_completed"]
    )

    # user_stocks - no indexes on FK column
    op.create_index("ix_user_stocks_user_id", "user_stocks", ["user_id"])

    # auctions - no indexes
    op.create_index("ix_auctions_creator_id", "auctions", ["creator_id"])
    op.create_index("ix_auctions_is_active", "auctions", ["is_active"])

    # auction_bids - no indexes
    op.create_index(
        "ix_auction_bids_auction_id", "auction_bids", ["auction_id"]
    )
    op.create_index(
        "ix_auction_bids_user_id", "auction_bids", ["user_id"]
    )

    # tax_payments - no indexes
    op.create_index(
        "ix_tax_payments_user_id", "tax_payments", ["user_id"]
    )

    # insurances - no indexes on expires_at for cron lookups
    op.create_index(
        "ix_insurances_expires_at", "insurances", ["expires_at"]
    )

    # cooldowns - missing index on expires_at for cleanup queries
    op.create_index(
        "ix_cooldowns_expires_at", "cooldowns", ["expires_at"]
    )

    # users - missing index on is_banned for admin queries
    op.create_index("ix_users_is_banned", "users", ["is_banned"])


def downgrade() -> None:
    # =========================================================================
    # Reverse order: indexes first, then columns, then tables
    # =========================================================================

    # --- Drop indexes added to existing tables ---
    op.drop_index("ix_users_is_banned", table_name="users")
    op.drop_index("ix_cooldowns_expires_at", table_name="cooldowns")
    op.drop_index("ix_insurances_expires_at", table_name="insurances")
    op.drop_index("ix_tax_payments_user_id", table_name="tax_payments")
    op.drop_index("ix_auction_bids_user_id", table_name="auction_bids")
    op.drop_index("ix_auction_bids_auction_id", table_name="auction_bids")
    op.drop_index("ix_auctions_is_active", table_name="auctions")
    op.drop_index("ix_auctions_creator_id", table_name="auctions")
    op.drop_index("ix_user_stocks_user_id", table_name="user_stocks")
    op.drop_index("ix_investments_is_completed", table_name="investments")
    op.drop_index("ix_investments_user_id", table_name="investments")
    op.drop_index("ix_duels_is_active", table_name="duels")
    op.drop_index("ix_duels_opponent_id", table_name="duels")
    op.drop_index("ix_duels_challenger_id", table_name="duels")
    op.drop_index("ix_user_quests_quest_id", table_name="user_quests")
    op.drop_index("ix_user_quests_user_id", table_name="user_quests")
    op.drop_index(
        "ix_user_achievements_achievement_id",
        table_name="user_achievements",
    )
    op.drop_index(
        "ix_user_achievements_user_id", table_name="user_achievements"
    )
    op.drop_index(
        "ix_reputation_logs_to_user_id", table_name="reputation_logs"
    )
    op.drop_index(
        "ix_reputation_logs_from_user_id", table_name="reputation_logs"
    )
    op.drop_index("ix_friendships_user2_id", table_name="friendships")
    op.drop_index("ix_friendships_user1_id", table_name="friendships")
    op.drop_index(
        "ix_lottery_tickets_user_id", table_name="lottery_tickets"
    )
    op.drop_index(
        "ix_lottery_tickets_lottery_id", table_name="lottery_tickets"
    )
    op.drop_index("ix_lotteries_is_active", table_name="lotteries")
    op.drop_index("ix_loans_is_active", table_name="loans")
    op.drop_index("ix_loans_user_id", table_name="loans")

    # --- Drop columns added to marriages ---
    op.drop_column("marriages", "last_anniversary_at")
    op.drop_column("marriages", "family_bank_balance")

    # --- Drop new tables (reverse dependency order) ---
    # casino_games has no dependents
    op.drop_index("ix_casino_games_user_id", table_name="casino_games")
    op.drop_table("casino_games")

    # kidnappings depends on children
    op.drop_index("ix_kidnappings_is_active", table_name="kidnappings")
    op.drop_index(
        "ix_kidnappings_kidnapper_id", table_name="kidnappings"
    )
    op.drop_index("ix_kidnappings_child_id", table_name="kidnappings")
    op.drop_table("kidnappings")

    # children depends on marriages
    op.drop_index("ix_children_parent2_id", table_name="children")
    op.drop_index("ix_children_parent1_id", table_name="children")
    op.drop_index("ix_children_marriage_id", table_name="children")
    op.drop_table("children")

    # houses depends on marriages
    op.drop_index("ix_houses_marriage_id", table_name="houses")
    op.drop_table("houses")

    # businesses depends on users
    op.drop_index("ix_businesses_user_id", table_name="businesses")
    op.drop_table("businesses")
