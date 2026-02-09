"""Economy handlers for advanced features."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.constants import (
    AUCTION_DURATION_HOURS,
    AUCTION_ITEMS,
    INVESTMENT_DURATION_DAYS,
    INVESTMENT_MAX_RETURN,
    INVESTMENT_MIN_AMOUNT,
    INVESTMENT_MIN_RETURN,
    STOCK_COMPANIES,
    TAX_RATE,
    TAX_THRESHOLD,
)
from app.database.connection import get_db
from app.database.models import (
    Auction,
    AuctionBid,
    Investment,
    Stock,
    TaxPayment,
    User,
    UserStock,
)
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_time_remaining

logger = structlog.get_logger()


@require_registered
async def invest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invest diamonds for weekly return."""
    user_id = update.effective_user.id

    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "📊 <b>Инвестиции</b>\n\n"
            "Вложи алмазы на неделю\n"
            "Доходность: от -20% до +50%\n\n"
            f"Минимум: {format_diamonds(INVESTMENT_MIN_AMOUNT)}\n\n"
            "Использование:\n"
            "/invest [количество]",
            parse_mode="HTML",
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Укажи число")
        return

    if amount < INVESTMENT_MIN_AMOUNT:
        await update.message.reply_text(f"Минимум: {format_diamonds(INVESTMENT_MIN_AMOUNT)}")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < amount:
            await update.message.reply_text(f"Недостаточно алмазов\n\nТвой баланс: {format_diamonds(user.balance)}")
            return

        # Check for active investments
        active_investment = (
            db.query(Investment).filter(Investment.user_id == user_id, Investment.is_completed.is_(False)).first()
        )

        if active_investment:
            remaining = (active_investment.completes_at - datetime.utcnow()).total_seconds()
            await update.message.reply_text(
                f"У тебя уже есть активная инвестиция\n\n" f"Завершится через {format_time_remaining(remaining)}"
            )
            return

        # Create investment
        return_percentage = random.randint(INVESTMENT_MIN_RETURN, INVESTMENT_MAX_RETURN)
        completes_at = datetime.utcnow() + timedelta(days=INVESTMENT_DURATION_DAYS)

        investment = Investment(
            user_id=user_id,
            amount=amount,
            return_percentage=return_percentage,
            is_completed=False,
            completes_at=completes_at,
        )

        user.balance -= amount
        db.add(investment)

        logger.info(
            "Investment created",
            user_id=user_id,
            amount=amount,
            return_percentage=return_percentage,
        )

        await update.message.reply_text(
            f"📊 <b>Инвестиция создана</b>\n\n"
            f"Вложено: {format_diamonds(amount)}\n"
            f"Завершится через {INVESTMENT_DURATION_DAYS} дней\n\n"
            f"Результат будет известен после завершения",
            parse_mode="HTML",
        )


@require_registered
async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stock exchange commands."""
    user_id = update.effective_user.id

    if not context.args:
        # Show stock prices
        with get_db() as db:
            stocks = db.query(Stock).all()

            if not stocks:
                # Initialize stocks
                for company in STOCK_COMPANIES:
                    stock = Stock(company=company, price=100)
                    db.add(stock)
                db.flush()
                stocks = db.query(Stock).all()

            text = "📈 <b>Биржа акций</b>\n\n"
            for stock in stocks:
                text += f"{stock.company}: {format_diamonds(stock.price)}/шт\n"

            # Show user's portfolio
            user_stocks = db.query(UserStock).filter(UserStock.user_id == user_id).all()

            if user_stocks:
                text += "\n<b>Твой портфель:</b>\n"
                total_value = 0
                for us in user_stocks:
                    stock = db.query(Stock).filter(Stock.company == us.company).first()
                    value = us.quantity * stock.price
                    total_value += value
                    text += f"{us.company}: {us.quantity} шт ({format_diamonds(value)})\n"
                text += f"\nОбщая стоимость: {format_diamonds(total_value)}"

            text += "\n\n/stock buy [компания] [количество]\n/stock sell [компания] [количество]"

            await update.message.reply_text(text, parse_mode="HTML")
            return

    action = context.args[0].lower()

    if action == "buy":
        if len(context.args) < 3:
            await update.message.reply_text("Использование: /stock buy [компания] [количество]")
            return

        company = " ".join(context.args[1:-1])
        try:
            quantity = int(context.args[-1])
        except ValueError:
            await update.message.reply_text("Укажи число")
            return

        if quantity <= 0:
            await update.message.reply_text("Количество должно быть больше 0")
            return

        with get_db() as db:
            stock = db.query(Stock).filter(Stock.company == company).first()

            if not stock:
                await update.message.reply_text(
                    f"Компания не найдена\n\nДоступные компании:\n" + "\n".join(STOCK_COMPANIES)
                )
                return

            cost = stock.price * quantity
            user = db.query(User).filter(User.telegram_id == user_id).first()

            if user.balance < cost:
                await update.message.reply_text(
                    f"Недостаточно алмазов\n\nНужно: {format_diamonds(cost)}\nУ тебя: {format_diamonds(user.balance)}"
                )
                return

            # Buy stocks
            user.balance -= cost

            user_stock = db.query(UserStock).filter(UserStock.user_id == user_id, UserStock.company == company).first()

            if user_stock:
                user_stock.quantity += quantity
            else:
                user_stock = UserStock(user_id=user_id, company=company, quantity=quantity)
                db.add(user_stock)

            logger.info("Stock purchased", user_id=user_id, company=company, quantity=quantity, cost=cost)

            await update.message.reply_text(
                f"✅ <b>Куплено</b>\n\n"
                f"{company}: {quantity} шт\n"
                f"Стоимость: {format_diamonds(cost)}\n\n"
                f"Баланс: {format_diamonds(user.balance)}",
                parse_mode="HTML",
            )

    elif action == "sell":
        if len(context.args) < 3:
            await update.message.reply_text("Использование: /stock sell [компания] [количество]")
            return

        company = " ".join(context.args[1:-1])
        try:
            quantity = int(context.args[-1])
        except ValueError:
            await update.message.reply_text("Укажи число")
            return

        if quantity <= 0:
            await update.message.reply_text("Количество должно быть больше 0")
            return

        with get_db() as db:
            user_stock = db.query(UserStock).filter(UserStock.user_id == user_id, UserStock.company == company).first()

            if not user_stock or user_stock.quantity < quantity:
                await update.message.reply_text(
                    f"У тебя нет столько акций\n\nУ тебя: {user_stock.quantity if user_stock else 0} шт"
                )
                return

            stock = db.query(Stock).filter(Stock.company == company).first()
            revenue = stock.price * quantity

            user = db.query(User).filter(User.telegram_id == user_id).first()
            user.balance += revenue

            user_stock.quantity -= quantity
            if user_stock.quantity == 0:
                db.delete(user_stock)

            logger.info("Stock sold", user_id=user_id, company=company, quantity=quantity, revenue=revenue)

            await update.message.reply_text(
                f"✅ <b>Продано</b>\n\n"
                f"{company}: {quantity} шт\n"
                f"Выручка: {format_diamonds(revenue)}\n\n"
                f"Баланс: {format_diamonds(user.balance)}",
                parse_mode="HTML",
            )


@require_registered
async def auction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auction commands."""
    user_id = update.effective_user.id

    if not context.args:
        # Show active auctions
        with get_db() as db:
            auctions = db.query(Auction).filter(Auction.is_active.is_(True)).all()

            if not auctions:
                text = (
                    "🔨 <b>Аукцион</b>\n\n"
                    "Нет активных аукционов\n\n"
                    "/auction create [предмет] [начальная цена]\n"
                    "/auction bid [ID] [ставка]\n\n"
                    "Предметы:\n"
                )
                for item_id, item_data in AUCTION_ITEMS.items():
                    text += f"{item_data['emoji']} {item_data['name']}\n"

                await update.message.reply_text(text, parse_mode="HTML")
                return

            text = "🔨 <b>Активные аукционы</b>\n\n"
            for auction in auctions:
                item_data = AUCTION_ITEMS[auction.item]
                remaining = (auction.ends_at - datetime.utcnow()).total_seconds()
                winner_text = f"@{auction.current_winner.username}" if auction.current_winner else "Нет ставок"

                text += (
                    f"<b>ID {auction.id}</b>\n"
                    f"{item_data['emoji']} {item_data['name']}\n"
                    f"Текущая ставка: {format_diamonds(auction.current_price)}\n"
                    f"Лидер: {winner_text}\n"
                    f"Завершится через {format_time_remaining(remaining)}\n\n"
                )

            text += "\n/auction bid [ID] [ставка]"

            await update.message.reply_text(text, parse_mode="HTML")
            return

    action = context.args[0].lower()

    if action == "create":
        if len(context.args) < 3:
            await update.message.reply_text("Использование: /auction create [предмет] [начальная цена]")
            return

        item = context.args[1].lower()
        try:
            start_price = int(context.args[2])
        except ValueError:
            await update.message.reply_text("Укажи число для начальной цены")
            return

        if item not in AUCTION_ITEMS:
            text = "Неизвестный предмет\n\nДоступные предметы:\n"
            for item_id, item_data in AUCTION_ITEMS.items():
                text += f"{item_id}: {item_data['emoji']} {item_data['name']}\n"
            await update.message.reply_text(text)
            return

        if start_price <= 0:
            await update.message.reply_text("Начальная цена должна быть больше 0")
            return

        with get_db() as db:
            # Check if user has active auctions
            active_auction = (
                db.query(Auction).filter(Auction.creator_id == user_id, Auction.is_active.is_(True)).first()
            )

            if active_auction:
                await update.message.reply_text("У тебя уже есть активный аукцион")
                return

            ends_at = datetime.utcnow() + timedelta(hours=AUCTION_DURATION_HOURS)

            auction = Auction(
                creator_id=user_id,
                item=item,
                start_price=start_price,
                current_price=start_price,
                is_active=True,
                ends_at=ends_at,
            )

            db.add(auction)
            db.flush()

            item_data = AUCTION_ITEMS[item]

            logger.info("Auction created", user_id=user_id, auction_id=auction.id, item=item, start_price=start_price)

            await update.message.reply_text(
                f"🔨 <b>Аукцион создан</b>\n\n"
                f"ID: {auction.id}\n"
                f"{item_data['emoji']} {item_data['name']}\n"
                f"Начальная цена: {format_diamonds(start_price)}\n"
                f"Длительность: {AUCTION_DURATION_HOURS} часов",
                parse_mode="HTML",
            )

    elif action == "bid":
        if len(context.args) < 3:
            await update.message.reply_text("Использование: /auction bid [ID] [ставка]")
            return

        try:
            auction_id = int(context.args[1])
            bid_amount = int(context.args[2])
        except ValueError:
            await update.message.reply_text("Укажи числа для ID и ставки")
            return

        with get_db() as db:
            auction = db.query(Auction).filter(Auction.id == auction_id, Auction.is_active.is_(True)).first()

            if not auction:
                await update.message.reply_text("Аукцион не найден")
                return

            if auction.creator_id == user_id:
                await update.message.reply_text("Ты не можешь ставить на свой аукцион")
                return

            if bid_amount <= auction.current_price:
                await update.message.reply_text(
                    f"Ставка должна быть больше текущей\n\nТекущая ставка: {format_diamonds(auction.current_price)}"
                )
                return

            user = db.query(User).filter(User.telegram_id == user_id).first()

            if user.balance < bid_amount:
                await update.message.reply_text(f"Недостаточно алмазов\n\nБаланс: {format_diamonds(user.balance)}")
                return

            # Return previous winner's bid
            if auction.current_winner_id:
                prev_winner = db.query(User).filter(User.telegram_id == auction.current_winner_id).first()
                prev_winner.balance += auction.current_price

            # Place new bid
            user.balance -= bid_amount

            auction.current_price = bid_amount
            auction.current_winner_id = user_id

            bid = AuctionBid(auction_id=auction_id, user_id=user_id, amount=bid_amount)
            db.add(bid)

            item_data = AUCTION_ITEMS[auction.item]

            logger.info("Auction bid placed", user_id=user_id, auction_id=auction_id, amount=bid_amount)

            await update.message.reply_text(
                f"✅ <b>Ставка принята</b>\n\n"
                f"{item_data['emoji']} {item_data['name']}\n"
                f"Твоя ставка: {format_diamonds(bid_amount)}\n\n"
                f"Баланс: {format_diamonds(user.balance)}",
                parse_mode="HTML",
            )


@require_registered
async def tax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tax information."""
    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        taxable_amount = max(0, user.balance - TAX_THRESHOLD)
        weekly_tax = int(taxable_amount * TAX_RATE)

        # Get total taxes paid
        total_taxes = db.query(TaxPayment).filter(TaxPayment.user_id == user_id).count()
        total_paid = sum(t.amount for t in db.query(TaxPayment).filter(TaxPayment.user_id == user_id).all())

        text = (
            f"🏛 <b>Налоговая система</b>\n\n"
            f"Баланс: {format_diamonds(user.balance)}\n"
            f"Налогооблагаемая база: {format_diamonds(taxable_amount)}\n\n"
            f"Еженедельный налог: {format_diamonds(weekly_tax)}\n"
            f"Ставка: {int(TAX_RATE * 100)}% от суммы свыше {format_diamonds(TAX_THRESHOLD)}\n\n"
            f"Всего выплачено налогов: {format_diamonds(total_paid)}\n"
            f"Выплат: {total_taxes}"
        )

        await update.message.reply_text(text, parse_mode="HTML")


def register_economy_handlers(application):
    """Register economy handlers."""
    application.add_handler(CommandHandler("invest", invest_command))
    application.add_handler(CommandHandler("stock", stock_command))
    application.add_handler(CommandHandler("auction", auction_command))
    application.add_handler(CommandHandler("tax", tax_command))
