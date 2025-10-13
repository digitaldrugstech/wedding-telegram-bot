"""Children and family management handlers."""

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.services.children_service import (
    ADOPTION_COST,
    AGE_CHILD_TO_TEEN_COST,
    AGE_INFANT_TO_CHILD_COST,
    BABYSITTER_COST,
    FEEDING_COST,
    IVF_COST,
    SCHOOL_COST,
    ChildrenService,
)
from app.services.marriage_service import MarriageService
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()


@require_registered
async def family_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /family command - show family menu."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        marriage = MarriageService.get_active_marriage(db, user_id)

        if not marriage:
            await update.message.reply_text(
                "👨‍👩‍👧‍👦 <b>Семья</b>\n\nНужен брак чтобы завести детей", parse_mode="HTML"
            )
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

            for child in alive_children:
                info = ChildrenService.get_child_info(child)
                message += f"{info['age_emoji']} {info['name']} {info['gender_emoji']}\n" f"{info['status']}"
                if info["school_status"]:
                    message += f" | {info['school_status']}"
                message += "\n\n"
        else:
            message = "👨‍👩‍👧‍👦 <b>Семья</b>\n\nУ вас пока нет детей"

        # Build keyboard
        keyboard = [
            [InlineKeyboardButton("👶 Список детей", callback_data=f"family:list:{user_id}")],
            [InlineKeyboardButton("🍼 Родить ребёнка", callback_data=f"family:birth_menu:{user_id}")],
            [InlineKeyboardButton("🍽️ Покормить всех", callback_data=f"family:feed_all:{user_id}")],
            [InlineKeyboardButton("📈 Вырастить всех", callback_data=f"family:age_all:{user_id}")],
            [InlineKeyboardButton("👩‍🍼 Няня", callback_data=f"family:babysitter:{user_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def family_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle family menu callbacks."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    action = parts[1]

    # Check button owner
    if len(parts) >= 3:
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    with get_db() as db:
        marriage = MarriageService.get_active_marriage(db, user_id)

        if not marriage:
            await query.edit_message_text("👨‍👩‍👧‍👦 <b>Семья</b>\n\nНужен брак чтобы завести детей", parse_mode="HTML")
            return

        # Handle list children
        if action == "list":
            children = ChildrenService.get_marriage_children(db, marriage.id)

            if not children:
                await query.edit_message_text("👨‍👩‍👧‍👦 <b>Список детей</b>\n\nУ вас пока нет детей", parse_mode="HTML")
                return

            alive_children = [c for c in children if c.is_alive]

            message = "👨‍👩‍👧‍👦 <b>Список детей</b>\n\n"

            keyboard = []
            for child in alive_children:
                info = ChildrenService.get_child_info(child)
                button_text = f"{info['age_emoji']} {info['name']} {info['gender_emoji']}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"family:child:{child.id}:{user_id}")])

            keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"menu:family:{user_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")

        # Handle birth menu
        elif action == "birth_menu":
            message = (
                "🍼 <b>Родить ребёнка</b>\n\n"
                f"💉 ЭКО: {format_diamonds(IVF_COST)} (100% шанс)\n"
                f"👶 Усыновление: {format_diamonds(ADOPTION_COST)}\n\n"
                "💡 Требования: дом + оба работают + разные профессии"
            )

            keyboard = [
                [InlineKeyboardButton(f"💉 ЭКО ({format_diamonds(IVF_COST)})", callback_data=f"family:ivf:{user_id}")],
                [
                    InlineKeyboardButton(
                        f"👶 Усыновить ({format_diamonds(ADOPTION_COST)})", callback_data=f"family:adopt:{user_id}"
                    )
                ],
                [InlineKeyboardButton("« Назад", callback_data=f"menu:family:{user_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")

        # Handle IVF
        elif action == "ivf":
            success, error, child = ChildrenService.ivf_birth(db, marriage.id, user_id)

            if not success:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            info = ChildrenService.get_child_info(child)

            message = (
                f"✅ <b>ЭКО успешно!</b>\n\n"
                f"{info['age_emoji']} Родился {info['name']} {info['gender_emoji']}\n\n"
                f"💰 Потрачено: {format_diamonds(IVF_COST)}"
            )

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle adoption
        elif action == "adopt":
            success, error, child = ChildrenService.adopt_child(db, marriage.id, user_id)

            if not success:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            info = ChildrenService.get_child_info(child)

            message = (
                f"✅ <b>Усыновление успешно!</b>\n\n"
                f"{info['age_emoji']} Усыновили {info['name']} {info['gender_emoji']}\n\n"
                f"💰 Потрачено: {format_diamonds(ADOPTION_COST)}"
            )

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle feed all
        elif action == "feed_all":
            fed, already_fed, insufficient = ChildrenService.feed_all_children(db, marriage.id, user_id)

            message = "🍽️ <b>Покормить всех</b>\n\n"

            if fed > 0:
                message += f"✅ Накормлено: {fed}\n"
                message += f"💰 Потрачено: {format_diamonds(fed * FEEDING_COST)}\n\n"

            if already_fed > 0:
                message += f"⏰ Уже сыты: {already_fed}\n\n"

            if insufficient > 0:
                message += f"❌ Недостаточно алмазов для: {insufficient}\n\n"

            if fed == 0 and already_fed == 0 and insufficient == 0:
                message += "Нет детей для кормления"

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle age all
        elif action == "age_all":
            await query.edit_message_text(
                "📈 <b>Вырастить всех</b>\n\nВыбери конкретного ребёнка из списка", parse_mode="HTML"
            )

        # Handle babysitter
        elif action == "babysitter":
            success, message_text = ChildrenService.hire_babysitter(db, marriage.id, user_id)

            if not success:
                await query.edit_message_text(f"❌ {message_text}", parse_mode="HTML")
                return

            message = (
                f"✅ <b>Няня нанята</b>\n\n" f"{message_text}\n\n" f"💰 Потрачено: {format_diamonds(BABYSITTER_COST)}"
            )

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle child menu
        elif action == "child":
            child_id = int(parts[2])

            from app.database.models import Child

            child = db.query(Child).filter(Child.id == child_id, Child.is_alive.is_(True)).first()

            if not child:
                await query.edit_message_text("❌ Ребёнок не найден", parse_mode="HTML")
                return

            info = ChildrenService.get_child_info(child)

            message = (
                f"{info['age_emoji']} <b>{info['name']}</b> {info['gender_emoji']}\n\n"
                f"📊 Возраст: {info['age_stage']}\n"
                f"🍽️ Статус: {info['status']}\n"
            )

            if info["school_status"]:
                message += f"🎓 {info['school_status']}\n"

            keyboard = []

            # Feed button
            keyboard.append([InlineKeyboardButton("🍽️ Покормить", callback_data=f"family:feed:{child_id}:{user_id}")])

            # Age up button
            if child.age_stage == "infant":
                cost = AGE_INFANT_TO_CHILD_COST
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"📈 Вырастить до ребёнка ({format_diamonds(cost)})",
                            callback_data=f"family:age:{child_id}:{user_id}",
                        )
                    ]
                )
            elif child.age_stage == "child":
                cost = AGE_CHILD_TO_TEEN_COST
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"📈 Вырастить до подростка ({format_diamonds(cost)})",
                            callback_data=f"family:age:{child_id}:{user_id}",
                        )
                    ]
                )

            # School button (child or teen)
            if child.age_stage in ("child", "teen"):
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"🎓 Школа ({format_diamonds(SCHOOL_COST)}/мес)",
                            callback_data=f"family:school:{child_id}:{user_id}",
                        )
                    ]
                )

            # Work button (teen only)
            if child.age_stage == "teen":
                keyboard.append(
                    [InlineKeyboardButton("💰 Работать", callback_data=f"family:work:{child_id}:{user_id}")]
                )

            keyboard.append([InlineKeyboardButton("« Назад к списку", callback_data=f"family:list:{user_id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")

        # Handle feed child
        elif action == "feed":
            child_id = int(parts[2])

            success, error = ChildrenService.feed_child(db, child_id, user_id)

            if not success:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            message = f"✅ <b>Ребёнок накормлен</b>\n\n💰 Потрачено: {format_diamonds(FEEDING_COST)}"

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle age up
        elif action == "age":
            child_id = int(parts[2])

            success, result = ChildrenService.age_up_child(db, child_id, user_id)

            if not success:
                await query.edit_message_text(f"❌ {result}", parse_mode="HTML")
                return

            stage_names = {"child": "ребёнок", "teen": "подросток"}
            stage_name = stage_names.get(result, result)

            cost = AGE_INFANT_TO_CHILD_COST if result == "child" else AGE_CHILD_TO_TEEN_COST

            message = (
                f"✅ <b>Ребёнок вырос!</b>\n\n" f"Теперь: {stage_name}\n\n" f"💰 Потрачено: {format_diamonds(cost)}"
            )

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle school enrollment
        elif action == "school":
            child_id = int(parts[2])

            success, error = ChildrenService.enroll_in_school(db, child_id, user_id)

            if not success:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            message = (
                f"✅ <b>Ребёнок зачислен в школу</b>\n\n"
                f"Бонус к работе: +50%\n"
                f"Длительность: 30 дней\n\n"
                f"💰 Потрачено: {format_diamonds(SCHOOL_COST)}"
            )

            await query.edit_message_text(message, parse_mode="HTML")

        # Handle teen work
        elif action == "work":
            child_id = int(parts[2])

            success, error, earnings = ChildrenService.work_teen(db, child_id)

            if not success:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            message = f"✅ <b>Подросток поработал</b>\n\n💰 Заработано: {format_diamonds(earnings)}"

            await query.edit_message_text(message, parse_mode="HTML")


def register_children_handlers(application):
    """Register children handlers."""
    application.add_handler(CommandHandler("family", family_command))
    application.add_handler(CallbackQueryHandler(family_callback, pattern="^family:"))
