"""Start and profile handlers."""

from sqlalchemy import func
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Business, Child, Job, User, UserAchievement
from app.handlers.work import PROFESSION_EMOJI, PROFESSION_NAMES
from app.services.business_service import BUSINESS_TYPES, BusinessService
from app.services.marriage_service import MarriageService
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import profile_keyboard
from app.utils.telegram_helpers import safe_edit_message


@button_owner_only
async def gender_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gender selection callback."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    gender = query.data.split(":")[1]  # "gender:male:user_id" -> "male"

    is_new_user = False
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user:
            # Update gender
            user.gender = gender
            user.username = username
        else:
            # Create new user
            user = User(telegram_id=user_id, username=username, gender=gender, balance=0)
            db.add(user)
            is_new_user = True

    # Award "first_steps" achievement for new users
    if is_new_user:
        from app.handlers.social import check_and_award_achievement

        check_and_award_achievement(user_id, "first_steps")

    gender_emoji = "♂️" if gender == "male" else "♀️"
    await safe_edit_message(
        query,
        f"✅ {gender_emoji} Регистрация завершена\n\n" f"/profile — профиль\n" f"/work — работа",
        reply_markup=profile_keyboard(user_id),
    )


@require_registered
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            return

        # Get job info
        job = db.query(Job).filter(Job.user_id == user_id).first()
        job_info = "Нет работы"
        if job:
            emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
            name = PROFESSION_NAMES.get(job.job_type, job.job_type)
            job_info = f"{emoji} {name} (уровень {job.job_level})"

        # Get business info
        businesses = BusinessService.get_user_businesses(db, user_id)
        if businesses:
            total_income = sum(b["weekly_payout"] for b in businesses)
            business_info = f"{len(businesses)} бизнесов (+{format_diamonds(total_income)}/нед)"
        else:
            business_info = "Нет бизнесов"

        # Get marriage info
        marriage = MarriageService.get_active_marriage(db, user_id)
        if marriage:
            partner_id = MarriageService.get_partner_id(marriage, user_id)
            partner = db.query(User).filter(User.telegram_id == partner_id).first()
            partner_name = partner.username if partner else f"User{partner_id}"
            marriage_info = f"Женат/Замужем (@{partner_name})"
        else:
            marriage_info = "Не в браке"

        # Get children count
        children_count = (
            db.query(Child)
            .filter((Child.parent1_id == user_id) | (Child.parent2_id == user_id), Child.is_alive.is_(True))
            .count()
        )

        # Get achievements count
        achievements_count = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).count()

        gender_emoji = "♂️" if user.gender == "male" else "♀️"
        rep_emoji = "⭐" if user.reputation >= 0 else "💀"

        # Title display
        title_display = ""
        if user.active_title:
            from app.handlers.shop import SHOP_TITLES

            title_info = SHOP_TITLES.get(user.active_title)
            if title_info:
                title_display = f" | {title_info['display']}"

        # Prestige display
        prestige_display = ""
        prestige = user.prestige_level or 0
        if prestige > 0:
            from app.handlers.prestige import get_prestige_display

            prestige_display = f"\n🔄 Престиж: {get_prestige_display(prestige)} (+{prestige * 5}% доход)"

        profile_text = (
            f"👤 {user.username} {gender_emoji}{title_display}\n"
            f"🎮 Сервер: не привязан\n\n"
            f"💰 {format_diamonds(user.balance)}\n"
            f"💼 {job_info}\n"
            f"🏢 {business_info}\n"
            f"💍 {marriage_info}\n"
            f"👶 Детей: {children_count}\n"
            f"{rep_emoji} Репутация: {user.reputation:+d}\n"
            f"🏆 Достижений: {achievements_count}{prestige_display}\n\n"
            f"📅 С {user.created_at.strftime('%d.%m.%Y')}"
        )

        await update.message.reply_text(profile_text, reply_markup=profile_keyboard(user_id))


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /top command - show leaderboards."""
    if not update.effective_user or not update.message:
        return

    with get_db() as db:
        # Top by balance
        top_balance = db.query(User).filter(User.is_banned.is_(False)).order_by(User.balance.desc()).limit(10).all()

        # Build message
        message = "🏆 <b>Топ по балансу</b>\n\n"

        for i, user in enumerate(top_balance, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            username = user.username or f"User{user.telegram_id}"
            message += f"{medal} @{username} — {format_diamonds(user.balance)}\n"

        if not top_balance:
            message += "Пусто\n"

        message += "\n💡 /profile — твой профиль"

        await update.message.reply_text(message, parse_mode="HTML")


def register_start_handlers(application):
    """Register start and profile handlers."""
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CallbackQueryHandler(gender_selection_callback, pattern="^gender:"))
