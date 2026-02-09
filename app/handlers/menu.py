"""Menu navigation handlers."""

from datetime import datetime

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.utils.telegram_helpers import safe_edit_message


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
        from app.handlers.work import JOB_TITLES, PROFESSION_EMOJI, PROFESSION_NAMES
        from app.utils.keyboards import work_menu_keyboard

        user_id = update.effective_user.id

        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if job:
                job_name = JOB_TITLES[job.job_type][job.job_level - 1]
                emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
                track_name = PROFESSION_NAMES.get(job.job_type, "")

                # Следующая должность
                max_level = 6 if job.job_type == "selfmade" else 10
                if job.job_level < max_level:
                    next_title = JOB_TITLES[job.job_type][job.job_level]
                    next_level_text = f"📈 {next_title}"
                else:
                    next_level_text = "🏆 Максимум"

                await safe_edit_message(
                    query,
                    f"💼 {track_name}\n"
                    f"{emoji} {job_name} ({job.job_level}/{max_level})\n"
                    f"📊 {job.times_worked}\n"
                    f"{next_level_text}",
                    reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                )
            else:
                await safe_edit_message(
                    query,
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
                days_married = (datetime.utcnow() - marriage.created_at).days
                partner_name = partner.username or f"User{partner.telegram_id}"

                message = (
                    f"💍 <b>Брак</b>\n\n"
                    f"👫 @{partner_name}\n"
                    f"📅 {days_married} дней\n"
                    f"❤️ Любовь: {marriage.love_count} раз\n\n"
                    f"💰 Ты: {format_diamonds(user.balance)}\n"
                    f"💰 Партнёр: {format_diamonds(partner.balance)}"
                )

                await safe_edit_message(query, message, reply_markup=reply_markup)
            else:
                await safe_edit_message(query, "💔 Не в браке\n\n/propose — сделать предложение")
        return

    # Handle house menu
    if menu_type == "house":
        from app.database.connection import get_db
        from app.database.models import House, Marriage
        from app.services.house_service import HouseService
        from app.utils.keyboards import house_menu_keyboard

        user_id = update.effective_user.id

        with get_db() as db:
            # Check if user is married
            marriage = (
                db.query(Marriage)
                .filter(
                    (Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id),
                    Marriage.is_active.is_(True),
                )
                .first()
            )

            if not marriage:
                await safe_edit_message(query, "🏠 <b>Дом</b>\n\nНужен брак чтобы купить дом")
                return

            # Check if has house
            house = db.query(House).filter(House.marriage_id == marriage.id).first()

            if house:
                house_info = HouseService.get_house_info(db, house.id)
                from app.utils.formatters import format_diamonds

                message = (
                    f"🏠 <b>Твой дом</b>\n\n"
                    f"{house_info['name']}\n"
                    f"💰 Куплен за: {format_diamonds(house_info['price'])}\n"
                    f"🛡️ Защита: {house_info['protection']}%"
                )

                await safe_edit_message(
                    query, message, reply_markup=house_menu_keyboard(has_house=True, user_id=user_id)
                )
            else:
                await safe_edit_message(
                    query,
                    "🏠 <b>Дом</b>\n\nУ семьи нет дома\n\n💡 Дом защищает детей от похищения",
                    reply_markup=house_menu_keyboard(has_house=False, user_id=user_id),
                )
        return

    # Handle business menu
    if menu_type == "business":
        from app.database.connection import get_db
        from app.services.business_service import BusinessService
        from app.utils.formatters import format_diamonds
        from app.utils.keyboards import business_menu_keyboard

        user_id = update.effective_user.id

        with get_db() as db:
            businesses = BusinessService.get_user_businesses(db, user_id)

            if businesses:
                message = "<b>💼 Твои бизнесы</b>\n\n"
                total_income = 0

                for business in businesses:
                    message += f"{business['name']}\n" f"📈 {format_diamonds(business['weekly_payout'])}/неделя\n\n"
                    total_income += business["weekly_payout"]

                message += f"💰 <b>Итого:</b> {format_diamonds(total_income)}/неделя"
            else:
                message = "💼 <b>Бизнесы</b>\n\nУ тебя нет бизнесов\n\n💡 Пассивный доход раз в неделю"

            await safe_edit_message(query, message, reply_markup=business_menu_keyboard(user_id=user_id))
        return

    # Handle casino menu
    if menu_type == "casino":
        from app.services.casino_service import MAX_BET, MIN_BET
        from app.utils.formatters import format_diamonds

        user_id = update.effective_user.id

        message = (
            "<b>🎰 Казино</b>\n\n"
            f"Ставка: {format_diamonds(MIN_BET)} - {format_diamonds(MAX_BET)}\n\n"
            "<b>Игры:</b>\n"
            "🎰 /slots [ставка] — Слот-машина (до x30)\n"
            "🎲 /dice [ставка] — Кости (до x3)\n"
            "🎯 /darts [ставка] — Дартс (до x5)\n"
            "🏀 /basketball [ставка] — Баскетбол (до x3)\n"
            "🎳 /bowling [ставка] — Боулинг (до x4)\n"
            "⚽ /football [ставка] — Футбол (до x3)\n"
            "🃏 /blackjack [ставка] — Блэкджек (до x2.5)\n"
            "🎫 /scratch [ставка] — Скретч-карта (до x5)\n\n"
            "💡 Выигрыш зависит от результата"
        )

        await safe_edit_message(query, message)
        return

    # Handle family menu
    if menu_type == "family":
        from app.database.connection import get_db
        from app.database.models import Marriage
        from app.services.children_service import ChildrenService
        from app.services.marriage_service import MarriageService

        user_id = update.effective_user.id

        with get_db() as db:
            marriage = MarriageService.get_active_marriage(db, user_id)

            if not marriage:
                await safe_edit_message(query, "👨‍👩‍👧‍👦 <b>Семья</b>\n\nНужен брак чтобы завести детей")
                return

            # Get children
            children = ChildrenService.get_marriage_children(db, marriage.id)

            # Build message
            if children:
                alive_children = [c for c in children if c.is_alive]
                dead_children = [c for c in children if not c.is_alive]

                message = "👨‍👩‍👧‍👦 <b>Семья</b>\n\n"
                message += f"👶 Детей: {len(alive_children)}\n"

                if dead_children:
                    message += f"💀 Умерло: {len(dead_children)}\n"

                message += "\n<b>Дети:</b>\n"

                for child in alive_children[:3]:  # Show first 3
                    info = ChildrenService.get_child_info(child)
                    message += f"{info['age_emoji']} {info['name']} {info['gender_emoji']}\n" f"{info['status']}"
                    if info["school_status"]:
                        message += f" | {info['school_status']}"
                    message += "\n\n"

                if len(alive_children) > 3:
                    message += f"... и ещё {len(alive_children) - 3}\n\n"

                message += "/family — полное меню"
            else:
                message = "👨‍👩‍👧‍👦 <b>Семья</b>\n\nУ тебя пока нет детей\n\n/family — завести детей"

            await safe_edit_message(query, message)
        return

    # Handle profile menu (go back)
    if menu_type == "profile":
        # Simulate a profile command
        if update.effective_message:
            await update.effective_message.reply_text("/profile — профиль")


def register_menu_handlers(application):
    """Register menu handlers."""
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
