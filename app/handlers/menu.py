"""Menu navigation handlers."""

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu navigation callbacks."""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("menu:"):
        return

    if not update.effective_user:
        return

    parts = query.data.split(":")
    menu_type = parts[1]

    # Check button owner (user_id is last part)
    if len(parts) >= 3:
        owner_id = int(parts[2])
        clicker_id = update.effective_user.id

        if clicker_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    # Handle work menu (redirect to work command)
    if menu_type == "work":
        from app.database.connection import get_db
        from app.database.models import Job
        from app.handlers.work import JOB_TITLES
        from app.utils.keyboards import work_menu_keyboard

        user_id = update.effective_user.id

        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if job:
                job_name = JOB_TITLES[job.job_type][job.job_level - 1]
                profession_emoji = {
                    "interpol": "🚔",
                    "banker": "💳",
                    "infrastructure": "🏗️",
                    "court": "⚖️",
                    "culture": "🎭",
                    "selfmade": "🐦",
                }
                emoji = profession_emoji.get(job.job_type, "💼")

                # Название трека
                profession_names = {
                    "interpol": "Интерпол",
                    "banker": "Банкир",
                    "infrastructure": "Инфраструктура",
                    "court": "Суд",
                    "culture": "Культура",
                    "selfmade": "Селфмейд",
                }
                track_name = profession_names.get(job.job_type, "")

                # Следующая должность
                max_level = 6 if job.job_type == "selfmade" else 10
                if job.job_level < max_level:
                    next_title = JOB_TITLES[job.job_type][job.job_level]
                    next_level_text = f"📈 {next_title}"
                else:
                    next_level_text = "🏆 Максимум"

                await query.edit_message_text(
                    f"💼 {track_name}\n"
                    f"{emoji} {job_name} ({job.job_level}/{max_level})\n"
                    f"📊 {job.times_worked}\n"
                    f"{next_level_text}",
                    reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                )
            else:
                await query.edit_message_text(
                    "💼 Нет работы\n\nВыбери профессию:",
                    reply_markup=work_menu_keyboard(has_job=False, user_id=user_id),
                )
        return

    # Handle marriage menu
    if menu_type == "marriage":
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from app.database.connection import get_db
        from app.database.models import User
        from app.services.marriage_service import MarriageService
        from app.utils.formatters import format_diamonds

        user_id = update.effective_user.id

        with get_db() as db:
            marriage = MarriageService.get_active_marriage(db, user_id)

            if marriage:
                # Get partner info
                partner_id = MarriageService.get_partner_id(marriage, user_id)
                partner = db.query(User).filter(User.telegram_id == partner_id).first()
                user = db.query(User).filter(User.telegram_id == user_id).first()

                # Build keyboard
                keyboard = [
                    [
                        InlineKeyboardButton("💝 Подарить", callback_data=f"marriage_gift:{user_id}"),
                        InlineKeyboardButton("💔 Развод", callback_data=f"marriage_divorce:{user_id}"),
                    ],
                    [
                        InlineKeyboardButton("❤️ /makelove", callback_data=f"marriage_help_love:{user_id}"),
                        InlineKeyboardButton("📅 /date", callback_data=f"marriage_help_date:{user_id}"),
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Build message
                days_married = (marriage.created_at - marriage.created_at).days  # Will be calculated properly
                partner_name = partner.username or f"User{partner.telegram_id}"

                message = (
                    f"💍 <b>Брак</b>\n\n"
                    f"👫 @{partner_name}\n"
                    f"📅 {days_married} дней\n"
                    f"❤️ Любовь: {marriage.love_count} раз\n\n"
                    f"💰 Ты: {format_diamonds(user.balance)}\n"
                    f"💰 Партнёр: {format_diamonds(partner.balance)}"
                )

                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await query.edit_message_text("💔 Не в браке\n\n/propose — сделать предложение", parse_mode="HTML")
        return

    # Handle unimplemented menus
    unimplemented_menus = ["family", "house", "business"]

    if menu_type in unimplemented_menus:
        await query.answer("⚠️ Эта функция пока не реализована", show_alert=True)
        return

    # Handle profile menu (go back)
    if menu_type == "profile":
        # Simulate a profile command
        if update.effective_message:
            await update.effective_message.reply_text("/profile — профиль")


def register_menu_handlers(application):
    """Register menu handlers."""
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
