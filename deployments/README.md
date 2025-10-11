# Docker Compose Deployment

Quick guide for running Wedding Telegram Bot locally with Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
- Bot tokens from @BotFather (for dev and/or prod)

---

## Development Environment

### 1. Setup Environment

```bash
cd deployments/

# Copy template
cp .env.dev.example .env.dev

# Edit with your dev bot token
vim .env.dev
```

Edit `.env.dev`:
```bash
TELEGRAM_BOT_TOKEN_DEV=your_dev_bot_token_here
POSTGRES_PASSWORD=password
```

### 2. Start Dev Bot

```bash
# Start services
docker-compose --env-file .env.dev up -d

# View logs
docker-compose logs -f bot

# Stop services
docker-compose down
```

### 3. Check Status

```bash
# Check containers
docker-compose ps

# View bot logs
docker-compose logs -f bot

# View postgres logs
docker-compose logs -f postgres

# Expected output:
# {"event": "Bot started successfully", "level": "info", ...}
```

---

## Production Environment

### 1. Setup Environment

```bash
cd deployments/

# Copy template
cp .env.prod.example .env.prod

# Edit with your prod bot token
vim .env.prod
```

Edit `.env.prod`:
```bash
TELEGRAM_BOT_TOKEN_PROD=your_prod_bot_token_here
POSTGRES_PASSWORD_PROD=your_secure_password_here
```

### 2. Start Prod Bot

```bash
# Start services
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f bot-prod

# Stop services
docker-compose -f docker-compose.prod.yml down
```

### 3. Check Status

```bash
# Check containers
docker-compose -f docker-compose.prod.yml ps

# View bot logs
docker-compose -f docker-compose.prod.yml logs -f bot-prod --tail=100

# View postgres logs
docker-compose -f docker-compose.prod.yml logs -f postgres-prod
```

---

## Database Migrations

Migrations run automatically on bot startup, but you can run them manually:

```bash
# Dev
docker-compose exec bot alembic upgrade head

# Prod
docker-compose -f docker-compose.prod.yml exec bot-prod alembic upgrade head
```

---

## Useful Commands

### Dev Environment

```bash
# Restart bot only (keeps database running)
docker-compose restart bot

# View bot logs (real-time)
docker-compose logs -f bot

# Access bot container shell
docker-compose exec bot bash

# Access postgres
docker-compose exec postgres psql -U wedding_bot -d wedding_bot

# Pull latest image
docker-compose pull bot

# Rebuild and restart
docker-compose up -d --build
```

### Prod Environment

```bash
# Restart bot only
docker-compose -f docker-compose.prod.yml restart bot-prod

# View bot logs (last 100 lines)
docker-compose -f docker-compose.prod.yml logs -f bot-prod --tail=100

# Access bot container
docker-compose -f docker-compose.prod.yml exec bot-prod bash

# Access postgres
docker-compose -f docker-compose.prod.yml exec postgres-prod psql -U wedding_bot_prod -d wedding_bot_prod

# Pull latest image
docker-compose -f docker-compose.prod.yml pull bot-prod

# Rebuild and restart
docker-compose -f docker-compose.prod.yml up -d --force-recreate
```

---

## Environment Differences

| Feature | Development | Production |
|---------|------------|------------|
| **Config File** | `docker-compose.yml` | `docker-compose.prod.yml` |
| **Env File** | `.env.dev` | `.env.prod` |
| **Bot Container** | `wedding-bot-dev` | `wedding-bot-prod` |
| **DB Container** | `wedding-bot-postgres-dev` | `wedding-bot-postgres-prod` |
| **Database Name** | `wedding_bot` | `wedding_bot_prod` |
| **Log Level** | `DEBUG` | `INFO` |
| **Log Rotation** | No | Yes (10MB, 3 files) |

---

## Troubleshooting

### Bot not starting

```bash
# Check bot logs
docker-compose logs bot --tail=50

# Check if PostgreSQL is ready
docker-compose exec postgres pg_isready -U wedding_bot -d wedding_bot

# Restart bot
docker-compose restart bot
```

### Database connection error

```bash
# Check postgres container
docker-compose ps postgres

# Check postgres logs
docker-compose logs postgres --tail=50

# Test connection
docker-compose exec postgres psql -U wedding_bot -d wedding_bot -c "SELECT 1"
```

### Migration errors

```bash
# Run migrations manually
docker-compose exec bot alembic upgrade head

# Check migration status
docker-compose exec bot alembic current

# Rollback last migration
docker-compose exec bot alembic downgrade -1
```

### Clean restart

```bash
# Stop everything
docker-compose down

# Remove volumes (⚠️ deletes database!)
docker-compose down -v

# Start fresh
docker-compose up -d
```

---

## Data Persistence

Database data is stored in Docker volumes:
- **Dev**: `postgres_data`
- **Prod**: `wedding-bot-postgres-prod-data`

To backup:
```bash
# Dev
docker-compose exec postgres pg_dump -U wedding_bot wedding_bot > backup_dev.sql

# Prod
docker-compose -f docker-compose.prod.yml exec postgres-prod pg_dump -U wedding_bot_prod wedding_bot_prod > backup_prod.sql
```

To restore:
```bash
# Dev
docker-compose exec -T postgres psql -U wedding_bot wedding_bot < backup_dev.sql

# Prod
docker-compose -f docker-compose.prod.yml exec -T postgres-prod psql -U wedding_bot_prod wedding_bot_prod < backup_prod.sql
```

---

## Security Notes

⚠️ **NEVER commit `.env.dev` or `.env.prod` files!**

These files contain sensitive bot tokens and are in `.gitignore`.

✅ **Safe to commit**:
- `.env.dev.example`
- `.env.prod.example`
- `docker-compose.yml`
- `docker-compose.prod.yml`

❌ **NEVER commit**:
- `.env`
- `.env.dev`
- `.env.prod`

---

## Next Steps

For production deployment to Kubernetes, see [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md).
