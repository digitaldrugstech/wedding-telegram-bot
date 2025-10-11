# Context Transfer: Wedding Telegram Bot Development

Этот документ содержит полный контекст для продолжения разработки Wedding Telegram Bot в новом терминале Claude Code.

---

## Prompt для нового терминала

```
Ты продолжаешь разработку Wedding Telegram Bot - Telegram бота для симуляции семейной жизни на игровом сервере.

# Проект

**Репозиторий**: https://github.com/digitaldrugstech/wedding-telegram-bot
**Рабочая директория**: /home/haffk/prdx/workspace/wedding-telegram-bot
**Текущая версия**: v1.1.0 (2025-10-11)
**Docker Image**: ghcr.io/digitaldrugstech/wedding-telegram-bot:latest

# Технологический стек

- **Python 3.11+** с async/await
- **python-telegram-bot 20.7** - асинхронный Telegram Bot API wrapper
- **PostgreSQL 15+** - база данных
- **SQLAlchemy 2.0** - ORM (context manager pattern)
- **Alembic** - миграции БД
- **APScheduler** - планировщик задач
- **structlog** - структурированное логирование (JSON)
- **Docker** + **Kubernetes** - деплоймент
- **GitHub Actions** - CI/CD (tests, lint, security, Docker builds)

# Форматирование кода

**КРИТИЧЕСКИ ВАЖНО**:
- **Line length**: 120 символов (не 80, не 100)
- **black**: `black --line-length 120 app/`
- **isort**: `isort --profile black app/` (конфиг в `.isort.cfg`)
- **flake8**: проверка E, W, F ошибок
- Все изменения проходят через CI/CD перед мержем

# Архитектура проекта

```
wedding-telegram-bot/
├── app/
│   ├── __version__.py          # "1.1.0"
│   ├── main.py                 # Entry point
│   ├── bot.py                  # Bot initialization & handlers registration
│   ├── config.py               # Config dataclass (env vars)
│   ├── constants.py            # Game constants (SALARY_RANGES, COOLDOWNS, etc.)
│   ├── database/
│   │   ├── models.py           # User, Job, Marriage, Cooldown, InterpolFine, Kidnapping
│   │   └── connection.py       # get_db() context manager
│   ├── handlers/
│   │   ├── start.py            # /profile (registration auto in @require_registered)
│   │   ├── work.py             # /work, /job (6 профессий, 10 уровней)
│   │   ├── marriage.py         # /propose, /marriage, /gift, /makelove, /date, /cheat
│   │   ├── admin.py            # /reset_cd (admin only)
│   │   ├── utils.py            # /balance, /help
│   │   └── menu.py             # Callback query handlers (buttons)
│   ├── services/
│   │   └── marriage_service.py # Marriage business logic
│   ├── utils/
│   │   ├── decorators.py       # @require_registered, @admin_only, @set_cooldown
│   │   ├── keyboards.py        # Inline keyboards
│   │   └── formatters.py       # format_diamonds()
│   └── tasks/                  # Scheduled tasks (будущие features)
├── .github/workflows/
│   ├── ci.yml                  # Tests (pytest + PostgreSQL)
│   ├── lint.yml                # black, isort, flake8
│   ├── docker-publish.yml      # Multi-platform builds → GHCR
│   └── security.yml            # safety, bandit, CodeQL
├── alembic/versions/           # DB migrations
├── tests/                      # pytest tests
├── CLAUDE.md                   # **ЧИТАЙ ПЕРВЫМ** - полный технический контекст
├── WRITING_STYLE.md            # **ОБЯЗАТЕЛЬНО** - правила написания текстов
├── CHANGELOG.md                # История версий
└── README.md                   # Документация для пользователей
```

# Ключевые файлы (читай обязательно)

1. **CLAUDE.md** - полный технический контекст проекта:
   - Все модели БД с полями
   - Job system (профессии, зарплаты, кулдауны, повышения)
   - Marriage system (механики всех команд)
   - Interpol special mechanics (штрафы, бонусы)
   - Selfmade easter egg (СЕКРЕТ - не писать в CHANGELOG!)
   - Паттерны кода (decorators, context managers, error handling)
   - CI/CD pipelines
   - Common pitfalls

2. **WRITING_STYLE.md** - КРИТИЧЕСКИ ВАЖНО для всех текстов:
   - Принципы сильного текста (краткость, конкретность, активный залог)
   - Всегда "ты", никогда "вы"
   - Эмодзи вместо текстовых меток
   - HTML formatting, НЕ Markdown
   - Примеры до/после для всех типов сообщений

3. **CHANGELOG.md** - формат записи изменений (conventional changelog)

# База данных (PostgreSQL + SQLAlchemy 2.0)

## Модели

### User (основная модель)
```python
telegram_id: BigInteger (PK)
username: String(255)
gender: 'male' | 'female'
balance: BigInteger  # алмазы 💎
is_banned: Boolean
created_at, updated_at: DateTime (UTC!)
```

### Job (работа)
```python
user_id: FK → User (unique)
job_type: 'interpol' | 'banker' | 'infrastructure' | 'court' | 'culture' | 'selfmade'
job_level: 1-10 (для selfmade 1-6, на 7 - ловушка!)
times_worked: Integer
last_work_time: DateTime (UTC!)
```

### Marriage (v1.1.0)
```python
partner1_id, partner2_id: FK → User
is_active: Boolean
married_at, divorced_at: DateTime (UTC!)
love_count: Integer  # сколько раз занимались любовью
```

### Cooldown (универсальная система кулдаунов)
```python
user_id: FK → User
action: String  # 'job', 'makelove', 'date', 'interpol_fine_{victim_id}'
expires_at: DateTime (UTC!)
Unique: (user_id, action)
```

### InterpolFine (штрафы от интерпола)
```python
interpol_id, victim_id: FK → User
fine_amount, bonus_amount: Integer
created_at: DateTime (UTC!)
```

## ВАЖНО: Context Manager для БД

**ВСЕГДА используй:**
```python
from app.database.connection import get_db

with get_db() as db:
    user = db.query(User).filter(User.telegram_id == user_id).first()
    user.balance += 100
    # Auto-commit on success, rollback on exception
```

**НЕ используй** ручной session management - get_db() всё делает сам!

# Игровая механика

## Job System (система работы)

### Профессии
1. **Интерпол (interpol)** - штрафует игроков `/job @username`
2. **Банкир (banker)** - экономика
3. **Инфраструктура (infrastructure)** - строительство
4. **Суд (court)** - рассмотрение дел
5. **Культура (culture)** - ивенты
6. **Селфмейд (selfmade)** - 6 уровней, на 7 - СЕКРЕТНАЯ ЛОВУШКА

### Зарплаты (constants.py)
```python
SALARY_RANGES = {
    1: (10, 20), 2: (20, 35), 3: (35, 55), 4: (55, 85), 5: (85, 130),
    6: (130, 200), 7: (200, 300), 8: (300, 450), 9: (450, 650), 10: (650, 1000)
}
SELFMADE_SALARY_RANGES = {1: (5, 10), 2: (8, 15), 3: (12, 20), 4: (18, 30), 5: (25, 40), 6: (35, 55)}
```

### Кулдауны (часы)
```python
COOLDOWN_BY_LEVEL = {1: 1, 2: 1, 3: 1.5, 4: 1.5, 5: 2, 6: 2, 7: 3, 8: 3, 9: 4, 10: 4}
SELFMADE_COOLDOWN = 0.5  # 30 минут
```

### Повышение
- Случайный шанс: 5% (lvl 1) → 1.5% (lvl 10)
- Гарантированное: после 20-60 работ (зависит от уровня)

### Interpol особенности
- **С reply** (`/job` reply): штраф игрока
  - Штраф = примерно одна зарплата жертвы
  - Бонус +50% если интерпол выше уровнем
  - Кулдаун 1 час на жертву
  - Защита: у жертвы ≥50 алмазов
- **Без reply** (`/job`): патрулирование (обычная зарплата + хинт)

### Selfmade Easter Egg (СЕКРЕТ!)
**НИКОГДА не упоминать в CHANGELOG, README, или сообщениях пользователям!**
- При попытке повысить с 6 на 7 уровень:
  - Баланс обнуляется
  - Уровень сбрасывается на 1 ("нищий")
  - Сообщение: "🎰 ВАС НАЕБАЛИ ДРУЗЬЯ НА КАЗИНО !"

## Marriage System (v1.1.0)

### Команды
- `/propose` (reply или `@username`) - предложение брака (50 💎)
- `/marriage` - меню брака (кнопки: gift, divorce, stats)
- `/gift [amount]` - подарить алмазы супругу
- `/makelove` - заняться любовью (кулдаун 24ч, 10% шанс зачатия)
- `/date` - свидание (кулдаун 12ч, стоимость 10-50 💎)
- `/cheat` (reply или `@username`) - измена (30% риск развода)

### Механики
- **Proposal**: стоит 50 💎, требует подтверждения обеих сторон
- **Make Love**: кулдаун 24ч, 10% шанс беременности (сейчас только инкремент love_count, дети не реализованы)
- **Date**: случайная стоимость 10-50 💎, кулдаун 12ч
- **Cheat**: 30% шанс что партнер узнает → развод, 70% успех
- **Gift**: перевод любого количества алмазов супругу
- **Divorce**: мгновенный, бесплатный, оба получают уведомление

# Стиль написания текстов (КРИТИЧЕСКИ ВАЖНО!)

**ВСЕГДА читай WRITING_STYLE.md перед написанием любого текста для бота!**

## Основные правила

1. **Краткость** - убирай все лишние слова
   - ❌ "Для того чтобы работать, используй команду /job"
   - ✅ "/job — работать"

2. **Всегда "ты"**, никогда "вы" или "Вы"
   - ❌ "Вы зарегистрированы"
   - ✅ "Зарегистрирован"

3. **Эмодзи вместо меток**
   - ❌ "Баланс: 100 алмазов"
   - ✅ "💰 100 алмазов"

4. **HTML, не Markdown**
   ```python
   await message.reply_text(
       f"<b>Заголовок</b>\n\nТекст",
       parse_mode="HTML"
   )
   ```

5. **Алмазы с правильными окончаниями** - используй `format_diamonds()`
   - 1 алмаз, 2 алмаза, 5 алмазов, 21 алмаз

# Декораторы (используй ВСЕГДА)

```python
from app.utils.decorators import require_registered, admin_only, set_cooldown, button_owner_only

@require_registered  # Автоматическая регистрация + проверка бана
async def some_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

@admin_only  # Только для админа (ADMIN_USER_ID)
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

@set_cooldown(action="job", get_cooldown=lambda user_id: 3600)  # 1 hour
async def work_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

@button_owner_only  # Для callback кнопок (формат: "action:param:user_id")
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass
```

# Datetime (ВСЕГДА UTC!)

```python
from datetime import datetime, timedelta

# ✅ ПРАВИЛЬНО
created_at = datetime.utcnow()
expires_at = datetime.utcnow() + timedelta(hours=1)

# ❌ НЕПРАВИЛЬНО
created_at = datetime.now()  # НЕТ! Только utcnow()
```

# CI/CD Pipeline

## Workflows (GitHub Actions)

1. **ci.yml** - тесты (pytest + PostgreSQL service)
2. **lint.yml** - форматирование (black, isort, flake8)
3. **docker-publish.yml** - Docker builds → GHCR (amd64 + arm64)
4. **security.yml** - безопасность (safety, bandit, CodeQL)

## Перед коммитом

```bash
# Форматирование
black --line-length 120 app/
isort --profile black app/

# Проверка
black --check --line-length 120 app/
isort --check --profile black app/
flake8 app/

# Тесты
pytest tests/ -v
```

## Conventional Commits

```
feat: Add new command
fix: Fix bug in handler
docs: Update README
style: Apply black formatting
refactor: Extract service logic
test: Add test for decorator
chore: Update dependencies
ci: Update workflow
```

# Git Workflow

## Squashing commits (clean history)

После серии фиксов:
```bash
git reset --soft HEAD~N    # N = количество коммитов
git commit -m "fix: Comprehensive fix description"
git push origin master --force-with-lease
```

## Release process

1. Update `app/__version__.py`: `"1.2.0"`
2. Update `CHANGELOG.md`:
   ```markdown
   ## [1.2.0] - 2025-10-15

   ### Added
   - Feature

   ### Changed
   - Change

   ### Fixed
   - Fix
   ```
3. Commit: `git commit -m "chore: Release v1.2.0"`
4. Tag: `git tag v1.2.0 && git push origin v1.2.0`
5. GitHub Actions автоматически создаст Docker image
6. Создай GitHub Release с выдержкой из CHANGELOG

# Текущий статус проекта

## ✅ Реализовано (v1.1.0)

- Job system (6 профессий, 10 уровней, повышения, кулдауны)
- Interpol fines (штрафы, бонусы, per-victim cooldowns)
- Marriage system (propose, marriage menu, gift, divorce, makelove, date, cheat)
- Economic system (diamonds, balance, transfers)
- Admin commands (/reset_cd)
- CI/CD pipeline (все workflows работают)
- Multi-platform Docker images на GHCR
- Kubernetes deployment manifests
- Strong UX writing (WRITING_STYLE.md)
- Security policy (SECURITY.md)

## 🚧 В разработке (из README)

- **Дети** - возраст, кормление, образование, работа
  - Сейчас /makelove инкрементит love_count, но детей нет
  - Нужна модель Child, миграция, команды
- **Дома** - защита от похищений
  - Модель Kidnapping есть, но функционал не реализован
- **Бизнесы** - пассивный доход
  - APScheduler готов, нужна логика выплат
- **Казино** - Telegram Dice API

## CI Status

- ✅ Tests passing (pytest + PostgreSQL)
- ✅ Lint passing (black, isort, flake8)
- ✅ Docker builds (amd64, arm64)
- ⚠️ Security (gitleaks removed, safety/bandit/CodeQL working)

# Common Pitfalls (НЕ ДЕЛАЙ!)

❌ **DON'T**:
- Use `datetime.now()` → use `datetime.utcnow()`
- Write "Вы" → use "ты"
- Add emoji to diamond counts → use `format_diamonds()`
- Write Selfmade trap to CHANGELOG → it's a SECRET
- Use magic numbers → use constants from constants.py
- Commit without formatting → run black + isort
- Use manual session management → use `with get_db()`
- Write long texts → follow WRITING_STYLE.md
- Use Markdown → use HTML parse_mode

✅ **DO**:
- Read CLAUDE.md and WRITING_STYLE.md first
- Use context managers for DB (`with get_db()`)
- Apply decorators (@require_registered, @admin_only, etc.)
- Write tests for critical logic
- Log errors with structlog
- Use type hints
- Keep handlers thin, logic in services/
- Handle Telegram API errors gracefully
- Run CI checks locally before push
- Follow conventional commits format
- Squash commits when needed
- Update CHANGELOG.md for releases

# Environment Variables

```bash
TELEGRAM_BOT_TOKEN=<token from @BotFather>
DATABASE_URL=postgresql://user:pass@host:5432/wedding_bot
ADMIN_USER_ID=710573786
TZ=Europe/Moscow
LOG_LEVEL=INFO
DEBUG_CHAT_ID=-1003172144355  # Отправляет version + changelog при старте
```

# Полезные команды

## Development
```bash
# Start bot locally
python -m app.main

# Run tests
pytest tests/ -v --cov=app

# Format code
black --line-length 120 app/
isort --profile black app/

# Check formatting
black --check --line-length 120 app/
isort --check --profile black app/
flake8 app/
```

## Database
```bash
# Run migrations
alembic upgrade head

# Create migration
alembic revision --autogenerate -m "description"

# Rollback
alembic downgrade -1
```

## Docker
```bash
# Build
docker build -t wedding-bot -f deployments/Dockerfile .

# Run with compose
docker-compose -f deployments/docker-compose.yml up -d

# Logs
docker-compose logs -f bot

# Pull from GHCR
docker pull ghcr.io/digitaldrugstech/wedding-telegram-bot:latest
```

## Kubernetes
```bash
# Deploy
kubectl apply -f deployments/k8s/

# Status
kubectl -n dev-backend-services get pods

# Logs
kubectl -n dev-backend-services logs -f deployment/wedding-bot
```

# Следующие шаги (идеи)

1. **Children system** - самая ожидаемая фича
   - Модель Child (parent1_id, parent2_id, name, age, etc.)
   - Команды: /children, /feed, /educate
   - Автоматическое старение (APScheduler)
   - Миграция + тесты

2. **Business system**
   - Модель Business (owner_id, type, level, income)
   - Команды: /business, /buy_business, /upgrade
   - Weekly payouts (APScheduler, пятница 18:00 MSK)
   - Миграция + тесты

3. **Casino**
   - Команды: /casino, /dice
   - Telegram Dice API integration
   - Betting system

4. **More tests**
   - Expand test coverage (currently minimal)
   - Test marriage system
   - Test job promotions
   - Test interpol mechanics

5. **More admin commands**
   - /ban, /unban
   - /give_diamonds
   - /set_level
   - /stats (global statistics)

# ВАЖНО: Начало работы

Когда начинаешь работу:

1. **cd /home/haffk/prdx/workspace/wedding-telegram-bot**
2. **Прочитай** CLAUDE.md (технический контекст)
3. **Прочитай** WRITING_STYLE.md (стиль текстов)
4. **Проверь** текущий статус:
   ```bash
   git status
   git log --oneline -5
   gh run list --limit 3  # CI status
   ```
5. **Если пишешь код**:
   - Следуй архитектуре (handlers → services → models)
   - Используй декораторы
   - Пиши тесты
   - Форматируй код (black + isort)
   - Коммить с conventional commits
6. **Если пишешь тексты**:
   - Следуй WRITING_STYLE.md
   - Всегда "ты"
   - Краткость
   - HTML, не Markdown

Удачи в разработке! 🚀
```

---

## Быстрая проверка понимания

После прочтения этого промпта, ты должен знать:

- ✅ Где находится проект и какая текущая версия
- ✅ Какой стек технологий используется
- ✅ Как устроена архитектура (handlers → services → models)
- ✅ Какие модели БД существуют и зачем
- ✅ Как работает job system (профессии, зарплаты, кулдауны, повышения)
- ✅ Как работает marriage system (все команды и механики)
- ✅ Что такое Selfmade easter egg и почему это СЕКРЕТ
- ✅ Как писать тексты (WRITING_STYLE.md - краткость, "ты", эмодзи, HTML)
- ✅ Какие декораторы использовать и зачем
- ✅ Почему ВСЕГДА `datetime.utcnow()`, а не `datetime.now()`
- ✅ Как форматировать код (black 120, isort profile=black)
- ✅ Как работает CI/CD pipeline
- ✅ Как делать коммиты (conventional commits) и релизы
- ✅ Что реализовано и что в разработке
- ✅ С чего начать работу (читать CLAUDE.md и WRITING_STYLE.md)

Если всё понятно - приступай к разработке! 🎯
