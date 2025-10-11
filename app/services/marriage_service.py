"""Marriage service for Wedding Telegram Bot."""

import random
from datetime import datetime, timedelta
from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import FamilyMember, Marriage, User

logger = structlog.get_logger()

# Constants
PROPOSE_COST = 50  # алмазы
DIVORCE_COST = 100  # алмазы
GIFT_MIN = 10  # минимум для подарка
DATE_COOLDOWN_HOURS = 12
LOVE_COOLDOWN_HOURS = 24
CHEAT_RISK_PERCENTAGE = 30  # 30% шанс поймают


class MarriageService:
    """Service for marriage operations."""

    @staticmethod
    def can_propose(db: Session, proposer_id: int) -> Tuple[bool, Optional[str]]:
        """Check if user can propose.

        Returns:
            (can_propose, error_message)
        """
        user = db.query(User).filter(User.telegram_id == proposer_id).first()
        if not user:
            return False, "Ты не зарегистрирован"

        if user.balance < PROPOSE_COST:
            return False, f"Нужно минимум {PROPOSE_COST} алмазов для предложения"

        if not user.gender:
            return False, "Сначала выбери пол в /start"

        # Check existing marriage
        existing = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == proposer_id) | (Marriage.partner2_id == proposer_id)),
            )
            .first()
        )

        if existing:
            return False, "Ты уже женат/замужем"

        return True, None

    @staticmethod
    def can_accept_proposal(db: Session, acceptor_id: int, proposer_id: int) -> Tuple[bool, Optional[str]]:
        """Check if user can accept proposal.

        Returns:
            (can_accept, error_message)
        """
        acceptor = db.query(User).filter(User.telegram_id == acceptor_id).first()
        proposer = db.query(User).filter(User.telegram_id == proposer_id).first()

        if not acceptor or not proposer:
            return False, "Один из пользователей не найден"

        if not acceptor.gender:
            return False, "Сначала выбери пол в /start"

        if acceptor.gender == proposer.gender:
            return False, "Можно жениться только на противоположном поле"

        # Check existing marriage
        existing = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == acceptor_id) | (Marriage.partner2_id == acceptor_id)),
            )
            .first()
        )

        if existing:
            return False, "Ты уже женат/замужем"

        return True, None

    @staticmethod
    def create_marriage(db: Session, partner1_id: int, partner2_id: int) -> Marriage:
        """Create new marriage."""
        # Charge proposer
        proposer = db.query(User).filter(User.telegram_id == partner1_id).first()
        proposer.balance -= PROPOSE_COST

        # Create marriage (smaller ID first for uniqueness)
        p1, p2 = min(partner1_id, partner2_id), max(partner1_id, partner2_id)

        marriage = Marriage(partner1_id=p1, partner2_id=p2, is_active=True)
        db.add(marriage)
        db.commit()
        db.refresh(marriage)

        logger.info("Marriage created", partner1_id=p1, partner2_id=p2, marriage_id=marriage.id)
        return marriage

    @staticmethod
    def get_active_marriage(db: Session, user_id: int) -> Optional[Marriage]:
        """Get user's active marriage."""
        return (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True), ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id))
            )
            .first()
        )

    @staticmethod
    def get_partner_id(marriage: Marriage, user_id: int) -> int:
        """Get partner's ID from marriage."""
        return marriage.partner2_id if marriage.partner1_id == user_id else marriage.partner1_id

    @staticmethod
    def divorce(db: Session, user_id: int) -> Tuple[bool, str]:
        """Divorce current marriage.

        Returns:
            (success, message)
        """
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user.balance < DIVORCE_COST:
            return False, f"Развод стоит {DIVORCE_COST} алмазов"

        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем"

        # Charge divorce cost
        user.balance -= DIVORCE_COST

        # End marriage
        marriage.is_active = False
        marriage.ended_at = datetime.utcnow()

        db.commit()

        logger.info("Divorce processed", user_id=user_id, marriage_id=marriage.id)
        return True, "Вы развелись"

    @staticmethod
    def gift_diamonds(db: Session, giver_id: int, amount: int) -> Tuple[bool, str]:
        """Gift diamonds to spouse.

        Returns:
            (success, message)
        """
        if amount < GIFT_MIN:
            return False, f"Минимальный подарок: {GIFT_MIN} алмазов"

        giver = db.query(User).filter(User.telegram_id == giver_id).first()
        if giver.balance < amount:
            return False, "Недостаточно алмазов"

        marriage = MarriageService.get_active_marriage(db, giver_id)
        if not marriage:
            return False, "Ты не женат/замужем"

        partner_id = MarriageService.get_partner_id(marriage, giver_id)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()

        # Transfer
        giver.balance -= amount
        partner.balance += amount

        db.commit()

        logger.info("Gift sent", giver_id=giver_id, partner_id=partner_id, amount=amount)
        return True, f"Подарил {amount} алмазов супругу/супруге"

    @staticmethod
    def can_make_love(db: Session, user_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if can /makelove.

        Returns:
            (can_love, error_message, cooldown_seconds)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем", None

        if marriage.last_love_at:
            cooldown_until = marriage.last_love_at + timedelta(hours=LOVE_COOLDOWN_HOURS)
            if datetime.utcnow() < cooldown_until:
                remaining = (cooldown_until - datetime.utcnow()).total_seconds()
                return False, None, int(remaining)

        return True, None, None

    @staticmethod
    def make_love(db: Session, user_id: int) -> Tuple[bool, bool]:
        """Process /makelove.

        Returns:
            (success, conceived)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        marriage.last_love_at = datetime.utcnow()
        marriage.love_count += 1

        # 20% chance of conception
        conceived = random.random() < 0.20

        db.commit()

        logger.info("Make love", user_id=user_id, marriage_id=marriage.id, conceived=conceived)
        return True, conceived

    @staticmethod
    def can_date(db: Session, user_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if can /date.

        Returns:
            (can_date, error_message, cooldown_seconds)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем", None

        if marriage.last_date_at:
            cooldown_until = marriage.last_date_at + timedelta(hours=DATE_COOLDOWN_HOURS)
            if datetime.utcnow() < cooldown_until:
                remaining = (cooldown_until - datetime.utcnow()).total_seconds()
                return False, None, int(remaining)

        return True, None, None

    @staticmethod
    def go_on_date(db: Session, user_id: int) -> Tuple[int, str]:
        """Process /date.

        Returns:
            (diamonds_earned, location)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        marriage.last_date_at = datetime.utcnow()

        # Random date earnings 10-50 diamonds
        earned = random.randint(10, 50)

        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += earned

        # Random date location
        locations = [
            "кафе",
            "кинотеатр",
            "парк",
            "ресторан",
            "боулинг",
            "каток",
            "пляж",
            "музей",
            "выставка",
            "концерт",
        ]
        location = random.choice(locations)

        db.commit()

        logger.info("Date completed", user_id=user_id, earned=earned, location=location)
        return earned, location

    @staticmethod
    def cheat(db: Session, cheater_id: int, target_id: int) -> Tuple[bool, bool, int]:
        """Process /cheat.

        Returns:
            (caught, divorced, fine_amount)
        """
        marriage = MarriageService.get_active_marriage(db, cheater_id)

        # 30% chance of getting caught
        caught = random.random() < (CHEAT_RISK_PERCENTAGE / 100)

        if caught:
            # Automatic divorce + fine
            cheater = db.query(User).filter(User.telegram_id == cheater_id).first()
            partner_id = MarriageService.get_partner_id(marriage, cheater_id)
            partner = db.query(User).filter(User.telegram_id == partner_id).first()

            # Fine: 50% of balance
            fine = int(cheater.balance * 0.5)
            cheater.balance -= fine
            partner.balance += fine

            # End marriage
            marriage.is_active = False
            marriage.ended_at = datetime.utcnow()

            db.commit()

            logger.info("Cheat caught", cheater_id=cheater_id, partner_id=partner_id, fine=fine)
            return True, True, fine
        else:
            # Success - nothing happens
            logger.info("Cheat succeeded", cheater_id=cheater_id, target_id=target_id)
            return False, False, 0

    @staticmethod
    def add_family_member(db: Session, marriage_id: int, user_id: int) -> bool:
        """Add user to family members.

        Returns:
            success
        """
        # Check if already member
        existing = (
            db.query(FamilyMember)
            .filter(FamilyMember.marriage_id == marriage_id, FamilyMember.user_id == user_id)
            .first()
        )

        if existing:
            return False

        member = FamilyMember(marriage_id=marriage_id, user_id=user_id)
        db.add(member)
        db.commit()

        logger.info("Family member added", marriage_id=marriage_id, user_id=user_id)
        return True

    @staticmethod
    def get_family_members(db: Session, marriage_id: int) -> list:
        """Get all family members."""
        return db.query(FamilyMember).filter(FamilyMember.marriage_id == marriage_id).all()
