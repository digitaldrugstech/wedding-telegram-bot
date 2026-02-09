"""SQLAlchemy database models for Wedding Telegram Bot."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    """User model."""

    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)
    gender = Column(String(10), CheckConstraint("gender IN ('male', 'female')"), nullable=True)
    balance = Column(BigInteger, default=0, nullable=False)
    reputation = Column(Integer, default=0, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    daily_streak = Column(Integer, default=0, nullable=False)
    last_daily_at = Column(DateTime, nullable=True)
    active_title = Column(String(100), nullable=True)
    purchased_titles = Column(String(1000), default="", nullable=False)
    prestige_level = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    job = relationship("Job", back_populates="user", uselist=False, cascade="all, delete-orphan")
    businesses = relationship("Business", back_populates="user", cascade="all, delete-orphan")
    casino_games = relationship("CasinoGame", back_populates="user", cascade="all, delete-orphan")
    cooldowns = relationship("Cooldown", back_populates="user", cascade="all, delete-orphan")
    loans = relationship("Loan", back_populates="user", cascade="all, delete-orphan")
    lottery_tickets = relationship("LotteryTicket", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username}, balance={self.balance})>"


class Job(Base):
    """Job model."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, unique=True)
    job_type = Column(
        String(50),
        CheckConstraint(
            "job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture', 'selfmade', "
            "'medic', 'teacher', 'journalist', 'transport', 'security', 'chef', "
            "'artist', 'scientist', 'programmer', 'lawyer', 'athlete', 'streamer')"
        ),
        nullable=False,
    )
    job_level = Column(Integer, CheckConstraint("job_level BETWEEN 1 AND 10"), nullable=False)
    times_worked = Column(Integer, default=0, nullable=False)
    last_work_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="job")

    def __repr__(self):
        return f"<Job(user_id={self.user_id}, job_type={self.job_type}, level={self.job_level})>"


class Marriage(Base):
    """Marriage model."""

    __tablename__ = "marriages"

    id = Column(Integer, primary_key=True)
    partner1_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    partner2_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    family_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    love_count = Column(Integer, default=0, nullable=False)
    last_love_at = Column(DateTime, nullable=True)
    last_date_at = Column(DateTime, nullable=True)
    family_bank_balance = Column(BigInteger, default=0, nullable=False)
    last_anniversary_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    ended_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("partner1_id", "partner2_id", name="uq_partners"),)

    # Relationships
    partner1 = relationship("User", foreign_keys=[partner1_id])
    partner2 = relationship("User", foreign_keys=[partner2_id])
    house = relationship("House", back_populates="marriage", uselist=False, cascade="all, delete-orphan")
    family_members = relationship("FamilyMember", back_populates="marriage", cascade="all, delete-orphan")
    children = relationship("Child", back_populates="marriage", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<Marriage(id={self.id}, partner1_id={self.partner1_id}, "
            f"partner2_id={self.partner2_id}, is_active={self.is_active})>"
        )


class FamilyMember(Base):
    """Family member model (extended family)."""

    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True)
    marriage_id = Column(Integer, ForeignKey("marriages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    joined_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("marriage_id", "user_id", name="uq_marriage_user"),)

    # Relationships
    marriage = relationship("Marriage", back_populates="family_members")
    user = relationship("User")

    def __repr__(self):
        return f"<FamilyMember(marriage_id={self.marriage_id}, user_id={self.user_id})>"


class House(Base):
    """House model."""

    __tablename__ = "houses"

    id = Column(Integer, primary_key=True)
    marriage_id = Column(Integer, ForeignKey("marriages.id", ondelete="CASCADE"), nullable=False, unique=True)
    house_type = Column(Integer, CheckConstraint("house_type BETWEEN 1 AND 6"), nullable=False)
    purchase_price = Column(BigInteger, nullable=False)
    purchased_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    marriage = relationship("Marriage", back_populates="house")

    def __repr__(self):
        return f"<House(id={self.id}, marriage_id={self.marriage_id}, house_type={self.house_type})>"


class Child(Base):
    """Child model."""

    __tablename__ = "children"

    id = Column(Integer, primary_key=True)
    marriage_id = Column(Integer, ForeignKey("marriages.id", ondelete="CASCADE"), nullable=False)
    parent1_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    parent2_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    name = Column(String(255), nullable=True)
    gender = Column(String(10), CheckConstraint("gender IN ('male', 'female')"), nullable=False)
    age_stage = Column(
        String(20),
        CheckConstraint("age_stage IN ('infant', 'child', 'teen')"),
        default="infant",
        nullable=False,
    )
    last_fed_at = Column(DateTime, default=func.now(), nullable=False)
    is_in_school = Column(Boolean, default=False, nullable=False)
    school_expires_at = Column(DateTime, nullable=True)
    last_work_time = Column(DateTime, nullable=True)
    is_working = Column(Boolean, default=False, nullable=False)
    is_alive = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    marriage = relationship("Marriage", back_populates="children")
    parent1 = relationship("User", foreign_keys=[parent1_id])
    parent2 = relationship("User", foreign_keys=[parent2_id])
    kidnapping = relationship("Kidnapping", back_populates="child", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Child(id={self.id}, name={self.name}, age_stage={self.age_stage}, is_alive={self.is_alive})>"


class Kidnapping(Base):
    """Kidnapping model."""

    __tablename__ = "kidnappings"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    kidnapper_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    victim_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    ransom_amount = Column(BigInteger, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    child = relationship("Child", back_populates="kidnapping")
    kidnapper = relationship("User", foreign_keys=[kidnapper_id])
    victim = relationship("User", foreign_keys=[victim_id])

    def __repr__(self):
        return (
            f"<Kidnapping(id={self.id}, child_id={self.child_id}, "
            f"kidnapper_id={self.kidnapper_id}, is_active={self.is_active})>"
        )


class Business(Base):
    """Business model."""

    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    business_type = Column(Integer, CheckConstraint("business_type BETWEEN 1 AND 12"), nullable=False)
    purchase_price = Column(BigInteger, nullable=False)
    purchased_at = Column(DateTime, default=func.now(), nullable=False)
    last_payout_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="businesses")

    def __repr__(self):
        return f"<Business(id={self.id}, user_id={self.user_id}, business_type={self.business_type})>"


class CasinoGame(Base):
    """Casino game model."""

    __tablename__ = "casino_games"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    bet_amount = Column(BigInteger, nullable=False)
    result = Column(String(10), CheckConstraint("result IN ('win', 'loss')"), nullable=False)
    payout = Column(BigInteger, nullable=False)
    played_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="casino_games")

    def __repr__(self):
        return f"<CasinoGame(id={self.id}, user_id={self.user_id}, result={self.result}, payout={self.payout})>"


class Cooldown(Base):
    """Cooldown model."""

    __tablename__ = "cooldowns"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    action = Column(String(50), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "action", name="uq_user_action"),)

    # Relationships
    user = relationship("User", back_populates="cooldowns")

    def __repr__(self):
        return f"<Cooldown(user_id={self.user_id}, action={self.action}, expires_at={self.expires_at})>"


class InterpolFine(Base):
    """Interpol fine model."""

    __tablename__ = "interpol_fines"

    id = Column(Integer, primary_key=True)
    interpol_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    victim_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    fine_amount = Column(Integer, nullable=False)
    bonus_amount = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    interpol = relationship("User", foreign_keys=[interpol_id])
    victim = relationship("User", foreign_keys=[victim_id])

    def __repr__(self):
        return (
            f"<InterpolFine(interpol_id={self.interpol_id}, victim_id={self.victim_id}, "
            f"fine={self.fine_amount}, bonus={self.bonus_amount})>"
        )


class Loan(Base):
    """Loan model."""

    __tablename__ = "loans"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    amount = Column(BigInteger, nullable=False)
    interest_rate = Column(Integer, default=20, nullable=False)  # Percentage
    created_at = Column(DateTime, default=func.now(), nullable=False)
    due_at = Column(DateTime, nullable=False)
    penalty_charged = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="loans")

    def __repr__(self):
        return f"<Loan(id={self.id}, user_id={self.user_id}, amount={self.amount}, is_active={self.is_active})>"


class Lottery(Base):
    """Lottery model."""

    __tablename__ = "lotteries"

    id = Column(Integer, primary_key=True)
    jackpot = Column(BigInteger, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    started_at = Column(DateTime, default=func.now(), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    winner_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)

    # Relationships
    winner = relationship("User")
    tickets = relationship("LotteryTicket", back_populates="lottery", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Lottery(id={self.id}, jackpot={self.jackpot}, is_active={self.is_active})>"


class LotteryTicket(Base):
    """Lottery ticket model."""

    __tablename__ = "lottery_tickets"

    id = Column(Integer, primary_key=True)
    lottery_id = Column(Integer, ForeignKey("lotteries.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    purchased_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    lottery = relationship("Lottery", back_populates="tickets")
    user = relationship("User", back_populates="lottery_tickets")

    def __repr__(self):
        return f"<LotteryTicket(id={self.id}, lottery_id={self.lottery_id}, user_id={self.user_id})>"


class Friendship(Base):
    """Friendship model."""

    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True)
    user1_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    user2_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), CheckConstraint("status IN ('pending', 'accepted')"), default="pending", nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user1_id", "user2_id", name="uq_friendship"),)

    # Relationships
    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])

    def __repr__(self):
        return f"<Friendship(user1_id={self.user1_id}, user2_id={self.user2_id}, status={self.status})>"


class ReputationLog(Base):
    """Reputation log model (track who gave reputation to whom)."""

    __tablename__ = "reputation_logs"

    id = Column(Integer, primary_key=True)
    from_user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    to_user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    value = Column(Integer, CheckConstraint("value IN (-1, 1)"), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

    def __repr__(self):
        return f"<ReputationLog(from={self.from_user_id}, to={self.to_user_id}, value={self.value})>"


class Achievement(Base):
    """Achievement model."""

    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=False)
    emoji = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self):
        return f"<Achievement(code={self.code}, name={self.name})>"


class UserAchievement(Base):
    """User achievement model."""

    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False)
    earned_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

    # Relationships
    user = relationship("User")
    achievement = relationship("Achievement")

    def __repr__(self):
        return f"<UserAchievement(user_id={self.user_id}, achievement_id={self.achievement_id})>"


class Quest(Base):
    """Quest model."""

    __tablename__ = "quests"

    id = Column(Integer, primary_key=True)
    quest_type = Column(
        String(50),
        CheckConstraint("quest_type IN ('work', 'casino', 'transfer', 'marriage', 'pet')"),
        nullable=False,
    )
    description = Column(String(255), nullable=False)
    target_count = Column(Integer, nullable=False)
    reward = Column(Integer, nullable=False)

    def __repr__(self):
        return f"<Quest(id={self.id}, type={self.quest_type}, target={self.target_count})>"


class UserQuest(Base):
    """User quest progress model."""

    __tablename__ = "user_quests"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    quest_id = Column(Integer, ForeignKey("quests.id", ondelete="CASCADE"), nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    assigned_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "quest_id", name="uq_user_quest"),)

    # Relationships
    user = relationship("User")
    quest = relationship("Quest")

    def __repr__(self):
        return f"<UserQuest(user_id={self.user_id}, quest_id={self.quest_id}, progress={self.progress})>"


class Pet(Base):
    """Pet model."""

    __tablename__ = "pets"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, unique=True)
    pet_type = Column(String(20), CheckConstraint("pet_type IN ('cat', 'dog', 'dragon')"), nullable=False)
    name = Column(String(100), nullable=False)
    hunger = Column(Integer, CheckConstraint("hunger BETWEEN 0 AND 100"), default=50, nullable=False)
    happiness = Column(Integer, CheckConstraint("happiness BETWEEN 0 AND 100"), default=50, nullable=False)
    last_fed_at = Column(DateTime, default=func.now(), nullable=False)
    last_played_at = Column(DateTime, nullable=True)
    is_alive = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<Pet(user_id={self.user_id}, type={self.pet_type}, name={self.name}, alive={self.is_alive})>"


class Duel(Base):
    """Duel model."""

    __tablename__ = "duels"

    id = Column(Integer, primary_key=True)
    challenger_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    opponent_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    bet_amount = Column(BigInteger, nullable=False)
    winner_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_accepted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    challenger = relationship("User", foreign_keys=[challenger_id])
    opponent = relationship("User", foreign_keys=[opponent_id])
    winner = relationship("User", foreign_keys=[winner_id])

    def __repr__(self):
        return (
            f"<Duel(id={self.id}, challenger={self.challenger_id}, opponent={self.opponent_id}, bet={self.bet_amount})>"
        )


class Investment(Base):
    """Investment model."""

    __tablename__ = "investments"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    amount = Column(BigInteger, nullable=False)
    return_percentage = Column(Integer, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    completes_at = Column(DateTime, nullable=False)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return (
            f"<Investment(id={self.id}, user_id={self.user_id}, "
            f"amount={self.amount}, return={self.return_percentage}%)>"
        )


class Stock(Base):
    """Stock price model."""

    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)
    company = Column(String(50), unique=True, nullable=False)
    price = Column(Integer, nullable=False)
    last_updated = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self):
        return f"<Stock(company={self.company}, price={self.price})>"


class UserStock(Base):
    """User stock holdings model."""

    __tablename__ = "user_stocks"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    company = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "company", name="uq_user_company"),)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<UserStock(user_id={self.user_id}, company={self.company}, quantity={self.quantity})>"


class Auction(Base):
    """Auction model."""

    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True)
    creator_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    item = Column(
        String(50),
        CheckConstraint("item IN ('vip_status', 'double_salary', 'lucky_charm')"),
        nullable=False,
    )
    start_price = Column(BigInteger, nullable=False)
    current_price = Column(BigInteger, nullable=False)
    current_winner_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    ends_at = Column(DateTime, nullable=False)

    # Relationships
    creator = relationship("User", foreign_keys=[creator_id])
    current_winner = relationship("User", foreign_keys=[current_winner_id])
    bids = relationship("AuctionBid", back_populates="auction", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<Auction(id={self.id}, item={self.item}, current_price={self.current_price}, is_active={self.is_active})>"
        )


class AuctionBid(Base):
    """Auction bid model."""

    __tablename__ = "auction_bids"

    id = Column(Integer, primary_key=True)
    auction_id = Column(Integer, ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    amount = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    auction = relationship("Auction", back_populates="bids")
    user = relationship("User")

    def __repr__(self):
        return f"<AuctionBid(id={self.id}, auction_id={self.auction_id}, user_id={self.user_id}, amount={self.amount})>"


class TaxPayment(Base):
    """Tax payment model."""

    __tablename__ = "tax_payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    amount = Column(BigInteger, nullable=False)
    balance_at_time = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<TaxPayment(user_id={self.user_id}, amount={self.amount}, created_at={self.created_at})>"


class Insurance(Base):
    """Insurance model."""

    __tablename__ = "insurances"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    purchased_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<Insurance(user_id={self.user_id}, is_active={self.is_active}, expires_at={self.expires_at})>"
