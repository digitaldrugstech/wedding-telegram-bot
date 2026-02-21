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

    # Ban check
    from app.database.connection import get_db
    from app.database.models import User

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

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
        from app.database.models import Child, Job, User, UserAchievement
        from app.handlers.work import PROFESSION_EMOJI, PROFESSION_NAMES
        from app.services.business_service import BusinessService
        from app.services.marriage_service import MarriageService
        from app.utils.formatters import format_diamonds, format_word
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
                marriage_info = (
                    f"@{html.escape(partner.username)}" if partner and partner.username else f"ID {partner_id}"
                )
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

            vip_badge = get_vip_badge(user_id, db=db)

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
        from app.utils.formatters import format_word  # noqa: F811
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
                    f"📊 Работал: {format_word(job.times_worked, 'раз', 'раза', 'раз')}\n"
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
        from app.utils.formatters import format_diamonds, format_word

        with get_db() as db:
            marriage = MarriageService.get_active_marriage(db, user_id)

            if marriage:
                partner_id = MarriageService.get_partner_id(marriage, user_id)
                partner = db.query(User).filter(User.telegram_id == partner_id).first()

                days_married = (datetime.utcnow() - marriage.created_at).days
                partner_name = html.escape(partner.username) if partner and partner.username else f"User{partner_id}"

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
                    f"📅 Вместе: {format_word(days_married, 'день', 'дня', 'дней')}\n"
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
                    "🏠 <b>Дом</b>\n\nНет дома\n\n💡 Защита от похищений и ограблений",
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
        from app.database.connection import get_db
        from app.database.models import User
        from app.utils.formatters import format_diamonds
        from app.utils.keyboards import casino_menu_keyboard

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            balance = user.balance if user else 0

        message = f"🎰 <b>Казино</b>\n\n💰 Баланс: {format_diamonds(balance)}\n\nВыбери игру:"
        await safe_edit_message(query, message, reply_markup=casino_menu_keyboard(user_id))
        return

    # Family menu
    if menu_type == "family":
        from app.database.connection import get_db
        from app.database.models import Marriage
        from app.services.children_service import ChildrenService
        from app.services.marriage_service import MarriageService
        from app.utils.formatters import format_word as _fw
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
                message = f"👨‍👩‍👧‍👦 <b>Семья</b> — {_fw(len(alive), 'ребёнок', 'ребёнка', 'детей')}\n\n"
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
    """Handle economy/games/social shortcut buttons — show info or command hints."""
    query = update.callback_query

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

    await query.answer()
    user_id = update.effective_user.id

    # Ban check
    from app.database.connection import get_db
    from app.database.models import User

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.utils.formatters import format_diamonds

    # --- DATA-DRIVEN ITEMS (show real info instead of hints) ---

    if action == "tax":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            balance = user.balance
        if balance > 50000:
            tax = int((balance - 50000) * 0.05)
            text = (
                f"🏛 <b>Налоги</b>\n\n💰 Баланс: {format_diamonds(balance)}"
                f"\n💸 Налог: ~{format_diamonds(tax)}/нед\n\n5% от суммы свыше 50,000"
            )
        else:
            text = f"🏛 <b>Налоги</b>\n\n💰 Баланс: {format_diamonds(balance)}\n✅ Налогов нет (до 50,000)"
        keyboard = [[InlineKeyboardButton("« Экономика", callback_data=f"menu:economy:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "prestige":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            prestige = user.prestige_level or 0
            balance = user.balance
        bonus = prestige * 5
        cost = 50000
        can_prestige = balance >= cost
        text = (
            f"🔄 <b>Престиж</b>\n\n"
            f"Уровень: {prestige} (+{bonus}% к доходу)\n"
            f"Стоимость: {format_diamonds(cost)}\n"
            f"💰 Баланс: {format_diamonds(balance)}\n\n"
        )
        if can_prestige:
            text += "✅ Доступно! Баланс обнулится"
        else:
            text += f"❌ Нужно ещё {format_diamonds(cost - balance)}"
        keyboard = [[InlineKeyboardButton("« Экономика", callback_data=f"menu:economy:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "insurance":
        from app.database.models import Cooldown

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            balance = user.balance
            ins = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "insurance").first()
            is_insured = ins and ins.expires_at > datetime.utcnow()
            if is_insured:
                remaining = ins.expires_at - datetime.utcnow()
                hours = int(remaining.total_seconds() // 3600)
                text = f"🛡 <b>Страховка</b>\n\n✅ Активна ({hours}ч осталось)\n\nЗащита от /rob"
            else:
                text = (
                    f"🛡 <b>Страховка</b>\n\n❌ Нет страховки"
                    f"\n💰 Стоимость: 500💎/нед\n💰 Баланс: {format_diamonds(balance)}\n\nНапиши /insurance buy"
                )
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "lottery":
        from app.database.models import Lottery, LotteryTicket

        with get_db() as db:
            lottery = db.query(Lottery).filter(Lottery.is_active.is_(True)).first()
            if lottery:
                jackpot = lottery.jackpot
                total_tickets = db.query(LotteryTicket).filter(LotteryTicket.lottery_id == lottery.id).count()
                user_tickets = (
                    db.query(LotteryTicket)
                    .filter(LotteryTicket.lottery_id == lottery.id, LotteryTicket.user_id == user_id)
                    .count()
                )
                text = (
                    f"🎟 <b>Лотерея</b>\n\n"
                    f"💰 Джекпот: {format_diamonds(jackpot)}\n"
                    f"🎫 Всего билетов: {total_tickets}\n"
                    f"🎫 Твоих билетов: {user_tickets}/10\n"
                    f"💵 Цена: 100💎/билет\n\n"
                    f"/buyticket [кол-во] — купить билеты"
                )
            else:
                text = "🎟 <b>Лотерея</b>\n\nСейчас нет активного розыгрыша"
        keyboard = [[InlineKeyboardButton("« Экономика", callback_data=f"menu:economy:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "quest":
        from app.database.models import Quest, UserQuest
        from app.handlers.quest import assign_daily_quests

        with get_db() as db:
            assign_daily_quests(user_id, db=db)
            db.flush()
            today = datetime.utcnow().date()
            user_quests = (
                db.query(UserQuest, Quest)
                .join(Quest)
                .filter(
                    UserQuest.user_id == user_id,
                    UserQuest.assigned_at >= datetime.combine(today, datetime.min.time()),
                )
                .order_by(UserQuest.is_completed, UserQuest.assigned_at)
                .all()
            )
            if user_quests:
                text = "📋 <b>Квесты</b>\n\n"
                for uq, quest in user_quests:
                    status = "✅" if uq.is_completed else "⏳"
                    text += (
                        f"{status} {quest.description}\n"
                        f"   {uq.progress}/{quest.target_count} | {format_diamonds(quest.reward)}\n"
                    )
            else:
                text = "📋 <b>Квесты</b>\n\nОбновятся завтра"
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "achievements":
        from app.database.models import Achievement, UserAchievement
        from app.services.achievement_service import AchievementService

        with get_db() as db:
            try:
                AchievementService.check_all_achievements(user_id, db=db)
                db.flush()
            except Exception:
                pass
            all_achievements = db.query(Achievement).all()
            earned_ids = set(
                row[0]
                for row in db.query(UserAchievement.achievement_id).filter(UserAchievement.user_id == user_id).all()
            )
            text = f"🏆 <b>Достижения</b> ({len(earned_ids)}/{len(all_achievements)})\n\n"
            for ach in all_achievements:
                mark = "✅" if ach.id in earned_ids else "⬜"
                text += f"{mark} {ach.name}\n"
        keyboard = [[InlineKeyboardButton("« Социальное", callback_data=f"menu:social:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- MORE DATA-DRIVEN ITEMS ---

    if action == "shop":
        from app.handlers.shop import SHOP_TITLES, get_user_titles

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            owned = get_user_titles(user)
            active = user.active_title

        text = "🏪 <b>Магазин титулов</b>\n\n"
        if active and active in SHOP_TITLES:
            text += f"Текущий: {SHOP_TITLES[active]['display']}\n\n"
        for tid, td in SHOP_TITLES.items():
            mark = "✅" if tid in owned else f"{format_diamonds(td['price'])}"
            text += f"{td['display']} — {mark}\n"
        text += "\n/shop — купить или сменить"
        keyboard = [[InlineKeyboardButton("« Экономика", callback_data=f"menu:economy:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "friends":
        from app.database.models import Friendship

        with get_db() as db:
            friendships = (
                db.query(Friendship).filter((Friendship.user1_id == user_id) | (Friendship.user2_id == user_id)).all()
            )
            friend_ids = []
            for f in friendships:
                fid = f.user2_id if f.user1_id == user_id else f.user1_id
                friend_ids.append(fid)

            if friend_ids:
                friends = db.query(User).filter(User.telegram_id.in_(friend_ids)).all()
                friend_map = {u.telegram_id: u for u in friends}
                text = f"👥 <b>Друзья</b> ({len(friend_ids)})\n\n"
                for fid in friend_ids[:10]:
                    u = friend_map.get(fid)
                    name = html.escape(u.username) if u and u.username else f"ID {fid}"
                    text += f"• @{name}\n"
                if len(friend_ids) > 10:
                    text += f"\n...и ещё {len(friend_ids) - 10}"
            else:
                text = "👥 <b>Друзья</b>\n\nПока нет друзей\n\nОтветь на сообщение: /addfriend"
        keyboard = [[InlineKeyboardButton("« Социальное", callback_data=f"menu:social:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action in ("top", "rating"):
        from app.handlers.start import build_top_message

        text, top_markup = build_top_message("balance", user_id)
        await safe_edit_message(query, text, reply_markup=top_markup)
        return

    if action == "explore":
        from app.database.models import Cooldown

        with get_db() as db:
            mine_cd = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "mine").first()
            fish_cd = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "fishing").first()
            now = datetime.utcnow()
            mine_status = (
                f"⏰ {int((mine_cd.expires_at - now).total_seconds() // 60)}м"
                if mine_cd and mine_cd.expires_at > now
                else "✅ /mine"
            )
            fish_status = (
                f"⏰ {int((fish_cd.expires_at - now).total_seconds() // 60)}м"
                if fish_cd and fish_cd.expires_at > now
                else "✅ /fish"
            )
        text = (
            f"🗺 <b>Исследование</b>\n\n⛏️ Шахта — {mine_status}"
            f"\n   5-75💎, шанс x3 редкой жилы\n\n🎣 Рыбалка — {fish_status}"
            f"\n   Наживка 20💎, улов до 100💎"
        )
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "mine":
        from app.database.models import Cooldown

        with get_db() as db:
            cd = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "mine").first()
            if cd and cd.expires_at > datetime.utcnow():
                remaining = cd.expires_at - datetime.utcnow()
                mins = int(remaining.total_seconds() // 60)
                text = f"⛏️ <b>Шахта</b>\n\n⏰ Кулдаун: {mins}м\n\nНаграда: 5-75💎 (шанс x3 редкой жилы)"
            else:
                text = "⛏️ <b>Шахта</b>\n\n✅ Можно копать!\n\nНапиши /mine в чат\nНаграда: 5-75💎"
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "fish":
        from app.database.models import Cooldown

        with get_db() as db:
            cd = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "fishing").first()
            if cd and cd.expires_at > datetime.utcnow():
                remaining = cd.expires_at - datetime.utcnow()
                mins = int(remaining.total_seconds() // 60)
                text = f"🎣 <b>Рыбалка</b>\n\n⏰ Кулдаун: {mins}м\n\nНаживка: 20💎, улов до 100💎"
            else:
                text = "🎣 <b>Рыбалка</b>\n\n✅ Можно рыбачить!\n\nНапиши /fish в чат\nНаживка: 20💎"
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "crate":
        from app.handlers.crate import CRATE_MILESTONES
        from app.utils.formatters import format_word

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            streak = user.daily_streak or 0

        next_crates = [(d, t) for d, t in sorted(CRATE_MILESTONES.items()) if d > streak]
        crate_names = {
            "bronze": "🟤 Бронзовый",
            "silver": "⚪ Серебряный",
            "gold": "🟡 Золотой",
            "diamond": "💎 Алмазный",
            "legendary": "🌟 Легендарный",
        }

        text = f"🎁 <b>Сундуки</b>\n\n📅 Серия /daily: {format_word(streak, 'день', 'дня', 'дней')}\n\n"
        if next_crates:
            for day, ctype in next_crates:
                days_left = day - streak
                name = crate_names.get(ctype, ctype)
                text += f"{name} — через {format_word(days_left, 'день', 'дня', 'дней')}\n"
        else:
            text += "🏆 Все сундуки получены!"
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "toto":
        from app.handlers.toto import _active_round

        r = _active_round
        if r and not r.get("resolved"):
            total_pool = r["pool_a"] + r["pool_b"]
            text = (
                f"🎰 <b>Тотализатор</b>\n\n"
                f"Сейчас идёт раунд!\n"
                f"{r['question']}\n\n"
                f"💰 Пул: {format_diamonds(total_pool)}\n\n"
                f"Жми кнопки на сообщении в чате"
            )
        else:
            text = (
                "🎰 <b>Тотализатор</b>\n\nСейчас нет раунда\n\n"
                "Раунды каждые 3 часа\nСтавка: 100 — 5000💎\nКомиссия: 10%"
            )
        keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "market":
        from app.handlers.market import _build_market_keyboard, _build_market_text, _get_stock

        stock = _get_stock()
        text = _build_market_text(stock)
        keyboard = _build_market_keyboard(user_id, stock)
        await safe_edit_message(query, text, reply_markup=keyboard)
        return

    # --- SIMPLE HINTS (reply-based / multiplayer only) ---

    HINTS = {
        "daily": ("🎁 <b>Ежедневный бонус</b>\n\nНапиши /daily в чат", f"menu:economy:{user_id}"),
        "premium": (
            "⭐ <b>Премиум</b>\n\nНапиши /premium в чат\n\nАлмазы, бусты и VIP за Telegram Stars",
            f"menu:economy:{user_id}",
        ),
        "pet": ("🐾 <b>Питомец</b>\n\nНапиши /pet в чат", f"menu:games:{user_id}"),
        "wheel": ("🎡 <b>Колесо фортуны</b>\n\nНапиши /wheel в чат (50💎)", f"menu:games:{user_id}"),
        "duel": ("⚔️ <b>Дуэль</b>\n\nОтветь на сообщение соперника:\n/duel [ставка]", f"menu:games:{user_id}"),
        "rob": ("🔫 <b>Ограбление</b>\n\nОтветь на сообщение жертвы:\n/rob", f"menu:games:{user_id}"),
        "gang": ("🔫 <b>Банды</b>\n\nНапиши /gang в чат", f"menu:social:{user_id}"),
        "bounties": (
            "🎯 <b>Награды</b>\n\n/bounties — доска\nОтветь на сообщение: /bounty [сумма]",
            f"menu:social:{user_id}",
        ),
        "roulette": (
            "🔫 <b>Русская рулетка</b>\n\nНапиши /rr [ставка] в чат\n\n2-6 игроков",
            f"menu:games:{user_id}",
        ),
        "heist": (
            "🏦 <b>Ограбление банка</b>\n\nНапиши /heist [easy|medium|hard] в чат\n\n2-8 игроков",
            f"menu:games:{user_id}",
        ),
        "raid": ("💥 <b>Рейд</b>\n\nНапиши /raid [банда] в чат\n\n2+ участника", f"menu:social:{user_id}"),
        "clanwar": ("⚔️ <b>Война кланов</b>\n\nНапиши /clanwar в чат", f"menu:social:{user_id}"),
    }

    if action in HINTS:
        hint_text, back_data = HINTS[action]
        keyboard = [[InlineKeyboardButton("« Назад", callback_data=back_data)]]
        await safe_edit_message(query, hint_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def casino_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle casino game buttons — show bet picker or stats."""
    query = update.callback_query

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

    await query.answer()
    user_id = update.effective_user.id

    # Stats — show inline
    if game == "stats":
        from app.database.connection import get_db
        from app.database.models import User
        from app.services.casino_service import CasinoService
        from app.utils.formatters import format_diamonds

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user or user.is_banned:
                await query.answer("Доступ запрещён", show_alert=True)
                return
            stats = CasinoService.get_user_stats(db, user_id)

        if stats["total_games"] == 0:
            text = "📊 <b>Статистика казино</b>\n\nТы ещё не играл в казино"
        else:
            profit = stats["total_profit"]
            profit_text = f"+{format_diamonds(profit)}" if profit >= 0 else f"-{format_diamonds(abs(profit))}"
            profit_emoji = "📈" if profit >= 0 else "📉"
            text = (
                "📊 <b>Статистика казино</b>\n\n"
                f"🎮 Игр: {stats['total_games']}\n"
                f"💰 Поставлено: {format_diamonds(stats['total_bet'])}\n"
                f"🏆 Выиграно: {format_diamonds(stats['total_winnings'])}\n"
                f"{profit_emoji} Профит: {profit_text}\n"
                f"📊 Винрейт: {stats['win_rate']:.1f}%"
            )

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [[InlineKeyboardButton("« Казино", callback_data=f"menu:casino:{user_id}")]]
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # All other games — show bet picker
    GAME_NAMES = {
        "slots": ("🎰 Слоты", "x30 джекпот"),
        "dice": ("🎲 Кости", "⚅ x3, ⚄ x2"),
        "darts": ("🎯 Дартс", "буллсай x5"),
        "blackjack": ("🃏 Блэкджек", "21 = x2.5"),
        "scratch": ("🎫 Скретч", "3💎 = x5"),
        "coinflip": ("🪙 Монетка", "орёл = x1.9"),
    }

    if game in GAME_NAMES:
        from app.database.connection import get_db
        from app.database.models import User
        from app.utils.formatters import format_diamonds
        from app.utils.keyboards import bet_picker_keyboard

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user or user.is_banned:
                await query.answer("Доступ запрещён", show_alert=True)
                return
            balance = user.balance

            from app.handlers.premium import is_vip

            user_is_vip = is_vip(user_id, db=db)

        name, desc = GAME_NAMES[game]
        vip_tag = " 👑" if user_is_vip else ""
        text = f"{name}\n{desc}\n\n💰 Баланс: {format_diamonds(balance)}{vip_tag}\n\nВыбери ставку:"
        await safe_edit_message(query, text, reply_markup=bet_picker_keyboard(game, user_id, vip=user_is_vip))


def register_menu_handlers(application):
    """Register menu handlers."""
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu:"))
    application.add_handler(CallbackQueryHandler(econ_callback, pattern="^econ:"))
    application.add_handler(CallbackQueryHandler(casino_info_callback, pattern="^casino_info:"))
