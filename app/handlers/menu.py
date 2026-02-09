"""Menu navigation handlers."""

import html
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.utils.decorators import require_registered
from app.utils.telegram_helpers import safe_edit_message


@require_registered
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu — main hub."""
    if not update.effective_user or not update.message:
        return

    from app.utils.keyboards import main_menu_keyboard

    user_id = update.effective_user.id
    await update.message.reply_text(
        "📋 <b>Меню</b>\n\nВыбери раздел:",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode="HTML",
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu navigation callbacks."""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("menu:"):
        return

    if not update.effective_user:
        return

    parts = query.data.split(":")
    menu_type = parts[1]

    # Check button owner (user_id is last part)
    if len(parts) >= 3:
        owner_id = int(parts[2])
        clicker_id = update.effective_user.id

        if clicker_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    user_id = update.effective_user.id

    # Main menu
    if menu_type == "main":
        from app.utils.keyboards import main_menu_keyboard

        await safe_edit_message(
            query,
            "📋 <b>Меню</b>\n\nВыбери раздел:",
            reply_markup=main_menu_keyboard(user_id),
        )
        return

    # Profile — re-render actual profile
    if menu_type == "profile":
        from app.database.connection import get_db
        from app.database.models import Business, Child, Job, User, UserAchievement
        from app.handlers.work import PROFESSION_EMOJI, PROFESSION_NAMES
        from app.services.business_service import BusinessService
        from app.services.marriage_service import MarriageService
        from app.utils.formatters import format_diamonds
        from app.utils.keyboards import profile_keyboard

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return

            job = db.query(Job).filter(Job.user_id == user_id).first()
            job_info = "Нет работы"
            if job:
                emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
                name = PROFESSION_NAMES.get(job.job_type, job.job_type)
                job_info = f"{emoji} {name} (ур. {job.job_level})"

            businesses = BusinessService.get_user_businesses(db, user_id)
            business_info = f"{len(businesses)} бизнесов" if businesses else "Нет"

            marriage = MarriageService.get_active_marriage(db, user_id)
            if marriage:
                partner_id = MarriageService.get_partner_id(marriage, user_id)
                partner = db.query(User).filter(User.telegram_id == partner_id).first()
                partner_name = html.escape(partner.username) if partner and partner.username else f"User{partner_id}"
                marriage_info = f"@{partner_name}"
            else:
                marriage_info = "Не в браке"

            children_count = (
                db.query(Child)
                .filter((Child.parent1_id == user_id) | (Child.parent2_id == user_id), Child.is_alive.is_(True))
                .count()
            )

            achievements_count = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).count()

            gender_emoji = "♂️" if user.gender == "male" else "♀️"

            title_display = ""
            if user.active_title:
                from app.handlers.shop import SHOP_TITLES

                title_info = SHOP_TITLES.get(user.active_title)
                if title_info:
                    title_display = f" | {title_info['display']}"

            prestige = user.prestige_level or 0
            prestige_display = f"\n🔄 Престиж {prestige} (+{prestige * 5}%)" if prestige > 0 else ""

            from app.handlers.premium import get_vip_badge

            vip_badge = get_vip_badge(user_id)

            profile_text = (
                f"👤 {html.escape(user.username or str(user_id))} {gender_emoji}{title_display}{vip_badge}\n\n"
                f"💰 {format_diamonds(user.balance)}\n"
                f"💼 {job_info}\n"
                f"🏢 {business_info}\n"
                f"💍 {marriage_info}\n"
                f"👶 Детей: {children_count}\n"
                f"🏆 {achievements_count}{prestige_display}"
            )

        await safe_edit_message(query, profile_text, reply_markup=profile_keyboard(user_id))
        return

    # Work menu
    if menu_type == "work":
        from app.database.connection import get_db
        from app.database.models import Job
        from app.handlers.work import JOB_TITLES, PROFESSION_EMOJI, PROFESSION_NAMES
        from app.utils.keyboards import work_menu_keyboard

        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if job:
                job_name = JOB_TITLES[job.job_type][job.job_level - 1]
                emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
                track_name = PROFESSION_NAMES.get(job.job_type, "")

                max_level = 6 if job.job_type == "selfmade" else 10
                if job.job_level < max_level:
                    next_title = JOB_TITLES[job.job_type][job.job_level]
                    next_level_text = f"📈 Следующий: {next_title}"
                else:
                    next_level_text = "🏆 Максимум"

                await safe_edit_message(
                    query,
                    f"💼 <b>{track_name}</b>\n\n"
                    f"{emoji} {job_name} ({job.job_level}/{max_level})\n"
                    f"📊 Работал: {job.times_worked} раз\n"
                    f"{next_level_text}",
                    reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                )
            else:
                await safe_edit_message(
                    query,
                    "💼 <b>Работа</b>\n\nВыбери профессию",
                    reply_markup=work_menu_keyboard(has_job=False, user_id=user_id),
                )
        return

    # Marriage menu
    if menu_type == "marriage":
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from app.database.connection import get_db
        from app.database.models import User
        from app.services.marriage_service import MarriageService
        from app.utils.formatters import format_diamonds

        with get_db() as db:
            marriage = MarriageService.get_active_marriage(db, user_id)

            if marriage:
                partner_id = MarriageService.get_partner_id(marriage, user_id)
                partner = db.query(User).filter(User.telegram_id == partner_id).first()

                days_married = (datetime.utcnow() - marriage.created_at).days
                partner_name = partner.username or f"User{partner_id}" if partner else f"User{partner_id}"

                keyboard = [
                    [
                        InlineKeyboardButton("🌙 Ночь", callback_data=f"marriage_help_love:{user_id}"),
                        InlineKeyboardButton("❤️ Свидание", callback_data=f"marriage_help_date:{user_id}"),
                    ],
                    [
                        InlineKeyboardButton("💝 Подарить", callback_data=f"marriage_gift:{user_id}"),
                        InlineKeyboardButton("👨‍👩‍👧‍👦 Дети", callback_data=f"menu:family:{user_id}"),
                    ],
                    [
                        InlineKeyboardButton("💔 Развод", callback_data=f"marriage_divorce:{user_id}"),
                        InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}"),
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                message = (
                    f"💍 <b>Брак</b>\n\n"
                    f"👫 @{partner_name}\n"
                    f"📅 Вместе: {days_married} дней\n"
                    f"❤️ Любовь: {marriage.love_count}"
                )
                await safe_edit_message(query, message, reply_markup=reply_markup)
            else:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [[InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")]]
                await safe_edit_message(
                    query,
                    "💍 <b>Брак</b>\n\nНе в браке\n\n/propose @username — предложить руку",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
        return

    # House menu
    if menu_type == "house":
        from app.database.connection import get_db
        from app.database.models import House, Marriage
        from app.services.house_service import HouseService
        from app.utils.formatters import format_diamonds
        from app.utils.keyboards import house_menu_keyboard

        with get_db() as db:
            marriage = (
                db.query(Marriage)
                .filter(
                    (Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id),
                    Marriage.is_active.is_(True),
                )
                .first()
            )

            if not marriage:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [[InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")]]
                await safe_edit_message(
                    query,
                    "🏠 <b>Дом</b>\n\nНужен брак, чтобы купить дом",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            house = db.query(House).filter(House.marriage_id == marriage.id).first()

            if house:
                house_info = HouseService.get_house_info(db, house.id)
                message = (
                    f"🏠 <b>{house_info['name']}</b>\n\n"
                    f"💰 Стоимость: {format_diamonds(house_info['price'])}\n"
                    f"🛡️ Защита: {house_info['protection']}%"
                )
                await safe_edit_message(
                    query, message, reply_markup=house_menu_keyboard(has_house=True, user_id=user_id)
                )
            else:
                await safe_edit_message(
                    query,
                    "🏠 <b>Дом</b>\n\nНет дома\n\n💡 Дом защищает от похищения детей",
                    reply_markup=house_menu_keyboard(has_house=False, user_id=user_id),
                )
        return

    # Business menu
    if menu_type == "business":
        from app.database.connection import get_db
        from app.services.business_service import BusinessService
        from app.utils.formatters import format_diamonds
        from app.utils.keyboards import business_menu_keyboard

        with get_db() as db:
            businesses = BusinessService.get_user_businesses(db, user_id)

            if businesses:
                message = "💼 <b>Бизнесы</b>\n\n"
                total_income = 0
                for b in businesses:
                    message += f"{b['name']} — {format_diamonds(b['weekly_payout'])}/нед\n"
                    total_income += b["weekly_payout"]
                message += f"\n💰 Итого: {format_diamonds(total_income)}/нед"
            else:
                message = "💼 <b>Бизнесы</b>\n\nНет бизнесов\n\n💡 Пассивный доход каждую неделю"

            await safe_edit_message(query, message, reply_markup=business_menu_keyboard(user_id=user_id))
        return

    # Casino menu — with game buttons
    if menu_type == "casino":
        from app.utils.keyboards import casino_menu_keyboard

        message = "🎰 <b>Казино</b>\n\n" "Выбери игру и напиши команду со ставкой\n\n" "Пример: /slots 100"
        await safe_edit_message(query, message, reply_markup=casino_menu_keyboard(user_id))
        return

    # Family menu
    if menu_type == "family":
        from app.database.connection import get_db
        from app.database.models import Marriage
        from app.services.children_service import ChildrenService
        from app.services.marriage_service import MarriageService
        from app.utils.keyboards import family_menu_keyboard

        with get_db() as db:
            marriage = MarriageService.get_active_marriage(db, user_id)

            if not marriage:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [[InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")]]
                await safe_edit_message(
                    query,
                    "👨‍👩‍👧‍👦 <b>Семья</b>\n\nНужен брак, чтобы завести детей\n\n/propose — предложить руку",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            children = ChildrenService.get_marriage_children(db, marriage.id)

            if children:
                alive = [c for c in children if c.is_alive]
                message = f"👨‍👩‍👧‍👦 <b>Семья</b> — {len(alive)} детей\n\n"
                for child in alive[:5]:
                    info = ChildrenService.get_child_info(child)
                    message += f"{info['age_emoji']} {info['name']} {info['gender_emoji']} — {info['status']}\n"
                if len(alive) > 5:
                    message += f"\n...и ещё {len(alive) - 5}"
            else:
                message = "👨‍👩‍👧‍👦 <b>Семья</b>\n\nДетей пока нет"

            await safe_edit_message(query, message, reply_markup=family_menu_keyboard(user_id=user_id))
        return

    # Economy menu
    if menu_type == "economy":
        from app.utils.keyboards import economy_menu_keyboard

        await safe_edit_message(
            query,
            "💰 <b>Экономика</b>\n\nВыбери раздел:",
            reply_markup=economy_menu_keyboard(user_id),
        )
        return

    # Games menu
    if menu_type == "games":
        from app.utils.keyboards import games_menu_keyboard

        await safe_edit_message(
            query,
            "🎮 <b>Игры</b>\n\nВыбери активность:",
            reply_markup=games_menu_keyboard(user_id),
        )
        return

    # Social menu
    if menu_type == "social":
        from app.utils.keyboards import social_menu_keyboard

        await safe_edit_message(
            query,
            "👥 <b>Социальное</b>\n\nВыбери раздел:",
            reply_markup=social_menu_keyboard(user_id),
        )
        return


async def econ_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle economy/games/social shortcut buttons — show command hints."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]
    owner_id = int(parts[2])

    if update.effective_user.id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    user_id = update.effective_user.id

    HINTS = {
        "daily": ("🎁 <b>Ежедневный бонус</b>\n\nНапиши /daily чтобы получить", f"menu:economy:{user_id}"),
        "lottery": (
            "🎟 <b>Лотерея</b>\n\n/lottery — джекпот\n/buyticket [кол-во] — купить билет",
            f"menu:economy:{user_id}",
        ),
        "shop": ("🏪 <b>Магазин</b>\n\nНапиши /shop чтобы открыть", f"menu:economy:{user_id}"),
        "tax": (
            "🏛 <b>Налоги</b>\n\n/tax — узнать налоговую информацию\n\n5% от баланса свыше 50k/нед",
            f"menu:economy:{user_id}",
        ),
        "prestige": ("🔄 <b>Престиж</b>\n\n/prestige — сбросить баланс за +5% к доходу", f"menu:economy:{user_id}"),
        "pet": ("🐾 <b>Питомец</b>\n\nНапиши /pet чтобы открыть меню питомца", f"menu:games:{user_id}"),
        "fish": ("🎣 <b>Рыбалка</b>\n\n/fish — закинуть удочку\n/fishlist — виды рыб", f"menu:games:{user_id}"),
        "mine": ("⛏️ <b>Шахта</b>\n\nНапиши /mine чтобы копать", f"menu:games:{user_id}"),
        "wheel": ("🎡 <b>Колесо фортуны</b>\n\nНапиши /wheel чтобы крутить (50💎)", f"menu:games:{user_id}"),
        "quest": ("🎯 <b>Квесты</b>\n\nНапиши /quest чтобы получить задание", f"menu:games:{user_id}"),
        "duel": ("⚔️ <b>Дуэль</b>\n\n/duel @user [ставка] — вызвать на дуэль", f"menu:games:{user_id}"),
        "rob": ("🔫 <b>Ограбление</b>\n\nОтветь на сообщение жертвы и напиши /rob", f"menu:games:{user_id}"),
        "insurance": (
            "🛡 <b>Страховка</b>\n\n/insurance buy — защита от ограблений (500💎/нед)",
            f"menu:games:{user_id}",
        ),
        "friends": ("👥 <b>Друзья</b>\n\n/friends — список\n/addfriend @user — добавить", f"menu:social:{user_id}"),
        "gang": ("🔫 <b>Банды</b>\n\n/gang — меню банды\n/gangs — топ банд", f"menu:social:{user_id}"),
        "bounties": (
            "🎯 <b>Награды</b>\n\n/bounties — доска разыскиваемых\n/bounty @user [сумма] — назначить",
            f"menu:social:{user_id}",
        ),
        "achievements": ("🏆 <b>Достижения</b>\n\nНапиши /achievements чтобы посмотреть", f"menu:social:{user_id}"),
        "rating": ("⭐ <b>Рейтинг</b>\n\nНапиши /rating чтобы посмотреть", f"menu:social:{user_id}"),
        "top": ("🏆 <b>Топ</b>\n\nНапиши /top чтобы посмотреть лидерборд", f"menu:social:{user_id}"),
        "premium": (
            "⭐ <b>Премиум</b>\n\nНапиши /premium чтобы открыть магазин\n\nАлмазы, бусты и спец. предложения за Telegram Stars",
            f"menu:economy:{user_id}",
        ),
        "roulette": (
            "🔫 <b>Русская рулетка</b>\n\n/rr [ставка] — начать раунд\n\n2-6 игроков, один проигрывает, остальные делят банк",
            f"menu:games:{user_id}",
        ),
        "heist": (
            "🏦 <b>Ограбление банка</b>\n\n/heist [easy|medium|hard] — начать\n\n2-8 игроков, совместное ограбление!",
            f"menu:games:{user_id}",
        ),
        "crate": (
            "🎁 <b>Сундуки</b>\n\n/crate — посмотреть доступные сундуки\n\nПолучай за серию /daily — не пропускай дни!",
            f"menu:games:{user_id}",
        ),
        "raid": (
            "💥 <b>Рейд</b>\n\n/raid [название банды] — напасть на чужую банду\n\nСобери 2+ участника и ограбь вражеский банк!",
            f"menu:social:{user_id}",
        ),
        "clanwar": (
            "⚔️ <b>Война кланов</b>\n\n/clanwar — недельный рейтинг банд\n\nЗарабатывай очки работой, казино, дуэлями",
            f"menu:social:{user_id}",
        ),
    }

    if action in HINTS:
        hint_text, back_data = HINTS[action]
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [[InlineKeyboardButton("« Назад", callback_data=back_data)]]
        await safe_edit_message(query, hint_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def casino_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle casino game info buttons — show how to play."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) < 3:
        return

    game = parts[1]
    owner_id = int(parts[2])

    if update.effective_user.id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    user_id = update.effective_user.id

    GAME_INFO = {
        "slots": ("🎰 <b>Слот-машина</b>\n\n/slots [ставка]\n\nТри одинаковых = джекпот!\nМакс: x30", "🎰"),
        "dice": ("🎲 <b>Кости</b>\n\n/dice [ставка]\n\n⚅ = x3, ⚄ = x2, ⚃ = x1.5", "🎲"),
        "darts": ("🎯 <b>Дартс</b>\n\n/darts [ставка]\n\nБуллсай = x5, кольцо = x2", "🎯"),
        "basketball": ("🏀 <b>Баскетбол</b>\n\n/basketball [ставка]\n\nПопал = x3, почти = x1.5", "🏀"),
        "bowling": ("🎳 <b>Боулинг</b>\n\n/bowling [ставка]\n\nСтрайк = x4, 5+ кеглей = x2", "🎳"),
        "football": ("⚽ <b>Футбол</b>\n\n/football [ставка]\n\nГол = x3, штанга = x1.5", "⚽"),
        "blackjack": ("🃏 <b>Блэкджек</b>\n\n/blackjack [ставка] или /bj [ставка]\n\nСобери 21 и получи x2.5", "🃏"),
        "scratch": ("🎫 <b>Скретч-карта</b>\n\n/scratch [ставка]\n\n3 💎 = x5, 3 ⭐ = x2.5", "🎫"),
        "coinflip": ("🪙 <b>Монетка</b>\n\n/coinflip [ставка] или /cf [ставка]\n\nОрёл = x1.9", "🪙"),
        "stats": ("📊 <b>Статистика</b>\n\nНапиши /casinostats чтобы посмотреть", "📊"),
    }

    if game in GAME_INFO:
        text, _ = GAME_INFO[game]
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [[InlineKeyboardButton("« Казино", callback_data=f"menu:casino:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))


def register_menu_handlers(application):
    """Register menu handlers."""
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
    application.add_handler(CallbackQueryHandler(econ_callback, pattern="^econ:"))
    application.add_handler(CallbackQueryHandler(casino_info_callback, pattern="^casino_info:"))
