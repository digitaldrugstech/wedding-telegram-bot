"""Utility command handlers (balance, help, transfer)."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.constants import TRANSFER_FEE_RATE
from app.database.connection import get_db
from app.database.models import User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message


@require_registered
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /balance command."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            return

        await update.message.reply_text(f"💰 {format_diamonds(user.balance)}")


@require_registered
async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /transfer command."""
    if not update.effective_user or not update.message:
        return

    sender_id = update.effective_user.id

    # Parse arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "💰 <b>Перевод алмазов</b>\n\n"
            "Использование:\n"
            "/transfer @username [сумма]\n\n"
            "Пример: /transfer @user 100",
            parse_mode="HTML",
        )
        return

    # Parse username and amount
    username = context.args[0].lstrip("@")
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом")
        return

    # Validate amount
    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше 0")
        return

    with get_db() as db:
        # Get sender
        sender = db.query(User).filter(User.telegram_id == sender_id).first()

        if not sender:
            await update.message.reply_text("❌ Ошибка: пользователь не найден")
            return

        # Check balance
        if sender.balance < amount:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n" f"💰 Твой баланс: {format_diamonds(sender.balance)}"
            )
            return

        # Get recipient
        recipient = db.query(User).filter(User.username == username).first()

        if not recipient:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден")
            return

        # Can't transfer to self
        if sender_id == recipient.telegram_id:
            await update.message.reply_text("❌ Нельзя перевести себе")
            return

        # Execute transfer with fee
        fee = int(amount * TRANSFER_FEE_RATE / 100)
        received = amount - fee

        sender.balance -= amount
        recipient.balance += received

        db.commit()

        fee_text = f"\n💸 Комиссия: {format_diamonds(fee)} ({TRANSFER_FEE_RATE}%)" if fee > 0 else ""

        await update.message.reply_text(
            f"✅ <b>Перевод выполнен</b>\n\n"
            f"💰 {format_diamonds(received)} → @{username}{fee_text}\n\n"
            f"💰 Твой баланс: {format_diamonds(sender.balance)}",
            parse_mode="HTML",
        )

        # Track quest progress
        try:
            update_quest_progress(sender_id, "transfer", increment=amount)
        except Exception:
            pass


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with categories."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id

    keyboard = [
        [
            InlineKeyboardButton("💰 Экономика", callback_data=f"help:economy:{user_id}"),
            InlineKeyboardButton("🎰 Казино", callback_data=f"help:casino:{user_id}"),
        ],
        [
            InlineKeyboardButton("💍 Семья", callback_data=f"help:family:{user_id}"),
            InlineKeyboardButton("🏠 Дом", callback_data=f"help:house:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎮 Игры", callback_data=f"help:games:{user_id}"),
            InlineKeyboardButton("👥 Социальное", callback_data=f"help:social:{user_id}"),
        ],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data=f"help:info:{user_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_text = (
        "📖 <b>Справка</b>\n\n"
        "Выбери категорию команд:\n\n"
        "💰 Экономика — работа, бизнес, переводы\n"
        "🎰 Казино — игры на алмазы\n"
        "💍 Семья — браки, дети, свидания\n"
        "🏠 Дом — покупка и управление\n"
        "🎮 Игры — дуэли, квесты, питомцы\n"
        "👥 Социальное — друзья, подарки, рейтинги\n"
        "ℹ️ Инфо — профиль, статистика\n\n"
        "💎 Валюта — алмазы"
    )

    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode="HTML")


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help category callbacks."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")

    # Check button owner
    if len(parts) >= 3:
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("⚠️ Эта кнопка не для тебя", show_alert=True)
            return

    category = parts[1]

    # Back button
    back_button = [[InlineKeyboardButton("« Назад", callback_data=f"help:main:{user_id}")]]

    if category == "main":
        keyboard = [
            [
                InlineKeyboardButton("💰 Экономика", callback_data=f"help:economy:{user_id}"),
                InlineKeyboardButton("🎰 Казино", callback_data=f"help:casino:{user_id}"),
            ],
            [
                InlineKeyboardButton("💍 Семья", callback_data=f"help:family:{user_id}"),
                InlineKeyboardButton("🏠 Дом", callback_data=f"help:house:{user_id}"),
            ],
            [
                InlineKeyboardButton("🎮 Игры", callback_data=f"help:games:{user_id}"),
                InlineKeyboardButton("👥 Социальное", callback_data=f"help:social:{user_id}"),
            ],
            [InlineKeyboardButton("ℹ️ Инфо", callback_data=f"help:info:{user_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            "📖 <b>Справка</b>\n\n"
            "Выбери категорию команд:\n\n"
            "💰 Экономика — работа, бизнес, переводы\n"
            "🎰 Казино — игры на алмазы\n"
            "💍 Семья — браки, дети, свидания\n"
            "🏠 Дом — покупка и управление\n"
            "🎮 Игры — дуэли, квесты, питомцы\n"
            "👥 Социальное — друзья, подарки, рейтинги\n"
            "ℹ️ Инфо — профиль, статистика\n\n"
            "💎 Валюта — алмазы"
        )

    elif category == "economy":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "💰 <b>Экономика</b>\n\n"
            "/work — меню работы\n"
            "/job — работать на текущей должности\n"
            "/business — меню бизнеса\n"
            "/transfer @user [сумма] — перевести алмазы\n"
            "/balance — проверить баланс\n"
            "/daily — ежедневный бонус\n"
            "/lottery — лотерея (джекпот)\n"
            "/giftbox — гифт-бокс (50-500💎)\n"
            "/shop — магазин титулов\n"
            "/insurance — страховка от ограблений\n"
            "/prestige — сброс за +5% к доходу\n\n"
            "<b>Как это работает:</b>\n"
            "• Выбери профессию через /work\n"
            "• Работай /job для повышения уровня\n"
            "• Открывай бизнесы для пассивного дохода\n"
            "• Переводи алмазы друзьям"
        )

    elif category == "casino":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "🎰 <b>Казино</b>\n\n"
            "/casino — открыть меню казино\n"
            "/slots — слот-машина (до x30)\n"
            "/dice — кости (до x3)\n"
            "/darts — дартс (до x5)\n"
            "/basketball — баскетбол (до x3)\n"
            "/bowling — боулинг (до x4)\n"
            "/football — футбол (до x3)\n"
            "/blackjack — блэкджек (до x2.5)\n"
            "/scratch — скретч-карта (до x5)\n"
            "/coinflip — монетка (x1.9)\n"
            "/rob — ограбить игрока\n\n"
            "<b>Как играть:</b>\n"
            "• Выбери игру и сделай ставку\n"
            "• Выигрывай или проигрывай алмазы\n"
            "• Чем выше ставка, тем больше риск"
        )

    elif category == "family":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "💍 <b>Семья</b>\n\n"
            "/propose @username — предложить брак\n"
            "/marriage — меню брака\n"
            "/gift [сумма] — подарить алмазы супругу\n"
            "/makelove — заняться любовью (24ч кд)\n"
            "/date — свидание (12ч кд)\n"
            "/cheat @username — измена (30% риск развода)\n"
            "/family — меню детей\n\n"
            "<b>Как создать семью:</b>\n"
            "• Предложи брак через /propose\n"
            "• Занимайся любовью для зачатия детей\n"
            "• Воспитывай детей через /family"
        )

    elif category == "house":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "🏠 <b>Дом</b>\n\n"
            "/house — меню дома\n\n"
            "<b>Зачем нужен дом:</b>\n"
            "• Защита от похищений детей\n"
            "• Престиж в обществе\n"
            "• Место для семьи\n\n"
            "<b>Типы домов:</b>\n"
            "1. Хрущевка — базовая защита\n"
            "2. Панелька — средняя защита\n"
            "3. Кирпичный — хорошая защита\n"
            "4. Коттедж — отличная защита\n"
            "5. Особняк — элитная защита\n"
            "6. Пентхаус — максимальная защита"
        )

    elif category == "games":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "🎮 <b>Игры</b>\n\n"
            "/duel @username [ставка] — дуэль на алмазы\n"
            "/mine — копать в шахте\n"
            "/wheel — колесо фортуны\n"
            "/quest — случайный квест\n"
            "/pet — питомец\n"
            "/pet shop — аксессуары для питомца\n"
            "/pet rename — переименовать питомца\n"
            "/fish — рыбалка\n"
            "/fishlist — виды рыб"
        )

    elif category == "social":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "👥 <b>Социальное</b>\n\n"
            "/friends — список друзей\n"
            "/addfriend @user — добавить в друзья\n"
            "/removefriend @user — удалить из друзей\n"
            "/gift @user [сумма] — подарок другу (мин. 10)\n"
            "/reputation @user [+/-] — репутация\n"
            "/achievements — достижения\n"
            "/rating — рейтинг игроков\n\n"
            "<b>Как это работает:</b>\n"
            "• Добавляй друзей через /addfriend\n"
            "• Дари алмазы только друзьям (без комиссии)\n"
            "• Ставь репутацию раз в день\n"
            "• Получай достижения за прогресс"
        )

    elif category == "info":
        reply_markup = InlineKeyboardMarkup(back_button)
        text = (
            "ℹ️ <b>Информация</b>\n\n"
            "/profile — твой профиль\n"
            "/stats — статистика бота\n"
            "/help — эта справка\n\n"
            "<b>Полезная информация:</b>\n"
            "• Валюта — алмазы (💎)\n"
            "• Все команды работают на русском\n"
            "• Нашёл баг? /bug_report"
        )

    else:
        return

    await safe_edit_message(query, text, reply_markup=reply_markup)


def register_utils_handlers(application):
    """Register utility handlers."""
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("transfer", transfer_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(help_callback, pattern="^help:"))
