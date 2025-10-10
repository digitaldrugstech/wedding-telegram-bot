# Deployment Guide

## Prerequisites

1. Telegram Bot Token (get from @BotFather)
2. PostgreSQL database
3. Kubernetes cluster access (for production)
4. Vault access (for secrets)

## Local Development

### 1. Using Docker Compose

The easiest way to run locally:

```bash
# Set your bot token
export TELEGRAM_BOT_TOKEN="your_bot_token_here"

# Start bot + PostgreSQL
cd deployments
docker-compose up
```

The bot will:
- Start PostgreSQL on port 5432
- Run migrations automatically
- Start the bot

### 2. Using Python directly

```bash
# Install dependencies
pip install -r requirements.txt

# Setup PostgreSQL
createdb wedding_bot
createuser wedding_bot

# Set environment variables
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export DATABASE_URL="postgresql://wedding_bot:password@localhost:5432/wedding_bot"
export ADMIN_USER_ID="710573786"

# Run migrations
alembic upgrade head

# Start bot
python -m app.main
```

## Production Deployment (Kubernetes)

### 1. Setup Secrets in Vault

```bash
# Login to Vault
kubectl exec -n vault vault-0 -- vault login

# Create secrets
kubectl exec -n vault vault-0 -- vault kv put secret/dev-backend-services/wedding-telegram-bot-secret \
  TELEGRAM_BOT_TOKEN='your_bot_token_here' \
  DATABASE_URL='postgresql://user:pass@host:5432/wedding_bot'
```

### 2. Setup PostgreSQL

Option A: Create dedicated PostgreSQL instance

```bash
# Example using CloudNativePG or similar
kubectl apply -f - <<EOF
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: wedding-bot-postgres
  namespace: dev-backend-services
spec:
  instances: 1
  storage:
    size: 10Gi
EOF
```

Option B: Use existing PostgreSQL cluster

Create database and user:
```sql
CREATE DATABASE wedding_bot;
CREATE USER wedding_bot WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE wedding_bot TO wedding_bot;
```

Update DATABASE_URL in Vault accordingly.

### 3. Build and Push Docker Image

```bash
# Build image
docker build -t your-registry/wedding-telegram-bot:latest -f deployments/Dockerfile .

# Push to registry
docker push your-registry/wedding-telegram-bot:latest
```

Update `deployments/k8s/deployment.yaml` with your image:
```yaml
image: your-registry/wedding-telegram-bot:latest
```

### 4. Deploy to Kubernetes

```bash
# Apply manifests
kubectl apply -f deployments/k8s/configmap.yaml
kubectl apply -f deployments/k8s/vault-secret.yaml
kubectl apply -f deployments/k8s/deployment.yaml

# Check deployment
kubectl get pods -n dev-backend-services | grep wedding

# View logs
kubectl logs -n dev-backend-services deployment/wedding-telegram-bot -f
```

### 5. Verify Deployment

```bash
# Check pod status
kubectl get pods -n dev-backend-services -l app=wedding-telegram-bot

# Check logs
kubectl logs -n dev-backend-services -l app=wedding-telegram-bot --tail=100

# Check secret sync
kubectl get secret -n dev-backend-services wedding-telegram-bot-secret
```

Expected log output:
```json
{"event": "Configuration validated", "level": "info", "timestamp": "..."}
{"event": "Database initialized", "level": "info", "timestamp": "..."}
{"event": "Bot started successfully", "level": "info", "timestamp": "..."}
```

### 6. Test Bot

1. Open Telegram and find your bot
2. Send `/start` command
3. Bot should respond with welcome message and gender selection buttons
4. Select gender and verify registration works
5. Try `/profile`, `/balance`, `/help` commands

## Monitoring

### Logs

```bash
# Real-time logs
kubectl logs -n dev-backend-services deployment/wedding-telegram-bot -f

# Last 100 lines
kubectl logs -n dev-backend-services deployment/wedding-telegram-bot --tail=100

# Logs from specific pod
kubectl logs -n dev-backend-services wedding-telegram-bot-xxxxx-xxxxx
```

### Health Checks

```bash
# Check pod health
kubectl describe pod -n dev-backend-services wedding-telegram-bot-xxxxx-xxxxx

# Check events
kubectl get events -n dev-backend-services --sort-by='.lastTimestamp' | grep wedding
```

### Resource Usage

```bash
# Check resource usage
kubectl top pod -n dev-backend-services -l app=wedding-telegram-bot
```

## Troubleshooting

### Bot Not Starting

1. Check secrets:
```bash
kubectl exec -n dev-backend-services deployment/wedding-telegram-bot -- env | grep TELEGRAM_BOT_TOKEN
```

2. Check database connectivity:
```bash
kubectl exec -n dev-backend-services deployment/wedding-telegram-bot -- pg_isready -h <db-host>
```

3. Check logs for errors:
```bash
kubectl logs -n dev-backend-services deployment/wedding-telegram-bot --tail=200
```

### Database Migration Issues

Run migrations manually:
```bash
kubectl exec -it -n dev-backend-services deployment/wedding-telegram-bot -- alembic upgrade head
```

### Secret Not Syncing

1. Check VaultStaticSecret status:
```bash
kubectl describe vaultstaticsecret -n dev-backend-services wedding-telegram-bot-vault
```

2. Force sync with annotation:
```bash
kubectl annotate vaultstaticsecret -n dev-backend-services wedding-telegram-bot-vault \
  force-sync="$(date +%s)" --overwrite
```

3. Check secret content:
```bash
kubectl get secret -n dev-backend-services wedding-telegram-bot-secret -o yaml
```

## Updating

### Update Bot Code

```bash
# Build new image
docker build -t your-registry/wedding-telegram-bot:v2 -f deployments/Dockerfile .
docker push your-registry/wedding-telegram-bot:v2

# Update deployment
kubectl set image deployment/wedding-telegram-bot -n dev-backend-services \
  wedding-telegram-bot=your-registry/wedding-telegram-bot:v2

# Check rollout
kubectl rollout status deployment/wedding-telegram-bot -n dev-backend-services
```

### Update Configuration

```bash
# Edit ConfigMap
kubectl edit configmap -n dev-backend-services wedding-telegram-bot-config

# Restart deployment to pick up changes
kubectl rollout restart deployment/wedding-telegram-bot -n dev-backend-services
```

### Update Secrets

```bash
# Update in Vault
kubectl exec -n vault vault-0 -- vault kv put secret/dev-backend-services/wedding-telegram-bot-secret \
  TELEGRAM_BOT_TOKEN='new_token' \
  DATABASE_URL='postgresql://...'

# Wait for Vault Operator to sync (30s)
# Or force sync with annotation
```

## Rollback

```bash
# Check rollout history
kubectl rollout history deployment/wedding-telegram-bot -n dev-backend-services

# Rollback to previous version
kubectl rollout undo deployment/wedding-telegram-bot -n dev-backend-services

# Rollback to specific revision
kubectl rollout undo deployment/wedding-telegram-bot -n dev-backend-services --to-revision=2
```

## Scaling

⚠️ **WARNING**: This bot uses APScheduler and MUST have `replicas: 1`

Do NOT scale to multiple replicas as it will cause:
- Duplicate weekly payouts
- Race conditions in scheduled tasks
- Inconsistent state

If you need high availability:
1. Use pod disruption budgets
2. Ensure fast startup times
3. Use readiness/liveness probes
4. Consider leader election pattern (future enhancement)

## Maintenance Mode

Use admin commands to enable maintenance mode:
```bash
# In Telegram, send to bot (as admin):
/maintenance on

# All users will see "Bot is under maintenance" message
# Admin can still use commands

# Disable maintenance mode:
/maintenance off
```

## Backup & Restore

### Database Backup

```bash
# Backup database
kubectl exec -n dev-backend-services deployment/wedding-telegram-bot -- \
  pg_dump $DATABASE_URL > wedding_bot_backup_$(date +%Y%m%d).sql

# Restore database
kubectl exec -i -n dev-backend-services deployment/wedding-telegram-bot -- \
  psql $DATABASE_URL < wedding_bot_backup_20250101.sql
```

### Admin Backup Command

```bash
# In Telegram, send to bot (as admin):
/backup

# This will create a backup and provide download link
```
