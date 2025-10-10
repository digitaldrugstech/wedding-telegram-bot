# Wedding Telegram Bot

Telegram bot для симуляции семейной жизни с упором на работу, брак, детей и экономику.

## Features

- 🏢 **5 профессий** с 6 уровнями каждая (Interpol, Banker, Infrastructure, Court, Culture)
- 💍 **Система браков** с детьми и семьями
- 👶 **Дети** с возрастами, кормлением, образованием и работой
- 🏠 **Дома** с защитой от похищений
- 💼 **Бизнесы** с пассивным доходом
- 🎰 **Казино** с Telegram Dice API
- 👨‍💼 **Админ-панель** для управления ботом

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
ADMIN_USER_ID=710573786
TZ=Europe/Moscow
BUSINESS_PAYOUT_DAY=4  # Friday
BUSINESS_PAYOUT_HOUR=18
BUSINESS_PAYOUT_MINUTE=0
```

## Commands

User commands:
- `/start` - Начать работу с ботом
- `/profile` - Показать профиль
- `/work` - Меню управления работой
- `/job` - Работать (получить зарплату)
- `/propose` - Предложить брак
- `/marriage` - Меню брака и семьи
- `/family` - Меню семьи и детей
- `/house` - Меню покупки и продажи дома
- `/business` - Меню бизнесов
- `/casino` - Играть в казино
- `/balance` - Показать баланс алмазов
- `/help` - Справка по командам

Admin commands (only for user_id: 710573786 in DM):
- `/admin` - Админ-панель
- `/stats` - Статистика бота
- `/user_info` - Информация о пользователе
- `/give` - Выдать алмазы
- `/take` - Забрать алмазы
- `/ban` / `/unban` - Блокировка пользователей
- `/broadcast` - Отправить сообщение всем
- `/maintenance` - Режим обслуживания

## Contributing

See [REQUIREMENTS.md](REQUIREMENTS.md) for detailed technical requirements.

Development process:
1. Create feature branch from `main`
2. Implement feature according to issues
3. Write tests
4. Create pull request

## License

Private project.
