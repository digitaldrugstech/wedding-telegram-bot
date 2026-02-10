"""Children service - birth, feeding, aging, education."""

import html
import random
from datetime import datetime, timedelta
from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import Child, House, Job, Marriage, User
from app.utils.formatters import format_diamonds, format_word

logger = structlog.get_logger()

# Constants
NATURAL_BIRTH_CHANCE = 0.10  # 10% chance on /makelove
IVF_COST = 5000  # 100% chance
ADOPTION_COST = 5000  # New adoption (child, not infant)

FEEDING_COST = 200  # Per child (increased from 50 to fix inflation)
FEEDING_COOLDOWN_DAYS = 3  # Must feed every 3 days
DEATH_THRESHOLD_DAYS = 5  # Dies after 5 days without food

AGE_INFANT_TO_CHILD_COST = 1000
AGE_CHILD_TO_TEEN_COST = 2000

SCHOOL_COST = 500  # Per month
SCHOOL_DURATION_DAYS = 30  # 1 month
SCHOOL_WORK_BONUS = 0.5  # +50%

BABYSITTER_COST = 1000  # Per week
BABYSITTER_DURATION_DAYS = 7

TEEN_WORK_MIN = 30
TEEN_WORK_MAX = 60
TEEN_WORK_COOLDOWN = 86400  # 24 hours in seconds
TEEN_AUTO_WORK_MIN = 20
TEEN_AUTO_WORK_MAX = 50
TEEN_AUTO_WORK_INTERVAL = 14400  # 4 hours in seconds

class ChildrenService:
    """Service for managing children."""

    @staticmethod
    def can_have_child(db: Session, marriage_id: int) -> Tuple[bool, str]:
        """Check if couple can have a child."""
        marriage = db.query(Marriage).filter(Marriage.id == marriage_id, Marriage.is_active.is_(True)).first()

        if not marriage:
            return False, "Брак не найден"

        # Check if both partners have houses
        house = db.query(House).filter(House.marriage_id == marriage_id).first()
        if not house:
            return False, "Нужен дом чтобы завести детей"

        # Check if both partners have jobs
        job1 = db.query(Job).filter(Job.user_id == marriage.partner1_id).first()
        job2 = db.query(Job).filter(Job.user_id == marriage.partner2_id).first()

        if not job1 or not job2:
            return False, "Оба партнёра должны работать"

        # Check if partners have different professions
        if job1.job_type == job2.job_type:
            return False, "Партнёры должны иметь разные профессии"

        return True, ""

    @staticmethod
    def create_child(db: Session, marriage_id: int, name: Optional[str] = None) -> Child:
        """Create a new child."""
        marriage = db.query(Marriage).filter(Marriage.id == marriage_id).first()

        if not marriage:
            raise ValueError("Marriage not found")

        # Random gender
        gender = random.choice(["male", "female"])

        # Generate random name if not provided
        if not name:
            if gender == "male":
                names = ["Максим", "Артём", "Иван", "Дмитрий", "Никита", "Александр", "Михаил"]
            else:
                names = ["Анастасия", "Мария", "Дарья", "Полина", "Елизавета", "Виктория", "Софья"]
            name = random.choice(names)

        child = Child(
            marriage_id=marriage_id,
            parent1_id=marriage.partner1_id,
            parent2_id=marriage.partner2_id,
            name=name,
            gender=gender,
            age_stage="infant",
            last_fed_at=datetime.utcnow(),
            is_alive=True,
        )

        db.add(child)
        db.flush()

        logger.info("Child created", child_id=child.id, marriage_id=marriage_id, name=name, gender=gender)

        return child

    @staticmethod
    def try_natural_birth(db: Session, marriage_id: int) -> Tuple[bool, Optional[Child]]:
        """Try natural birth (10% chance)."""
        if random.random() < NATURAL_BIRTH_CHANCE:
            can_have, error = ChildrenService.can_have_child(db, marriage_id)

            if not can_have:
                logger.warning("Natural birth failed - requirements not met", marriage_id=marriage_id, error=error)
                return False, None

            child = ChildrenService.create_child(db, marriage_id)
    

            logger.info("Natural birth successful", child_id=child.id, marriage_id=marriage_id)
            return True, child

        return False, None

    @staticmethod
    def ivf_birth(db: Session, marriage_id: int, user_id: int) -> Tuple[bool, str, Optional[Child]]:
        """IVF birth (5000 diamonds, 100% chance)."""
        can_have, error = ChildrenService.can_have_child(db, marriage_id)

        if not can_have:
            return False, error, None

        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < IVF_COST:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(IVF_COST)})", None

        # Charge
        user.balance -= IVF_COST

        # Create child
        child = ChildrenService.create_child(db, marriage_id)

        logger.info("IVF birth successful", child_id=child.id, marriage_id=marriage_id, user_id=user_id)

        return True, "", child

    @staticmethod
    def adopt_child(
        db: Session, marriage_id: int, user_id: int, child_name: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Child]]:
        """Adopt a child (5000 diamonds, directly 'child' age stage).

        Args:
            db: Database session
            marriage_id: Marriage ID
            user_id: User ID who is paying
            child_name: Optional custom name for the child

        Returns:
            (success, error_message, child_object)
        """
        # Check marriage exists
        marriage = db.query(Marriage).filter(Marriage.id == marriage_id, Marriage.is_active.is_(True)).first()
        if not marriage:
            return False, "Брак не найден", None

        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < ADOPTION_COST:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(ADOPTION_COST)})", None

        # Charge
        user.balance -= ADOPTION_COST

        # Create child directly as "child" age stage (not infant)
        gender = random.choice(["male", "female"])

        # Use provided name or generate random
        if not child_name:
            if gender == "male":
                names = ["Максим", "Артём", "Иван", "Дмитрий", "Никита", "Александр", "Михаил"]
            else:
                names = ["Анастасия", "Мария", "Дарья", "Полина", "Елизавета", "Виктория", "Софья"]
            child_name = random.choice(names)

        child = Child(
            marriage_id=marriage_id,
            parent1_id=marriage.partner1_id,
            parent2_id=marriage.partner2_id,
            name=child_name,
            gender=gender,
            age_stage="child",  # Directly "child", not "infant"
            last_fed_at=datetime.utcnow(),
            is_alive=True,
        )

        db.add(child)
        db.flush()
        db.refresh(child)

        logger.info("Adoption successful", child_id=child.id, marriage_id=marriage_id, user_id=user_id, name=child_name)

        return True, "", child

    @staticmethod
    def feed_child(db: Session, child_id: int, user_id: int) -> Tuple[bool, str]:
        """Feed a child (50 diamonds)."""
        child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

        if not child:
            return False, "Ребёнок не найден"

        # Check if already fed recently (cooldown 3 days)
        time_since_last_feed = datetime.utcnow() - child.last_fed_at
        if time_since_last_feed.total_seconds() < FEEDING_COOLDOWN_DAYS * 86400:
            hours_left = (FEEDING_COOLDOWN_DAYS * 86400 - time_since_last_feed.total_seconds()) / 3600
            return False, f"Уже накормлен (можно через {hours_left:.1f}ч)"

        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < FEEDING_COST:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(FEEDING_COST)})"

        # Charge
        user.balance -= FEEDING_COST

        # Feed
        child.last_fed_at = datetime.utcnow()

        logger.info("Child fed", child_id=child_id, user_id=user_id)

        return True, ""

    @staticmethod
    def feed_all_children(db: Session, marriage_id: int, user_id: int) -> Tuple[int, int, int]:
        """Feed all children (returns: fed, already_fed, insufficient_funds)."""
        children = db.query(Child).filter(Child.marriage_id == marriage_id, Child.is_alive.is_(True)).all()

        fed_count = 0
        already_fed_count = 0
        insufficient_funds_count = 0

        user = db.query(User).filter(User.telegram_id == user_id).first()

        for child in children:
            # Check if already fed
            time_since_last_feed = datetime.utcnow() - child.last_fed_at
            if time_since_last_feed.total_seconds() < FEEDING_COOLDOWN_DAYS * 86400:
                already_fed_count += 1
                continue

            # Check balance
            if user.balance < FEEDING_COST:
                insufficient_funds_count += 1
                continue

            # Feed
            user.balance -= FEEDING_COST
            child.last_fed_at = datetime.utcnow()
            fed_count += 1

        logger.info(
            "Fed all children",
            marriage_id=marriage_id,
            user_id=user_id,
            fed=fed_count,
            already_fed=already_fed_count,
            insufficient=insufficient_funds_count,
        )

        return fed_count, already_fed_count, insufficient_funds_count

    @staticmethod
    def check_and_kill_starving_children(db: Session):
        """Background task: kill children who haven't been fed in 5+ days.

        Returns:
            List of tuples: [(child, parent1_id, parent2_id), ...]
        """
        threshold = datetime.utcnow() - timedelta(days=DEATH_THRESHOLD_DAYS)

        starving_children = db.query(Child).filter(Child.is_alive.is_(True), Child.last_fed_at < threshold).all()

        dead_children_info = []
        for child in starving_children:
            child.is_alive = False
            dead_children_info.append((child, child.parent1_id, child.parent2_id))
            logger.warning("Child died from starvation", child_id=child.id, last_fed_at=child.last_fed_at)

        return dead_children_info

    @staticmethod
    def age_up_child(db: Session, child_id: int, user_id: int) -> Tuple[bool, str]:
        """Age up a child to the next stage."""
        child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

        if not child:
            return False, "Ребёнок не найден"

        # Determine cost and next stage
        if child.age_stage == "infant":
            cost = AGE_INFANT_TO_CHILD_COST
            next_stage = "child"
        elif child.age_stage == "child":
            cost = AGE_CHILD_TO_TEEN_COST
            next_stage = "teen"
        else:
            return False, "Ребёнок уже подросток"

        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < cost:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(cost)})"

        # Charge
        user.balance -= cost

        # Age up
        child.age_stage = next_stage

        logger.info("Child aged up", child_id=child_id, new_stage=next_stage, user_id=user_id)

        return True, next_stage

    @staticmethod
    def enroll_in_school(db: Session, child_id: int, user_id: int) -> Tuple[bool, str]:
        """Enroll child in school (500 diamonds/month, +50% work bonus)."""
        child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

        if not child:
            return False, "Ребёнок не найден"

        if child.age_stage not in ("child", "teen"):
            return False, "Только дети и подростки могут учиться"

        # Check if already in school
        if child.is_in_school and child.school_expires_at and child.school_expires_at > datetime.utcnow():
            days_left = (child.school_expires_at - datetime.utcnow()).days
            return False, f"Уже учится (осталось {format_word(days_left, 'день', 'дня', 'дней')})"

        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < SCHOOL_COST:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(SCHOOL_COST)})"

        # Charge
        user.balance -= SCHOOL_COST

        # Enroll
        child.is_in_school = True
        child.school_expires_at = datetime.utcnow() + timedelta(days=SCHOOL_DURATION_DAYS)

        logger.info("Child enrolled in school", child_id=child_id, user_id=user_id)

        return True, ""

    @staticmethod
    def hire_babysitter(db: Session, marriage_id: int, user_id: int) -> Tuple[bool, str]:
        """Hire babysitter (1000 diamonds/week, auto-feeds all children)."""
        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Calculate total cost upfront: babysitter + feeding costs
        children = db.query(Child).filter(Child.marriage_id == marriage_id, Child.is_alive.is_(True)).all()
        hungry_count = 0
        for child in children:
            time_since_feed = datetime.utcnow() - child.last_fed_at
            if time_since_feed.total_seconds() >= FEEDING_COOLDOWN_DAYS * 86400:
                hungry_count += 1

        total_cost = BABYSITTER_COST + (hungry_count * FEEDING_COST)

        if user.balance < total_cost:
            return (
                False,
                f"Недостаточно алмазов (нужно {format_diamonds(total_cost)}: няня {format_diamonds(BABYSITTER_COST)} + кормление {format_diamonds(hungry_count * FEEDING_COST)})",
            )

        # Charge babysitter first
        user.balance -= BABYSITTER_COST

        # Feed all children who need it
        fed, already_fed, insufficient = ChildrenService.feed_all_children(db, marriage_id, user_id)

        logger.info("Babysitter hired", marriage_id=marriage_id, user_id=user_id, children_fed=fed)

        return True, f"Няня накормила {fed} детей"

    @staticmethod
    def work_teen(db: Session, child_id: int, user_id: int = None) -> Tuple[bool, str, int]:
        """Teen works and earns diamonds (30-60, +50% if in school)."""
        child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

        if not child:
            return False, "Ребёнок не найден", 0

        if child.age_stage != "teen":
            return False, "Только подростки могут работать", 0

        # Check cooldown
        if child.last_work_time:
            time_since_work = datetime.utcnow() - child.last_work_time
            if time_since_work.total_seconds() < TEEN_WORK_COOLDOWN:
                hours_left = (TEEN_WORK_COOLDOWN - time_since_work.total_seconds()) / 3600
                return False, f"Cooldown {hours_left:.1f}ч", 0

        # Calculate earnings
        base_earnings = random.randint(TEEN_WORK_MIN, TEEN_WORK_MAX)
        earnings = base_earnings

        # School bonus
        if child.is_in_school and child.school_expires_at and child.school_expires_at > datetime.utcnow():
            earnings = int(base_earnings * (1 + SCHOOL_WORK_BONUS))

        # Pay the initiating parent (fallback to parent1)
        parent_id = user_id if user_id in (child.parent1_id, child.parent2_id) else child.parent1_id
        parent = db.query(User).filter(User.telegram_id == parent_id).first()
        parent.balance += earnings

        # Update child
        child.last_work_time = datetime.utcnow()

        logger.info("Teen worked", child_id=child_id, earnings=earnings, school_bonus=child.is_in_school)

        return True, "", earnings

    @staticmethod
    def get_marriage_children(db: Session, marriage_id: int):
        """Get all children for a marriage."""
        return db.query(Child).filter(Child.marriage_id == marriage_id).order_by(Child.created_at).all()

    @staticmethod
    def toggle_child_work(db: Session, child_id: int) -> Tuple[bool, str, bool]:
        """Toggle child working status (only for teens).

        Returns:
            (success, error_message, new_is_working_status)
        """
        child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

        if not child:
            return False, "Ребёнок не найден", False

        if child.age_stage != "teen":
            return False, "Только подростки могут работать", False

        # Toggle work status
        child.is_working = not child.is_working

        # If enabling work, set last_work_time to allow immediate first payout
        if child.is_working and not child.last_work_time:
            child.last_work_time = datetime.utcnow() - timedelta(seconds=TEEN_AUTO_WORK_INTERVAL)

        logger.info("Child work toggled", child_id=child_id, is_working=child.is_working)

        return True, "", child.is_working

    @staticmethod
    def process_auto_work_for_child(db: Session, child_id: int) -> Tuple[bool, str, int]:
        """Process automatic work payout for a teen (called by scheduler).

        Returns:
            (success, error_message, earnings)
        """
        child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

        if not child:
            return False, "Ребёнок не найден", 0

        if child.age_stage != "teen":
            return False, "Только подростки могут работать", 0

        if not child.is_working:
            return False, "Ребёнок не работает", 0

        # Check if enough time has passed (4 hours)
        if child.last_work_time:
            time_since_work = datetime.utcnow() - child.last_work_time
            if time_since_work.total_seconds() < TEEN_AUTO_WORK_INTERVAL:
                return False, "Слишком рано", 0

        # Calculate earnings (20-50 diamonds)
        earnings = random.randint(TEEN_AUTO_WORK_MIN, TEEN_AUTO_WORK_MAX)

        # Pay parent1 (primary parent)
        parent = db.query(User).filter(User.telegram_id == child.parent1_id).first()
        if parent:
            parent.balance += earnings

        # Update child work time
        child.last_work_time = datetime.utcnow()

        logger.info("Child auto work processed", child_id=child_id, earnings=earnings, parent_id=child.parent1_id)

        return True, "", earnings

    @staticmethod
    def process_all_working_children(db: Session):
        """Process all working children (called by scheduler every 4 hours).

        Returns:
            List of tuples: [(child_id, parent_id, earnings), ...]
        """
        # Find all working teens
        working_children = (
            db.query(Child)
            .filter(Child.is_alive.is_(True), Child.age_stage == "teen", Child.is_working.is_(True))
            .all()
        )

        results = []
        for child in working_children:
            # Check if enough time has passed
            if child.last_work_time:
                time_since_work = datetime.utcnow() - child.last_work_time
                if time_since_work.total_seconds() < TEEN_AUTO_WORK_INTERVAL:
                    continue

            # Calculate earnings
            earnings = random.randint(TEEN_AUTO_WORK_MIN, TEEN_AUTO_WORK_MAX)

            # Pay parent
            parent = db.query(User).filter(User.telegram_id == child.parent1_id).first()
            if parent:
                parent.balance += earnings

            # Update work time
            child.last_work_time = datetime.utcnow()

            results.append((child.id, child.parent1_id, earnings))

            logger.info("Child auto work processed", child_id=child.id, earnings=earnings, parent_id=child.parent1_id)

        return results

    @staticmethod
    def get_child_info(child: Child) -> dict:
        """Format child info for display."""
        # Age emoji
        age_emojis = {"infant": "👶", "child": "🧒", "teen": "👦"}
        age_emoji = age_emojis.get(child.age_stage, "👤")

        # Gender emoji
        gender_emoji = "♂️" if child.gender == "male" else "♀️"

        # Status
        if not child.is_alive:
            status = "💀 Мёртв"
        else:
            # Check feeding status
            time_since_feed = datetime.utcnow() - child.last_fed_at
            days_without_food = time_since_feed.days

            if days_without_food >= DEATH_THRESHOLD_DAYS:
                status = "☠️ Умирает от голода"
            elif days_without_food >= FEEDING_COOLDOWN_DAYS:
                status = "🍽️ Голоден"
            else:
                status = "✅ Сыт"

        # School status
        school_status = ""
        if child.is_in_school and child.school_expires_at and child.school_expires_at > datetime.utcnow():
            days_left = (child.school_expires_at - datetime.utcnow()).days
            school_status = f"🎓 Учится ({days_left}д)"

        # Work status
        work_status = ""
        if child.age_stage == "teen" and child.is_working:
            work_status = "💼 Работает"

        return {
            "id": child.id,
            "name": html.escape(child.name),
            "age_emoji": age_emoji,
            "gender_emoji": gender_emoji,
            "age_stage": child.age_stage,
            "status": status,
            "school_status": school_status,
            "work_status": work_status,
            "is_alive": child.is_alive,
            "is_working": child.is_working,
            "last_fed_at": child.last_fed_at,
        }
