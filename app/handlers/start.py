"""Start and profile handlers."""

import html

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.constants import REFERRAL_INVITEE_REWARD
from app.database.connection import get_db
from app.database.models import Child, Job, User, UserAchievement
from app.handlers.work import PROFESSION_EMOJI, PROFESSION_NAMES
from app.services.business_service import BusinessService
from app.services.marriage_service import MarriageService
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.keyboards import gender_selection_keyboard, profile_keyboard
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with optional deep link referral parameter."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    # Parse deep link parameter (e.g., /start ref_123456)
    referrer_id = None
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg[4:])
            except ValueError:
                referrer_id = None

    # Store referrer_id in user_data for use during gender selection
    if referrer_id:
        context.user_data["referrer_id"] = referrer_id

    # Check if user already registered + referrer lookup in single session
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        is_registered = user is not None

        ref_text = ""
        if not is_registered and referrer_id and referrer_id != user_id:
            referrer = db.query(User).filter(User.telegram_id == referrer_id).first()
            if referrer:
                ref_name = f"@{referrer.username}" if referrer.username else "друга"
                ref_text = f"\n🎁 По приглашению {ref_name} — бонус {format_diamonds(REFERRAL_INVITEE_REWARD)}!\n"

    if is_registered:
        # Already registered — show profile hint
        if referrer_id:
            await update.message.reply_text(
                "👋 Ты уже зарегистрирован\n\n" "/profile — твой профиль\n" "/help — справка",
            )
        else:
            await update.message.reply_text(
                "👋 С возвращением!\n\n" "/profile — профиль\n" "/help — справка\n" "/menu — главное меню",
            )
        return

    await update.message.reply_text(
        f"👋 Привет, {username}\n\n"
        f"Wedding Bot — семейная жизнь на сервере\n{ref_text}\n"
        f"💍 Женись, заводи детей\n"
        f"💼 Работай, покупай дом\n"
        f"💰 Открывай бизнес\n"
        f"🎰 Играй в казино\n\n"
        f"Выбери пол:",
        reply_markup=gender_selection_keyboard(user_id),
    )


@button_owner_only
async def gender_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gender selection callback."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    gender = query.data.split(":")[1]  # "gender:male:user_id" -> "male"

    is_new_user = False
    referrer_id = context.user_data.get("referrer_id")
    referral_bonus = 0

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user:
            # Update gender
            user.gender = gender
            user.username = username
        else:
            # Create new user (with referral bonus if applicable)
            starting_balance = 0
            if referrer_id and referrer_id != user_id:
                starting_balance = REFERRAL_INVITEE_REWARD
                referral_bonus = REFERRAL_INVITEE_REWARD

            user = User(telegram_id=user_id, username=username, gender=gender, balance=starting_balance)
            db.add(user)
            is_new_user = True

    # Award "first_steps" achievement for new users
    if is_new_user:
        from app.handlers.social import check_and_award_achievement

        check_and_award_achievement(user_id, "first_steps")

        # Process referral
        if referrer_id and referrer_id != user_id:
            from app.handlers.referral import process_referral_registration

            if process_referral_registration(referrer_id, user_id):
                logger.info("Referral registration processed", referrer_id=referrer_id, referred_id=user_id)

    # Clear referrer from user_data
    context.user_data.pop("referrer_id", None)

    gender_emoji = "♂️" if gender == "male" else "♀️"
    bonus_text = ""
    if referral_bonus > 0:
        bonus_text = f"\n🎁 Бонус за приглашение: {format_diamonds(referral_bonus)}\n"

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    onboarding_keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💼 Выбрать работу", callback_data=f"onboard:work:{user_id}")],
            [
                InlineKeyboardButton("🎰 Казино", callback_data=f"onboard:casino:{user_id}"),
                InlineKeyboardButton("🎁 Бонус", callback_data=f"onboard:daily:{user_id}"),
            ],
        ]
    )

    await safe_edit_message(
        query,
        f"✅ {gender_emoji} <b>Добро пожаловать!</b>{bonus_text}\n\n"
        f"С чего начать:\n"
        f"1. Выбери профессию — зарабатывай алмазы\n"
        f"2. Забирай /daily бонус каждый день\n"
        f"3. Предложи кому-то /propose 💍\n\n"
        f"Жми кнопку:",
        reply_markup=onboarding_keyboard,
    )


@button_owner_only
async def onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle onboarding button clicks after registration."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    action = query.data.split(":")[1]  # "onboard:work:user_id" -> "work"

    if action == "work":
        # Show profession selection for new user
        from app.utils.keyboards import work_menu_keyboard

        await safe_edit_message(
            query,
            "💼 <b>Выбери профессию</b>\n\n"
            "Каждая профессия приносит алмазы.\n"
            "Работай /job → повышай уровень → больше зарплата!",
            reply_markup=work_menu_keyboard(has_job=False, user_id=user_id),
        )

    elif action == "casino":
        # Show casino menu
        from app.utils.keyboards import casino_menu_keyboard

        await safe_edit_message(
            query,
            "🎰 <b>Казино</b>\n\n"
            "Выбери игру и сделай ставку.\n"
            "Чем выше ставка — тем больше выигрыш (или проигрыш)!\n\n"
            "💡 Начни с /daily чтобы получить стартовые алмазы",
            reply_markup=casino_menu_keyboard(user_id),
        )

    elif action == "daily":
        # Tell user to use /daily command (can't trigger command from callback)
        await safe_edit_message(
            query,
            "🎁 <b>Ежедневный бонус</b>\n\n"
            "Напиши /daily чтобы забрать бонус!\n\n"
            "📅 Бонус растёт с каждым днём серии:\n"
            "День 1: 10💎 → День 7: 100💎\n"
            "🏆 Бонусы за серию: 7д (+50💎), 14д (+150💎), 30д (+500💎)",
        )


@require_registered
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            return

        # Get job info
        job = db.query(Job).filter(Job.user_id == user_id).first()
        job_info = "Нет работы"
        if job:
            emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
            name = PROFESSION_NAMES.get(job.job_type, job.job_type)
            job_info = f"{emoji} {name} (уровень {job.job_level})"

        # Get business info
        businesses = BusinessService.get_user_businesses(db, user_id)
        if businesses:
            total_income = sum(b["weekly_payout"] for b in businesses)
            business_info = f"{len(businesses)} бизнесов (+{format_diamonds(total_income)}/нед)"
        else:
            business_info = "Нет бизнесов"

        # Get marriage info
        marriage = MarriageService.get_active_marriage(db, user_id)
        if marriage:
            partner_id = MarriageService.get_partner_id(marriage, user_id)
            partner = db.query(User).filter(User.telegram_id == partner_id).first()
            partner_name = html.escape(partner.username) if partner and partner.username else f"User{partner_id}"
            marriage_info = f"Женат/Замужем (@{partner_name})"
        else:
            marriage_info = "Не в браке"

        # Get children count
        children_count = (
            db.query(Child)
            .filter((Child.parent1_id == user_id) | (Child.parent2_id == user_id), Child.is_alive.is_(True))
            .count()
        )

        # Get achievements count
        achievements_count = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).count()

        gender_emoji = "♂️" if user.gender == "male" else "♀️"
        rep_emoji = "⭐" if user.reputation >= 0 else "💀"

        # Title display
        title_display = ""
        if user.active_title:
            from app.handlers.shop import SHOP_TITLES

            title_info = SHOP_TITLES.get(user.active_title)
            if title_info:
                title_display = f" | {title_info['display']}"

        # Prestige display
        prestige_display = ""
        prestige = user.prestige_level or 0
        if prestige > 0:
            from app.handlers.prestige import get_prestige_display

            prestige_display = f"\n🔄 Престиж: {get_prestige_display(prestige)} (+{prestige * 5}% доход)"

        # Active boosts display
        from app.handlers.premium import _format_active_boosts, get_vip_badge, has_ever_purchased

        boosts_text = _format_active_boosts(user_id, db=db)
        boosts_display = f"\n\n<b>Бусты:</b>\n{boosts_text}" if boosts_text else ""

        # VIP badge (shows crown next to name if any boost is active)
        vip_badge = get_vip_badge(user_id, db=db)

        # Starter pack nudge for non-payers (profile is always shown so not throttled — it's opt-in)
        starter_nudge = ""
        if not has_ever_purchased(user_id, db=db) and not boosts_text:
            starter_nudge = "\n\n🎁 <i>Стартовый набор: 5000 алмазов + бусты за 50 ⭐ — /premium</i>"

        # Tax info one-liner
        from app.constants import TAX_RATE, TAX_THRESHOLD

        tax_line = ""
        if user.balance > TAX_THRESHOLD:
            weekly_tax = int((user.balance - TAX_THRESHOLD) * TAX_RATE)
            tax_line = f"\n🏛 Налог: ~{format_diamonds(weekly_tax)}/нед"

        profile_text = (
            f"👤 <b>{html.escape(user.username or str(user_id))}</b> {gender_emoji}{title_display}{vip_badge}\n\n"
            f"💰 {format_diamonds(user.balance)}\n"
            f"💼 {job_info}\n"
            f"🏢 {business_info}\n"
            f"💍 {marriage_info}\n"
            f"👶 Детей: {children_count}\n"
            f"{rep_emoji} Репутация: {user.reputation:+d}\n"
            f"🏆 Достижений: {achievements_count}{tax_line}{prestige_display}{boosts_display}{starter_nudge}"
        )

        await update.message.reply_text(profile_text, reply_markup=profile_keyboard(user_id), parse_mode="HTML")


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /top command — show leaderboards with category buttons."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text, reply_markup = build_top_message("balance", user_id)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


def build_top_message(category: str, user_id: int):
    """Build top message for given category."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = [
        [
            InlineKeyboardButton("💰 Баланс", callback_data=f"top:balance:{user_id}"),
            InlineKeyboardButton("⭐ Репутация", callback_data=f"top:rep:{user_id}"),
        ],
        [
            InlineKeyboardButton("🔄 Престиж", callback_data=f"top:prestige:{user_id}"),
            InlineKeyboardButton("🏆 Достижения", callback_data=f"top:achievements:{user_id}"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    from app.handlers.premium import get_vip_badge

    with get_db() as db:
        if category == "balance":
            users = db.query(User).filter(User.is_banned.is_(False)).order_by(User.balance.desc()).limit(10).all()
            title = "💰 Топ по балансу"
            rows = []
            for i, u in enumerate(users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = html.escape(u.username or f"User{u.telegram_id}")
                badge = get_vip_badge(u.telegram_id, db=db)
                rows.append(f"{medal} @{name}{badge} — {format_diamonds(u.balance)}")

        elif category == "rep":
            users = (
                db.query(User)
                .filter(User.is_banned.is_(False), User.reputation != 0)
                .order_by(User.reputation.desc())
                .limit(10)
                .all()
            )
            title = "⭐ Топ по репутации"
            rows = []
            for i, u in enumerate(users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = html.escape(u.username or f"User{u.telegram_id}")
                badge = get_vip_badge(u.telegram_id, db=db)
                rows.append(f"{medal} @{name}{badge} — {u.reputation:+d}")

        elif category == "prestige":
            users = (
                db.query(User)
                .filter(User.is_banned.is_(False), User.prestige_level > 0)
                .order_by(User.prestige_level.desc())
                .limit(10)
                .all()
            )
            title = "🔄 Топ по престижу"
            rows = []
            for i, u in enumerate(users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = html.escape(u.username or f"User{u.telegram_id}")
                badge = get_vip_badge(u.telegram_id, db=db)
                rows.append(f"{medal} @{name}{badge} — уровень {u.prestige_level} (+{u.prestige_level * 5}%)")

        elif category == "achievements":
            from sqlalchemy import func as sqlfunc

            results = (
                db.query(User.username, User.telegram_id, sqlfunc.count(UserAchievement.id).label("cnt"))
                .join(UserAchievement, UserAchievement.user_id == User.telegram_id)
                .filter(User.is_banned.is_(False))
                .group_by(User.telegram_id, User.username)
                .order_by(sqlfunc.count(UserAchievement.id).desc())
                .limit(10)
                .all()
            )
            title = "🏆 Топ по достижениям"
            rows = []
            for i, (username, tid, cnt) in enumerate(results, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = html.escape(username or f"User{tid}")
                badge = get_vip_badge(tid, db=db)
                rows.append(f"{medal} @{name}{badge} — {format_word(cnt, 'достижение', 'достижения', 'достижений')}")

        else:
            title = "💰 Топ по балансу"
            rows = []

    text = f"🏆 <b>{title}</b>\n\n"
    if rows:
        text += "\n".join(rows)
    else:
        text += "Пусто"

    return text, reply_markup


@button_owner_only
async def top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle top category switching."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    category = parts[1]

    text, reply_markup = build_top_message(category, user_id)
    await safe_edit_message(query, text, reply_markup=reply_markup)


def register_start_handlers(application):
    """Register start and profile handlers."""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CallbackQueryHandler(gender_selection_callback, pattern="^gender:"))
    application.add_handler(CallbackQueryHandler(onboarding_callback, pattern="^onboard:"))
    application.add_handler(CallbackQueryHandler(top_callback, pattern="^top:"))
