"""Menu navigation handlers."""

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu navigation callbacks."""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("menu:"):
        return

    menu_type = query.data.split(":")[1]

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
                    next_level_text = f"📈 Следующая должность: {next_title}"
                else:
                    next_level_text = "🏆 Максимальный уровень достигнут"

                await query.edit_message_text(
                    f"💼 Твоя работа:\n\n"
                    f"🎯 Трек: {track_name}\n"
                    f"{emoji} Должность: {job_name} (уровень {job.job_level}/{max_level})\n"
                    f"📊 Отработано смен: {job.times_worked}\n"
                    f"{next_level_text}\n\n"
                    f"Выбери действие:",
                    reply_markup=work_menu_keyboard(has_job=True),
                )
            else:
                await query.edit_message_text(
                    "💼 У тебя нет работы!\n\n"
                    "Выберите профессию чтобы начать работать:",
                    reply_markup=work_menu_keyboard(has_job=False),
                )
        return

    # Handle marriage menu
    if menu_type == "marriage":
        from app.database.connection import get_db
        from app.database.models import Marriage, User
        from app.services.marriage_service import MarriageService
        from app.utils.formatters import format_diamonds
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
                        InlineKeyboardButton("💔 Развод", callback_data=f"marriage_divorce:{user_id}")
                    ],
                    [
                        InlineKeyboardButton("❤️ /makelove", callback_data=f"marriage_help_love:{user_id}"),
                        InlineKeyboardButton("📅 /date", callback_data=f"marriage_help_date:{user_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Build message
                days_married = (marriage.created_at - marriage.created_at).days  # Will be calculated properly
                partner_name = partner.username or f"User{partner.telegram_id}"

                message = (
                    f"💍 <b>Твой брак</b>\n\n"
                    f"👫 <b>Супруг/Супруга:</b> @{partner_name}\n"
                    f"📅 <b>В браке:</b> {days_married} дней\n"
                    f"❤️ <b>Занимались любовью:</b> {marriage.love_count} раз\n\n"
                    f"💰 <b>Твой баланс:</b> {format_diamonds(user.balance)}\n"
                    f"💰 <b>Баланс супруга:</b> {format_diamonds(partner.balance)}"
                )

                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await query.edit_message_text(
                    "💔 Ты не женат/замужем\n\n"
                    "Используй /propose чтобы сделать предложение",
                    parse_mode="HTML"
                )
        return

    # Handle unimplemented menus
    unimplemented_menus = ["family", "house", "business"]

    if menu_type in unimplemented_menus:
        await query.answer("⚠️ Эта функция пока не реализована", show_alert=True)
        return

    # Handle profile menu (go back)
    if menu_type == "profile":
        from app.handlers.start import profile_command
        # Simulate a profile command
        if update.effective_message:
            # Create a fake message update to reuse profile_command
            await update.effective_message.reply_text("Используйте /profile для просмотра профиля.")


def register_menu_handlers(application):
    """Register menu handlers."""
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
