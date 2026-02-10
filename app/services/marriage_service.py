"""Marriage service for Wedding Telegram Bot."""

import os
import random
from datetime import datetime, timedelta
from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import FamilyMember, Marriage, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Check if DEBUG mode (DEV environment)
IS_DEBUG = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"

# Constants
PROPOSE_COST = 50  # алмазы
DIVORCE_COST = 100  # алмазы
GIFT_MIN = 10  # минимум для подарка
DATE_COOLDOWN_HOURS = 12
LOVE_COOLDOWN_HOURS = 24
CHEAT_RISK_PERCENTAGE = 30  # 30% шанс поймают
ANNIVERSARY_COOLDOWN_DAYS = 7  # 1 week
ANNIVERSARY_REWARD_PER_WEEK = 100  # алмазы за каждую неделю брака
ANNIVERSARY_MAX_REWARD = 1000  # макс награда

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
            return False, f"Нужно минимум {format_diamonds(PROPOSE_COST)} для предложения"

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

        # Check for existing inactive marriages and delete them (to avoid unique constraint violation)
        existing_inactive = (
            db.query(Marriage)
            .filter(Marriage.partner1_id == p1, Marriage.partner2_id == p2, Marriage.is_active.is_(False))
            .all()
        )
        for old_marriage in existing_inactive:
            db.delete(old_marriage)
            logger.info("Deleted old inactive marriage", marriage_id=old_marriage.id)

        # Flush to apply deletions before inserting new marriage
        if existing_inactive:
            db.flush()

        marriage = Marriage(partner1_id=p1, partner2_id=p2, is_active=True)
        db.add(marriage)
        db.flush()
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
    def divorce(db: Session, user_id: int) -> Tuple[bool, str, Optional[int]]:
        """Divorce current marriage with settlement.

        Returns:
            (success, message, partner_id)
        """
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user.balance < DIVORCE_COST:
            return False, f"Развод стоит {format_diamonds(DIVORCE_COST)}", None

        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем", None

        partner_id = MarriageService.get_partner_id(marriage, user_id)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()

        # Divorce settlement: split family bank 50/50 (remainder to initiator)
        if marriage.family_bank_balance > 0:
            split_amount = marriage.family_bank_balance // 2
            remainder = marriage.family_bank_balance % 2
            user.balance += split_amount + remainder
            partner.balance += split_amount
            logger.info(
                "Divorce settlement",
                marriage_id=marriage.id,
                split_amount=split_amount,
                family_bank=marriage.family_bank_balance,
            )
            marriage.family_bank_balance = 0

        # Charge divorce cost BEFORE custody comparison so balance is accurate
        user.balance -= DIVORCE_COST

        # Child custody: children go to parent with higher balance (or random if equal)
        from app.database.models import Child

        children = db.query(Child).filter(Child.marriage_id == marriage.id, Child.is_alive.is_(True)).all()

        if children:
            # Decide custody
            if user.balance > partner.balance:
                custody_parent_id = user_id
            elif partner.balance > user.balance:
                custody_parent_id = partner_id
            else:
                # Equal balance - random
                custody_parent_id = random.choice([user_id, partner_id])

            # Update all children's parent1_id to custody parent
            for child in children:
                child.parent1_id = custody_parent_id
                child.parent2_id = custody_parent_id  # Both parents same (single parent)

            logger.info(
                "Child custody assigned",
                marriage_id=marriage.id,
                custody_parent=custody_parent_id,
                children_count=len(children),
            )

        # End marriage
        marriage.is_active = False
        marriage.ended_at = datetime.utcnow()

        logger.info("Divorce processed", user_id=user_id, marriage_id=marriage.id, partner_id=partner_id)
        return True, "Развод оформлен", partner_id

    @staticmethod
    def gift_diamonds(db: Session, giver_id: int, amount: int) -> Tuple[bool, str]:
        """Gift diamonds to spouse.

        Returns:
            (success, message)
        """
        if amount < GIFT_MIN:
            return False, f"Минимальный подарок: {format_diamonds(GIFT_MIN)}"

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

        logger.info("Gift sent", giver_id=giver_id, partner_id=partner_id, amount=amount)
        return True, f"Подарил {format_diamonds(amount)} супругу/супруге"

    @staticmethod
    def can_make_love(db: Session, user_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if can /makelove.

        Returns:
            (can_love, error_message, cooldown_seconds)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем", None

        # Skip cooldown check in DEBUG mode
        if IS_DEBUG:
            return True, None, None

        if marriage.last_love_at:
            cooldown_until = marriage.last_love_at + timedelta(hours=LOVE_COOLDOWN_HOURS)
            if datetime.utcnow() < cooldown_until:
                remaining = (cooldown_until - datetime.utcnow()).total_seconds()
                return False, None, int(remaining)

        return True, None, None

    @staticmethod
    def make_love(db: Session, user_id: int) -> Tuple[bool, bool, bool, bool, str]:
        """Process /makelove.

        Returns:
            (success, conceived, same_gender, can_have_children, requirements_error)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        marriage.last_love_at = datetime.utcnow()
        marriage.love_count += 1

        # Check if partners are same gender
        partner1 = db.query(User).filter(User.telegram_id == marriage.partner1_id).first()
        partner2 = db.query(User).filter(User.telegram_id == marriage.partner2_id).first()
        same_gender = partner1.gender == partner2.gender

        # Check if can have children (requirements)
        can_have_children = False
        requirements_error = ""
        try:
            from app.services.children_service import ChildrenService

            can_have_children, requirements_error = ChildrenService.can_have_child(db, marriage.id)
        except Exception as e:
            logger.error("Failed to check child requirements", marriage_id=marriage.id, error=str(e))

        # 10% chance of conception (only if can have children)
        conceived = False
        if can_have_children:
            conceived = random.random() < 0.10

            # Actually create child if conceived
            if conceived:
                try:
                    from app.services.children_service import ChildrenService

                    ChildrenService.create_child(db, marriage.id)
                    logger.info("Natural birth successful", user_id=user_id, marriage_id=marriage.id)
                except Exception as e:
                    # Fallback - don't break the command
                    conceived = False
                    logger.error("Failed to create child", marriage_id=marriage.id, error=str(e))

        logger.info(
            "Make love",
            user_id=user_id,
            marriage_id=marriage.id,
            conceived=conceived,
            same_gender=same_gender,
            can_have_children=can_have_children,
        )
        return True, conceived, same_gender, can_have_children, requirements_error

    @staticmethod
    def can_date(db: Session, user_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if can /date.

        Returns:
            (can_date, error_message, cooldown_seconds)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем", None

        # Skip cooldown check in DEBUG mode
        if IS_DEBUG:
            return True, None, None

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

        logger.info("Family member added", marriage_id=marriage_id, user_id=user_id)
        return True

    @staticmethod
    def get_family_members(db: Session, marriage_id: int) -> list:
        """Get all family members."""
        return db.query(FamilyMember).filter(FamilyMember.marriage_id == marriage_id).all()

    @staticmethod
    def can_celebrate_anniversary(db: Session, user_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if can celebrate anniversary.

        Returns:
            (can_celebrate, error_message, cooldown_seconds)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем", None

        # Skip cooldown check in DEBUG mode
        if IS_DEBUG:
            return True, None, None

        if marriage.last_anniversary_at:
            cooldown_until = marriage.last_anniversary_at + timedelta(days=ANNIVERSARY_COOLDOWN_DAYS)
            if datetime.utcnow() < cooldown_until:
                remaining = (cooldown_until - datetime.utcnow()).total_seconds()
                return False, None, int(remaining)

        return True, None, None

    @staticmethod
    def celebrate_anniversary(db: Session, user_id: int) -> Tuple[int, int]:
        """Celebrate wedding anniversary.

        Returns:
            (reward_per_partner, weeks_married)
        """
        marriage = MarriageService.get_active_marriage(db, user_id)
        marriage.last_anniversary_at = datetime.utcnow()

        # Calculate weeks married
        time_married = datetime.utcnow() - marriage.created_at
        weeks_married = int(time_married.total_seconds() // (7 * 86400))

        # Calculate reward (100 per week, max 1000, minimum 1 week's worth)
        reward_per_partner = min(max(1, weeks_married) * ANNIVERSARY_REWARD_PER_WEEK, ANNIVERSARY_MAX_REWARD)

        # Give reward to both partners
        partner1_id = marriage.partner1_id
        partner2_id = marriage.partner2_id

        partner1 = db.query(User).filter(User.telegram_id == partner1_id).first()
        partner2 = db.query(User).filter(User.telegram_id == partner2_id).first()

        partner1.balance += reward_per_partner
        partner2.balance += reward_per_partner

        logger.info("Anniversary celebrated", user_id=user_id, weeks=weeks_married, reward=reward_per_partner)
        return reward_per_partner, weeks_married

    @staticmethod
    def deposit_to_family_bank(db: Session, user_id: int, amount: int) -> Tuple[bool, str]:
        """Deposit diamonds to family bank.

        Returns:
            (success, message)
        """
        if amount <= 0:
            return False, "Укажи положительное число"

        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user.balance < amount:
            return False, "Недостаточно алмазов"

        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем"

        # Transfer
        user.balance -= amount
        marriage.family_bank_balance += amount

        logger.info(
            "Deposited to family bank", user_id=user_id, amount=amount, new_balance=marriage.family_bank_balance
        )
        return True, f"Внесено {format_diamonds(amount)} в семейный банк"

    @staticmethod
    def withdraw_from_family_bank(db: Session, user_id: int, amount: int) -> Tuple[bool, str]:
        """Withdraw diamonds from family bank.

        Returns:
            (success, message)
        """
        if amount <= 0:
            return False, "Укажи положительное число"

        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return False, "Ты не женат/замужем"

        if marriage.family_bank_balance < amount:
            return False, f"В семейном банке только {format_diamonds(marriage.family_bank_balance)}"

        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Transfer
        marriage.family_bank_balance -= amount
        user.balance += amount

        logger.info(
            "Withdrawn from family bank", user_id=user_id, amount=amount, new_balance=marriage.family_bank_balance
        )
        return True, f"Снято {format_diamonds(amount)} из семейного банка"

    @staticmethod
    def get_family_bank_balance(db: Session, user_id: int) -> Optional[int]:
        """Get family bank balance."""
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            return None
        return marriage.family_bank_balance
