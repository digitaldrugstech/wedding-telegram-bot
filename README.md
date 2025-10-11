# Wedding Telegram Bot

[![CI](https://github.com/digitaldrugstech/wedding-telegram-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/digitaldrugstech/wedding-telegram-bot/actions/workflows/ci.yml)
[![Docker](https://github.com/digitaldrugstech/wedding-telegram-bot/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/digitaldrugstech/wedding-telegram-bot/actions/workflows/docker-publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Telegram bot для симуляции семейной жизни с упором на работу, брак и экономику.

## Features

### ✅ Реализовано (v1.1.0)

- 🏢 **6 профессий** с 10 уровнями (Interpol, Banker, Infrastructure, Court, Culture, Selfmade)
- 💍 **Система браков** (propose, gift, divorce)
- ❤️ **Взаимодействия**: /makelove (зачатие), /date (свидание), /cheat (измена)
- 💰 **Экономика**: работа, зарплата, кулдауны
- 👨‍💼 **Админ-команды**: /reset_cd
- 📝 **Сильные тексты**: UX-оптимизированные сообщения
- 🔒 **Безопасность**: security scanning, dependency updates

### 🚧 В разработке

- 👶 **Дети**: возраст, кормление, образование, работа
- 🏠 **Дома**: защита от похищений
- 💼 **Бизнесы**: пассивный доход
- 🎰 **Казино**: Telegram Dice API

**Валюта:** Алмазы 💎

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** python-telegram-bot 20.x
- **Database:** PostgreSQL 15+
- **ORM:** SQLAlchemy 2.x
- **Migrations:** Alembic
- **Scheduler:** APScheduler
- **Logging:** structlog
- **Deployment:** Docker + Kubernetes

## Project Structure

```
wedding-telegram-bot/
├── app/
│   ├── main.py              # Entry point
│   ├── bot.py               # Bot initialization
│   ├── config.py            # Configuration
│   ├── database/            # Database models and connection
│   ├── handlers/            # Command handlers
│   ├── services/            # Business logic
│   ├── tasks/               # Scheduled tasks
│   └── utils/               # Utilities (decorators, keyboards)
├── tests/                   # Tests
├── deployments/             # Docker and K8s manifests
├── requirements.txt         # Python dependencies
└── alembic.ini             # Alembic configuration
```

## Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker (optional)

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/digitaldrugstech/wedding-telegram-bot.git
cd wedding-telegram-bot
```

2. Create virtual environment:
```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Setup environment variables:
```bash
cp .env.example .env
# Edit .env with your values
```

5. Run migrations:
```bash
alembic upgrade head
```

6. Start the bot:
```bash
python -m app.main
```

### Docker Development

```bash
docker-compose -f deployments/docker-compose.yml up
```

## Deployment

### Kubernetes

Deploy to K8s cluster:

```bash
kubectl apply -f deployments/k8s/
```

The bot will be deployed in `dev-backend-services` namespace.

## Environment Variables

Required environment variables:

```env
TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
DATABASE_URL=postgresql://user:pass@host:5432/wedding_bot
ADMIN_USER_ID=<your telegram user id>
TZ=Europe/Moscow
BUSINESS_PAYOUT_DAY=4  # Friday
BUSINESS_PAYOUT_HOUR=18
BUSINESS_PAYOUT_MINUTE=0
```

## Installation

### Using Docker (recommended)

Pull the latest image from GitHub Container Registry:

```bash
docker pull ghcr.io/digitaldrugstech/wedding-telegram-bot:latest
```

Or use docker-compose:

```bash
cd deployments
docker-compose up -d
```

### From Source

See [Development Setup](#development-setup) below.

## Commands

### User Commands

**Профиль и экономика:**
- `/profile` - Профиль
- `/balance` - Баланс алмазов
- `/help` - Справка

**Работа:**
- `/work` - Меню работы
- `/job` - Работать (или `/job @username` для Interpol)

**Брак:**
- `/propose` - Предложить брак (reply или `/propose @username`)
- `/marriage` - Меню брака
- `/gift [amount]` - Подарить алмазы супругу
- `/makelove` - Заняться любовью (шанс зачатия)
- `/date` - Свидание (10-50 алмазов)
- `/cheat` - Измена (reply или `/cheat @username`, риск 30%)

### Admin Commands

Admin access configured via `ADMIN_USER_ID` environment variable:

- `/reset_cd` - Сбросить кулдаун (reply на пользователя)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

Quick start:
1. Fork the repository
2. Create feature branch from `master`
3. Follow the coding standards (pre-commit hooks will help)
4. Write tests for new functionality
5. Create a pull request

See [REQUIREMENTS.md](REQUIREMENTS.md) for detailed technical requirements.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- Create an [Issue](https://github.com/digitaldrugstech/wedding-telegram-bot/issues) for bugs or feature requests
- Join [Discussions](https://github.com/digitaldrugstech/wedding-telegram-bot/discussions) for questions

## Acknowledgments

Built with:
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
- [SQLAlchemy](https://www.sqlalchemy.org/) - SQL toolkit and ORM
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [APScheduler](https://apscheduler.readthedocs.io/) - Task scheduling
