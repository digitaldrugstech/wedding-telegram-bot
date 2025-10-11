# Wedding Telegram Bot - Claude Code Context

## Project Overview
Telegram bot для симуляции семейной жизни на игровом сервере. Боты на Python 3.11+ с async/await, PostgreSQL, SQLAlchemy 2.0, python-telegram-bot 20.7.

**Current Version**: v1.1.0 (2025-10-11)
**Repository**: https://github.com/digitaldrugstech/wedding-telegram-bot
**Docker Image**: ghcr.io/digitaldrugstech/wedding-telegram-bot:latest

## Key Technologies
- **Framework**: python-telegram-bot 20.7 (async)
- **Database**: PostgreSQL 15+ + SQLAlchemy 2.0 ORM
- **Migrations**: Alembic
- **Logging**: structlog (JSON)
- **Scheduler**: APScheduler
- **Code Quality**: black (120 chars), isort, flake8
- **CI/CD**: GitHub Actions (tests, lint, security, Docker builds)
- **Deployment**: Docker + Kubernetes, GHCR registry

## Project Structure
```
wedding-telegram-bot/
├── .github/workflows/          # CI/CD pipelines
│   ├── ci.yml                  # Tests (pytest + coverage)
│   ├── lint.yml                # Code quality (black, isort, flake8)
│   ├── docker-publish.yml      # Multi-platform Docker builds → GHCR
│   └── security.yml            # Security scanning (safety, bandit, CodeQL)
├── app/
│   ├── __version__.py          # Version: "1.1.0"
│   ├── main.py                 # Entry point
│   ├── bot.py                  # Bot initialization
│   ├── config.py               # Config dataclass
│   ├── constants.py            # Game constants (cooldowns, salaries, etc.)
│   ├── database/
│   │   ├── models.py           # SQLAlchemy models (User, Job, Marriage, etc.)
│   │   └── connection.py       # DB session management
│   ├── handlers/
│   │   ├── start.py            # /profile (registration merged into @require_registered)
│   │   ├── work.py             # /work, /job (job system)
│   │   ├── marriage.py         # /propose, /marriage, /gift, /makelove, /date, /cheat
│   │   ├── admin.py            # Admin commands
│   │   ├── utils.py            # /balance, /help
│   │   └── menu.py             # Inline menu callbacks
│   ├── services/
│   │   └── marriage_service.py # Marriage business logic
│   ├── utils/
│   │   ├── decorators.py       # @require_registered, @admin_only, @set_cooldown
│   │   ├── keyboards.py        # Inline keyboards
│   │   └── formatters.py       # format_diamonds()
│   └── tasks/                  # Scheduled tasks (future: business payouts)
├── alembic/                    # Database migrations
│   └── versions/
│       ├── 001_expand_job_levels.py
│       ├── 002_interpol_fines.py
│       └── 003_marriage_system.py
├── deployments/
│   ├── Dockerfile              # Multi-stage Docker build
│   ├── docker-compose.yml      # Local development
│   └── k8s/                    # Kubernetes manifests
├── tests/
│   └── test_decorators.py
├── .isort.cfg                  # isort configuration (profile=black)
├── CHANGELOG.md                # Version history
├── CLAUDE.md                   # This file - context for AI
├── WRITING_STYLE.md            # Text writing guidelines
├── SECURITY.md                 # Security policy
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

### Marriage (NEW in v1.1.0)
- `partner1_id`, `partner2_id` (FK to User)
- `is_active`: Boolean
- `married_at`: DateTime
- `divorced_at`: DateTime (nullable)
- `love_count`: Integer (times made love)
- Indexes: (partner1_id, is_active), (partner2_id, is_active)

### Kidnapping (NEW in v1.1.0)
- `kidnapper_id`, `victim_id`, `owner_id` (FK to User)
- `is_active`: Boolean
- `kidnapped_at`, `released_at`: DateTime
- Note: Planned feature, not implemented yet

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

## Marriage System (v1.1.0)

### Commands
- `/propose` (reply or `/propose @username`) - Предложение брака (50 💎)
- `/marriage` - Меню брака (gift, divorce, stats)
- `/gift [amount]` - Подарить алмазы супругу
- `/makelove` - Заняться любовью (24h cooldown, 10% шанс зачатия)
- `/date` - Свидание (12h cooldown, 10-50 💎 cost)
- `/cheat` (reply or `/cheat @username`) - Измена (30% риск развода)

### Mechanics
- **Proposal**: Costs 50 💎, requires confirmation from both parties
- **Marriage**: Only one active marriage per person, stored in DB
- **Make Love**:
  - 24h cooldown
  - 10% chance of pregnancy (not implemented yet, just increments `love_count`)
  - Shows conception message but no actual child system yet
- **Date**: Random cost 10-50 💎, 12h cooldown, shows romantic message
- **Cheat**:
  - Target must not be spouse
  - 30% chance partner finds out → instant divorce
  - 70% success (just a message, no rewards)
- **Gift**: Transfer any amount of diamonds to spouse
- **Divorce**: Instant, free, both partners notified

### UI Integration
- Profile shows "💍 Брак" button if married
- Marriage menu: gift, divorce, stats buttons
- All buttons use `@button_owner_only` decorator for security

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

## CI/CD Pipeline

### GitHub Actions Workflows
1. **CI (ci.yml)** - Main tests
   - PostgreSQL service container
   - pytest with coverage (>80% target)
   - Runs on: push to master/dev, pull requests

2. **Lint (lint.yml)** - Code quality
   - black --check --line-length 120
   - isort --check --profile black
   - flake8 (E, W, F errors)
   - Runs on: push to master/dev, pull requests

3. **Docker (docker-publish.yml)** - Multi-platform builds
   - Builds for linux/amd64, linux/arm64
   - Pushes to ghcr.io/digitaldrugstech/wedding-telegram-bot
   - Tags: latest, v*, sha-*
   - Runs on: push to master/dev, releases

4. **Security (security.yml)**
   - safety (Python dependency vulnerabilities)
   - bandit (Python security linting)
   - CodeQL (GitHub advanced security)
   - Runs on: push to master, schedule (weekly)

### Deployment

#### Docker (Production)
```bash
docker pull ghcr.io/digitaldrugstech/wedding-telegram-bot:latest
docker-compose -f deployments/docker-compose.prod.yml up -d
docker-compose logs -f bot
```

#### Local Development
```bash
docker-compose -f deployments/docker-compose.yml up -d  # Start
docker-compose logs -f bot                              # Logs
docker-compose down                                     # Stop
```

#### Kubernetes
```bash
kubectl apply -f deployments/k8s/
kubectl -n dev-backend-services get pods
kubectl -n dev-backend-services logs -f deployment/wedding-bot
```

### Database Migrations
```bash
alembic upgrade head          # Apply migrations
alembic revision -m "desc"    # Create migration
alembic downgrade -1          # Rollback last migration
```

### Code Quality Tools
```bash
# Format code
black --line-length 120 app/
isort --profile black app/

# Check formatting
black --check --line-length 120 app/
isort --check --profile black app/
flake8 app/

# Run tests
pytest tests/ -v
pytest --cov=app --cov-report=html
```

## Admin Commands

- `/reset_cd` (reply to user) - сбросить кулдаун (работает в любом чате)

## Debug

- **Debug chat ID**: -1003172144355
- Sends version + changelog on startup

## Git Workflow

### Branch Strategy
- **master** - production-ready code
- **dev** - development branch (optional)
- **feature/** - feature branches (merge to master via PR)

### Commit Messages (Conventional Commits)
```
feat: Add marriage proposal system
fix: Fix cooldown check in /job command
docs: Update README with marriage commands
style: Apply black and isort formatting
refactor: Extract marriage logic to service
test: Add tests for marriage proposal
chore: Update dependencies
ci: Add Docker multi-platform builds
```

### Release Process
1. Update `app/__version__.py` (e.g., "1.2.0")
2. Update `CHANGELOG.md`:
   ```markdown
   ## [1.2.0] - 2025-10-15

   ### Added
   - Feature description

   ### Changed
   - Change description

   ### Fixed
   - Fix description
   ```
3. Commit: `git commit -m "chore: Release v1.2.0"`
4. Tag: `git tag v1.2.0 && git push origin v1.2.0`
5. GitHub Actions auto-builds and publishes Docker image
6. Create GitHub Release with CHANGELOG excerpt

### Squashing Commits
When cleaning up commit history:
```bash
git reset --soft HEAD~N    # N = number of commits to squash
git commit -m "message"
git push origin master --force-with-lease
```

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
pytest --cov=app --cov-report=html  # HTML coverage report
```

## Current Version & Status

**v1.1.0** (2025-10-11)

### Implemented Features
✅ Job system (6 professions, 10 levels, promotions, cooldowns)
✅ Interpol fines with bonus mechanics
✅ Marriage system (propose, gift, divorce, makelove, date, cheat)
✅ Economic system (diamonds, balance, transfers)
✅ Admin commands (/reset_cd)
✅ CI/CD pipeline (tests, lint, Docker, security)
✅ Multi-platform Docker images on GHCR
✅ Kubernetes deployment manifests
✅ Strong UX writing (WRITING_STYLE.md)
✅ Security policy (SECURITY.md)

### In Development (from README)
🚧 Children system (age, feeding, education, work)
🚧 Houses (protection from kidnapping)
🚧 Businesses (passive income)
🚧 Casino (Telegram Dice API)

### CI Status
- ✅ Tests passing (pytest + PostgreSQL)
- ✅ Lint passing (black, isort, flake8)
- ✅ Docker builds (amd64, arm64)
- ⚠️ Security scan (gitleaks removed, bandit/safety/CodeQL working)

### Next Steps (ideas)
- Implement children system with pregnancy from /makelove
- Add business system with weekly payouts (APScheduler)
- Create casino commands using Telegram Dice API
- Add house purchase and kidnapping protection
- Expand test coverage (currently minimal)
- Add more admin commands (ban, give_diamonds, etc.)
