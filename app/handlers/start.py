"""Start and profile handlers."""

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Job, User
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import gender_selection_keyboard, profile_keyboard


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user:
            # User already registered
            await update.message.reply_text(
                f"👋 Снова привет, {username}\n\n"
                f"💰 Баланс: {format_diamonds(user.balance)}\n\n"
                f"Открой /profile",
                reply_markup=profile_keyboard(),
            )
        else:
            # New user registration
            await update.message.reply_text(
                f"👋 Привет, {username}\n\n"
                f"Это Wedding Bot — симулятор семейной жизни на сервере\n\n"
                f"💍 Женись или выходи замуж\n"
                f"👶 Заводи детей\n"
                f"💼 Работай, получай зарплату\n"
                f"🏠 Покупай дом\n"
                f"💰 Открывай бизнес\n\n"
                f"Выбери пол:",
                reply_markup=gender_selection_keyboard(user_id),
            )


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

    gender_emoji = "♂️" if gender == "male" else "♀️"
    await query.edit_message_text(
        f"✅ Готово {gender_emoji}\n\n"
        f"Ты зарегистрирован\n"
        f"Стартовый баланс: {format_diamonds(0)}\n\n"
        f"/profile — твой профиль\n"
        f"/work — устройся на работу",
        reply_markup=profile_keyboard(),
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
            job_names = {
                "interpol": "🚔 Интерпол",
                "banker": "💳 Банкир",
                "infrastructure": "🏗️ Инфраструктура",
                "court": "⚖️ Суд",
                "culture": "🎭 Культура",
            }
            job_info = f"{job_names.get(job.job_type, job.job_type)} (уровень {job.job_level})"

        # Get marriage info
        # TODO: Query marriages when marriage system is implemented
        marriage_info = "Не в браке"

        # Get children count
        # TODO: Query children when children system is implemented
        children_count = 0

        gender_emoji = "♂️" if user.gender == "male" else "♀️"

        profile_text = (
            f"👤 Профиль: {user.username} {gender_emoji}\n"
            f"🆔 ID: {user.telegram_id}\n"
            f"🎮 Аккаунт на сервере: не привязан\n\n"
            f"💰 Баланс: {format_diamonds(user.balance)}\n"
            f"💼 Работа: {job_info}\n"
            f"💍 Брак: {marriage_info}\n"
            f"👶 Детей: {children_count}\n\n"
            f"📅 В игре с {user.created_at.strftime('%d.%m.%Y')}"
        )

        await update.message.reply_text(profile_text, reply_markup=profile_keyboard())


def register_start_handlers(application):
    """Register start and profile handlers."""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CallbackQueryHandler(gender_selection_callback, pattern="^gender:"))
