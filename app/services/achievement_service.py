"""Achievement service for checking and awarding achievements."""

import structlog

from app.database.connection import get_db
from app.database.models import Achievement, Business, Job, Marriage, UserAchievement

logger = structlog.get_logger()


class AchievementService:
    """Service for managing achievements."""

    @staticmethod
    def check_and_award(user_id: int, achievement_code: str) -> bool:
        """
        Check and award achievement to user if not already earned.

        Args:
            user_id: User Telegram ID
            achievement_code: Achievement code (e.g., "first_steps")

        Returns:
            True if awarded, False if already earned or achievement not found
        """
        with get_db() as db:
            achievement = db.query(Achievement).filter(Achievement.code == achievement_code).first()
            if not achievement:
                logger.warning("Achievement not found", code=achievement_code)
                return False

            existing = (
                db.query(UserAchievement)
                .filter(UserAchievement.user_id == user_id, UserAchievement.achievement_id == achievement.id)
                .first()
            )

            if not existing:
                user_achievement = UserAchievement(user_id=user_id, achievement_id=achievement.id)
                db.add(user_achievement)
                logger.info("Achievement awarded", user_id=user_id, achievement=achievement_code)
                return True

        return False

    @staticmethod
    def check_balance_achievements(user_id: int, balance: int):
        """Check and award balance-based achievements."""
        if balance >= 10000:
            AchievementService.check_and_award(user_id, "rich")
        if balance >= 100000:
            AchievementService.check_and_award(user_id, "tycoon")

    @staticmethod
    def check_work_achievements(user_id: int):
        """Check and award work-based achievements."""
        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()
            if job and job.times_worked >= 100:
                AchievementService.check_and_award(user_id, "hard_worker")

    @staticmethod
    def check_marriage_achievements(user_id: int):
        """Check and award marriage-based achievements."""
        with get_db() as db:
            marriage = (
                db.query(Marriage)
                .filter(
                    ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
                    Marriage.is_active.is_(True),
                )
                .first()
            )
            if marriage:
                AchievementService.check_and_award(user_id, "family_man")

    @staticmethod
    def check_business_achievements(user_id: int):
        """Check and award business-based achievements."""
        with get_db() as db:
            business_count = db.query(Business).filter(Business.user_id == user_id).count()
            if business_count >= 1:
                AchievementService.check_and_award(user_id, "businessman")
            if business_count >= 10:
                AchievementService.check_and_award(user_id, "empire")

    @staticmethod
    def check_all_achievements(user_id: int):
        """
        Check all possible achievements for a user.

        This is useful to call periodically or when displaying achievements.
        """
        with get_db() as db:
            from app.database.models import CasinoGame, Child, User

            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return

            # Balance achievements
            AchievementService.check_balance_achievements(user_id, user.balance)

            # Work achievements
            AchievementService.check_work_achievements(user_id)

            # Marriage achievements
            AchievementService.check_marriage_achievements(user_id)

            # Business achievements
            AchievementService.check_business_achievements(user_id)

            # Parent achievement
            children_count = (
                db.query(Child)
                .filter((Child.parent1_id == user_id) | (Child.parent2_id == user_id), Child.is_alive.is_(True))
                .count()
            )
            if children_count >= 1:
                AchievementService.check_and_award(user_id, "parent")

            # Casino achievements
            casino_games_count = db.query(CasinoGame).filter(CasinoGame.user_id == user_id).count()
            if casino_games_count >= 100:
                AchievementService.check_and_award(user_id, "gambler")

            # Lucky achievement (won big in casino)
            # This should be checked when user wins big in casino
