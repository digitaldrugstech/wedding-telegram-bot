"""Gang handler — form gangs with other players."""

import html

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Gang, GangMember, User
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

GANG_CREATE_COST = 1000
GANG_MAX_MEMBERS = 5
GANG_UPGRADE_COSTS = {2: 2000, 3: 5000, 4: 10000, 5: 25000}  # level -> cost
GANG_MAX_MEMBERS_BY_LEVEL = {1: 5, 2: 7, 3: 10, 4: 15, 5: 20}
GANG_DEPOSIT_MIN = 50


def get_user_gang(db, user_id: int):
    """Get the gang a user belongs to, or None."""
    member = db.query(GangMember).filter(GangMember.user_id == user_id).first()
    if not member:
        return None, None
    gang = db.query(Gang).filter(Gang.id == member.gang_id).first()
    return gang, member


@require_registered
async def gang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gang — gang menu and info."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    args = context.args

    if args:
        subcommand = args[0].lower()
        if subcommand == "create":
            await gang_create(update, context, user_id)
            return
        elif subcommand == "invite":
            await gang_invite(update, context, user_id)
            return
        elif subcommand == "leave":
            await gang_leave(update, user_id)
            return
        elif subcommand == "kick":
            await gang_kick(update, context, user_id)
            return
        elif subcommand == "deposit":
            await gang_deposit(update, context, user_id)
            return
        elif subcommand == "upgrade":
            await gang_upgrade(update, user_id)
            return
        elif subcommand == "disband":
            await gang_disband(update, user_id)
            return

    # Show gang info
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang:
            await update.message.reply_text(
                "🔫 <b>Банды</b>\n\n"
                "Ты не состоишь в банде\n\n"
                f"/gang create [название] — создать ({format_diamonds(GANG_CREATE_COST)})\n\n"
                "Вступить можно по приглашению лидера",
                parse_mode="HTML",
            )
            return

        # Build gang info
        members = db.query(GangMember).filter(GangMember.gang_id == gang.id).all()
        max_members = GANG_MAX_MEMBERS_BY_LEVEL.get(gang.level, 5)

        member_list = []
        for m in members:
            u = db.query(User).filter(User.telegram_id == m.user_id).first()
            name = u.username or f"ID {m.user_id}" if u else f"ID {m.user_id}"
            role_emoji = "👑" if m.role == "leader" else "👤"
            member_list.append(f"{role_emoji} @{html.escape(str(name))}")

        next_upgrade = GANG_UPGRADE_COSTS.get(gang.level + 1)
        upgrade_text = f"\n💰 Апгрейд до ур.{gang.level + 1}: {format_diamonds(next_upgrade)} (из банка)" if next_upgrade else ""

        text = (
            f"🔫 <b>{html.escape(gang.name)}</b>\n\n"
            f"Уровень: {gang.level}\n"
            f"Банк: {format_diamonds(gang.bank)}\n"
            f"Участники ({len(members)}/{max_members}):\n"
            + "\n".join(member_list)
            + f"\n{upgrade_text}\n\n"
            "Команды:\n"
            "/gang invite @user — пригласить\n"
            "/gang deposit [сумма] — вклад в банк\n"
            "/gang upgrade — улучшить банду\n"
            "/gang leave — покинуть\n"
        )

        if member.role == "leader":
            text += "/gang kick @user — выгнать\n/gang disband — распустить\n"

    await update.message.reply_text(text, parse_mode="HTML")


async def gang_create(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Create a new gang."""
    if len(context.args) < 2:
        await update.message.reply_text(
            f"❌ Укажи название\n\n/gang create [название]\n\nСтоимость: {format_diamonds(GANG_CREATE_COST)}"
        )
        return

    name = " ".join(context.args[1:])[:30].strip()

    if len(name) < 2:
        await update.message.reply_text("❌ Название слишком короткое (мин. 2 символа)")
        return

    with get_db() as db:
        # Check not already in a gang
        existing_member = db.query(GangMember).filter(GangMember.user_id == user_id).first()
        if existing_member:
            await update.message.reply_text("❌ Ты уже состоишь в банде\n\n/gang leave — покинуть текущую")
            return

        # Check name unique
        existing_gang = db.query(Gang).filter(Gang.name == name).first()
        if existing_gang:
            await update.message.reply_text("❌ Банда с таким названием уже существует")
            return

        # Check balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.balance < GANG_CREATE_COST:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(GANG_CREATE_COST)}\nУ тебя: {format_diamonds(user.balance if user else 0)}"
            )
            return

        # Create gang
        user.balance -= GANG_CREATE_COST
        gang = Gang(name=name, leader_id=user_id)
        db.add(gang)
        db.flush()

        # Add leader as member
        db.add(GangMember(gang_id=gang.id, user_id=user_id, role="leader"))

        balance = user.balance
        safe_name = html.escape(name)

    await update.message.reply_text(
        f"🔫 <b>Банда создана!</b>\n\n"
        f"Название: {safe_name}\n"
        f"Стоимость: {format_diamonds(GANG_CREATE_COST)}\n\n"
        f"/gang invite @user — пригласить участников\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Gang created", user_id=user_id, name=name)


async def gang_invite(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Invite someone to the gang."""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /gang invite @username")
        return

    target_username = context.args[1].lstrip("@")

    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang:
            await update.message.reply_text("❌ Ты не состоишь в банде")
            return

        if member.role != "leader":
            await update.message.reply_text("❌ Только лидер может приглашать")
            return

        # Check member count
        current_count = db.query(GangMember).filter(GangMember.gang_id == gang.id).count()
        max_members = GANG_MAX_MEMBERS_BY_LEVEL.get(gang.level, 5)
        if current_count >= max_members:
            await update.message.reply_text(f"❌ Банда полна ({format_word(current_count, 'участник', 'участника', 'участников')}/{max_members})\n\n/gang upgrade — увеличить лимит")
            return

        # Find target
        target = db.query(User).filter(User.username == target_username).first()
        if not target:
            await update.message.reply_text(f"❌ Игрок @{html.escape(target_username)} не найден")
            return

        if target.telegram_id == user_id:
            await update.message.reply_text("❌ Ты уже в банде")
            return

        # Check if target already in a gang
        target_member = db.query(GangMember).filter(GangMember.user_id == target.telegram_id).first()
        if target_member:
            await update.message.reply_text("❌ Этот игрок уже состоит в банде")
            return

        gang_name = html.escape(gang.name)
        gang_id = gang.id
        target_id = target.telegram_id

    # Send invite with buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"gang:accept:{gang_id}:{target_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"gang:decline:{gang_id}:{target_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🔫 <b>Приглашение в банду</b>\n\n"
        f"@{html.escape(target_username)}, тебя приглашают в банду «{gang_name}»\n\n"
        f"Принимаешь?",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


@button_owner_only
async def gang_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept gang invitation."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    try:
        gang_id = int(parts[2])
        target_id = int(parts[3])
    except (ValueError, IndexError):
        return

    with get_db() as db:
        # Ban check + gang logic in single session
        user_check = db.query(User).filter(User.telegram_id == target_id).first()
        if not user_check or user_check.is_banned:
            await safe_edit_message(query, "❌ Доступ запрещён")
            return

        # Verify gang exists
        gang = db.query(Gang).filter(Gang.id == gang_id).first()
        if not gang:
            await safe_edit_message(query, "❌ Банда больше не существует")
            return

        # Check not already in a gang
        existing = db.query(GangMember).filter(GangMember.user_id == target_id).first()
        if existing:
            await safe_edit_message(query, "❌ Ты уже состоишь в банде")
            return

        # Check member limit
        current_count = db.query(GangMember).filter(GangMember.gang_id == gang_id).count()
        max_members = GANG_MAX_MEMBERS_BY_LEVEL.get(gang.level, 5)
        if current_count >= max_members:
            await safe_edit_message(query, "❌ Банда уже полна")
            return

        # Add member
        db.add(GangMember(gang_id=gang_id, user_id=target_id, role="member"))
        gang_name = html.escape(gang.name)

    await safe_edit_message(query, f"✅ Ты вступил в банду «{gang_name}»!\n\n/gang — меню банды")
    logger.info("Gang member joined", user_id=target_id, gang_id=gang_id)


@button_owner_only
async def gang_decline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Decline gang invitation."""
    query = update.callback_query
    await query.answer()
    await safe_edit_message(query, "❌ Приглашение отклонено")


async def gang_leave(update: Update, user_id: int):
    """Leave current gang."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang:
            await update.message.reply_text("❌ Ты не состоишь в банде")
            return

        if member.role == "leader":
            await update.message.reply_text("❌ Лидер не может покинуть банду\n\n/gang disband — распустить банду")
            return

        db.delete(member)
        gang_name = html.escape(gang.name)

    await update.message.reply_text(f"✅ Ты покинул банду «{gang_name}»")
    logger.info("Gang member left", user_id=user_id)


async def gang_kick(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Kick a member from the gang."""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /gang kick @username")
        return

    target_username = context.args[1].lstrip("@")

    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang or member.role != "leader":
            await update.message.reply_text("❌ Только лидер может выгонять")
            return

        target = db.query(User).filter(User.username == target_username).first()
        if not target:
            await update.message.reply_text(f"❌ Игрок @{html.escape(target_username)} не найден")
            return

        target_member = db.query(GangMember).filter(
            GangMember.gang_id == gang.id, GangMember.user_id == target.telegram_id
        ).first()

        if not target_member:
            await update.message.reply_text("❌ Этот игрок не в твоей банде")
            return

        if target_member.role == "leader":
            await update.message.reply_text("❌ Нельзя выгнать лидера")
            return

        db.delete(target_member)

    await update.message.reply_text(f"✅ @{html.escape(target_username)} выгнан из банды")
    logger.info("Gang member kicked", user_id=user_id, kicked=target_username)


async def gang_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Deposit diamonds into gang bank."""
    if len(context.args) < 2:
        await update.message.reply_text(f"❌ /gang deposit [сумма]\n\nМинимум: {format_diamonds(GANG_DEPOSIT_MIN)}")
        return

    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Укажи число")
        return

    if amount < GANG_DEPOSIT_MIN:
        await update.message.reply_text(f"❌ Минимум: {format_diamonds(GANG_DEPOSIT_MIN)}")
        return

    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang:
            await update.message.reply_text("❌ Ты не состоишь в банде")
            return

        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user.balance < amount:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\nУ тебя: {format_diamonds(user.balance)}"
            )
            return

        user.balance -= amount
        gang.bank += amount

        balance = user.balance
        bank = gang.bank

    await update.message.reply_text(
        f"✅ <b>Вклад в банк банды</b>\n\n"
        f"Внесено: {format_diamonds(amount)}\n"
        f"Банк банды: {format_diamonds(bank)}\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Gang deposit", user_id=user_id, amount=amount)


async def gang_upgrade(update: Update, user_id: int):
    """Upgrade gang level (costs from bank)."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang:
            await update.message.reply_text("❌ Ты не состоишь в банде")
            return

        if member.role != "leader":
            await update.message.reply_text("❌ Только лидер может улучшать банду")
            return

        next_level = gang.level + 1
        cost = GANG_UPGRADE_COSTS.get(next_level)

        if not cost:
            await update.message.reply_text("❌ Банда уже максимального уровня")
            return

        if gang.bank < cost:
            await update.message.reply_text(
                f"❌ Недостаточно в банке\n\n"
                f"Нужно: {format_diamonds(cost)}\n"
                f"В банке: {format_diamonds(gang.bank)}\n\n"
                f"/gang deposit [сумма] — пополнить"
            )
            return

        gang.bank -= cost
        gang.level = next_level
        new_max = GANG_MAX_MEMBERS_BY_LEVEL.get(next_level, 5)
        bank = gang.bank
        gang_name = html.escape(gang.name)

    await update.message.reply_text(
        f"⬆️ <b>Банда улучшена!</b>\n\n"
        f"«{gang_name}» — уровень {next_level}\n"
        f"Макс. участников: {new_max}\n"
        f"Банк: {format_diamonds(bank)}",
        parse_mode="HTML",
    )

    logger.info("Gang upgraded", user_id=user_id, level=next_level, cost=cost)


async def gang_disband(update: Update, user_id: int):
    """Disband the gang (leader only)."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)

        if not gang or member.role != "leader":
            await update.message.reply_text("❌ Только лидер может распустить банду")
            return

        # Refund bank to leader
        user = db.query(User).filter(User.telegram_id == user_id).first()
        refund = gang.bank
        if refund > 0:
            user.balance += refund

        gang_name = html.escape(gang.name)

        # Delete gang (cascade deletes members)
        db.delete(gang)
        balance = user.balance

    refund_text = f"\n💰 Возврат из банка: {format_diamonds(refund)}" if refund > 0 else ""

    await update.message.reply_text(
        f"💥 <b>Банда распущена</b>\n\n"
        f"«{gang_name}» больше не существует{refund_text}\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Gang disbanded", user_id=user_id, name=gang_name, refund=refund)


@require_registered
async def gangs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gangs — show all gangs leaderboard."""
    if not update.effective_user or not update.message:
        return

    with get_db() as db:
        gangs = db.query(Gang).order_by(Gang.level.desc(), Gang.bank.desc()).limit(10).all()

        if not gangs:
            await update.message.reply_text("🔫 Пока нет банд\n\n/gang create [название] — создать первую!")
            return

        text = "🔫 <b>Топ банд</b>\n\n"
        for i, gang in enumerate(gangs, 1):
            member_count = db.query(GangMember).filter(GangMember.gang_id == gang.id).count()
            leader = db.query(User).filter(User.telegram_id == gang.leader_id).first()
            leader_name = leader.username or f"ID {gang.leader_id}" if leader else "?"

            text += (
                f"{i}. <b>{html.escape(gang.name)}</b> (ур.{gang.level})\n"
                f"   👑 @{html.escape(str(leader_name))} | {format_word(member_count, 'участник', 'участника', 'участников')} | Банк: {format_diamonds(gang.bank)}\n\n"
            )

    await update.message.reply_text(text, parse_mode="HTML")


def register_gang_handlers(application):
    """Register gang handlers."""
    application.add_handler(CommandHandler("gang", gang_command))
    application.add_handler(CommandHandler("gangs", gangs_command))
    application.add_handler(CallbackQueryHandler(gang_accept_callback, pattern=r"^gang:accept:"))
    application.add_handler(CallbackQueryHandler(gang_decline_callback, pattern=r"^gang:decline:"))
    logger.info("Gang handlers registered")
