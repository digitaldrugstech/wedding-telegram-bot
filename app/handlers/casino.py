"""Casino handlers for Wedding Telegram Bot."""

import structlog
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.handlers.quest import update_quest_progress
from app.services.casino_service import (
    BASKETBALL,
    BOWLING,
    DARTS,
    DICE,
    FOOTBALL,
    MAX_BET,
    MIN_BET,
    SLOT_MACHINE,
    CasinoService,
)
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import casino_after_game_keyboard, casino_menu_keyboard

logger = structlog.get_logger()

# Emoji map for dice-based games
DICE_GAME_EMOJI = {
    SLOT_MACHINE: "🎰",
    DICE: "🎲",
    DARTS: "🎯",
    BASKETBALL: "🏀",
    BOWLING: "🎳",
    FOOTBALL: "⚽",
}


@require_registered
async def casino_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /casino command - show available games."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        from app.database.models import User

        user = db.query(User).filter(User.telegram_id == user_id).first()
        balance = user.balance if user else 0

    casino_text = f"🎰 <b>Казино</b>\n\n💰 Баланс: {format_diamonds(balance)}\n\nВыбери игру:"

    await update.message.reply_text(casino_text, parse_mode="HTML", reply_markup=casino_menu_keyboard(user_id))


async def _play_casino_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str, emoji: str):
    """Universal casino game handler."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Parse bet amount
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            f"❌ Укажи ставку: /{game_type} [ставка]\n\n"
            f"Пример: /{game_type} 50\n"
            f"Лимиты: {format_diamonds(MIN_BET)} - {format_diamonds(MAX_BET)}"
        )
        return

    try:
        bet_amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом")
        return

    # Reserve bet (deduct immediately to prevent TOCTOU race condition)
    with get_db() as db:
        can_bet, error_msg = CasinoService.reserve_bet(db, user_id, bet_amount)
        if not can_bet:
            await update.message.reply_text(f"❌ {error_msg}")
            return

    # Send dice (bet already deducted)
    await update.message.chat.send_action(ChatAction.TYPING)
    dice_message = await update.message.reply_dice(emoji=emoji)
    dice_value = dice_message.dice.value

    # Schedule result processing after animation
    context.job_queue.run_once(
        _process_casino_result,
        when=4.5,  # Dice animation duration
        data={
            "chat_id": update.message.chat_id,
            "message_id": dice_message.message_id,
            "user_id": user_id,
            "game_type": game_type,
            "dice_value": dice_value,
            "bet_amount": bet_amount,
        },
    )


async def _process_casino_result(context: ContextTypes.DEFAULT_TYPE):
    """Process casino game result after dice animation."""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    user_id = job_data["user_id"]
    game_type = job_data["game_type"]
    dice_value = job_data["dice_value"]
    bet_amount = job_data["bet_amount"]

    try:
        with get_db() as db:
            success, message, winnings, balance = CasinoService.play_game(
                db, user_id, game_type, bet_amount, dice_value
            )

            if success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    reply_to_message_id=message_id,
                    reply_markup=casino_after_game_keyboard(game_type, user_id, bet=bet_amount),
                )
                # Track quest progress
                try:
                    update_quest_progress(user_id, "casino", db=db)
                except Exception:
                    pass
    except Exception as e:
        import structlog

        logger = structlog.get_logger()
        logger.error("Failed to process casino result", user_id=user_id, game_type=game_type, error=str(e))


@require_registered
async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /slots command - slot machine."""
    await _play_casino_game(update, context, SLOT_MACHINE, "🎰")


@require_registered
async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dice command - dice game."""
    await _play_casino_game(update, context, DICE, "🎲")


@require_registered
async def darts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /darts command - darts game."""
    await _play_casino_game(update, context, DARTS, "🎯")


@require_registered
async def basketball_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /basketball command - basketball game."""
    await _play_casino_game(update, context, BASKETBALL, "🏀")


@require_registered
async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bowling command - bowling game."""
    await _play_casino_game(update, context, BOWLING, "🎳")


@require_registered
async def football_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /football command - football game."""
    await _play_casino_game(update, context, FOOTBALL, "⚽")


@require_registered
async def casinostats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /casinostats command - show casino statistics."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        stats = CasinoService.get_user_stats(db, user_id)

        if stats["total_games"] == 0:
            await update.message.reply_text(
                "📊 <b>Статистика казино</b>\n\n" "Ты ещё не играл в казино\n\n" "💡 /casino — список игр",
                parse_mode="HTML",
            )
            return

        # Format profit with sign
        profit = stats["total_profit"]
        profit_text = f"+{format_diamonds(profit)}" if profit >= 0 else f"-{format_diamonds(abs(profit))}"
        profit_emoji = "📈" if profit >= 0 else "📉"

        message = (
            "📊 <b>Статистика казино</b>\n\n"
            f"🎮 Игр сыграно: {stats['total_games']}\n"
            f"💰 Поставлено: {format_diamonds(stats['total_bet'])}\n"
            f"🏆 Выиграно: {format_diamonds(stats['total_winnings'])}\n"
            f"{profit_emoji} Профит: {profit_text}\n"
            f"📊 Винрейт: {stats['win_rate']:.1f}%"
        )

        await update.message.reply_text(message, parse_mode="HTML")


async def casino_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bet selection from buttons — cbet:{game}:{amount}:{user_id}."""
    query = update.callback_query
    if not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 4:
        return

    game = parts[1]
    amount_str = parts[2]
    owner_id = int(parts[3])

    if update.effective_user.id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    # Only handle dice-based games here
    if game not in DICE_GAME_EMOJI:
        return

    user_id = update.effective_user.id
    chat_id = query.message.chat_id

    # Parse bet amount
    from app.database.models import User

    if amount_str == "all":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user or user.is_banned:
                await query.answer("Доступ запрещён", show_alert=True)
                return
            bet_amount = min(user.balance, MAX_BET)
            if bet_amount < MIN_BET:
                await query.answer(f"Недостаточно алмазов (мин. {MIN_BET})", show_alert=True)
                return
    else:
        try:
            bet_amount = int(amount_str)
        except ValueError:
            return

    # Reserve bet (deduct immediately)
    with get_db() as db:
        can_bet, error_msg = CasinoService.reserve_bet(db, user_id, bet_amount)
        if not can_bet:
            await query.answer(f"❌ {error_msg}", show_alert=True)
            return

    await query.answer()

    # Update the bet picker message to show "playing"
    try:
        await query.edit_message_text(
            f"🎲 Ставка: {format_diamonds(bet_amount)}...",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Send dice
    emoji = DICE_GAME_EMOJI[game]
    dice_message = await context.bot.send_dice(chat_id=chat_id, emoji=emoji)
    dice_value = dice_message.dice.value

    # Schedule result processing after animation
    context.job_queue.run_once(
        _process_casino_result,
        when=4.5,
        data={
            "chat_id": chat_id,
            "message_id": dice_message.message_id,
            "user_id": user_id,
            "game_type": game,
            "dice_value": dice_value,
            "bet_amount": bet_amount,
        },
    )


def register_casino_handlers(application):
    """Register casino handlers."""
    application.add_handler(CommandHandler("casino", casino_command))
    application.add_handler(CommandHandler("casinostats", casinostats_command))
    application.add_handler(CommandHandler("slots", slots_command))
    application.add_handler(CommandHandler("dice", dice_command))
    application.add_handler(CommandHandler("darts", darts_command))
    application.add_handler(CommandHandler("basketball", basketball_command))
    application.add_handler(CommandHandler("bowling", bowling_command))
    application.add_handler(CommandHandler("football", football_command))
    application.add_handler(
        CallbackQueryHandler(casino_bet_callback, pattern=r"^cbet:(slots|dice|darts|basketball|bowling|football):")
    )
