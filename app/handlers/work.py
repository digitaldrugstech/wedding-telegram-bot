"""Work and job handlers."""

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
from app.utils.decorators import require_registered, set_cooldown
from app.utils.formatters import format_diamonds
from app.utils.keyboards import profession_selection_keyboard, work_menu_keyboard

logger = structlog.get_logger()

# Check if DEBUG mode (DEV environment)
IS_DEBUG = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"

# Job titles by profession and level
JOB_TITLES = {
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


@require_registered
async def work_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /work command - show work menu."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        job = db.query(Job).filter(Job.user_id == user_id).first()

        if job:
            job_name = JOB_TITLES[job.job_type][job.job_level - 1]
            profession_emoji = {
                "interpol": "🚔",
                "banker": "💳",
                "infrastructure": "🏗️",
                "court": "⚖️",
                "culture": "🎭",
                "selfmade": "🐦",
            }
            emoji = profession_emoji.get(job.job_type, "💼")

            # Название трека
            profession_names = {
                "interpol": "Интерпол",
                "banker": "Банкир",
                "infrastructure": "Инфраструктура",
                "court": "Суд",
                "culture": "Культура",
                "selfmade": "Селфмейд",
            }
            track_name = profession_names.get(job.job_type, "")

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
    if not update.effective_user:
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

                        await update.message.reply_text(f"Можешь работать через {' '.join(time_str)}")
                        return

                # Check per-victim cooldown (skip in DEBUG mode)
                if not IS_DEBUG:
                    last_fine = (
                        db.query(InterpolFine)
                        .filter(
                            InterpolFine.interpol_id == user_id,
                            InterpolFine.victim_id == victim_id,
                            InterpolFine.created_at > datetime.utcnow() - timedelta(hours=INTERPOL_VICTIM_COOLDOWN_HOURS),
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

                db.commit()

                # Set cooldown (skip for debug chat)

                cooldown_hours = COOLDOWN_BY_LEVEL.get(job.job_level, 4)

                set_cooldown(update, user_id, "job", cooldown_hours)

                # Response
                response = f"🚔 @{victim_username} оштрафован\n\n"
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

                await update.message.reply_text(f"Можешь работать через {' '.join(time_str)}")
                return

        # Calculate salary based on profession
        if job.job_type == "selfmade":
            min_salary, max_salary = SELFMADE_SALARY_RANGES.get(job.job_level, (5, 10))
        else:
            min_salary, max_salary = SALARY_RANGES.get(job.job_level, (10, 20))

        earned = random.randint(min_salary, max_salary)

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

        if job.job_level < max_level:  # Not max level
            if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                # Selfmade trap: при попытке апа с максимального уровня
                if job.job_type == "selfmade" and job.job_level == SELFMADE_TRAP_LEVEL:
                    # НАЕБАЛИ!
                    user.balance = 0  # Обнуляем баланс
                    job.job_level = 1  # Сбрасываем на нищий
                    job.times_worked = 0
                    scammed = True
                else:
                    job.job_level += 1
                    job.times_worked = 0  # Reset counter
                    promoted = True

        # Set cooldown AFTER successful work (skip for debug chat)

        if job.job_type == "selfmade":

            cooldown_hours = SELFMADE_COOLDOWN

        else:

            cooldown_hours = COOLDOWN_BY_LEVEL.get(job.job_level, 4)

        set_cooldown(update, user_id, "job", cooldown_hours)

        db.commit()

        # Generate work flavor text
        flavor_texts = {
            "interpol": [
                "Обеспечил безопасность на ивенте",
                "Патрулировал территорию сервера",
                "Дежурил на охране мероприятия",
                "Проверил документы у игроков",
            ],
            "banker": [
                f"Обслужил {random.randint(15, 30)} клиентов в банке",
                f"Провёл {random.randint(10, 25)} финансовых транзакций",
                f"Одобрил {random.randint(5, 15)} кредитных заявок",
                f"Обработал {random.randint(20, 35)} платежей",
            ],
            "infrastructure": [
                f"Собрал {random.randint(20, 40)} единиц ресурсов",
                f"Построил {random.randint(5, 15)} новых объектов",
                f"Отремонтировал {random.randint(3, 10)} зданий на спавне",
                f"Обслужил инфраструктуру города",
            ],
            "court": [
                f"Рассмотрел {random.randint(3, 8)} судебных дел",
                f"Вынес {random.randint(2, 6)} обоснованных приговоров",
                f"Провёл {random.randint(1, 4)} судебных слушания",
                f"Изучил материалы дел",
            ],
            "culture": [
                f"Провёл {random.randint(2, 5)} крутых ивентов",
                f"Организовал {random.randint(1, 3)} мероприятия для игроков",
                f"Подготовил {random.randint(2, 4)} концерта",
                f"Развлекал население города",
            ],
            "selfmade": [
                "Весь день крутил казино (и проиграл)",
                "Забирал муку на рынке у чебуреков",
                "Звонил юристам по своим делам",
                "Весь день не мылся (типичный день)",
                "Заебался, но работал",
                "Планировал месть обидчикам",
            ],
        }

        flavor = random.choice(flavor_texts.get(job.job_type, ["Отработал смену"]))

        # Build response with clear structure
        job_emoji = {"interpol": "🚔", "banker": "💳", "infrastructure": "🏗️", "court": "⚖️", "culture": "🎭", "selfmade": "🐦"}
        emoji = job_emoji.get(job.job_type, "💼")

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

    if action == "choose_profession":
        await query.edit_message_text(
            "💼 Профессия\n\n"
            "🚔 Интерпол — штрафы\n"
            "💳 Банкир — транзакции\n"
            "🏗️ Инфраструктура — ресурсы\n"
            "⚖️ Суд — приговоры\n"
            "🎭 Культура — ивенты\n"
            "🐦 Селфмейд — крути каз и забирай муку",
            reply_markup=profession_selection_keyboard(user_id=user_id),
        )

    elif action == "do_job":
        # Execute job command directly
        # For Interpol: show instruction
        # For others: execute job inline

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if not job:
                await query.edit_message_text("⚠️ Нет работы. Используй /work")
                return

            # Interpol must use /job with reply
            if job.job_type == "interpol":
                await query.edit_message_text(
                    "🚔 Интерпол\n\n" "💡 Штраф:\n" "• /job (ответь)\n" "• /job @username\n\n" "💡 Охрана:\n" "/job"
                )
                return

            # Check cooldown (skip in DEBUG mode)
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

                    await query.edit_message_text(f"Можешь работать через {' '.join(time_str)}")
                    return

            # Calculate salary
            if job.job_type == "selfmade":
                min_salary, max_salary = SELFMADE_SALARY_RANGES.get(job.job_level, (5, 10))
            else:
                min_salary, max_salary = SALARY_RANGES.get(job.job_level, (10, 20))

            earned = random.randint(min_salary, max_salary)

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

            if job.job_level < max_level:
                if random.random() < promotion_chance or job.times_worked >= guaranteed_works:
                    if job.job_type == "selfmade" and job.job_level == SELFMADE_TRAP_LEVEL:
                        # НАЕБАЛИ!
                        user.balance = 0
                        job.job_level = 1
                        job.times_worked = 0
                        scammed = True
                    else:
                        job.job_level += 1
                        job.times_worked = 0
                        promoted = True

            # Set cooldown (skip for debug chat)

            if job.job_type == "selfmade":

                cooldown_hours = SELFMADE_COOLDOWN

            else:

                cooldown_hours = COOLDOWN_BY_LEVEL.get(job.job_level, 4)

            set_cooldown(update, user_id, "job", cooldown_hours)

            db.commit()

            # Generate work flavor text
            flavor_texts = {
                "interpol": [
                    "Проверил документы у подозрительных личностей",
                    "Провёл рейд по нелегальным точкам",
                    "Задержал нарушителей порядка",
                    "Патрулировал территорию сервера",
                ],
                "banker": [
                    f"Обслужил {random.randint(15, 30)} клиентов в банке",
                    f"Провёл {random.randint(10, 25)} финансовых транзакций",
                    f"Одобрил {random.randint(5, 15)} кредитных заявок",
                    f"Обработал {random.randint(20, 35)} платежей",
                ],
                "infrastructure": [
                    f"Собрал {random.randint(20, 40)} единиц ресурсов",
                    f"Построил {random.randint(5, 15)} новых объектов",
                    f"Отремонтировал {random.randint(3, 10)} зданий на спавне",
                    f"Обслужил инфраструктуру города",
                ],
                "court": [
                    f"Рассмотрел {random.randint(3, 8)} судебных дел",
                    f"Вынес {random.randint(2, 6)} обоснованных приговоров",
                    f"Провёл {random.randint(1, 4)} судебных слушания",
                    f"Изучил материалы дел",
                ],
                "culture": [
                    f"Провёл {random.randint(2, 5)} крутых ивентов",
                    f"Организовал {random.randint(1, 3)} мероприятия для игроков",
                    f"Подготовил {random.randint(2, 4)} концерта",
                    f"Развлекал население города",
                ],
                "selfmade": [
                    "Весь день крутил казино (и проиграл)",
                    "Забирал муку на рынке у чебуреков",
                    "Звонил юристам по своим делам",
                    "Весь день не мылся (типичный день)",
                    "Заебался, но работал",
                    "Планировал месть обидчикам",
                ],
            }

            flavor = random.choice(flavor_texts.get(job.job_type, ["Отработал смену"]))

            # Build response with clear structure
            job_emoji = {"interpol": "🚔", "banker": "💳", "infrastructure": "🏗️", "court": "⚖️", "culture": "🎭", "selfmade": "🐦"}
            emoji = job_emoji.get(job.job_type, "💼")

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

            await query.edit_message_text(response, parse_mode="HTML")

    elif action == "quit":
        # Show confirmation dialog
        from app.utils.keyboards import confirm_keyboard

        await query.edit_message_text(
            "⚠️ Точно?\n\nПотеряешь должность и прогресс",
            reply_markup=confirm_keyboard("quit_job", user_id=user_id),
        )

    elif action == "quit_job_confirmed":
        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()
            if job:
                db.delete(job)
                db.commit()
                await query.edit_message_text("❌ Уволен", reply_markup=work_menu_keyboard(has_job=False, user_id=user_id))
            else:
                await query.edit_message_text("⚠️ Нет работы", reply_markup=work_menu_keyboard(has_job=False, user_id=user_id))

    elif action == "quit_job_cancelled":
        # Go back to work menu
        with get_db() as db:
            job = db.query(Job).filter(Job.user_id == user_id).first()

            if job:
                job_name = JOB_TITLES[job.job_type][job.job_level - 1]
                profession_emoji = {
                    "interpol": "🚔",
                    "banker": "💳",
                    "infrastructure": "🏗️",
                    "court": "⚖️",
                    "culture": "🎭",
                    "selfmade": "🐦",
                }
                emoji = profession_emoji.get(job.job_type, "💼")

                profession_names = {
                    "interpol": "Интерпол",
                    "banker": "Банкир",
                    "infrastructure": "Инфраструктура",
                    "court": "Суд",
                    "culture": "Культура",
                    "selfmade": "Селфмейд",
                }
                track_name = profession_names.get(job.job_type, "")

                max_level = 6 if job.job_type == "selfmade" else 10
                if job.job_level < max_level:
                    next_title = JOB_TITLES[job.job_type][job.job_level]
                    next_level_text = f"📈 {next_title}"
                else:
                    next_level_text = "🏆 Максимум"

                await query.edit_message_text(
                    f"💼 {track_name}\n"
                    f"{emoji} {job_name} ({job.job_level}/{max_level})\n"
                    f"📊 {job.times_worked}\n"
                    f"{next_level_text}",
                    reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                )
            else:
                await query.edit_message_text(
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
        existing_job = db.query(Job).filter(Job.user_id == user_id).first()

        if existing_job:
            # Change profession (1-2 levels down)
            level_penalty = random.randint(1, 2)
            new_level = max(1, existing_job.job_level - level_penalty)

            existing_job.job_type = profession
            existing_job.job_level = new_level
            existing_job.times_worked = 0
            db.commit()

            new_title = JOB_TITLES[profession][new_level - 1]
            await query.edit_message_text(
                f"✅ Профессия сменена\n\n"
                f"📋 {new_title} ({new_level} ур.)\n\n"
                f"⚠️ Потерял {level_penalty} {'уровень' if level_penalty == 1 else 'уровня'}",
                reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                parse_mode="HTML",
            )
        else:
            # First job
            job = Job(user_id=user_id, job_type=profession, job_level=1)
            db.add(job)
            db.commit()

            job_title = JOB_TITLES[profession][0]

            # Зарплата зависит от профессии
            if profession == "selfmade":
                min_sal, max_sal = SELFMADE_SALARY_RANGES[1]
            else:
                min_sal, max_sal = SALARY_RANGES[1]

            await query.edit_message_text(
                f"✅ Принят\n\n" f"📋 {job_title} (1 ур.)\n" f"💰 {min_sal}-{max_sal} алмазов\n\n" f"/job — работать",
                reply_markup=work_menu_keyboard(has_job=True, user_id=user_id),
                parse_mode="HTML",
            )


def register_work_handlers(application):
    """Register work handlers."""
    application.add_handler(CommandHandler("work", work_menu_command))
    application.add_handler(CommandHandler("job", job_command))
    application.add_handler(CallbackQueryHandler(work_callback, pattern="^work:"))
    application.add_handler(CallbackQueryHandler(profession_callback, pattern="^profession:"))
