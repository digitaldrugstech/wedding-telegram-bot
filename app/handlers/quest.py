"""Quest command handlers."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Quest, User, UserQuest
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Quest templates
QUEST_TEMPLATES = {
    "work": [
        ("Поработай {count} раз", [3, 5], [100, 150]),
    ],
    "casino": [
        ("Сыграй в казино {count} раз", [5, 10], [100, 200]),
    ],
    "transfer": [
        ("Переведи {count} алмазов другим игрокам", [100, 200], [50, 100]),
    ],
    "marriage": [
        ("Сходи на свидание {count} раз", [2, 3], [150, 200]),
    ],
    "pet": [
        ("Покорми питомца {count} раз", [3, 5], [50, 100]),
    ],
    "fish": [
        ("Порыбачь {count} раз", [3, 5], [80, 120]),
    ],
    "duel": [
        ("Выиграй дуэли ({count} шт)", [1, 2], [150, 250]),
    ],
    "rob": [
        ("Ограбь игроков ({count} раз)", [1, 2], [100, 200]),
    ],
    "bounty": [
        ("Назначь награды ({count} шт)", [1, 2], [100, 150]),
    ],
    "daily": [
        ("Получи ежедневный бонус {count} раз", [1, 1], [50, 50]),
    ],
}


def initialize_quests():
    """Initialize quest templates in database. Adds new types on each startup."""
    with get_db() as db:
        existing_types = set(row[0] for row in db.query(Quest.quest_type).distinct().all())

        added = 0
        for quest_type, templates in QUEST_TEMPLATES.items():
            if quest_type in existing_types:
                continue
            for description, counts, rewards in templates:
                for i in range(len(counts)):
                    quest = Quest(
                        quest_type=quest_type,
                        description=description.format(count=counts[i]),
                        target_count=counts[i],
                        reward=rewards[i],
                    )
                    db.add(quest)
                    added += 1

        if added > 0:
            logger.info("Added new quest templates", count=added)


def assign_daily_quests(user_id: int):
    """Assign 3 random quests to user for the day."""
    with get_db() as db:
        # Check if user already has quests assigned today
        today = datetime.utcnow().date()
        existing_quests = (
            db.query(UserQuest)
            .filter(
                UserQuest.user_id == user_id,
                UserQuest.assigned_at >= datetime.combine(today, datetime.min.time()),
            )
            .count()
        )

        if existing_quests > 0:
            return  # Already assigned today

        # Get 3 random quests
        all_quests = db.query(Quest).all()
        if len(all_quests) < 3:
            logger.error("Not enough quests in database", count=len(all_quests))
            return

        selected_quests = random.sample(all_quests, 3)

        # Assign to user
        for quest in selected_quests:
            user_quest = UserQuest(user_id=user_id, quest_id=quest.id, progress=0, is_completed=False)
            db.add(user_quest)

        logger.info("Assigned daily quests", user_id=user_id, count=3)


def update_quest_progress(user_id: int, quest_type: str, increment: int = 1):
    """Update progress for user's active quests of given type."""
    with get_db() as db:
        user_quests = (
            db.query(UserQuest, Quest)
            .join(Quest)
            .filter(
                UserQuest.user_id == user_id,
                UserQuest.is_completed.is_(False),
                Quest.quest_type == quest_type,
            )
            .all()
        )

        for user_quest, quest in user_quests:
            user_quest.progress += increment

            # Check if completed
            if user_quest.progress >= quest.target_count:
                user_quest.is_completed = True
                user_quest.completed_at = datetime.utcnow()

                # Award reward (with double income boost)
                user = db.query(User).filter(User.telegram_id == user_id).first()
                if user:
                    reward_amount = quest.reward
                    from app.handlers.premium import has_active_boost

                    if has_active_boost(user_id, "double_income", db=db):
                        reward_amount *= 2
                    user.balance += reward_amount
                    logger.info(
                        "Quest completed",
                        user_id=user_id,
                        quest_id=quest.id,
                        reward=quest.reward,
                    )

                    # Award 2 loyalty points for quest completion
                    try:
                        from app.handlers.premium import add_loyalty_points

                        add_loyalty_points(user_id, 2)
                    except Exception:
                        pass


@require_registered
async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show daily quests (/quest)."""
    user_id = update.effective_user.id

    # Assign daily quests if needed
    assign_daily_quests(user_id)

    with get_db() as db:
        # Get user's active quests for today
        today = datetime.utcnow().date()
        user_quests = (
            db.query(UserQuest, Quest)
            .join(Quest)
            .filter(
                UserQuest.user_id == user_id,
                UserQuest.assigned_at >= datetime.combine(today, datetime.min.time()),
            )
            .order_by(UserQuest.is_completed, UserQuest.assigned_at)
            .all()
        )

        if not user_quests:
            await update.message.reply_text("Квесты обновятся завтра в полночь")
            return

        # Build quest list
        text = "📋 <b>Дневные квесты</b>\n\n"

        for user_quest, quest in user_quests:
            status = "✅" if user_quest.is_completed else "⏳"
            progress = f"{user_quest.progress}/{quest.target_count}"
            reward_str = format_diamonds(quest.reward)

            text += f"{status} {quest.description}\n"
            text += f"   Прогресс: {progress} | Награда: {reward_str}\n\n"

        # Calculate time until midnight
        tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
        time_left = tomorrow - datetime.utcnow()
        hours, remainder = divmod(time_left.total_seconds(), 3600)
        minutes = remainder // 60

        text += f"⏰ Обновление через {int(hours)}ч {int(minutes)}м"

        await update.message.reply_text(text, parse_mode="HTML")


def register_quest_handlers(application):
    """Register quest handlers."""
    application.add_handler(CommandHandler("quest", quest_command))
    logger.info("Quest handlers registered")
