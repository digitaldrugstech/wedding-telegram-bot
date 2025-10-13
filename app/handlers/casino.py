"""Casino handlers for Wedding Telegram Bot."""

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
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


@require_registered
async def casino_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /casino command - show available games."""
    if not update.effective_user or not update.message:
        return

    casino_text = (
        "<b>🎰 Казино</b>\n\n"
        f"Ставка: {format_diamonds(MIN_BET)} - {format_diamonds(MAX_BET)}\n\n"
        "<b>Игры:</b>\n"
        "🎰 /slots [ставка] — Слот-машина (до x50)\n"
        "🎲 /dice [ставка] — Кости (до x5)\n"
        "🎯 /darts [ставка] — Дартс (до x10)\n"
        "🏀 /basketball [ставка] — Баскетбол (до x4)\n"
        "🎳 /bowling [ставка] — Боулинг (до x6)\n"
        "⚽ /football [ставка] — Футбол (до x5)\n\n"
        "💡 Выигрыш зависит от результата"
    )

    await update.message.reply_text(casino_text)


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

    # Check if user can bet
    with get_db() as db:
        can_bet, error_msg = CasinoService.can_bet(db, user_id, bet_amount)
        if not can_bet:
            await update.message.reply_text(f"❌ {error_msg}")
            return

    # Send dice
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

    with get_db() as db:
        success, message, winnings, balance = CasinoService.play_game(
            db, user_id, game_type, bet_amount, dice_value
        )

        if success:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                reply_to_message_id=message_id
            )


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


def register_casino_handlers(application):
    """Register casino handlers."""
    application.add_handler(CommandHandler("casino", casino_command))
    application.add_handler(CommandHandler("slots", slots_command))
    application.add_handler(CommandHandler("dice", dice_command))
    application.add_handler(CommandHandler("darts", darts_command))
    application.add_handler(CommandHandler("basketball", basketball_command))
    application.add_handler(CommandHandler("bowling", bowling_command))
    application.add_handler(CommandHandler("football", football_command))
