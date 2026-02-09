"""Achievement service for checking and awarding achievements."""

import structlog

from app.database.connection import get_db
from app.database.models import Achievement, Business, Job, Marriage, UserAchievement

logger = structlog.get_logger()


class AchievementService:
    """Service for managing achievements."""

    @staticmethod
    def check_and_award(user_id: int, achievement_code: str, db=None) -> bool:
        """
        Check and award achievement to user if not already earned.

        Pass an existing db session to avoid opening a nested one.
        """

        def _award(session):
            achievement = session.query(Achievement).filter(Achievement.code == achievement_code).first()
            if not achievement:
                return False

            existing = (
                session.query(UserAchievement)
                .filter(UserAchievement.user_id == user_id, UserAchievement.achievement_id == achievement.id)
                .first()
            )

            if not existing:
                session.add(UserAchievement(user_id=user_id, achievement_id=achievement.id))
                logger.info("Achievement awarded", user_id=user_id, achievement=achievement_code)
                return True
            return False

        if db is not None:
            return _award(db)
        with get_db() as session:
            return _award(session)

    @staticmethod
    def check_balance_achievements(user_id: int, balance: int, db=None):
        """Check and award balance-based achievements."""
        if balance >= 10000:
            AchievementService.check_and_award(user_id, "rich", db=db)
        if balance >= 100000:
            AchievementService.check_and_award(user_id, "tycoon", db=db)

    @staticmethod
    def check_work_achievements(user_id: int, db=None):
        """Check and award work-based achievements."""

        def _check(session):
            job = session.query(Job).filter(Job.user_id == user_id).first()
            if job and job.times_worked >= 100:
                AchievementService.check_and_award(user_id, "hard_worker", db=session)

        if db is not None:
            _check(db)
        else:
            with get_db() as session:
                _check(session)

    @staticmethod
    def check_marriage_achievements(user_id: int, db=None):
        """Check and award marriage-based achievements."""

        def _check(session):
            marriage = (
                session.query(Marriage)
                .filter(
                    ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
                    Marriage.is_active.is_(True),
                )
                .first()
            )
            if marriage:
                AchievementService.check_and_award(user_id, "family_man", db=session)

        if db is not None:
            _check(db)
        else:
            with get_db() as session:
                _check(session)

    @staticmethod
    def check_business_achievements(user_id: int, db=None):
        """Check and award business-based achievements."""

        def _check(session):
            business_count = session.query(Business).filter(Business.user_id == user_id).count()
            if business_count >= 1:
                AchievementService.check_and_award(user_id, "businessman", db=session)
            if business_count >= 10:
                AchievementService.check_and_award(user_id, "empire", db=session)

        if db is not None:
            _check(db)
        else:
            with get_db() as session:
                _check(session)

    @staticmethod
    def check_all_achievements(user_id: int, db=None):
        """
        Check all possible achievements for a user.

        This is useful to call periodically or when displaying achievements.
        """

        def _check_all(session):
            from app.database.models import CasinoGame, Child, User

            user = session.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return

            # Balance achievements
            AchievementService.check_balance_achievements(user_id, user.balance, db=session)

            # Work achievements
            AchievementService.check_work_achievements(user_id, db=session)

            # Marriage achievements
            AchievementService.check_marriage_achievements(user_id, db=session)

            # Business achievements
            AchievementService.check_business_achievements(user_id, db=session)

            # Parent achievement
            children_count = (
                session.query(Child)
                .filter((Child.parent1_id == user_id) | (Child.parent2_id == user_id), Child.is_alive.is_(True))
                .count()
            )
            if children_count >= 1:
                AchievementService.check_and_award(user_id, "parent", db=session)

            # Casino achievements
            casino_games_count = session.query(CasinoGame).filter(CasinoGame.user_id == user_id).count()
            if casino_games_count >= 100:
                AchievementService.check_and_award(user_id, "gambler", db=session)

            # Lucky achievement (won big in casino)
            # This should be checked when user wins big in casino

        if db is not None:
            _check_all(db)
        else:
            with get_db() as session:
                _check_all(session)
