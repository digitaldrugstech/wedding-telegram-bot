"""Gang handler — form gangs with other players, full inline button menu."""

import html

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Gang, GangMember, User
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import delete_command_and_reply, safe_edit_message

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


# ==================== KEYBOARD BUILDERS ====================


def _gang_menu_keyboard(user_id: int, is_leader: bool, next_upgrade_cost: int | None) -> InlineKeyboardMarkup:
    """Main gang menu buttons."""
    keyboard = [
        [
            InlineKeyboardButton("100", callback_data=f"gang:dep:100:{user_id}"),
            InlineKeyboardButton("500", callback_data=f"gang:dep:500:{user_id}"),
            InlineKeyboardButton("1000", callback_data=f"gang:dep:1000:{user_id}"),
        ],
    ]
    row2 = []
    if next_upgrade_cost and is_leader:
        row2.append(
            InlineKeyboardButton(
                f"Улучшить ({format_diamonds(next_upgrade_cost)})", callback_data=f"gang:upgrade:{user_id}"
            )
        )
    if is_leader:
        row2.append(InlineKeyboardButton("Распустить", callback_data=f"gang:disband:{user_id}"))
    else:
        row2.append(InlineKeyboardButton("Покинуть", callback_data=f"gang:leave:{user_id}"))
    if row2:
        keyboard.append(row2)
    return InlineKeyboardMarkup(keyboard)


def _confirm_keyboard(
    action: str, user_id: int, label_yes: str = "Да", label_no: str = "Отмена"
) -> InlineKeyboardMarkup:
    """Generic confirmation keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label_yes, callback_data=f"gang:{action}_yes:{user_id}"),
                InlineKeyboardButton(label_no, callback_data=f"gang:back:{user_id}"),
            ]
        ]
    )


# ==================== GANG INFO BUILDER ====================


def _build_gang_info(db, user_id: int):
    """Build gang info text + keyboard. Returns (text, keyboard) or (text, None) if no gang."""
    gang, member = get_user_gang(db, user_id)

    if not gang:
        text = (
            "🔫 <b>Банды</b>\n\n"
            "Ты не состоишь в банде\n\n"
            f"<code>/gang create [название]</code> — создать ({format_diamonds(GANG_CREATE_COST)})\n\n"
            "Вступить можно по приглашению лидера"
        )
        return text, None

    members = db.query(GangMember).filter(GangMember.gang_id == gang.id).all()
    max_members = GANG_MAX_MEMBERS_BY_LEVEL.get(gang.level, 5)

    member_list = []
    for m in members:
        u = db.query(User).filter(User.telegram_id == m.user_id).first()
        display = f"@{html.escape(u.username)}" if u and u.username else f"ID {m.user_id}"
        role_emoji = "👑" if m.role == "leader" else "👤"
        member_list.append(f"{role_emoji} {display}")

    next_upgrade_cost = GANG_UPGRADE_COSTS.get(gang.level + 1)
    is_leader = member.role == "leader"

    upgrade_text = ""
    if next_upgrade_cost:
        upgrade_text = f"\nАпгрейд до ур.{gang.level + 1}: {format_diamonds(next_upgrade_cost)} из банка"

    text = (
        f"🔫 <b>{html.escape(gang.name)}</b>\n\n"
        f"Уровень: {gang.level}\n"
        f"Банк: {format_diamonds(gang.bank)}\n"
        f"Участники ({len(members)}/{max_members}):\n" + "\n".join(member_list) + f"{upgrade_text}"
    )

    keyboard = _gang_menu_keyboard(user_id, is_leader, next_upgrade_cost)
    return text, keyboard


# ==================== COMMAND HANDLER ====================


@require_registered
async def gang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gang — gang menu with buttons."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    args = context.args

    # Text-input subcommands (need typed arguments)
    if args:
        subcommand = args[0].lower()
        if subcommand == "create":
            await gang_create(update, context, user_id)
            return
        elif subcommand == "invite":
            await gang_invite(update, context, user_id)
            return
        elif subcommand == "kick":
            await gang_kick(update, context, user_id)
            return
        # Legacy: still support typed deposit/leave/upgrade/disband
        elif subcommand == "deposit":
            await gang_deposit(update, context, user_id)
            return
        elif subcommand == "leave":
            await gang_leave_typed(update, user_id)
            return
        elif subcommand == "upgrade":
            await gang_upgrade_typed(update, user_id)
            return
        elif subcommand == "disband":
            await gang_disband_typed(update, user_id)
            return

    with get_db() as db:
        text, keyboard = _build_gang_info(db, user_id)

    reply = await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    await delete_command_and_reply(update, reply, context, delay=90)


# ==================== CALLBACK ROUTER ====================


async def gang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all gang:* callbacks."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]
    user_id = update.effective_user.id

    # Owner check
    owner_id = int(parts[-1])
    if user_id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    # Ban check
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if action == "dep":
        amount = int(parts[2])
        await _handle_deposit(query, user_id, amount)
    elif action == "upgrade":
        await _handle_upgrade_confirm(query, user_id)
    elif action == "upgrade_yes":
        await _handle_upgrade(query, user_id)
    elif action == "leave":
        await _handle_leave_confirm(query, user_id)
    elif action == "leave_yes":
        await _handle_leave(query, user_id)
    elif action == "disband":
        await _handle_disband_confirm(query, user_id)
    elif action == "disband_yes":
        await _handle_disband(query, user_id)
    elif action == "back":
        await _handle_back(query, user_id)


async def _handle_deposit(query, user_id: int, amount: int):
    """Deposit via button."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang:
            await query.answer("Ты не в банде", show_alert=True)
            return

        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user.balance < amount:
            await query.answer(
                f"Нужно {format_diamonds(amount)}, у тебя {format_diamonds(user.balance)}", show_alert=True
            )
            return

        user.balance -= amount
        gang.bank += amount
        bank = gang.bank

    await query.answer(f"+{amount} в банк банды ({format_diamonds(bank)})")

    # Refresh menu
    with get_db() as db:
        text, keyboard = _build_gang_info(db, user_id)
    if keyboard:
        await safe_edit_message(query, text, reply_markup=keyboard)

    logger.info("Gang deposit", user_id=user_id, amount=amount)


async def _handle_upgrade_confirm(query, user_id: int):
    """Show upgrade confirmation."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang or member.role != "leader":
            await query.answer("Только лидер", show_alert=True)
            return

        next_level = gang.level + 1
        cost = GANG_UPGRADE_COSTS.get(next_level)
        if not cost:
            await query.answer("Максимальный уровень", show_alert=True)
            return

        bank = gang.bank
        gang_name = html.escape(gang.name)
        new_max = GANG_MAX_MEMBERS_BY_LEVEL.get(next_level, 5)

    if bank < cost:
        await query.answer(f"В банке {format_diamonds(bank)}, нужно {format_diamonds(cost)}", show_alert=True)
        return

    await query.answer()
    await safe_edit_message(
        query,
        f"⬆️ <b>Улучшить «{gang_name}»?</b>\n\n"
        f"Уровень: {next_level - 1} → {next_level}\n"
        f"Макс. участников: {new_max}\n"
        f"Стоимость: {format_diamonds(cost)} из банка",
        reply_markup=_confirm_keyboard("upgrade", user_id, "Улучшить"),
    )


async def _handle_upgrade(query, user_id: int):
    """Execute upgrade."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang or member.role != "leader":
            await query.answer("Только лидер", show_alert=True)
            return

        next_level = gang.level + 1
        cost = GANG_UPGRADE_COSTS.get(next_level)
        if not cost or gang.bank < cost:
            await query.answer("Недостаточно в банке", show_alert=True)
            return

        gang.bank -= cost
        gang.level = next_level

    await query.answer(f"Уровень {next_level}!")

    with get_db() as db:
        text, keyboard = _build_gang_info(db, user_id)
    if keyboard:
        await safe_edit_message(query, text, reply_markup=keyboard)

    logger.info("Gang upgraded", user_id=user_id, level=next_level, cost=cost)


async def _handle_leave_confirm(query, user_id: int):
    """Show leave confirmation."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang:
            await query.answer("Ты не в банде", show_alert=True)
            return
        if member.role == "leader":
            await query.answer("Лидер не может покинуть, только распустить", show_alert=True)
            return
        gang_name = html.escape(gang.name)

    await query.answer()
    await safe_edit_message(
        query,
        f"🚪 <b>Покинуть «{gang_name}»?</b>\n\nТы больше не сможешь участвовать в рейдах банды",
        reply_markup=_confirm_keyboard("leave", user_id, "Покинуть"),
    )


async def _handle_leave(query, user_id: int):
    """Execute leave."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang:
            await query.answer("Ты не в банде", show_alert=True)
            return
        if member.role == "leader":
            await query.answer("Лидер не может покинуть", show_alert=True)
            return
        gang_name = html.escape(gang.name)
        db.delete(member)

    await query.answer()
    await safe_edit_message(query, f"✅ Ты покинул банду «{gang_name}»")
    logger.info("Gang member left", user_id=user_id)


async def _handle_disband_confirm(query, user_id: int):
    """Show disband confirmation."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang or member.role != "leader":
            await query.answer("Только лидер", show_alert=True)
            return
        gang_name = html.escape(gang.name)
        bank = gang.bank

    refund_text = f"\nВозврат из банка: {format_diamonds(bank)}" if bank > 0 else ""

    await query.answer()
    await safe_edit_message(
        query,
        f"💥 <b>Распустить «{gang_name}»?</b>\n\n" f"Все участники будут исключены{refund_text}",
        reply_markup=_confirm_keyboard("disband", user_id, "Распустить"),
    )


async def _handle_disband(query, user_id: int):
    """Execute disband."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang or member.role != "leader":
            await query.answer("Только лидер", show_alert=True)
            return

        user = db.query(User).filter(User.telegram_id == user_id).first()
        refund = gang.bank
        if refund > 0:
            user.balance += refund

        gang_name = html.escape(gang.name)
        db.delete(gang)
        balance = user.balance

    refund_text = f"\n💰 Возврат из банка: {format_diamonds(refund)}" if refund > 0 else ""

    await query.answer()
    await safe_edit_message(
        query,
        f"💥 <b>Банда распущена</b>\n\n«{gang_name}» больше не существует{refund_text}\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
    )
    logger.info("Gang disbanded", user_id=user_id, name=gang_name, refund=refund)


async def _handle_back(query, user_id: int):
    """Back to gang menu."""
    with get_db() as db:
        text, keyboard = _build_gang_info(db, user_id)
    await query.answer()
    await safe_edit_message(query, text, reply_markup=keyboard)


# ==================== TYPED SUBCOMMANDS (still supported) ====================


async def gang_create(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Create a new gang."""
    if len(context.args) < 2:
        await update.message.reply_text(
            f"❌ Укажи название\n\n<code>/gang create [название]</code>"
            f"\n\nСтоимость: {format_diamonds(GANG_CREATE_COST)}",
            parse_mode="HTML",
        )
        return

    name = " ".join(context.args[1:])[:30].strip()

    if len(name) < 2:
        await update.message.reply_text("❌ Название слишком короткое (мин. 2 символа)")
        return

    with get_db() as db:
        existing_member = db.query(GangMember).filter(GangMember.user_id == user_id).first()
        if existing_member:
            await update.message.reply_text("❌ Ты уже состоишь в банде")
            return

        existing_gang = db.query(Gang).filter(Gang.name == name).first()
        if existing_gang:
            await update.message.reply_text("❌ Банда с таким названием уже существует")
            return

        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.balance < GANG_CREATE_COST:
            await update.message.reply_text(
                f"❌ Нужно {format_diamonds(GANG_CREATE_COST)}, у тебя {format_diamonds(user.balance if user else 0)}"
            )
            return

        user.balance -= GANG_CREATE_COST
        gang = Gang(name=name, leader_id=user_id)
        db.add(gang)
        db.flush()
        db.add(GangMember(gang_id=gang.id, user_id=user_id, role="leader"))
        balance = user.balance
        safe_name = html.escape(name)

    await update.message.reply_text(
        f"🔫 <b>Банда создана!</b>\n\n"
        f"Название: {safe_name}\n"
        f"Стоимость: {format_diamonds(GANG_CREATE_COST)}\n\n"
        f"<code>/gang invite @user</code> — пригласить участников\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )
    logger.info("Gang created", user_id=user_id, name=name)


async def gang_invite(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Invite someone to the gang."""
    if len(context.args) < 2:
        await update.message.reply_text("❌ <code>/gang invite @username</code>", parse_mode="HTML")
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

        current_count = db.query(GangMember).filter(GangMember.gang_id == gang.id).count()
        max_members = GANG_MAX_MEMBERS_BY_LEVEL.get(gang.level, 5)
        if current_count >= max_members:
            await update.message.reply_text(
                f"❌ Банда полна ({format_word(current_count, 'участник', 'участника', 'участников')}/{max_members})"
            )
            return

        target = db.query(User).filter(User.username == target_username).first()
        if not target:
            await update.message.reply_text(f"❌ Игрок @{html.escape(target_username)} не найден")
            return

        if target.telegram_id == user_id:
            await update.message.reply_text("❌ Ты уже в банде")
            return

        target_member = db.query(GangMember).filter(GangMember.user_id == target.telegram_id).first()
        if target_member:
            await update.message.reply_text("❌ Этот игрок уже состоит в банде")
            return

        gang_name = html.escape(gang.name)
        gang_id = gang.id
        target_id = target.telegram_id

    keyboard = [
        [
            InlineKeyboardButton("Принять", callback_data=f"gang:accept:{gang_id}:{target_id}"),
            InlineKeyboardButton("Отклонить", callback_data=f"gang:decline:{gang_id}:{target_id}"),
        ]
    ]

    await update.message.reply_text(
        f"🔫 <b>Приглашение в банду</b>\n\n" f"@{html.escape(target_username)}, тебя приглашают в «{gang_name}»",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
        user_check = db.query(User).filter(User.telegram_id == target_id).first()
        if not user_check or user_check.is_banned:
            await safe_edit_message(query, "❌ Доступ запрещён")
            return

        gang = db.query(Gang).filter(Gang.id == gang_id).first()
        if not gang:
            await safe_edit_message(query, "❌ Банда больше не существует")
            return

        existing = db.query(GangMember).filter(GangMember.user_id == target_id).first()
        if existing:
            await safe_edit_message(query, "❌ Ты уже состоишь в банде")
            return

        current_count = db.query(GangMember).filter(GangMember.gang_id == gang_id).count()
        max_members = GANG_MAX_MEMBERS_BY_LEVEL.get(gang.level, 5)
        if current_count >= max_members:
            await safe_edit_message(query, "❌ Банда уже полна")
            return

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


async def gang_kick(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Kick a member from the gang."""
    if len(context.args) < 2:
        await update.message.reply_text("❌ <code>/gang kick @username</code>", parse_mode="HTML")
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

        target_member = (
            db.query(GangMember).filter(GangMember.gang_id == gang.id, GangMember.user_id == target.telegram_id).first()
        )

        if not target_member:
            await update.message.reply_text("❌ Этот игрок не в твоей банде")
            return

        if target_member.role == "leader":
            await update.message.reply_text("❌ Нельзя выгнать лидера")
            return

        db.delete(target_member)

    await update.message.reply_text(f"✅ @{html.escape(target_username)} выгнан из банды")
    logger.info("Gang member kicked", user_id=user_id, kicked=target_username)


# Legacy typed subcommands (redirect to same logic as buttons)


async def gang_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Deposit diamonds into gang bank (typed)."""
    if len(context.args) < 2:
        await update.message.reply_text(
            f"❌ <code>/gang deposit [сумма]</code>\n\nМинимум: {format_diamonds(GANG_DEPOSIT_MIN)}", parse_mode="HTML"
        )
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
            await update.message.reply_text(f"❌ Недостаточно алмазов\n\nУ тебя: {format_diamonds(user.balance)}")
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


async def gang_leave_typed(update: Update, user_id: int):
    """Leave current gang (typed)."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang:
            await update.message.reply_text("❌ Ты не состоишь в банде")
            return
        if member.role == "leader":
            await update.message.reply_text("❌ Лидер не может покинуть банду\n\n/gang disband — распустить")
            return
        db.delete(member)
        gang_name = html.escape(gang.name)

    await update.message.reply_text(f"✅ Ты покинул банду «{gang_name}»")
    logger.info("Gang member left", user_id=user_id)


async def gang_upgrade_typed(update: Update, user_id: int):
    """Upgrade gang level (typed)."""
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
                f"❌ Недостаточно в банке\n\nНужно: {format_diamonds(cost)}\nВ банке: {format_diamonds(gang.bank)}"
            )
            return

        gang.bank -= cost
        gang.level = next_level
        new_max = GANG_MAX_MEMBERS_BY_LEVEL.get(next_level, 5)
        bank = gang.bank
        gang_name = html.escape(gang.name)

    await update.message.reply_text(
        f"⬆️ <b>Банда улучшена!</b>\n\n«{gang_name}» — уровень {next_level}"
        f"\nМакс. участников: {new_max}\nБанк: {format_diamonds(bank)}",
        parse_mode="HTML",
    )
    logger.info("Gang upgraded", user_id=user_id, level=next_level, cost=cost)


async def gang_disband_typed(update: Update, user_id: int):
    """Disband the gang (typed, leader only)."""
    with get_db() as db:
        gang, member = get_user_gang(db, user_id)
        if not gang or member.role != "leader":
            await update.message.reply_text("❌ Только лидер может распустить банду")
            return

        user = db.query(User).filter(User.telegram_id == user_id).first()
        refund = gang.bank
        if refund > 0:
            user.balance += refund
        gang_name = html.escape(gang.name)
        db.delete(gang)
        balance = user.balance

    refund_text = f"\n💰 Возврат из банка: {format_diamonds(refund)}" if refund > 0 else ""
    await update.message.reply_text(
        f"💥 <b>Банда распущена</b>\n\n«{gang_name}» больше не существует{refund_text}\n\n"
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
            await update.message.reply_text(
                "🔫 Пока нет банд\n\n<code>/gang create [название]</code> — создать первую!", parse_mode="HTML"
            )
            return

        text = "🔫 <b>Топ банд</b>\n\n"
        for i, gang in enumerate(gangs, 1):
            member_count = db.query(GangMember).filter(GangMember.gang_id == gang.id).count()
            leader = db.query(User).filter(User.telegram_id == gang.leader_id).first()
            leader_display = (
                f"@{html.escape(leader.username)}" if leader and leader.username else f"ID {gang.leader_id}"
            )

            text += (
                f"{i}. <b>{html.escape(gang.name)}</b> (ур.{gang.level})\n"
                f"   👑 {leader_display} | "
                f"{format_word(member_count, 'участник', 'участника', 'участников')}"
                f" | Банк: {format_diamonds(gang.bank)}\n\n"
            )

    reply = await update.message.reply_text(text, parse_mode="HTML")
    await delete_command_and_reply(update, reply, context, delay=90)


def register_gang_handlers(application):
    """Register gang handlers."""
    application.add_handler(CommandHandler("gang", gang_command))
    application.add_handler(CommandHandler("gangs", gangs_command))
    # New unified callback handler (must be registered BEFORE specific accept/decline)
    application.add_handler(
        CallbackQueryHandler(
            gang_callback, pattern=r"^gang:(dep|upgrade|upgrade_yes|leave|leave_yes|disband|disband_yes|back):"
        )
    )
    application.add_handler(CallbackQueryHandler(gang_accept_callback, pattern=r"^gang:accept:"))
    application.add_handler(CallbackQueryHandler(gang_decline_callback, pattern=r"^gang:decline:"))
    logger.info("Gang handlers registered")
