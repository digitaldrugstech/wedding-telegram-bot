# Wedding Telegram Bot - Technical Requirements

## Overview
Telegram bot для симуляции семейной жизни с упором на работу, брак, детей и экономику. Минималистичный интерфейс с максимальным использованием inline кнопок вместо команд.

**Валюта:** Алмазы 💎

---

## Core Features

### 1. User Registration & Profile

**Команды:**
- `/start` - начать работу с ботом
  - Показывает приветствие
  - Кнопки выбора пола: "Мужчина ♂️" / "Женщина ♀️"

- `/profile` - профиль пользователя
  - Показывает: имя (username), пол, баланс, работу, брак, детей
  - Кнопки быстрого доступа к `/work`, `/marriage`, `/family`

**Данные:**
- telegram_id (primary key)
- username
- gender (male/female)
- balance (алмазы)
- created_at, updated_at

---

### 2. Economy & Jobs System

**5 профессий (по 6 уровней каждая):**

#### 2.1 Интерпол
- Уровни: Стажер → Сотрудник интерпола → Дежурный интерполенок → Инспектор → Зам главы интерпола → Глава интерпола
- **Механика:** `/job` @username - штрафуешь игрока, получаешь алмазы с его баланса
- **Штрафы:** 10-20 💎 (ур.1) → 400-720 💎 (ур.6)
- **Защита:** можно штрафовать одного игрока раз в час, нельзя штрафовать с балансом < 50 💎

#### 2.2 Банкир
- Уровни: Стажер → Бухгалтер банка → Банкир → Зам главного банкира → Главный банкир → Глава экономики
- **Механика:** `/job` - "Обслужил 15-30 человек, комиссия: X 💎"

#### 2.3 Инфраструктура
- Уровни: Сборщик ресурсов → Строитель → Хранитель → Главный по спавну → Зам главы инфраструктуры → Глава инфраструктуры
- **Механика:** `/job` - "Собрал 20-40 ресурсов, комиссия: X 💎"

#### 2.4 Суд
- Уровни: Стажер → Помощник судьи → Судья → Старший судья → Зам главного судьи → Главный судья
- **Механика:** `/job` - "Рассмотрел 3-8 дел, гонорар: X 💎"

#### 2.5 Культура
- Уровни: Стажер → Ивентмейкер → Организатор мероприятий → Главный ивентмейкер → Зам главы культуры → Глава культуры
- **Механика:** `/job` - "Выполнил 2-5 ивентов, гонорар: X 💎"

**Зарплаты по уровням (диапазон):**
| Уровень | Зарплата |
|---------|----------|
| 1 | 10-20 💎 |
| 2 | 25-40 💎 |
| 3 | 50-80 💎 |
| 4 | 100-160 💎 |
| 5 | 200-320 💎 |
| 6 | 400-640 💎 |

**Система повышений:**
- Шанс повышения зависит от уровня: 5% → 2%
- Гарантированное повышение каждые 20-40 работ (зависит от уровня)
- При смене профессии: переходишь на 1-2 ранга ниже текущего уровня

**Команды:**
- `/work` - меню работы (inline кнопки)
  - Кнопки: "Выбрать профессию", "Работать", "Уволиться", "Моя работа"
- `/job` - быстрая работа (без меню)
  - Для Интерпола: `/job` @username
  - Для остальных: просто `/job`

**Ограничения:**
- Кулдаун между работами: **4 часа**

**Данные (таблица jobs):**
- user_id (FK)
- job_type (interpol, banker, infrastructure, court, culture)
- job_level (1-6)
- times_worked (счётчик для гарантированного повышения)
- last_work_time
- created_at

---

### 3. Marriage System

**Команды:**
- `/propose` - предложить брак (ответом на сообщение)
  - **Требования:** 100 💎 у каждого
  - Второй игрок подтверждает кнопкой "Принять 💍" / "Отказать ❌"
  - При согласии списывается по 100 💎 у обоих

- `/marriage` - меню брака (inline кнопки)
  - Кнопки: "Брачная ночь 🌙", "Изменить 💔", "Свидание ❤️", "Развестись", "Семья", "Бюджет", "Фамилия"

**Брачная ночь:**
- Кнопка "Брачная ночь 🌙" (или `/make_love`)
- **Требования:** дом + оба работают + разные профессии
- **Шанс зачатия:** 10%
- **Кулдаун:** 12 часов

**Измена:**
- Кнопка "Изменить 💔" → выбор пользователя (или `/cheat` @username)
- Брак немедленно распадается
- Уведомление супругу

**Свидание:**
- Кнопка "Свидание ❤️"
- **Стоимость:** 200 💎 (платит инициатор)
- **Кулдаун:** 24 часа
- Просто флейвор

**Развод:**
- Кнопка "Развестись"
- Подтверждение кнопкой (без согласия супруга)

**Фамилия:**
- Кнопка "Фамилия" → ввод текста
- Может установить любой из супругов

**Инфо:**
- Показывает супругов, фамилию, дату брака, детей

**Бюджет:**
- Показывает сумму алмазов обоих супругов

**Family система (расширенная семья):**
- Кнопка "Семья" → "Пригласить", "Участники", "Исключить"
- `/family` @username - пригласить в семью (только супруги)
- `/leave_family` - покинуть семью
- `/kickf` @username - исключить

**Данные (таблица marriages):**
- id (PK)
- partner1_id (FK users)
- partner2_id (FK users)
- family_name
- is_active
- created_at, ended_at

**Данные (таблица family_members):**
- marriage_id (FK)
- user_id (FK)
- joined_at

---

### 4. Housing System

**Дома:**
| Дом | Цена | Защита от похищения |
|-----|------|---------------------|
| Хибара | 1,000 💎 | -2% |
| Деревянный домик | 5,000 💎 | -4% |
| Каменный дом | 20,000 💎 | -6% |
| Коттедж | 100,000 💎 | -8% |
| Особняк | 500,000 💎 | -9% |
| Замок | 2,000,000 💎 | -9.5% |

**Команды:**
- `/house` - меню дома (inline кнопки)
  - Кнопки: "Купить дом", "Продать дом", "Мой дом"
  - Покупка: список домов кнопками
  - Продажа: возврат 70% стоимости

**Механика:**
- Дом покупает семья (общая собственность супругов)
- Дом требуется для рождения детей
- Дом снижает шанс похищения ребёнка

**Данные (таблица houses):**
- id (PK)
- marriage_id (FK)
- house_type (1-6)
- purchase_price
- purchased_at

---

### 5. Children System

**Рождение детей:**

**Естественное зачатие:**
- Через `/marriage` → "Брачная ночь 🌙"
- **Шанс:** 10%
- **Требования:** дом + оба работают + разные профессии
- Рождение мгновенное (без беременности)

**ЭКО:**
- Через `/family` → "Родить ребёнка" → "ЭКО"
- **Стоимость:** 5,000 💎
- **Гарантия:** 100% зачатие
- **Требования:** те же

**Усыновление:**
- Через `/family` → "Родить ребёнка" → "Усыновить"
- **Стоимость:** 500 💎
- **Требования:** те же

**Возраста детей:**
1. **Младенец** (0-5 лет) - только кормить
2. **Ребёнок** (6-14 лет) - кормить + школа
3. **Подросток** (15-18 лет) - кормить + школа + работа

**Управление детьми:**
- `/family` - меню семьи
  - Кнопки: "Список детей", "Родить ребёнка", "Покормить всех", "Вырастить всех", "Няня"
  - Выбор ребёнка → кнопки: "Покормить", "Вырастить", "Имя", "Работа", "Школа", "Инфо", "Приют"

**Кормление:**
- **Стоимость:** 50 💎 за ребёнка
- **Частота:** раз в 3 дня
- Если не кормить 5 дней → ребёнок умирает

**Взросление:**
- Младенец → Ребёнок: 1,000 💎
- Ребёнок → Подросток: 2,000 💎

**Образование:**
- Доступно: Ребёнок и Подросток
- **Стоимость:** 500 💎/месяц
- **Бонус:** +50% к доходу от работы ребёнка

**Работа детей:**
- Доступно: только Подростки
- **Доход:** 30-60 💎
- **Кулдаун:** 24 часа

**Няня:**
- **Стоимость:** 1,000 💎/неделя
- **Эффект:** автоматически кормит всех детей каждые 3 дня

**Аборт/Приют:**
- Аборт: 1,000 💎 (если беременна)
- Приют: бесплатно (отказ от ребёнка)

**Похищение детей:**
- Через меню ребёнка → "Похитить"
- `/kidnap_child` @username - украсть случайного ребёнка у пользователя
- **Шанс:** 10% - бонус дома жертвы
- Похититель устанавливает выкуп
- `/release_child` - вернуть после выкупа

**Данные (таблица children):**
- id (PK)
- parent1_id (FK users)
- parent2_id (FK users)
- name
- gender (male/female)
- age_stage (infant/child/teen)
- last_fed_at
- is_in_school (boolean)
- school_expires_at
- last_work_time
- is_alive
- created_at

**Данные (таблица kidnappings):**
- id (PK)
- child_id (FK)
- kidnapper_id (FK users)
- victim_id (FK users)
- ransom_amount
- is_active
- created_at

---

### 6. Business System (Passive Income)

**Типы бизнесов (окупаемость 1 неделя):**

| Бизнес | Цена | Доход/неделю |
|--------|------|--------------|
| Палатка на рынке | 1,000 💎 | 1,000 💎 |
| Магазин на спавне | 5,000 💎 | 5,000 💎 |
| Филиал банка | 25,000 💎 | 25,000 💎 |
| Свой город | 150,000 💎 | 150,000 💎 |

**Механика:**
- Можно владеть несколькими бизнесами (макс 3 каждого типа)
- Доход приходит **раз в неделю** (пятница 18:00 МСК)
- Продажа: возврат 70% стоимости

**Команды:**
- `/business` - меню бизнеса (inline кнопки)
  - Кнопки: "Мои бизнесы", "Купить", "Продать"

**Данные (таблица businesses):**
- id (PK)
- user_id (FK)
- business_type (1-4)
- purchase_price
- purchased_at
- last_payout_at

---

### 7. Casino

**Команда:**
- `/casino` [ставка] - играть в казино
  - Дефолтная ставка: 10 💎

**Механика:**
- Использует Telegram Dice API (🎰)
- **Выплаты:**
  - Разные символы: проигрыш
  - 3 одинаковых: ставка × 10
  - Джекпот: ставка × 50

**Ограничения:**
- Минимальная ставка: 10 💎
- Максимальная ставка: 1,000 💎
- **Кулдаун:** 1 минута

**Данные (таблица casino_games):**
- id (PK)
- user_id (FK)
- bet_amount
- result (win/loss)
- payout
- played_at

---

### 8. Utility Commands

**Команды:**
- `/balance` - показать баланс алмазов
- `/help` - справка по командам
- `/rbudget` @username [сумма] - передать алмазы
  - **Ограничение:** оба не в чужих семьях или в одной семье

---

### 9. Admin Commands (для user_id: 710573786)

**Команды в ЛС бота:**
- `/admin` - админ-панель (inline кнопки)
  - "Статистика", "Управление пользователями", "Управление экономикой", "Системные команды"

**Статистика:**
- `/stats` - общая статистика бота
  - Количество пользователей
  - Количество браков
  - Количество детей
  - Общая сумма алмазов в экономике
  - Активные бизнесы

**Управление пользователями:**
- `/user_info` [telegram_id] - полная инфо о пользователе
- `/give` [telegram_id] [amount] - выдать алмазы
- `/take` [telegram_id] [amount] - забрать алмазы
- `/ban` [telegram_id] - заблокировать пользователя
- `/unban` [telegram_id] - разблокировать

**Управление экономикой:**
- `/set_salary` [job_type] [level] [min] [max] - изменить зарплату
- `/adjust_prices` - меню настройки цен (дома, бизнесы, услуги)

**Системные команды:**
- `/broadcast` [message] - отправить сообщение всем пользователям
- `/maintenance` [on/off] - режим обслуживания
- `/backup` - создать бэкап БД
- `/logs` - последние 50 строк логов

---

## Bot Commands List (for BotFather)

```
start - Начать работу с ботом
profile - Показать профиль
work - Меню управления работой
job - Работать (получить зарплату)
propose - Предложить брак
divorce - Развестись
marriage - Меню брака и семьи
family - Меню семьи и детей
house - Меню покупки и продажи дома
business - Меню бизнесов
casino - Играть в казино
balance - Показать баланс алмазов
help - Справка по командам
```

---

## Technical Architecture

### Technology Stack
- **Language:** Python 3.11+
- **Framework:** python-telegram-bot 20.x
- **Database:** PostgreSQL 15+
- **ORM:** SQLAlchemy 2.x
- **Migrations:** Alembic
- **Task Scheduler:** APScheduler (для weekly payouts)
- **Deployment:** Docker + Kubernetes
- **Secrets:** Vault (bot token, DB credentials)
- **Logging:** structlog (JSON format)

### Project Structure
```
wedding-telegram-bot/
├── app/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── bot.py               # Bot initialization
│   ├── config.py            # Configuration
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── connection.py    # DB connection
│   │   └── migrations/      # Alembic migrations
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py         # /start, /profile
│   │   ├── work.py          # /work, /job
│   │   ├── marriage.py      # /propose, /marriage
│   │   ├── family.py        # /family (children)
│   │   ├── house.py         # /house
│   │   ├── business.py      # /business
│   │   ├── casino.py        # /casino
│   │   ├── admin.py         # Admin commands
│   │   └── utils.py         # /balance, /help, /rbudget
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── job_service.py
│   │   ├── marriage_service.py
│   │   ├── children_service.py
│   │   ├── house_service.py
│   │   ├── business_service.py
│   │   └── economy_service.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── scheduler.py     # APScheduler setup
│   │   ├── weekly_payout.py # Business payouts (пятница 18:00)
│   │   └── child_hunger.py  # Check starving children
│   └── utils/
│       ├── __init__.py
│       ├── decorators.py    # @require_registered, @cooldown
│       └── keyboards.py     # Inline keyboard builders
├── tests/
│   └── ...
├── deployments/
│   ├── Dockerfile
│   ├── k8s/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── vault-secret.yaml
│   └── docker-compose.yml   # For local development
├── alembic.ini
├── requirements.txt
├── README.md
└── REQUIREMENTS.md
```

---

## Database Schema

### Tables

#### users
```sql
CREATE TABLE users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    gender VARCHAR(10) CHECK (gender IN ('male', 'female')),
    balance BIGINT DEFAULT 0,
    is_banned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### jobs
```sql
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    job_type VARCHAR(50) CHECK (job_type IN ('interpol', 'banker', 'infrastructure', 'court', 'culture')),
    job_level INT CHECK (job_level BETWEEN 1 AND 6),
    times_worked INT DEFAULT 0,
    last_work_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);
```

#### marriages
```sql
CREATE TABLE marriages (
    id SERIAL PRIMARY KEY,
    partner1_id BIGINT REFERENCES users(telegram_id),
    partner2_id BIGINT REFERENCES users(telegram_id),
    family_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    UNIQUE(partner1_id, partner2_id)
);
```

#### family_members
```sql
CREATE TABLE family_members (
    id SERIAL PRIMARY KEY,
    marriage_id INT REFERENCES marriages(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(telegram_id),
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(marriage_id, user_id)
);
```

#### houses
```sql
CREATE TABLE houses (
    id SERIAL PRIMARY KEY,
    marriage_id INT REFERENCES marriages(id) ON DELETE CASCADE,
    house_type INT CHECK (house_type BETWEEN 1 AND 6),
    purchase_price BIGINT,
    purchased_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(marriage_id)
);
```

#### children
```sql
CREATE TABLE children (
    id SERIAL PRIMARY KEY,
    parent1_id BIGINT REFERENCES users(telegram_id),
    parent2_id BIGINT REFERENCES users(telegram_id),
    name VARCHAR(255),
    gender VARCHAR(10) CHECK (gender IN ('male', 'female')),
    age_stage VARCHAR(20) CHECK (age_stage IN ('infant', 'child', 'teen')) DEFAULT 'infant',
    last_fed_at TIMESTAMP DEFAULT NOW(),
    is_in_school BOOLEAN DEFAULT FALSE,
    school_expires_at TIMESTAMP,
    last_work_time TIMESTAMP,
    is_alive BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### kidnappings
```sql
CREATE TABLE kidnappings (
    id SERIAL PRIMARY KEY,
    child_id INT REFERENCES children(id) ON DELETE CASCADE,
    kidnapper_id BIGINT REFERENCES users(telegram_id),
    victim_id BIGINT REFERENCES users(telegram_id),
    ransom_amount BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### businesses
```sql
CREATE TABLE businesses (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    business_type INT CHECK (business_type BETWEEN 1 AND 4),
    purchase_price BIGINT,
    purchased_at TIMESTAMP DEFAULT NOW(),
    last_payout_at TIMESTAMP DEFAULT NOW()
);
```

#### casino_games
```sql
CREATE TABLE casino_games (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id),
    bet_amount BIGINT,
    result VARCHAR(10) CHECK (result IN ('win', 'loss')),
    payout BIGINT,
    played_at TIMESTAMP DEFAULT NOW()
);
```

#### cooldowns
```sql
CREATE TABLE cooldowns (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id),
    action VARCHAR(50),
    expires_at TIMESTAMP,
    UNIQUE(user_id, action)
);
```

---

## Deployment

### Environment Variables
```env
# Telegram
TELEGRAM_BOT_TOKEN=<from Vault>

# Database
DATABASE_URL=postgresql://user:pass@host:5432/wedding_bot

# Admin
ADMIN_USER_ID=710573786

# Timezone
TZ=Europe/Moscow

# Scheduler
BUSINESS_PAYOUT_DAY=4  # Friday (0=Monday)
BUSINESS_PAYOUT_HOUR=18
BUSINESS_PAYOUT_MINUTE=0
```

### Kubernetes Deployment
- Namespace: `dev-backend-services`
- Service: `wedding-telegram-bot`
- Deployment: 1 replica (stateful bot with APScheduler)
- Secret: VaultStaticSecret for bot token
- ConfigMap: для конфигурации
- PostgreSQL: отдельный instance или shared cluster

### Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic.ini .

CMD ["python", "-m", "app.main"]
```

---

## Development Roadmap

### Phase 1: Foundation (Issues #1-5)
- [ ] Setup project structure
- [ ] Database models and migrations
- [ ] Bot initialization and basic handlers
- [ ] User registration (/start, /profile)
- [ ] Balance system

### Phase 2: Jobs System (Issues #6-10)
- [ ] Job models and logic
- [ ] /work command with inline keyboards
- [ ] /job command (all 5 professions)
- [ ] Job level progression
- [ ] Interpol special mechanics

### Phase 3: Marriage System (Issues #11-15)
- [ ] Marriage models
- [ ] /propose command
- [ ] /marriage menu
- [ ] Make love, cheat, date
- [ ] Family system

### Phase 4: Children System (Issues #16-20)
- [ ] Children models
- [ ] Birth/adoption mechanics
- [ ] /family command
- [ ] Feeding, aging, education
- [ ] Child work system
- [ ] Kidnapping mechanics

### Phase 5: Economy Features (Issues #21-25)
- [ ] Housing system
- [ ] Business system
- [ ] Weekly payout scheduler
- [ ] Casino
- [ ] Transfer system

### Phase 6: Admin & Polish (Issues #26-30)
- [ ] Admin commands
- [ ] Admin panel
- [ ] Statistics
- [ ] Help system
- [ ] Error handling and logging

### Phase 7: Deployment (Issues #31-35)
- [ ] Dockerfile
- [ ] Kubernetes manifests
- [ ] Database setup
- [ ] Vault secrets
- [ ] Deploy to cluster
- [ ] Testing and monitoring

---

## Success Metrics

- Active users: 100+ after 1 month
- Daily active users: 30+
- Average session length: 5+ minutes
- Marriage rate: 50%+ of users
- Business ownership: 20%+ of users
- Zero downtime during business payouts

---

## Future Enhancements (Post-MVP)

- Топы игроков (по балансу, детям, бизнесам)
- События и конкурсы
- Достижения (ачивки)
- Питомцы (упрощенная версия)
- Seasonal events
- Referral system
