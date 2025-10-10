"""SQLAlchemy database models for Wedding Telegram Bot."""

from datetime import datetime
from typing import List

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
from sqlalchemy.ext.declarative import declarative_base
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
    is_banned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    job = relationship("Job", back_populates="user", uselist=False, cascade="all, delete-orphan")
    businesses = relationship("Business", back_populates="user", cascade="all, delete-orphan")
    casino_games = relationship("CasinoGame", back_populates="user", cascade="all, delete-orphan")
    cooldowns = relationship("Cooldown", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username}, balance={self.balance})>"


class Job(Base):
    """Job model."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, unique=True)
    job_type = Column(
        String(50),
        CheckConstraint("job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture')"),
        nullable=False,
    )
    job_level = Column(Integer, CheckConstraint("job_level BETWEEN 1 AND 6"), nullable=False)
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
    partner1_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    partner2_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    family_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
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
        return f"<Marriage(id={self.id}, partner1_id={self.partner1_id}, partner2_id={self.partner2_id}, is_active={self.is_active})>"


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
        return f"<Kidnapping(id={self.id}, child_id={self.child_id}, kidnapper_id={self.kidnapper_id}, is_active={self.is_active})>"


class Business(Base):
    """Business model."""

    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    business_type = Column(Integer, CheckConstraint("business_type BETWEEN 1 AND 4"), nullable=False)
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
