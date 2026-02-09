"""Work and job handlers."""

import html
import os
import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.constants import (
    INTERPOL_BONUS_MAX_PERCENTAGE,
    INTERPOL_MIN_VICTIM_BALANCE,
    INTERPOL_VICTIM_COOLDOWN_HOURS,
    SELFMADE_TRAP_LEVEL,
)
from app.database.connection import get_db
from app.database.models import Cooldown, InterpolFine, Job, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered, set_cooldown
from app.utils.formatters import format_diamonds
from app.utils.keyboards import profession_selection_keyboard, work_menu_keyboard
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

# Check if DEBUG mode (DEV environment)
IS_DEBUG = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"

# Job titles by profession and level (18 professions total)
JOB_TITLES = {
    # === ORIGINAL 6 PROFESSIONS ===
    "interpol": [
        "Стажер",
        "Младший сотрудник интерпола",
        "Сотрудник интерпола",
        "Дежурный интерполенок",
        "Старший дежурный",
        "Инспектор",
        "Старший инспектор",
        "Зам главы интерпола",
        "Первый зам главы",
        "Глава интерпола",
    ],
    "banker": [
        "Стажер",
        "Бухгалтер банка",
        "Старший бухгалтер",
        "Банкир",
        "Старший банкир",
        "Зам главного банкира",
        "Первый зам главного банкира",
        "Главный банкир",
        "Первый зам главы экономики",
        "Глава экономики",
    ],
    "infrastructure": [
        "Сборщик ресурсов",
        "Старший сборщик",
        "Строитель",
        "Мастер-строитель",
        "Хранитель",
        "Старший хранитель",
        "Главный по спавну",
        "Зам главы инфраструктуры",
        "Первый зам главы",
        "Глава инфраструктуры",
    ],
    "court": [
        "Стажер",
        "Помощник судьи",
        "Младший судья",
        "Судья",
        "Окружной судья",
        "Старший судья",
        "Апелляционный судья",
        "Зам главного судьи",
        "Первый зам верховного судьи",
        "Верховный судья",
    ],
    "culture": [
        "Стажер",
        "Ивентмейкер",
        "Старший ивентмейкер",
        "Организатор мероприятий",
        "Креативный директор",
        "Главный ивентмейкер",
        "Продюсер",
        "Зам главы культуры",
        "Первый зам главы",
        "Глава культуры",
    ],
    "selfmade": [
        "нищий",
        "чибон",
        "голубь",
        "проверенный посан",
        "четкий пацык",
        "лучший сын",
    ],
    # === NEW 12 PROFESSIONS ===
    "medic": [
        "Санитар",
        "Медсестра",
        "Фельдшер",
        "Терапевт",
        "Хирург",
        "Заведующий отделением",
        "Главврач поликлиники",
        "Зам министра здравоохранения",
        "Первый зам министра",
        "Министр здравоохранения",
    ],
    "teacher": [
        "Практикант",
        "Воспитатель",
        "Учитель начальных классов",
        "Учитель средних классов",
        "Учитель старших классов",
        "Завуч",
        "Директор школы",
        "Зам министра образования",
        "Первый зам министра",
        "Министр образования",
    ],
    "journalist": [
        "Стажер редакции",
        "Корреспондент",
        "Репортер",
        "Ведущий новостей",
        "Главный редактор рубрики",
        "Шеф-редактор",
        "Главный редактор",
        "Зам генерального директора СМИ",
        "Генеральный директор СМИ",
        "Медиамагнат",
    ],
    "transport": [
        "Кондуктор",
        "Водитель автобуса",
        "Машинист метро",
        "Пилот вертолета",
        "Капитан корабля",
        "Командир экипажа самолета",
        "Начальник депо",
        "Зам министра транспорта",
        "Первый зам министра",
        "Министр транспорта",
    ],
    "security": [
        "Охранник",
        "Старший охранник",
        "Начальник смены",
        "Телохранитель",
        "Личный телохранитель VIP",
        "Начальник охраны",
        "Глава службы безопасности",
        "Зам директора ЧОП",
        "Директор ЧОП",
        "Владелец охранного холдинга",
    ],
    "chef": [
        "Посудомойщик",
        "Помощник повара",
        "Повар",
        "Старший повар",
        "Су-шеф",
        "Шеф-повар",
        "Шеф ресторана",
        "Бренд-шеф сети",
        "Знаменитый шеф",
        "Шеф со звездой Мишлен",
    ],
    "artist": [
        "Начинающий художник",
        "Уличный художник",
        "Иллюстратор",
        "Дизайнер",
        "Арт-директор",
        "Известный художник",
        "Галерист",
        "Владелец галереи",
        "Коллекционер искусства",
        "Легенда искусства",
    ],
    "scientist": [
        "Лаборант",
        "Младший научный сотрудник",
        "Научный сотрудник",
        "Старший научный сотрудник",
        "Ведущий научный сотрудник",
        "Заведующий лабораторией",
        "Профессор",
        "Академик",
        "Директор института",
        "Нобелевский лауреат",
    ],
    "programmer": [
        "Джун",
        "Мидл",
        "Сеньор",
        "Тимлид",
        "Архитектор",
        "Технический директор",
        "VP of Engineering",
        "CTO стартапа",
        "CTO корпорации",
        "Основатель IT-компании",
    ],
    "lawyer": [
        "Помощник юриста",
        "Юрист",
        "Старший юрист",
        "Ведущий юрист",
        "Партнер-юниор",
        "Партнер",
        "Старший партнер",
        "Управляющий партнер",
        "Глава юридической фирмы",
        "Легенда адвокатуры",
    ],
    "athlete": [
        "Новичок",
        "Любитель",
        "Кандидат в мастера спорта",
        "Мастер спорта",
        "Мастер спорта международного класса",
        "Чемпион региона",
        "Чемпион страны",
        "Призер Олимпиады",
        "Олимпийский чемпион",
        "Легенда спорта",
    ],
    "streamer": [
        "Начинающий стример",
        "Стример (100 подписчиков)",
        "Стример (1К подписчиков)",
        "Стример (10К подписчиков)",
        "Стример (100К подписчиков)",
        "Стример (500К подписчиков)",
        "Стример (1М подписчиков)",
        "Топ-стример",
        "Партнер Twitch",
        "Легенда стриминга",
    ],
}

# Salary ranges by level (min, max) - для обычных профессий
SALARY_RANGES = {
    1: (10, 20),
    2: (20, 35),
    3: (35, 55),
    4: (55, 85),
    5: (85, 130),
    6: (130, 200),
    7: (200, 300),
    8: (300, 450),
    9: (450, 650),
    10: (650, 1000),
}

# Зарплаты для selfmade (меньше всех)
SELFMADE_SALARY_RANGES = {
    1: (5, 10),
    2: (8, 15),
    3: (12, 20),
    4: (18, 30),
    5: (25, 40),
    6: (35, 55),
}

# Promotion chances by level
PROMOTION_CHANCES = {
    1: 0.05,  # 5%
    2: 0.045,
    3: 0.04,
    4: 0.035,
    5: 0.03,
    6: 0.025,
    7: 0.022,
    8: 0.02,
    9: 0.018,
    10: 0.015,  # 1.5%
}

# Guaranteed promotion after N works
GUARANTEED_PROMOTION_WORKS = {
    1: 20,
    2: 25,
    3: 30,
    4: 35,
    5: 40,
    6: 45,
    7: 50,
    8: 55,
    9: 60,
    10: 999,  # Max level, no more promotions
}

# Cooldowns by level (in hours)
COOLDOWN_BY_LEVEL = {
    1: 1,  # 1 hour
    2: 1,
    3: 1.5,  # 1.5 hours
    4: 1.5,
    5: 2,  # 2 hours
    6: 2,
    7: 3,  # 3 hours
    8: 3,
    9: 4,  # 4 hours
    10: 4,
}

# Selfmade cooldown (самый короткий)
SELFMADE_COOLDOWN = 0.5  # 30 minutes

# Centralized profession metadata (emoji, name, flavor texts)
PROFESSION_EMOJI = {
    # Original 6
    "interpol": "🚔",
    "banker": "💳",
    "infrastructure": "🏗️",
    "court": "⚖️",
    "culture": "🎭",
    "selfmade": "🐦",
    # New 12
    "medic": "🏥",
    "teacher": "📚",
    "journalist": "📰",
    "transport": "🚂",
    "security": "🛡️",
    "chef": "👨‍🍳",
    "artist": "🎨",
    "scientist": "🔬",
    "programmer": "💻",
    "lawyer": "⚖️",
    "athlete": "🏆",
    "streamer": "🎮",
}

PROFESSION_NAMES = {
    # Original 6
    "interpol": "Интерпол",
    "banker": "Банкир",
    "infrastructure": "Инфраструктура",
    "court": "Суд",
    "culture": "Культура",
    "selfmade": "Селфмейд",
    # New 12
    "medic": "Медицина",
    "teacher": "Образование",
    "journalist": "Журналистика",
    "transport": "Транспорт",
    "security": "Охрана",
    "chef": "Кулинария",
    "artist": "Искусство",
    "scientist": "Наука",
    "programmer": "IT",
    "lawyer": "Юриспруденция",
    "athlete": "Спорт",
    "streamer": "Стриминг",
}

FLAVOR_TEXTS = {
    # Original 6
    "interpol": [
        "Обеспечил безопасность на ивенте",
        "Патрулировал территорию сервера",
        "Дежурил на охране мероприятия",
        "Проверил документы у игроков",
    ],
    "banker": [
        "Обслужил клиентов в банке",
        "Провёл финансовые транзакции",
        "Одобрил кредитные заявки",
        "Обработал платежи",
    ],
    "infrastructure": [
        "Собрал ресурсы для строительства",
        "Построил новые объекты",
        "Отремонтировал здания на спавне",
        "Обслужил инфраструктуру города",
    ],
    "court": [
        "Рассмотрел судебные дела",
        "Вынес обоснованные приговоры",
        "Провёл судебные слушания",
        "Изучил материалы дел",
    ],
    "culture": [
        "Провёл крутые ивенты",
        "Организовал мероприятия для игроков",
        "Подготовил концерты",
        "Развлекал население города",
    ],
    "selfmade": [
        "крутить каз",
        "забирать муку",
        "звонить юристам",
        "НЕ мыться",
        "заебаться",
        "планировать месть",
    ],
    # New 12
    "medic": [
        "Вылечил пациентов",
        "Провёл операцию",
        "Поставил диагнозы",
        "Выписал рецепты",
        "Спас чью-то жизнь",
    ],
    "teacher": [
        "Провёл уроки",
        "Проверил контрольные",
        "Подготовил учебный план",
        "Воспитал будущих гениев",
        "Объяснил сложную тему",
    ],
    "journalist": [
        "Написал статью",
        "Провёл расследование",
        "Взял интервью у звезды",
        "Снял репортаж",
        "Раскрыл громкое дело",
    ],
    "transport": [
        "Перевёз пассажиров",
        "Доставил грузы вовремя",
        "Провёл рейс без происшествий",
        "Обслужил транспорт",
        "Спланировал маршруты",
    ],
    "security": [
        "Охранял объект",
        "Предотвратил кражу",
        "Провёл патрулирование",
        "Обеспечил безопасность VIP",
        "Нейтрализовал угрозу",
    ],
    "chef": [
        "Приготовил изысканные блюда",
        "Накормил голодных гостей",
        "Придумал новый рецепт",
        "Прошёл проверку санэпидемстанции",
        "Получил похвалу от критика",
    ],
    "artist": [
        "Нарисовал картину",
        "Продал работу коллекционеру",
        "Провёл выставку",
        "Создал шедевр",
        "Вдохновил молодых художников",
    ],
    "scientist": [
        "Провёл эксперимент",
        "Сделал открытие",
        "Опубликовал статью в Nature",
        "Получил грант на исследования",
        "Защитил диссертацию",
    ],
    "programmer": [
        "Написал код без багов",
        "Исправил критический баг",
        "Сделал code review",
        "Выкатил релиз в прод",
        "Оптимизировал алгоритм",
    ],
    "lawyer": [
        "Выиграл дело в суде",
        "Заключил выгодную сделку",
        "Защитил невиновного",
        "Составил контракт",
        "Провёл консультацию",
    ],
    "athlete": [
        "Выиграл соревнования",
        "Побил личный рекорд",
        "Провёл изнурительную тренировку",
        "Получил медаль",
        "Вдохновил болельщиков",
    ],
    "streamer": [
        "Провёл эпичный стрим",
        "Набрал новых подписчиков",
        "Получил донаты от фанатов",
        "Сделал вирусный клип",
        "Затащил на стриме",
    ],
}


@require_registered
async def work_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /work command - show work menu."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        job = db.query(Job).filter(Job.user_id == user_id).first()

        if job:
            job_name = JOB_TITLES[job.job_type][job.job_level - 1]
            emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
            track_name = PROFESSION_NAMES.get(job.job_type, "")

            # Следующая должность
            max_level = 6 if job.job_type == "selfmade" else 10
            if job.job_level < max_level:
                next_title = JOB_TITLES[job.job_type][job.job_level]
                next_level_text = f"📈 {next_title}"
            else:
                next_level_text = "🏆 Максимум"

            await update.message.reply_text(
                f"💼 {track_name}\n"
                f"{emoji} {job_name} ({job.job_level}/{max_level})\n"
                f"📊 {job.times_worked}\n"
                f"{next_level_text}",
                reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
            )
        else:
            await update.message.reply_text(
                "💼 Нет работы\n\nВыбери профессию:",
                reply_markup=work_menu_keyboard(has_job=False, user_id=user_id),
            )


@require_registered
async def job_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /job command - quick work."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        job = db.query(Job).filter(Job.user_id == user_id).first()

        if not job:
            await update.message.reply_text("⚠️ Нет работы. Используй /work")
            return

        # Interpol special mechanics: reply = fine, no reply = patrol
        if job.job_type == "interpol":
            victim_id = None
            victim_username = None

            # Option 1: Reply to message
            if update.message.reply_to_message and update.message.reply_to_message.from_user:
                victim_id = update.message.reply_to_message.from_user.id
                victim_username = (
                    update.message.reply_to_message.from_user.username
                    or update.message.reply_to_message.from_user.first_name
                )
            # Option 2: Username argument (@username)
            elif context.args and len(context.args) > 0:
                username = context.args[0].lstrip("@")
                victim_user_check = db.query(User).filter(User.username == username).first()
                if not victim_user_check:
                    await update.message.reply_text(f"Пользователь @{username} не найден")
                    return
                victim_id = victim_user_check.telegram_id
                victim_username = username

            # Check if we have a victim to fine
            if victim_id:

                # Can't fine yourself
                if victim_id == user_id:
                    await update.message.reply_text("Нельзя штрафовать себя")
                    return

                # Get victim's data
                victim_user = db.query(User).filter(User.telegram_id == victim_id).first()
                if not victim_user:
                    await update.message.reply_text("Этот игрок не зарегистрирован")
                    return

                # Check if victim has enough balance
                if victim_user.balance < INTERPOL_MIN_VICTIM_BALANCE:
                    await update.message.reply_text(
                        f"У @{victim_username} мало алмазов (< {format_diamonds(INTERPOL_MIN_VICTIM_BALANCE)})"
                    )
                    return

                # Check global job cooldown FIRST (skip in DEBUG mode)
                if not IS_DEBUG:
                    cooldown_entry = (
                        db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "job").first()
                    )

                    if cooldown_entry and cooldown_entry.expires_at > datetime.utcnow():
                        remaining = cooldown_entry.expires_at - datetime.utcnow()
                        hours, remainder = divmod(remaining.total_seconds(), 3600)
                        minutes, seconds_remaining = divmod(remainder, 60)

                        time_str = []
                        if hours > 0:
                            time_str.append(f"{int(hours)}ч")
                        if minutes > 0:
                            time_str.append(f"{int(minutes)}м")
                        if seconds_remaining > 0 and not time_str:
                            time_str.append(f"{int(seconds_remaining)}с")

                        await update.message.reply_text(f"Можешь работать через {' '.join(time_str)}")
                        return

                # Check per-victim cooldown (skip in DEBUG mode)
                if not IS_DEBUG:
                    last_fine = (
                        db.query(InterpolFine)
                        .filter(
                            InterpolFine.interpol_id == user_id,
                            InterpolFine.victim_id == victim_id,
                            InterpolFine.created_at
                            > datetime.utcnow() - timedelta(hours=INTERPOL_VICTIM_COOLDOWN_HOURS),
                        )
                        .first()
                    )

                    if last_fine:
                        remaining = (
                            last_fine.created_at + timedelta(hours=INTERPOL_VICTIM_COOLDOWN_HOURS)
                        ) - datetime.utcnow()
                        minutes = int(remaining.total_seconds() / 60)
                        await update.message.reply_text(f"Можешь оштрафовать @{victim_username} через {minutes}м")
                        return

                # Calculate fine based on victim's job level (approximately one salary)
                victim_job = db.query(Job).filter(Job.user_id == victim_id).first()
                if victim_job:
                    if victim_job.job_type == "selfmade":
                        fine_ranges = SELFMADE_SALARY_RANGES
                    else:
                        fine_ranges = SALARY_RANGES
                    min_sal, max_sal = fine_ranges.get(victim_job.job_level, (10, 20))
                    fine_amount = random.randint(min_sal, max_sal)
                else:
                    # No job = minimum fine
                    fine_amount = random.randint(10, 20)

                # Cap fine at victim's balance
                fine_amount = min(fine_amount, victim_user.balance)

                # Calculate bonus if interpol is higher level
                bonus_amount = 0
                if victim_job and job.job_level > victim_job.job_level:
                    level_diff = job.job_level - victim_job.job_level
                    bonus_amount = int(fine_amount * INTERPOL_BONUS_MAX_PERCENTAGE * min(level_diff / 5, 1))

                # Apply fine
                victim_user.balance -= fine_amount
                user.balance += fine_amount + bonus_amount

                # Record fine
                fine_record = InterpolFine(
                    interpol_id=user_id,
                    victim_id=victim_id,
                    fine_amount=fine_amount,
                    bonus_amount=bonus_amount,
                )
                db.add(fine_record)

                # Update interpol stats
                job.times_worked += 1
                job.last_work_time = datetime.utcnow()

                # Check for promotion
                promoted = False
                max_level = 10
                promotion_chance = PROMOTION_CHANCES.get(job.job_level, 0.02)
                guaranteed_works = GUARANTEED_PROMOTION_WORKS.get(job.job_level, 999)

                if job.job_level < max_level:
                    if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                        job.job_level += 1
                        job.times_worked = 0
                        promoted = True

                # Set cooldown (skip for debug chat)

                cooldown_hours = COOLDOWN_BY_LEVEL.get(job.job_level, 4)

                set_cooldown(update, user_id, "job", cooldown_hours)

                # Response
                response = f"🚔 @{html.escape(victim_username)} оштрафован\n\n"
                response += f"💰 {format_diamonds(fine_amount)}\n"
                if bonus_amount > 0:
                    response += f"💎 <b>За говновызов:</b> +{format_diamonds(bonus_amount)}\n"
                response += f"💰 <b>Итого:</b> {format_diamonds(fine_amount + bonus_amount)}"

                if promoted:
                    new_title = JOB_TITLES[job.job_type][job.job_level - 1]
                    response += f"\n\n🎉 {new_title} ({job.job_level} ур.)"

                await update.message.reply_text(response, parse_mode="HTML")

                # Notify victim
                try:
                    victim_message = (
                        f"🚔 Штраф\n\n"
                        f"💸 -{format_diamonds(fine_amount)}\n"
                        f"💰 {format_diamonds(victim_user.balance)}"
                    )
                    await context.bot.send_message(chat_id=victim_id, text=victim_message, parse_mode="HTML")
                except Exception as e:
                    logger.warning("Failed to notify victim about fine", victim_id=victim_id, error=str(e))

                return
            else:
                # No reply = patrol work (охрана ивента)
                # Continue to normal work flow below, but will add hint at the end
                pass

        # Check cooldown AFTER verifying user has a job (skip in DEBUG mode)
        if not IS_DEBUG:
            cooldown_entry = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "job").first()

            if cooldown_entry and cooldown_entry.expires_at > datetime.utcnow():
                remaining = cooldown_entry.expires_at - datetime.utcnow()
                hours, remainder = divmod(remaining.total_seconds(), 3600)
                minutes, seconds_remaining = divmod(remainder, 60)

                time_str = []
                if hours > 0:
                    time_str.append(f"{int(hours)}ч")
                if minutes > 0:
                    time_str.append(f"{int(minutes)}м")
                if seconds_remaining > 0 and not time_str:
                    time_str.append(f"{int(seconds_remaining)}с")

                from app.handlers.premium import build_premium_nudge

                nudge = build_premium_nudge("cooldown", user_id)
                await update.message.reply_text(
                    f"Можешь работать через {' '.join(time_str)}{nudge}", parse_mode="HTML"
                )
                return

        # Calculate salary based on profession
        if job.job_type == "selfmade":
            min_salary, max_salary = SELFMADE_SALARY_RANGES.get(job.job_level, (5, 10))
        else:
            min_salary, max_salary = SALARY_RANGES.get(job.job_level, (10, 20))

        earned = random.randint(min_salary, max_salary)

        # Apply prestige bonus
        prestige = user.prestige_level or 0
        if prestige > 0:
            earned = int(earned * (1 + prestige * 0.05))

        # Apply double income boost
        from app.handlers.premium import has_active_boost

        double_income = has_active_boost(user_id, "double_income", db=db)
        if double_income:
            earned *= 2

        # Update user balance
        user.balance += earned

        # Update job stats
        job.times_worked += 1
        job.last_work_time = datetime.utcnow()

        # Check for promotion
        promoted = False
        scammed = False  # Для selfmade trap

        # Определяем максимальный уровень
        max_level = 6 if job.job_type == "selfmade" else 10

        promotion_chance = PROMOTION_CHANCES.get(job.job_level, 0.02)
        guaranteed_works = GUARANTEED_PROMOTION_WORKS.get(job.job_level, 999)

        # Check premium promotion boost (50% chance, consumed on use)
        from app.handlers.premium import consume_boost

        if consume_boost(user_id, "promotion_chance", db=db):
            promotion_chance = 0.50  # 50% instead of normal 2-5%

        # Selfmade trap: при попытке апа с максимального уровня (отдельная проверка)
        if job.job_type == "selfmade" and job.job_level == SELFMADE_TRAP_LEVEL:
            if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                # НАЕБАЛИ!
                user.balance = 0  # Обнуляем баланс
                job.job_level = 1  # Сбрасываем на нищий
                job.times_worked = 0
                scammed = True
        elif job.job_level < max_level:  # Not max level
            if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                job.job_level += 1
                job.times_worked = 0  # Reset counter
                promoted = True

        # Set cooldown AFTER successful work (skip for debug chat)

        if job.job_type == "selfmade":

            cooldown_hours = SELFMADE_COOLDOWN

        else:

            cooldown_hours = COOLDOWN_BY_LEVEL.get(job.job_level, 4)

        set_cooldown(update, user_id, "job", cooldown_hours)

        # Generate work flavor text
        flavor = random.choice(FLAVOR_TEXTS.get(job.job_type, ["Отработал смену"]))

        # Build response with clear structure
        emoji = PROFESSION_EMOJI.get(job.job_type, "💼")

        # Check if scammed
        if scammed:
            response = (
                f"💼 <b>Работа завершена</b>\n\n"
                f"{emoji} {flavor}\n\n"
                f"💰 Заработано: {format_diamonds(earned)}\n"
                f"💰 Баланс: {format_diamonds(user.balance + earned)}\n\n"
                f"🎰 <b>ВАС НАЕБАЛИ ДРУЗЬЯ НА КАЗИНО!</b>\n\n"
                f"💸 Баланс обнулен: {format_diamonds(0)}\n"
                f"📉 Уровень сброшен: нищий"
            )
        else:
            response = (
                f"💼 <b>Работа завершена</b>\n\n"
                f"{emoji} {flavor}\n\n"
                f"💰 Заработано: {format_diamonds(earned)}\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )

            if promoted:
                new_title = JOB_TITLES[job.job_type][job.job_level - 1]
                response += f"\n\n🎉 <b>Повышение!</b>\n{new_title} (уровень {job.job_level})"

            # Add hint for Interpol patrol work
            if job.job_type == "interpol":
                response += "\n\n💡 <b>Подсказка:</b> Штрафуй игроков\n• /job (ответь на сообщение)\n• /job @username"

            # Add DEBUG mode note
            if IS_DEBUG:
                response += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"

        await update.message.reply_text(response, parse_mode="HTML")

        # Track quest progress
        try:
            update_quest_progress(user_id, "work", db=db)
        except Exception:
            pass  # Quest tracking is non-critical

        # Award loyalty point
        try:
            from app.handlers.premium import add_loyalty_points

            add_loyalty_points(user_id, 1)
        except Exception:
            pass


async def work_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle work menu callbacks."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    action = parts[1]

    # Check button owner (user_id is last part)
    if len(parts) >= 3:
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    # Ban check
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if action == "choose_profession":
        await safe_edit_message(
            query,
            "💼 Профессия\n\n" "Выбери сферу деятельности:",
            reply_markup=profession_selection_keyboard(user_id=user_id, page=1),
        )

    elif action == "do_job":
        # Execute job command directly
        # For Interpol: show instruction
        # For others: execute job inline

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if not job:
                await safe_edit_message(query, "⚠️ Нет работы. Используй /work")
                return

            # Interpol must use /job with reply
            if job.job_type == "interpol":
                await safe_edit_message(
                    query,
                    "🚔 Интерпол\n\n" "💡 Штраф:\n" "• /job (ответь)\n" "• /job @username\n\n" "💡 Охрана:\n" "/job",
                )
                return

            # Check cooldown (skip in DEBUG mode)
            if not IS_DEBUG:
                cooldown_entry = (
                    db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "job").first()
                )

                if cooldown_entry and cooldown_entry.expires_at > datetime.utcnow():
                    remaining = cooldown_entry.expires_at - datetime.utcnow()
                    hours, remainder = divmod(remaining.total_seconds(), 3600)
                    minutes, seconds_remaining = divmod(remainder, 60)

                    time_str = []
                    if hours > 0:
                        time_str.append(f"{int(hours)}ч")
                    if minutes > 0:
                        time_str.append(f"{int(minutes)}м")
                    if seconds_remaining > 0 and not time_str:
                        time_str.append(f"{int(seconds_remaining)}с")

                    from app.handlers.premium import build_premium_nudge

                    nudge = build_premium_nudge("cooldown", user_id)
                    await safe_edit_message(query, f"Можешь работать через {' '.join(time_str)}{nudge}")
                    return

            # Calculate salary
            if job.job_type == "selfmade":
                min_salary, max_salary = SELFMADE_SALARY_RANGES.get(job.job_level, (5, 10))
            else:
                min_salary, max_salary = SALARY_RANGES.get(job.job_level, (10, 20))

            earned = random.randint(min_salary, max_salary)

            # Apply prestige bonus
            prestige = user.prestige_level or 0
            if prestige > 0:
                earned = int(earned * (1 + prestige * 0.05))

            # Apply double income boost
            from app.handlers.premium import has_active_boost

            if has_active_boost(user_id, "double_income", db=db):
                earned *= 2

            # Update user balance
            user.balance += earned

            # Update job stats
            job.times_worked += 1
            job.last_work_time = datetime.utcnow()

            # Check for promotion
            promoted = False
            scammed = False

            max_level = 6 if job.job_type == "selfmade" else 10
            promotion_chance = PROMOTION_CHANCES.get(job.job_level, 0.02)
            guaranteed_works = GUARANTEED_PROMOTION_WORKS.get(job.job_level, 999)

            # Check premium promotion boost (50% chance, consumed on use)
            from app.handlers.premium import consume_boost

            if consume_boost(user_id, "promotion_chance", db=db):
                promotion_chance = 0.50  # 50% instead of normal 2-5%

            # Selfmade trap: при попытке апа с максимального уровня
            if job.job_type == "selfmade" and job.job_level == SELFMADE_TRAP_LEVEL:
                if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                    # НАЕБАЛИ!
                    user.balance = 0
                    job.job_level = 1
                    job.times_worked = 0
                    scammed = True
            elif job.job_level < max_level:
                if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                    job.job_level += 1
                    job.times_worked = 0
                    promoted = True

            # Set cooldown (skip for debug chat)

            if job.job_type == "selfmade":

                cooldown_hours = SELFMADE_COOLDOWN

            else:

                cooldown_hours = COOLDOWN_BY_LEVEL.get(job.job_level, 4)

            set_cooldown(update, user_id, "job", cooldown_hours)

            # Generate work flavor text
            flavor = random.choice(FLAVOR_TEXTS.get(job.job_type, ["Отработал смену"]))

            # Build response with clear structure
            emoji = PROFESSION_EMOJI.get(job.job_type, "💼")

            # Check if scammed
            if scammed:
                response = (
                    f"💼 <b>Работа завершена</b>\n\n"
                    f"{emoji} {flavor}\n\n"
                    f"💰 Заработано: {format_diamonds(earned)}\n"
                    f"💰 Баланс: {format_diamonds(user.balance + earned)}\n\n"
                    f"🎰 <b>ВАС НАЕБАЛИ ДРУЗЬЯ НА КАЗИНО!</b>\n\n"
                    f"💸 Баланс обнулен: {format_diamonds(0)}\n"
                    f"📉 Уровень сброшен: нищий"
                )
            else:
                response = (
                    f"💼 <b>Работа завершена</b>\n\n"
                    f"{emoji} {flavor}\n\n"
                    f"💰 Заработано: {format_diamonds(earned)}\n"
                    f"💰 Баланс: {format_diamonds(user.balance)}"
                )

                if promoted:
                    new_title = JOB_TITLES[job.job_type][job.job_level - 1]
                    response += f"\n\n🎉 <b>Повышение!</b>\n{new_title} (уровень {job.job_level})"

                # Add DEBUG mode note
                if IS_DEBUG:
                    response += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"

            await safe_edit_message(query, response)

    elif action == "quit":
        # Show confirmation dialog
        from app.utils.keyboards import confirm_keyboard

        await safe_edit_message(
            query,
            "⚠️ Точно?\n\nПотеряешь должность и прогресс",
            reply_markup=confirm_keyboard("quit_job", user_id=user_id),
        )

    elif action == "quit_job_confirmed":
        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()
            if job:
                db.delete(job)
                await safe_edit_message(
                    query, "❌ Уволен", reply_markup=work_menu_keyboard(has_job=False, user_id=user_id)
                )
            else:
                await safe_edit_message(
                    query, "⚠️ Нет работы", reply_markup=work_menu_keyboard(has_job=False, user_id=user_id)
                )

    elif action == "quit_job_cancelled":
        # Go back to work menu
        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if job:
                job_name = JOB_TITLES[job.job_type][job.job_level - 1]
                emoji = PROFESSION_EMOJI.get(job.job_type, "💼")
                track_name = PROFESSION_NAMES.get(job.job_type, "")

                max_level = 6 if job.job_type == "selfmade" else 10
                if job.job_level < max_level:
                    next_title = JOB_TITLES[job.job_type][job.job_level]
                    next_level_text = f"📈 {next_title}"
                else:
                    next_level_text = "🏆 Максимум"

                await safe_edit_message(
                    query,
                    f"💼 {track_name}\n"
                    f"{emoji} {job_name} ({job.job_level}/{max_level})\n"
                    f"📊 {job.times_worked}\n"
                    f"{next_level_text}",
                    reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                )
            else:
                await safe_edit_message(
                    query,
                    "💼 Нет работы\n\nВыбери профессию:",
                    reply_markup=work_menu_keyboard(has_job=False, user_id=user_id),
                )


async def profession_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profession selection callback."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    profession = parts[1]

    # Check button owner (user_id is last part)
    if len(parts) >= 3:
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    with get_db() as db:
        # Ban check
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

        existing_job = db.query(Job).filter(Job.user_id == user_id).first()

        if existing_job:
            # Change profession (1-2 levels down)
            level_penalty = random.randint(1, 2)
            new_level = max(1, existing_job.job_level - level_penalty)

            existing_job.job_type = profession
            existing_job.job_level = new_level
            existing_job.times_worked = 0

            new_title = JOB_TITLES[profession][new_level - 1]
            await safe_edit_message(
                query,
                f"✅ Профессия сменена\n\n"
                f"📋 {new_title} ({new_level} ур.)\n\n"
                f"⚠️ Потерял {level_penalty} {'уровень' if level_penalty == 1 else 'уровня'}",
                reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
            )
        else:
            # First job
            job = Job(user_id=user_id, job_type=profession, job_level=1)
            db.add(job)

            job_title = JOB_TITLES[profession][0]

            # Зарплата зависит от профессии
            if profession == "selfmade":
                min_sal, max_sal = SELFMADE_SALARY_RANGES[1]
            else:
                min_sal, max_sal = SALARY_RANGES[1]

            await safe_edit_message(
                query,
                f"✅ Принят\n\n" f"📋 {job_title} (1 ур.)\n" f"💰 {min_sal}-{max_sal} алмазов\n\n" f"/job — работать",
                reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
            )


async def profession_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profession page navigation."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    page = int(parts[1])

    # Check button owner
    if len(parts) >= 3:
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    await safe_edit_message(
        query,
        "💼 Профессия\n\n" "Выбери сферу деятельности:",
        reply_markup=profession_selection_keyboard(user_id=user_id, page=page),
    )


def register_work_handlers(application):
    """Register work handlers."""
    application.add_handler(CommandHandler("work", work_menu_command))
    application.add_handler(CommandHandler("job", job_command))
    application.add_handler(CallbackQueryHandler(work_callback, pattern="^work:"))
    application.add_handler(CallbackQueryHandler(profession_page_callback, pattern="^profession_page:"))
    application.add_handler(CallbackQueryHandler(profession_callback, pattern="^profession:"))
