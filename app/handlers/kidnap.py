"""Kidnapping handler — kidnap children from other families."""

import html
import random
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Child, Cooldown, House, Kidnapping, Marriage, User
from app.services.marriage_service import MarriageService
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

KIDNAP_COOLDOWN_HOURS = 6
RANSOM_BASE = 500
RANSOM_PER_STAGE = {"infant": 500, "child": 1000, "teen": 2000}
KIDNAP_SUCCESS_CHANCE_NO_HOUSE = 60  # % success without house
KIDNAP_SUCCESS_CHANCE_WITH_HOUSE = 30  # % success with house
KIDNAP_FAIL_FINE = 300  # fine on failure


@require_registered
async def kidnap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kidnap — reply to someone to kidnap their child."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Must reply to target
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text("❌ Зареплай на сообщение жертвы\n\n/kidnap (реплай)")
        return

    target_id = update.message.reply_to_message.from_user.id
    target_name = (
        update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
    )

    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя похитить своего ребёнка")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "kidnap").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours}ч")
            if minutes > 0:
                time_parts.append(f"{minutes}м")
            await update.message.reply_text(f"⏰ Можешь похитить через {' '.join(time_parts)}")
            return

        # Check if user already has an active kidnapping
        active_kidnapping = (
            db.query(Kidnapping).filter(Kidnapping.kidnapper_id == user_id, Kidnapping.is_active.is_(True)).first()
        )
        if active_kidnapping:
            await update.message.reply_text("❌ У тебя уже есть похищенный ребёнок\n\n/release — отпустить")
            return

        # Find target's marriage
        target_marriage = MarriageService.get_active_marriage(db, target_id)
        if not target_marriage:
            await update.message.reply_text("❌ У жертвы нет семьи")
            return

        # Find target's children
        children = db.query(Child).filter(Child.marriage_id == target_marriage.id, Child.is_alive.is_(True)).all()

        # Filter out already kidnapped children
        available_children = []
        for child in children:
            existing = (
                db.query(Kidnapping).filter(Kidnapping.child_id == child.id, Kidnapping.is_active.is_(True)).first()
            )
            if not existing:
                available_children.append(child)

        if not available_children:
            await update.message.reply_text("❌ У жертвы нет доступных детей для похищения")
            return

        # Check premium shield
        from app.handlers.premium import has_active_boost

        if has_active_boost(target_id, "shield", db=db):
            await update.message.reply_text("🛡 У жертвы есть премиум-щит\n\nПохищение невозможно")
            return

        # Check if target has house (affects success chance)
        has_house = db.query(House).filter(House.marriage_id == target_marriage.id).first() is not None
        success_chance = KIDNAP_SUCCESS_CHANCE_WITH_HOUSE if has_house else KIDNAP_SUCCESS_CHANCE_NO_HOUSE

        # Roll for success
        roll = random.randint(1, 100)
        success = roll <= success_chance

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(hours=KIDNAP_COOLDOWN_HOURS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="kidnap", expires_at=expires_at))

        if not success:
            # Failed — pay fine
            fine = min(KIDNAP_FAIL_FINE, user.balance)
            user.balance -= fine

            safe_target_name = html.escape(str(target_name))
            balance = user.balance

            await update.message.reply_text(
                f"🚨 <b>Похищение провалилось!</b>\n\n"
                f"Ты попался при попытке похитить ребёнка @{safe_target_name}\n"
                f"{'🏠 Дом защитил семью!' if has_house else '👮 Тебя поймали!'}\n\n"
                f"💸 Штраф: {format_diamonds(fine)}\n"
                f"💰 Баланс: {format_diamonds(balance)}",
                parse_mode="HTML",
            )
            logger.info("Kidnap failed", user_id=user_id, target_id=target_id, fine=fine)
            return

        # Success — pick random child
        child = random.choice(available_children)

        # Create kidnapping record
        kidnapping = Kidnapping(
            child_id=child.id,
            kidnapper_id=user_id,
            victim_id=target_id,
            ransom_amount=RANSOM_PER_STAGE.get(child.age_stage, RANSOM_BASE),
            is_active=True,
        )
        db.add(kidnapping)
        db.flush()

        kidnapping_id = kidnapping.id
        child_id = child.id
        child_name = child.name or "Безымянный"
        child_stage = child.age_stage
        ransom = kidnapping.ransom_amount
        safe_target_name = html.escape(str(target_name))

    stage_emoji = {"infant": "👶", "child": "🧒", "teen": "🧑"}
    emoji = stage_emoji.get(child_stage, "👶")

    await update.message.reply_text(
        f"🦹 <b>Похищение!</b>\n\n"
        f"Ты похитил {emoji} {html.escape(child_name)} у @{safe_target_name}!\n\n"
        f"💰 Выкуп: {format_diamonds(ransom)}\n\n"
        f"Жертва может заплатить выкуп: /ransom\n"
        f"Или ты можешь отпустить: /release",
        parse_mode="HTML",
    )

    # Notify victim with shield nudge
    try:
        from app.handlers.premium import build_premium_nudge

        shield_nudge = build_premium_nudge("robbed", target_id)
        victim_msg = (
            f"🚨 <b>Твоего ребёнка похитили!</b>\n\n"
            f"{emoji} {html.escape(child_name)}\n"
            f"💰 Выкуп: {format_diamonds(ransom)}\n"
            f"/ransom — заплатить выкуп{shield_nudge}"
        )
        await context.bot.send_message(chat_id=target_id, text=victim_msg, parse_mode="HTML")
    except Exception:
        pass

    logger.info("Kidnap success", user_id=user_id, target_id=target_id, child_id=child_id, ransom=ransom)


@require_registered
async def ransom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ransom — pay ransom to get child back."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        # Find kidnapping where user is victim
        kidnapping = (
            db.query(Kidnapping).filter(Kidnapping.victim_id == user_id, Kidnapping.is_active.is_(True)).first()
        )

        if not kidnapping:
            await update.message.reply_text("❌ У тебя нет похищенных детей")
            return

        user = db.query(User).filter(User.telegram_id == user_id).first()
        kidnapper = db.query(User).filter(User.telegram_id == kidnapping.kidnapper_id).first()
        child = db.query(Child).filter(Child.id == kidnapping.child_id).first()

        ransom = kidnapping.ransom_amount

        if user.balance < ransom:
            child_name = child.name or "Безымянный" if child else "Ребёнок"
            await update.message.reply_text(
                f"❌ Недостаточно алмазов для выкупа\n\n"
                f"👶 {html.escape(child_name)}\n"
                f"💰 Выкуп: {format_diamonds(ransom)}\n"
                f"💰 У тебя: {format_diamonds(user.balance)}",
                parse_mode="HTML",
            )
            return

        # Pay ransom
        user.balance -= ransom
        kidnapper.balance += ransom

        # Release child
        kidnapping.is_active = False

        child_name = child.name or "Безымянный" if child else "Ребёнок"
        balance = user.balance
        kidnapper_id = kidnapping.kidnapper_id
        kidnapper_name = kidnapper.username or f"ID {kidnapper_id}"

    await update.message.reply_text(
        f"✅ <b>Ребёнок спасён!</b>\n\n"
        f"👶 {html.escape(child_name)} вернулся домой\n"
        f"💸 Выкуп {format_diamonds(ransom)} уплачен @{html.escape(str(kidnapper_name))}\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Ransom paid", user_id=user_id, kidnapper_id=kidnapper_id, ransom=ransom)


@require_registered
async def release_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /release — kidnapper releases child for free."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        kidnapping = (
            db.query(Kidnapping).filter(Kidnapping.kidnapper_id == user_id, Kidnapping.is_active.is_(True)).first()
        )

        if not kidnapping:
            await update.message.reply_text("❌ У тебя нет похищенных детей")
            return

        child = db.query(Child).filter(Child.id == kidnapping.child_id).first()
        kidnapping.is_active = False
        child_name = child.name or "Безымянный" if child else "Ребёнок"

    await update.message.reply_text(
        f"✅ <b>Ребёнок отпущен</b>\n\n👶 {html.escape(child_name)} вернулся домой",
        parse_mode="HTML",
    )

    logger.info("Child released", user_id=user_id)


@require_registered
async def kidnap_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kidnaps — show kidnapping status."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        # Check if user has kidnapped someone's child
        as_kidnapper = (
            db.query(Kidnapping).filter(Kidnapping.kidnapper_id == user_id, Kidnapping.is_active.is_(True)).first()
        )

        # Check if user's child is kidnapped
        as_victim = db.query(Kidnapping).filter(Kidnapping.victim_id == user_id, Kidnapping.is_active.is_(True)).first()

        text = "🦹 <b>Похищения</b>\n\n"

        if as_kidnapper:
            child = db.query(Child).filter(Child.id == as_kidnapper.child_id).first()
            victim = db.query(User).filter(User.telegram_id == as_kidnapper.victim_id).first()
            child_name = child.name or "Безымянный" if child else "?"
            victim_name = victim.username or f"ID {as_kidnapper.victim_id}" if victim else "?"

            text += (
                f"🔓 <b>Ты похитил:</b>\n"
                f"👶 {html.escape(child_name)} (у @{html.escape(str(victim_name))})\n"
                f"💰 Выкуп: {format_diamonds(as_kidnapper.ransom_amount)}\n"
                f"/release — отпустить\n\n"
            )

        if as_victim:
            child = db.query(Child).filter(Child.id == as_victim.child_id).first()
            kidnapper = db.query(User).filter(User.telegram_id == as_victim.kidnapper_id).first()
            child_name = child.name or "Безымянный" if child else "?"
            kidnapper_name = kidnapper.username or f"ID {as_victim.kidnapper_id}" if kidnapper else "?"

            text += (
                f"🚨 <b>У тебя похитили:</b>\n"
                f"👶 {html.escape(child_name)} (похитил @{html.escape(str(kidnapper_name))})\n"
                f"💰 Выкуп: {format_diamonds(as_victim.ransom_amount)}\n"
                f"/ransom — заплатить выкуп\n\n"
            )

        if not as_kidnapper and not as_victim:
            text += "Нет активных похищений\n\n"

        text += (
            "Команды:\n" "/kidnap (реплай) — похитить ребёнка\n" "/ransom — заплатить выкуп\n" "/release — отпустить"
        )

    await update.message.reply_text(text, parse_mode="HTML")


def register_kidnap_handlers(application):
    """Register kidnapping handlers."""
    application.add_handler(CommandHandler("kidnap", kidnap_command))
    application.add_handler(CommandHandler("ransom", ransom_command))
    application.add_handler(CommandHandler("release", release_command))
    application.add_handler(CommandHandler("kidnaps", kidnap_status_command))
    logger.info("Kidnap handlers registered")
