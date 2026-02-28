"""Assets / net worth dashboard."""

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import BankDeposit, Business, GangMember, House, Job, Marriage, User
from app.services.business_service import BUSINESS_TYPES, UPGRADE_MULTIPLIERS, get_maintenance_rate
from app.services.house_service import HOUSE_TYPES
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()


@require_registered
async def assets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /assets — show total empire overview."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return

        cash = user.balance
        prestige = user.prestige_level

        # Job info
        job = db.query(Job).filter(Job.user_id == user_id).first()
        job_line = ""
        if job:
            from app.handlers.work import PROFESSION_EMOJI, PROFESSION_NAMES, SALARY_RANGES

            emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
            name = PROFESSION_NAMES.get(job.job_type, job.job_type)
            salary_range = SALARY_RANGES.get(job.job_level, (0, 0))
            avg_salary = (salary_range[0] + salary_range[1]) // 2
            job_line = f"{emoji} {name} ур.{job.job_level} (~{format_diamonds(avg_salary)}/раз)"

        # Businesses
        businesses = db.query(Business).filter(Business.user_id == user_id).all()
        biz_count = len(businesses)
        biz_value = 0
        weekly_biz_income = 0
        rate = get_maintenance_rate(biz_count)
        for biz in businesses:
            info = BUSINESS_TYPES.get(biz.business_type, BUSINESS_TYPES[1])
            mult = UPGRADE_MULTIPLIERS.get(biz.upgrade_level, 1.0)
            biz_value += biz.purchase_price
            gross = int(info["weekly_payout"] * mult)
            weekly_biz_income += gross - int(gross * rate)

        # Bank deposits
        deposits = db.query(BankDeposit).filter(BankDeposit.user_id == user_id, BankDeposit.is_active.is_(True)).all()
        total_deposits = sum(d.amount for d in deposits)

        # House value
        house_value = 0
        marriage = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
            )
            .first()
        )
        if marriage:
            house = db.query(House).filter(House.marriage_id == marriage.id).first()
            if house:
                house_value = HOUSE_TYPES.get(house.house_type, {}).get("price", 0)

        # Gang bank share
        gang_share = 0
        membership = db.query(GangMember).filter(GangMember.user_id == user_id).first()
        if membership:
            from app.database.models import Gang

            gang = db.query(Gang).filter(Gang.id == membership.gang_id).first()
            if gang:
                member_count = db.query(GangMember).filter(GangMember.gang_id == gang.id).count()
                if member_count > 0:
                    gang_share = gang.bank // member_count

    # Calculate totals
    net_worth = cash + biz_value + total_deposits + house_value + gang_share
    weekly_income = weekly_biz_income  # Could add salary estimate later

    # Build message
    text = "🏛 <b>Твоя империя</b>\n\n"

    # Net worth breakdown
    text += f"💎 Наличные: {format_diamonds(cash)}\n"
    if biz_value:
        text += f"💼 Бизнесы ({biz_count}): {format_diamonds(biz_value)}\n"
    if total_deposits:
        text += f"🏦 Вклады: {format_diamonds(total_deposits)}\n"
    if house_value:
        text += f"🏠 Дом: {format_diamonds(house_value)}\n"
    if gang_share:
        text += f"⚔️ Доля в банде: ~{format_diamonds(gang_share)}\n"

    text += f"\n<b>Чистая стоимость: {format_diamonds(net_worth)}</b>\n"

    # Income section
    if weekly_biz_income or job_line:
        text += "\n📊 <b>Доход</b>\n"
        if job_line:
            text += f"{job_line}\n"
        if weekly_biz_income:
            text += f"💼 Бизнес: {format_diamonds(weekly_biz_income)}/нед\n"
        if total_deposits:
            weekly_interest = int(total_deposits * 0.02)
            text += f"🏦 Проценты: ~{format_diamonds(weekly_interest)}/нед\n"
        if weekly_income > 0 or total_deposits:
            total_passive = weekly_biz_income + int(total_deposits * 0.02)
            text += f"\n💰 Пассивный доход: {format_diamonds(total_passive)}/нед"

    # Prestige
    if prestige > 0:
        text += f"\n\n⭐ Престиж: {prestige} (+{prestige * 5}% к доходу)"

    # PRDX ad (light, occasional)
    if net_worth > 50000:
        text += "\n\n<i>Как настоящий тайкун на prdx.so</i>"

    await update.message.reply_text(text, parse_mode="HTML")


def register_assets_handlers(application):
    """Register assets handlers."""
    application.add_handler(CommandHandler("assets", assets_command))
    logger.info("Assets handlers registered")
