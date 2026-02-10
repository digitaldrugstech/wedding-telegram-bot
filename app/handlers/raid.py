"""Gang raid handler — gangs can raid other gangs' banks."""

import html
import random
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, Gang, GangMember, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

RAID_COOLDOWN_HOURS = 12
RAID_MIN_MEMBERS = 2  # Need at least 2 online members to raid
RAID_JOIN_TIMEOUT_SECONDS = 120  # 2 minutes to join raid
RAID_BASE_SUCCESS = 40  # Base 40% success chance
RAID_MEMBER_BONUS = 10  # +10% per additional raider (beyond 1)
RAID_MAX_STEAL_PERCENT = 30  # Steal up to 30% of target gang bank
RAID_MIN_STEAL_PERCENT = 10  # Steal at least 10%
RAID_FAIL_PENALTY_PERCENT = 15  # Lose 15% of OWN gang bank on fail
RAID_MIN_TARGET_BANK = 500  # Target gang must have at least 500 in bank

# Active raids: {raid_key: {attacker_gang_id, target_gang_id, raiders: set(), message_id, chat_id, initiated_at}}
active_raids = {}


def _raid_key(attacker_id: int, target_id: int) -> str:
    return f"raid:{attacker_id}:{target_id}"


@require_registered
async def raid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /raid [gang_name] — initiate a gang raid."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "💥 <b>Рейд на банду</b>\n\n"
            "/raid [название банды] — напасть на чужую банду\n\n"
            f"• Укради до {RAID_MAX_STEAL_PERCENT}% из их банка\n"
            f"• Нужно {RAID_MIN_MEMBERS}+ участника ({RAID_JOIN_TIMEOUT_SECONDS // 60} мин на сбор)\n"
            "• Чем больше рейдеров, тем выше шанс\n"
            f"• Провал = потеря {RAID_FAIL_PENALTY_PERCENT}% из своего банка\n"
            f"• Кулдаун: {RAID_COOLDOWN_HOURS}ч\n\n"
            "/gangs — список банд",
            parse_mode="HTML",
        )
        return

    target_name = " ".join(context.args)

    with get_db() as db:
        # Check user is in a gang
        member = db.query(GangMember).filter(GangMember.user_id == user_id).first()
        if not member:
            await update.message.reply_text("❌ Ты не состоишь в банде\n\n/gang create [название] — создать")
            return

        attacker_gang = db.query(Gang).filter(Gang.id == member.gang_id).first()
        if not attacker_gang:
            await update.message.reply_text("❌ Банда не найдена")
            return

        # Check cooldown
        cd_action = "raid"
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == cd_action).first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours}ч")
            if minutes > 0:
                time_parts.append(f"{minutes}м")
            await update.message.reply_text(f"⏰ Следующий рейд через {' '.join(time_parts)}")
            return

        # Find target gang
        target_gang = db.query(Gang).filter(Gang.name == target_name).first()
        if not target_gang:
            # Try case-insensitive search
            all_gangs = db.query(Gang).all()
            for g in all_gangs:
                if g.name.lower() == target_name.lower():
                    target_gang = g
                    break

        if not target_gang:
            await update.message.reply_text(f"❌ Банда «{html.escape(target_name)}» не найдена\n\n/gangs — список банд")
            return

        if target_gang.id == attacker_gang.id:
            await update.message.reply_text("❌ Нельзя напасть на свою банду")
            return

        if target_gang.bank < RAID_MIN_TARGET_BANK:
            await update.message.reply_text(
                f"❌ У банды «{html.escape(target_gang.name)}» слишком мало в банке\n\n"
                f"Минимум: {format_diamonds(RAID_MIN_TARGET_BANK)}\n"
                f"У них: {format_diamonds(target_gang.bank)}"
            )
            return

        # Check for existing active raid
        key = _raid_key(attacker_gang.id, target_gang.id)
        if key in active_raids:
            await update.message.reply_text("❌ Рейд на эту банду уже идёт")
            return

        attacker_name = html.escape(attacker_gang.name)
        target_safe_name = html.escape(target_gang.name)
        attacker_gang_id = attacker_gang.id
        target_gang_id = target_gang.id
        target_bank = target_gang.bank

    # Create raid invitation
    active_raids[key] = {
        "attacker_gang_id": attacker_gang_id,
        "target_gang_id": target_gang_id,
        "raiders": {user_id},
        "initiated_at": datetime.utcnow(),
        "initiator_id": user_id,
    }

    username_display = f"@{html.escape(update.effective_user.username)}" if update.effective_user.username else html.escape(update.effective_user.first_name)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚔️ Присоединиться", callback_data=f"raid:join:{attacker_gang_id}:{target_gang_id}"
                ),
                InlineKeyboardButton(
                    "🚀 НАЧАТЬ РЕЙД", callback_data=f"raid:go:{attacker_gang_id}:{target_gang_id}:{user_id}"
                ),
            ]
        ]
    )

    await update.message.reply_text(
        f"💥 <b>РЕЙД!</b>\n\n"
        f"⚔️ «{attacker_name}» нападает на «{target_safe_name}»!\n\n"
        f"💰 В банке цели: {format_diamonds(target_bank)}\n"
        f"👥 Рейдеров: 1\n\n"
        f"{username_display} начинает рейд!\n\n"
        f"⏰ {RAID_JOIN_TIMEOUT_SECONDS // 60} мин на сбор — жми «Присоединиться»!\n"
        f"Нужно минимум {format_word(RAID_MIN_MEMBERS, 'участник', 'участника', 'участников')}\n\n"
        f"Лидер жмёт «НАЧАТЬ РЕЙД» когда готовы",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    logger.info("Raid initiated", user_id=user_id, attacker_gang=attacker_gang_id, target_gang=target_gang_id)


async def raid_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle raid join button."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    attacker_gang_id = int(parts[2])
    target_gang_id = int(parts[3])
    key = _raid_key(attacker_gang_id, target_gang_id)

    if key not in active_raids:
        await query.answer("❌ Рейд уже завершён", show_alert=True)
        return

    raid = active_raids[key]

    # Check timeout
    if (datetime.utcnow() - raid["initiated_at"]).total_seconds() > RAID_JOIN_TIMEOUT_SECONDS:
        del active_raids[key]
        await query.answer("❌ Время вышло", show_alert=True)
        return

    # Check registration, ban, and gang membership
    with get_db() as db:
        raid_user = db.query(User).filter(User.telegram_id == user_id).first()
        if not raid_user:
            await query.answer("❌ Ты не зарегистрирован — /start", show_alert=True)
            return
        if raid_user.is_banned:
            await query.answer("❌ Ты забанен", show_alert=True)
            return
        member = (
            db.query(GangMember).filter(GangMember.user_id == user_id, GangMember.gang_id == attacker_gang_id).first()
        )
        if not member:
            await query.answer("❌ Ты не в этой банде", show_alert=True)
            return

    if user_id in raid["raiders"]:
        await query.answer("Ты уже в рейде!", show_alert=True)
        return

    raid["raiders"].add(user_id)
    count = len(raid["raiders"])
    chance = min(90, RAID_BASE_SUCCESS + (count - 1) * RAID_MEMBER_BONUS)

    await query.answer(f"Ты в рейде! ({count} участников, {chance}% шанс)")

    logger.info("Raid member joined", user_id=user_id, raid_key=key, count=count)


async def raid_go_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle raid start button — execute the raid."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    attacker_gang_id = int(parts[2])
    target_gang_id = int(parts[3])
    initiator_id = int(parts[4])

    # Only initiator can start
    if user_id != initiator_id:
        await query.answer("❌ Только организатор может начать рейд", show_alert=True)
        return

    # Ban check
    with get_db() as db:
        initiator = db.query(User).filter(User.telegram_id == user_id).first()
        if not initiator or initiator.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    key = _raid_key(attacker_gang_id, target_gang_id)

    if key not in active_raids:
        await query.answer("❌ Рейд уже завершён", show_alert=True)
        return

    db_committed = False
    try:
        raid = active_raids.pop(key)
        raiders = raid["raiders"]
        count = len(raiders)

        await query.answer()

        # Check minimum raiders
        if count < RAID_MIN_MEMBERS:
            await safe_edit_message(
                query,
                f"❌ <b>Рейд отменён</b>\n\n"
                f"Недостаточно участников: {count}/{RAID_MIN_MEMBERS}\n"
                f"Нужно минимум {format_word(RAID_MIN_MEMBERS, 'рейдер', 'рейдера', 'рейдеров')}",
            )
            return

        # Calculate success chance
        chance = min(90, RAID_BASE_SUCCESS + (count - 1) * RAID_MEMBER_BONUS)
        success = random.randint(1, 100) <= chance

        with get_db() as db:
            attacker_gang = db.query(Gang).filter(Gang.id == attacker_gang_id).first()
            target_gang = db.query(Gang).filter(Gang.id == target_gang_id).first()

            if not attacker_gang or not target_gang:
                await safe_edit_message(query, "❌ Одна из банд больше не существует")
                return

            attacker_name = html.escape(attacker_gang.name)
            target_name = html.escape(target_gang.name)

            if success:
                # Steal from target bank
                steal_percent = random.randint(RAID_MIN_STEAL_PERCENT, RAID_MAX_STEAL_PERCENT)
                stolen = max(1, int(target_gang.bank * steal_percent / 100))
                stolen = min(stolen, target_gang.bank)

                target_gang.bank -= stolen

                # Split between gang bank and raiders personally
                gang_share = stolen // 2  # 50% to gang bank
                raider_share = stolen - gang_share  # 50% split among raiders
                per_raider = max(1, raider_share // count)
                remainder = raider_share - per_raider * count

                attacker_gang.bank += gang_share

                # Pay each raider (distribute remainder to first N raiders)
                for i, raider_id in enumerate(raiders):
                    raider_user = db.query(User).filter(User.telegram_id == raider_id).first()
                    if raider_user:
                        bonus = 1 if i < remainder else 0
                        raider_user.balance += per_raider + bonus

                result_text = (
                    f"💥 <b>РЕЙД УСПЕШЕН!</b>\n\n"
                    f"⚔️ «{attacker_name}» ограбили «{target_name}»!\n\n"
                    f"💰 Украдено: {format_diamonds(stolen)}\n"
                    f"🏦 В банк банды: {format_diamonds(gang_share)}\n"
                    f"👤 Каждому рейдеру: {format_diamonds(per_raider)}\n"
                    f"👥 Рейдеров: {count} (шанс был {chance}%)\n\n"
                    f"🏦 Банк «{target_name}»: {format_diamonds(target_gang.bank)}"
                )
            else:
                # Penalty — lose from own gang bank
                penalty = max(1, int(attacker_gang.bank * RAID_FAIL_PENALTY_PERCENT / 100))
                penalty = min(penalty, attacker_gang.bank)
                attacker_gang.bank -= penalty

                result_text = (
                    f"🚨 <b>РЕЙД ПРОВАЛЕН!</b>\n\n"
                    f"⚔️ «{attacker_name}» не смогли ограбить «{target_name}»!\n\n"
                    f"💸 Штраф из банка банды: {format_diamonds(penalty)}\n"
                    f"👥 Рейдеров: {count} (шанс был {chance}%)\n\n"
                    f"🏦 Банк «{attacker_name}»: {format_diamonds(attacker_gang.bank)}"
                )

            # Set cooldown for all raiders
            expires_at = datetime.utcnow() + timedelta(hours=RAID_COOLDOWN_HOURS)
            cd_action = "raid"
            for raider_id in raiders:
                cooldown = db.query(Cooldown).filter(Cooldown.user_id == raider_id, Cooldown.action == cd_action).first()
                if cooldown:
                    cooldown.expires_at = expires_at
                else:
                    db.add(Cooldown(user_id=raider_id, action=cd_action, expires_at=expires_at))

            # Try to notify target gang leader
            target_leader_id = target_gang.leader_id

        db_committed = True
        await safe_edit_message(query, result_text)

        # Notify target gang leader
        if success:
            try:
                notify_text = (
                    f"🚨 <b>Твою банду ограбили!</b>\n\n"
                    f"⚔️ «{attacker_name}» совершили рейд!\n"
                    f"💸 Украдено из банка: {format_diamonds(stolen)}\n\n"
                    f"/gang — посмотреть банду"
                )
                await context.bot.send_message(chat_id=target_leader_id, text=notify_text, parse_mode="HTML")
            except Exception:
                pass

        logger.info(
            "Raid completed",
            attacker_gang=attacker_gang_id,
            target_gang=target_gang_id,
            success=success,
            raiders=count,
            chance=chance,
        )
    except Exception as e:
        if not db_committed:
            logger.error("Raid processing failed", error=str(e), exc_info=True)
            try:
                await safe_edit_message(query, "❌ Ошибка рейда")
            except Exception:
                pass
        else:
            # DB committed OK, only notification failed
            logger.warning("Raid notification failed (DB OK)", error=str(e))


def register_raid_handlers(application):
    """Register raid handlers."""
    application.add_handler(CommandHandler("raid", raid_command))
    application.add_handler(CallbackQueryHandler(raid_join_callback, pattern=r"^raid:join:"))
    application.add_handler(CallbackQueryHandler(raid_go_callback, pattern=r"^raid:go:"))
    logger.info("Raid handlers registered")
