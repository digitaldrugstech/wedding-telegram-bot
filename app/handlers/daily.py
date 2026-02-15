"""Daily bonus command handler."""

from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word

logger = structlog.get_logger()

# Tips for feature discovery — shown one per day, rotating
DAILY_TIPS = [
    "💡 /propose @user — предложи руку и сердце!",
    "💡 /heist easy — ограбь банк с друзьями!",
    "💡 /roulette 100 — русская рулетка на алмазы",
    "💡 /duel @user 50 — вызови друга на дуэль",
    "💡 /rob @user — ограбь другого игрока (рискованно!)",
    "💡 /blackjack 100 — блэкджек против бота",
    "💡 /lottery — купи билет лотереи, джекпот растёт каждый день",
    "💡 /mine — добывай алмазы (прокачивай кирку!)",
    "💡 /fish — рыбалка с редким уловом и коллекцией",
    "💡 /business — купи бизнес и получай пассивный доход",
    "💡 /quest — ежедневные квесты за алмазы",
    "💡 /wheel — колесо фортуны, крути бесплатно раз в день",
    "💡 /scratch — скретч-карта, может повезти!",
    "💡 /gang create — создай банду с друзьями",
    "💡 /invite — пригласи друга и получи бонус",
    "💡 /pet — заведи питомца, качай уровень",
    "💡 /crate — сундуки за серию /daily",
    "💡 /house — купи дом (защита от похищений)",
    "💡 /coinflip @user 100 — монетка на алмазы",
    "💡 /bounty — назначь награду за голову",
]

# Streak rewards (day: diamonds)
STREAK_REWARDS = {
    1: 10,
    2: 15,
    3: 25,
    4: 35,
    5: 50,
    6: 75,
    7: 100,
}
# Days 8+ get the day 7 reward
MAX_STREAK_REWARD = 100

# Bonus milestones
MILESTONE_BONUSES = {
    7: 50,
    14: 150,
    30: 500,
}


def get_daily_reward(streak: int) -> int:
    """Calculate daily reward based on streak."""
    return STREAK_REWARDS.get(streak, MAX_STREAK_REWARD)


def get_milestone_bonus(streak: int) -> int:
    """Check if streak hits a milestone bonus."""
    return MILESTONE_BONUSES.get(streak, 0)


@require_registered
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /daily command — collect daily bonus."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        now = datetime.utcnow()

        # Check if already claimed today
        if user.last_daily_at:
            last_claim = user.last_daily_at
            # Same calendar day (UTC)
            if last_claim.date() == now.date():
                # Calculate time until next day
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                remaining = tomorrow - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)

                time_str = []
                if hours > 0:
                    time_str.append(f"{hours}ч")
                if minutes > 0:
                    time_str.append(f"{minutes}м")

                await update.message.reply_text(
                    f"⏰ Ты уже забрал бонус сегодня\n\n" f"Следующий через: {' '.join(time_str)}"
                )
                return

            # Check if streak continues (claimed yesterday)
            yesterday = (now - timedelta(days=1)).date()
            if last_claim.date() == yesterday:
                new_streak = user.daily_streak + 1
            else:
                # Streak broken
                new_streak = 1
        else:
            new_streak = 1

        # Calculate reward
        base_reward = get_daily_reward(new_streak)
        milestone = get_milestone_bonus(new_streak)
        reward = base_reward

        # Apply double income boost
        from app.handlers.premium import has_active_boost as _daily_has_boost

        daily_boosted = _daily_has_boost(user_id, "double_income", db=db)
        if daily_boosted:
            reward = base_reward * 2

        total = reward + milestone

        # Update user
        user.balance += total
        user.daily_streak = new_streak
        user.last_daily_at = now

        balance = user.balance

    # Build message
    streak_bar = "🔥" * min(new_streak, 7) + "⬜" * max(0, 7 - new_streak)

    text = (
        f"🎁 <b>Ежедневный бонус</b>\n\n"
        f"💎 +{format_diamonds(reward)}\n"
        f"📅 Серия: {format_word(new_streak, 'день', 'дня', 'дней')}\n"
        f"{streak_bar}\n"
    )

    if milestone > 0:
        text += (
            f"\n🏆 <b>Бонус за {format_word(new_streak, 'день', 'дня', 'дней')}!</b> +{format_diamonds(milestone)}\n"
        )

    text += f"\n💰 Баланс: {format_diamonds(balance)}"

    # Show next milestone
    next_milestones = [d for d in sorted(MILESTONE_BONUSES.keys()) if d > new_streak]
    if next_milestones:
        next_m = next_milestones[0]
        days_left = next_m - new_streak
        text += f"\n\n📌 До бонуса x{MILESTONE_BONUSES[next_m]}: {format_word(days_left, 'день', 'дня', 'дней')}"

    # Show next crate milestone
    from app.handlers.crate import CRATE_MILESTONES

    next_crates = [d for d in sorted(CRATE_MILESTONES.keys()) if d > new_streak]
    if next_crates:
        next_c = next_crates[0]
        crate_days = next_c - new_streak
        text += f"\n🎁 До сундука: {format_word(crate_days, 'день', 'дня', 'дней')} (/crate)"

    # VIP nudge — show what double income would have given (throttled)
    from app.handlers.premium import build_premium_nudge

    if daily_boosted:
        text += f"\n\n👑 <b>VIP бонус:</b> +{format_diamonds(base_reward)} (x2)"
    else:
        nudge = build_premium_nudge("daily", user_id)
        if nudge:
            text += nudge

    # Show today's quests (compact)
    try:
        from app.handlers.quest import assign_daily_quests

        with get_db() as db:
            assign_daily_quests(user_id, db=db)
            db.flush()
            from app.database.models import Quest, UserQuest

            today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
            user_quests = (
                db.query(UserQuest, Quest)
                .join(Quest)
                .filter(UserQuest.user_id == user_id, UserQuest.assigned_at >= today_start)
                .order_by(UserQuest.is_completed, UserQuest.assigned_at)
                .all()
            )
            if user_quests:
                text += "\n\n📋 <b>Квесты:</b>"
                for uq, q in user_quests:
                    icon = "✅" if uq.is_completed else "⏳"
                    text += f"\n{icon} {q.description} ({uq.progress}/{q.target_count})"
    except Exception:
        pass

    # Tip of the day — rotate through tips based on streak
    tip = DAILY_TIPS[new_streak % len(DAILY_TIPS)]
    text += f"\n\n{tip}"

    await update.message.reply_text(text, parse_mode="HTML")

    # Check for streak crate
    try:
        from app.handlers.crate import check_streak_crate, open_crate_and_announce

        if check_streak_crate(new_streak):
            crate_text = await open_crate_and_announce(update, context, user_id, new_streak)
            if crate_text:
                await update.message.reply_text(crate_text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to open streak crate", error=str(e))

    try:
        update_quest_progress(user_id, "daily")
    except Exception:
        pass

    # Award loyalty point
    try:
        from app.handlers.premium import add_loyalty_points

        add_loyalty_points(user_id, 1)
    except Exception:
        pass

    logger.info("Daily claimed", user_id=user_id, streak=new_streak, reward=total)


def register_daily_handlers(application):
    """Register daily handlers."""
    application.add_handler(CommandHandler("daily", daily_command))
    logger.info("Daily handlers registered")
