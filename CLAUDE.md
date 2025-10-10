# Wedding Telegram Bot - Claude Code Context

## Project Overview
Telegram bot для симуляции семейной жизни на игровом сервере. Боты на Python 3.11+ с async/await, PostgreSQL, SQLAlchemy 2.0, python-telegram-bot 20.7.

## Key Technologies
- **Framework**: python-telegram-bot 20.7 (async)
- **Database**: PostgreSQL + SQLAlchemy 2.0 ORM
- **Migrations**: Alembic
- **Logging**: structlog (JSON)
- **Scheduler**: APScheduler
- **Code Quality**: black (120 chars), isort, flake8, pre-commit hooks

## Project Structure
```
wedding-telegram-bot/
├── app/
│   ├── __version__.py          # Version: "0.1.2"
│   ├── main.py                 # Entry point
│   ├── bot.py                  # Bot initialization
│   ├── config.py               # Config dataclass
│   ├── database/
│   │   ├── models.py           # SQLAlchemy models
│   │   └── connection.py       # DB session management
│   ├── handlers/
│   │   ├── start.py            # /start, /profile
│   │   ├── work.py             # /work, /job (job system)
│   │   ├── admin.py            # Admin commands
│   │   ├── utils.py            # /balance, /help
│   │   └── menu.py             # Menu handlers
│   ├── utils/
│   │   ├── decorators.py       # @require_registered, @admin_only, @cooldown, @button_owner_only
│   │   └── keyboards.py        # Inline keyboards
│   └── services/               # Business logic
├── alembic/                    # Database migrations
│   └── versions/
│       ├── 001_expand_job_levels.py
│       └── 002_interpol_fines.py
├── deployments/
│   ├── Dockerfile
│   └── docker-compose.yml
├── CHANGELOG.md                # Version history
├── requirements.txt
└── .env.example
```

## Environment Variables
```bash
TELEGRAM_BOT_TOKEN=         # Required
DATABASE_URL=               # postgresql://user:pass@host:port/db
ADMIN_USER_ID=710573786     # Admin Telegram ID
TZ=Europe/Moscow
LOG_LEVEL=INFO
```

## Database Models

### User
- `telegram_id` (PK): BigInteger
- `username`: String(255)
- `gender`: 'male' | 'female'
- `balance`: BigInteger (алмазы)
- `is_banned`: Boolean
- `created_at`, `updated_at`: DateTime

### Job
- `user_id` (FK to User, unique)
- `job_type`: 'interpol' | 'banker' | 'infrastructure' | 'court' | 'culture' | 'selfmade'
- `job_level`: 1-10 (1-6 for selfmade)
- `times_worked`: Integer
- `last_work_time`: DateTime

### InterpolFine
- `interpol_id`, `victim_id` (FK to User)
- `fine_amount`, `bonus_amount`: Integer
- `created_at`: DateTime
- Index: (interpol_id, victim_id, created_at)

### Cooldown
- `user_id` (FK), `action`: String
- `expires_at`: DateTime
- Unique: (user_id, action)

## Job System

### Professions (10 levels each, except Selfmade = 6)
- **Интерпол (interpol)**: Штрафует игроков
- **Банкир (banker)**: Экономика
- **Инфраструктура (infrastructure)**: Строительство
- **Суд (court)**: Рассмотрение дел
- **Культура (culture)**: Ивенты
- **Селфмейд (selfmade)**: 6 уровней, trap на 7

### Salary Ranges (алмазы)
```python
SALARY_RANGES = {
    1: (10, 20), 2: (20, 35), 3: (35, 55), 4: (55, 85), 5: (85, 130),
    6: (130, 200), 7: (200, 300), 8: (300, 450), 9: (450, 650), 10: (650, 1000)
}
SELFMADE_SALARY_RANGES = {1: (5, 10), 2: (8, 15), 3: (12, 20), 4: (18, 30), 5: (25, 40), 6: (35, 55)}
```

### Cooldowns (hours)
```python
COOLDOWN_BY_LEVEL = {1: 1, 2: 1, 3: 1.5, 4: 1.5, 5: 2, 6: 2, 7: 3, 8: 3, 9: 4, 10: 4}
SELFMADE_COOLDOWN = 0.5  # 30 min
```

### Promotion System
- **Random chance**: 5% (lvl 1) → 1.5% (lvl 10)
- **Guaranteed**: after 20-60 works (depends on level)

### Interpol Special Mechanics
- **With reply** (`/job` reply to message): Fine player
  - Fine = victim's ~one salary (based on their job level)
  - Bonus "за говновызов": +50% if interpol higher level
  - Cooldown: 1 hour per victim
  - Protection: victim must have ≥50 алмазов
- **Without reply** (`/job`): Patrol work (охрана ивента)
  - Normal salary + hint: "💡 Чтобы выписать штраф, зареплай на сообщение с /job"

### Selfmade Easter Egg (SECRET - не писать в CHANGELOG!)
- **Level 6→7 promotion**: Обнуляет баланс, сбрасывает на уровень 1 "нищий"
- Message: "🎰 ВАС НАЕБАЛИ ДРУЗЬЯ НА КАЗИНО !"

## Russian Language Rules

### Word Endings (алмазы)
```python
def format_diamonds(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11: return f"{count} алмаз"
    elif count % 10 in (2,3,4) and count % 100 not in (12,13,14): return f"{count} алмаза"
    else: return f"{count} алмазов"
```

### Tone & Style
- **Всегда "ты"**, никогда "вы/Вы"
- Короткие, ясные тексты (UX writing principles)
- Эмодзи для визуального разделения
- Дружелюбный тон, не канцелярщина

## Important Patterns

### Context Manager for DB
```python
with get_db() as db:
    user = db.query(User).filter(User.telegram_id == user_id).first()
    user.balance += 100
    # Auto-commit on exit, rollback on exception
```

### Decorators
- `@require_registered` - проверка регистрации и бана
- `@admin_only` - доступ только админу (любой чат)
- `@admin_only_private` - доступ только админу (только ЛС)
- `@button_owner_only` - кнопки только для владельца (callback_data: "action:param:user_id")
- `@cooldown(action, seconds)` - автоматический кулдаун

### Callback Data Security
Формат: `"action:param:user_id"` - user_id в конце для защиты кнопок

### Datetime
**ALWAYS USE** `datetime.utcnow()` (UTC timezone everywhere)

## Code Style

### Line Length
120 characters (black --line-length 120)

### Imports Order (isort)
1. Standard library
2. Third-party (telegram, sqlalchemy, etc.)
3. Local (app.*)

### Error Handling
```python
try:
    # risky operation
except SpecificException as e:
    logger.error("description", error=str(e), exc_info=True)
    await update.message.reply_text("Понятное сообщение пользователю")
```

## Deployment

### Docker
```bash
docker-compose up -d          # Start
docker-compose logs -f bot    # Logs
docker-compose down           # Stop
```

### Migrations
```bash
alembic upgrade head          # Apply migrations
alembic revision -m "desc"    # Create migration
```

### Pre-commit
```bash
pre-commit run --all-files    # Manual check
git commit                    # Auto-runs hooks
```

## Admin Commands

- `/reset_cd` (reply to user) - сбросить кулдаун (работает в любом чате)

## Debug

- **Debug chat ID**: -1003172144355
- Sends version + changelog on startup

## Version Management

1. Update `app/__version__.py`
2. Add entry to `CHANGELOG.md` (format: ## [X.Y.Z] - YYYY-MM-DD)
3. Commit changes
4. Deploy

## Common Pitfalls

❌ **DON'T**:
- Use `datetime.now()` (use `utcnow()`)
- Write "Вы" instead of "ты"
- Add emojis to diamond counts (use `format_diamonds()`)
- Commit without pre-commit hooks
- Write Selfmade trap to CHANGELOG
- Use magic numbers for IDs/constants
- Forget to validate user input

✅ **DO**:
- Use context managers for DB
- Apply decorators for common checks
- Write tests for critical logic
- Log errors with structlog
- Use type hints
- Keep handlers thin, logic in services/
- Handle Telegram API errors gracefully

## Testing

```bash
pytest tests/                 # Run all tests
pytest -v                     # Verbose
pytest --cov=app             # Coverage
```

## Current Version
**0.1.2** - Interpol fines mechanics, алмазы with proper endings, improved UX texts
