# Quick Deployment Guide

## 🚀 Deploy to Kubernetes

### Prerequisites
- kubectl configured with cluster access
- Namespace `dev-backend-services` exists
- Bot tokens from @BotFather (2 tokens: prod and dev)

---

## Development Environment

### 1. Create Secret

```bash
# Copy template
cp deployments/k8s/secret-dev.yaml.example deployments/k8s/secret-dev.yaml

# Edit with real dev bot token (get from @BotFather)
vim deployments/k8s/secret-dev.yaml

# Apply secret
kubectl apply -f deployments/k8s/secret-dev.yaml
```

### 2. Deploy Bot

```bash
kubectl apply -f deployments/k8s/deployment-dev.yaml
```

### 3. Check Status

```bash
# Check pod
kubectl -n dev-backend-services get pods -l environment=dev

# View logs
kubectl -n dev-backend-services logs -f deployment/wedding-telegram-bot-dev

# Expected output:
# {"event": "Bot started successfully", "level": "info", ...}
```

---

## Production Environment

### 1. Create Secret

```bash
# Copy template
cp deployments/k8s/secret-prod.yaml.example deployments/k8s/secret-prod.yaml

# Edit with real prod bot token (get from @BotFather)
vim deployments/k8s/secret-prod.yaml

# Apply secret
kubectl apply -f deployments/k8s/secret-prod.yaml
```

### 2. Deploy Bot

```bash
kubectl apply -f deployments/k8s/deployment-prod.yaml
```

### 3. Check Status

```bash
# Check pod
kubectl -n dev-backend-services get pods -l environment=prod

# View logs
kubectl -n dev-backend-services logs -f deployment/wedding-telegram-bot-prod
```

---

## Quick Commands

```bash
# View all wedding bot pods (both envs)
kubectl -n dev-backend-services get pods -l app=wedding-telegram-bot

# Restart dev bot
kubectl -n dev-backend-services rollout restart deployment/wedding-telegram-bot-dev

# Restart prod bot
kubectl -n dev-backend-services rollout restart deployment/wedding-telegram-bot-prod

# Delete dev bot
kubectl -n dev-backend-services delete deployment wedding-telegram-bot-dev

# Delete prod bot
kubectl -n dev-backend-services delete deployment wedding-telegram-bot-prod
```

---

## Environment Differences

| Feature | Development | Production |
|---------|------------|------------|
| **Bot Token** | Dev bot (8458433644) | Prod bot (7454412857) |
| **Image Pull** | Always (latest) | IfNotPresent |
| **Log Level** | DEBUG | INFO |
| **Resources** | 256Mi / 512Mi | 512Mi / 1Gi |
| **CPU** | 100m / 500m | 200m / 1000m |

---

## Troubleshooting

### Bot not starting

```bash
# Check logs
kubectl -n dev-backend-services logs deployment/wedding-telegram-bot-dev --tail=100

# Check secret
kubectl -n dev-backend-services get secret wedding-telegram-bot-secret -o yaml

# Verify token (first 10 chars should match bot ID)
kubectl -n dev-backend-services get secret wedding-telegram-bot-secret \
  -o jsonpath='{.data.TELEGRAM_BOT_TOKEN}' | base64 -d | head -c 10
```

### Database connection failed

```bash
# Check DATABASE_URL
kubectl -n dev-backend-services get secret wedding-telegram-bot-secret \
  -o jsonpath='{.data.DATABASE_URL}' | base64 -d
```

---

## Token Rotation

When rotating bot tokens:

1. Get new token from @BotFather
2. Update secret yaml file (secret-dev.yaml or secret-prod.yaml)
3. Apply changes:
   ```bash
   kubectl apply -f deployments/k8s/secret-dev.yaml
   # OR
   kubectl apply -f deployments/k8s/secret-prod.yaml
   ```
4. Restart deployment:
   ```bash
   kubectl -n dev-backend-services rollout restart deployment/wedding-telegram-bot-dev
   # OR
   kubectl -n dev-backend-services rollout restart deployment/wedding-telegram-bot-prod
   ```

⚠️ **Remember**: NEVER commit real secrets to git! Files `secret-dev.yaml` and `secret-prod.yaml` are in `.gitignore`.
