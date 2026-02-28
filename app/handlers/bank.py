"""Investment bank — deposit diamonds, earn 2% weekly interest."""

from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import BankDeposit, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

INTEREST_RATE = 0.02  # 2% per week
MIN_DEPOSIT = 100
MAX_TOTAL_DEPOSITS = 200000  # Max total deposited per user
LOCK_DAYS = 7  # Days before withdrawal allowed


@require_registered
async def bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bank command — show investment bank menu."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return
        balance = user.balance

        deposits = db.query(BankDeposit).filter(BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True)).all()
        total_deposited = sum(d.amount for d in deposits)

        # Calculate pending interest
        now = datetime.utcnow()
        total_interest = 0
        deposit_lines = []
        for d in deposits:
            weeks = (now - d.last_interest_at).total_seconds() / (7 * 86400)
            interest = int(d.amount * INTEREST_RATE * weeks)
            total_interest += interest
            unlock_at = d.deposited_at + timedelta(days=LOCK_DAYS)
            locked = now < unlock_at
            lock_str = f" (разблок. {unlock_at.strftime('%d.%m')})" if locked else ""
            deposit_lines.append(f"  {format_diamonds(d.amount)}{lock_str}")

    text = (
        f"🏦 <b>Инвестиционный банк</b>\n\n"
        f"💰 Баланс: {format_diamonds(balance)}\n"
        f"🏦 На вкладах: {format_diamonds(total_deposited)}\n"
    )
    if total_interest > 0:
        text += f"📈 Накопленные %: ~{format_diamonds(total_interest)}\n"

    if deposit_lines:
        text += "\n<b>Вклады:</b>\n" + "\n".join(deposit_lines) + "\n"

    text += (
        f"\n<b>Условия:</b>\n"
        f"• Ставка: {int(INTEREST_RATE * 100)}% в неделю\n"
        f"• Мин. вклад: {format_diamonds(MIN_DEPOSIT)}\n"
        f"• Макс. всего: {format_diamonds(MAX_TOTAL_DEPOSITS)}\n"
        f"• Блокировка: {LOCK_DAYS} дней\n"
        f"• Защита от /rob"
    )

    keyboard = [
        [
            InlineKeyboardButton("💰 Вложить", callback_data=f"bank:deposit_menu:{user_id}"),
            InlineKeyboardButton("💸 Снять", callback_data=f"bank:withdraw_menu:{user_id}"),
        ],
        [InlineKeyboardButton("📈 Собрать проценты", callback_data=f"bank:collect:{user_id}")],
    ]

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def bank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank callbacks."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    action = parts[1]

    # Owner check
    if len(parts) >= 3 and parts[-1].isdigit():
        owner_id = int(parts[-1])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    await query.answer()

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if action == "deposit_menu":
        # Show deposit amount buttons
        keyboard = []
        amounts = [500, 1000, 5000, 10000, 50000]
        row = []
        for amt in amounts:
            row.append(InlineKeyboardButton(f"{amt}", callback_data=f"bank:deposit:{amt}:{user_id}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"bank:back:{user_id}")])

        await safe_edit_message(
            query,
            f"💰 <b>Вложить в банк</b>\n\n"
            f"Выбери сумму вклада:\n"
            f"Мин: {format_diamonds(MIN_DEPOSIT)}, Макс всего: {format_diamonds(MAX_TOTAL_DEPOSITS)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif action == "deposit":
        try:
            amount = int(parts[2])
        except (ValueError, IndexError):
            return

        if amount < MIN_DEPOSIT:
            await safe_edit_message(query, f"❌ Минимальный вклад: {format_diamonds(MIN_DEPOSIT)}")
            return

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user or user.balance < amount:
                await safe_edit_message(query, "❌ Недостаточно алмазов")
                return

            total_amt = sum(
                d.amount
                for d in db.query(BankDeposit)
                .filter(BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True))
                .all()
            )

            if total_amt + amount > MAX_TOTAL_DEPOSITS:
                space = MAX_TOTAL_DEPOSITS - total_amt
                await safe_edit_message(query, f"❌ Лимит! Можно ещё {format_diamonds(max(0, space))}")
                return

            user.balance -= amount
            deposit = BankDeposit(user_id=user_id, amount=amount)
            db.add(deposit)
            db.flush()

            remaining_balance = user.balance
            unlock_date = (datetime.utcnow() + timedelta(days=LOCK_DAYS)).strftime("%d.%m")
            weekly_interest = int(amount * INTEREST_RATE)

        await safe_edit_message(
            query,
            f"🏦 <b>Вклад открыт!</b>\n\n"
            f"💰 Сумма: {format_diamonds(amount)}\n"
            f"📈 Доход: ~{format_diamonds(weekly_interest)}/нед\n"
            f"🔒 Разблокировка: {unlock_date}\n\n"
            f"💰 Остаток: {format_diamonds(remaining_balance)}",
        )
        logger.info("Bank deposit", user_id=user_id, amount=amount)

    elif action == "withdraw_menu":
        with get_db() as db:
            now = datetime.utcnow()
            deposits = (
                db.query(BankDeposit).filter(BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True)).all()
            )

            if not deposits:
                await safe_edit_message(query, "🏦 У тебя нет активных вкладов")
                return

            keyboard = []
            for d in deposits:
                unlock_at = d.deposited_at + timedelta(days=LOCK_DAYS)
                if now >= unlock_at:
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                f"Снять {format_diamonds(d.amount)}",
                                callback_data=f"bank:withdraw:{d.id}:{user_id}",
                            )
                        ]
                    )
            keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"bank:back:{user_id}")])

            if len(keyboard) == 1:
                await safe_edit_message(query, "🔒 Все вклады ещё заблокированы (7 дней с момента открытия)")
                return

            await safe_edit_message(
                query,
                "💸 <b>Снять вклад</b>\n\nВыбери вклад для снятия:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif action == "withdraw":
        try:
            deposit_id = int(parts[2])
        except (ValueError, IndexError):
            return

        with get_db() as db:
            deposit = (
                db.query(BankDeposit)
                .filter(BankDeposit.id == deposit_id, BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True))
                .first()
            )
            if not deposit:
                await safe_edit_message(query, "❌ Вклад не найден")
                return

            now = datetime.utcnow()
            unlock_at = deposit.deposited_at + timedelta(days=LOCK_DAYS)
            if now < unlock_at:
                await safe_edit_message(query, "🔒 Вклад ещё заблокирован")
                return

            # Calculate interest
            weeks = (now - deposit.last_interest_at).total_seconds() / (7 * 86400)
            interest = int(deposit.amount * INTEREST_RATE * weeks)
            total_return = deposit.amount + interest

            user = db.query(User).filter(User.telegram_id == user_id).first()
            if user:
                user.balance += total_return
                new_balance = user.balance
            else:
                new_balance = 0

            deposit_amount = deposit.amount
            deposit.is_active = False
            deposit.withdrawn_at = now

        await safe_edit_message(
            query,
            f"💸 <b>Вклад закрыт</b>\n\n"
            f"💰 Вклад: {format_diamonds(deposit_amount)}\n"
            f"📈 Проценты: +{format_diamonds(interest)}\n"
            f"💰 Получено: {format_diamonds(total_return)}\n\n"
            f"💰 Баланс: {format_diamonds(new_balance)}",
        )
        logger.info("Bank withdrawal", user_id=user_id, amount=deposit_amount, interest=interest)

    elif action == "collect":
        # Collect accumulated interest without closing deposits
        with get_db() as db:
            deposits = (
                db.query(BankDeposit).filter(BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True)).all()
            )

            if not deposits:
                await safe_edit_message(query, "🏦 У тебя нет активных вкладов")
                return

            now = datetime.utcnow()
            total_interest = 0
            for d in deposits:
                weeks = (now - d.last_interest_at).total_seconds() / (7 * 86400)
                interest = int(d.amount * INTEREST_RATE * weeks)
                if interest > 0:
                    total_interest += interest
                    d.last_interest_at = now

            if total_interest == 0:
                await safe_edit_message(query, "📈 Проценты ещё не накопились\n\nПроценты начисляются каждую неделю")
                return

            user = db.query(User).filter(User.telegram_id == user_id).first()
            if user:
                user.balance += total_interest
                new_balance = user.balance
            else:
                new_balance = 0

        await safe_edit_message(
            query,
            f"📈 <b>Проценты собраны!</b>\n\n"
            f"+{format_diamonds(total_interest)}\n\n"
            f"💰 Баланс: {format_diamonds(new_balance)}",
        )
        logger.info("Bank interest collected", user_id=user_id, interest=total_interest)

    elif action == "back":
        # Redirect to /bank view
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            balance = user.balance if user else 0

            deposits = (
                db.query(BankDeposit).filter(BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True)).all()
            )
            total_deposited = sum(d.amount for d in deposits)

        text = (
            f"🏦 <b>Инвестиционный банк</b>\n\n"
            f"💰 Баланс: {format_diamonds(balance)}\n"
            f"🏦 На вкладах: {format_diamonds(total_deposited)}\n\n"
            f"Ставка: {int(INTEREST_RATE * 100)}% в неделю"
        )

        keyboard = [
            [
                InlineKeyboardButton("💰 Вложить", callback_data=f"bank:deposit_menu:{user_id}"),
                InlineKeyboardButton("💸 Снять", callback_data=f"bank:withdraw_menu:{user_id}"),
            ],
            [InlineKeyboardButton("📈 Собрать проценты", callback_data=f"bank:collect:{user_id}")],
        ]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))


def register_bank_handlers(application):
    """Register bank handlers."""
    application.add_handler(CommandHandler("bank", bank_command))
    application.add_handler(CallbackQueryHandler(bank_callback, pattern=r"^bank:"))
    logger.info("Bank handlers registered")
