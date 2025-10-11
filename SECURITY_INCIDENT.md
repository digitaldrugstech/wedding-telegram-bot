# Security Incident Report - Token Exposure

**Date**: 2025-10-11
**Severity**: HIGH
**Status**: RESOLVED

## Incident Summary

Telegram Bot API token was accidentally committed to the public GitHub repository in commit `31cd9d2` (release: v1.0.0) and remained in the repository history.

## Affected Assets

- **File**: `deployments/k8s/secret-prod.yaml`
- **Commit**: `31cd9d2` (2025-10-11 02:13:09 +0300)
- **Exposed Token**: `8458433644:AAFGSsQE2-RrClEjVIc0ZymE-eHjBa1viEw`
- **Exposure Duration**: October 11, 2025 → October 11, 2025 (same day discovery & remediation)

## Root Cause

1. Production secrets were committed directly to the repository instead of using external secret management
2. No automated secret scanning (gitleaks) was configured in CI/CD pipeline
3. CodeQL workflow conflicted with GitHub's default security setup, causing security checks to fail

## Remediation Steps Taken

### 1. Token Rotation ✅
- [x] Revoked compromised token via @BotFather
- [x] Generated new token
- [x] Updated production deployment with new token

### 2. Repository Cleanup ✅
- [x] Removed `secret-prod.yaml` from repository (`git rm`)
- [x] Added `deployments/k8s/*secret*.yaml` to `.gitignore`
- [x] Created `secret-prod.yaml.example` as template

### 3. Security Enhancements ✅
- [x] Added Gitleaks secret scanning to CI/CD pipeline
- [x] Created `.gitleaks.toml` configuration with custom rules for:
  - Telegram Bot API tokens
  - Database connection strings
  - Generic API keys
- [x] Removed conflicting CodeQL workflow (using GitHub default instead)
- [x] Configured GITLEAKS_LICENSE secret in GitHub repository settings

### 4. Documentation ✅
- [x] Created this incident report
- [x] Updated deployment documentation with secret management best practices

## Impact Assessment

**Low Impact** - Token was revoked same day, no evidence of unauthorized access.

- ✅ Token revoked within hours of commit
- ✅ New token deployed successfully
- ✅ Bot operational with no downtime
- ✅ No suspicious activity detected in bot logs

## Lessons Learned

1. **Never commit secrets**: Use templates (`.example` files) and external secret management
2. **Automate security**: Gitleaks should have caught this before merge
3. **Monitor CI/CD**: Failed security checks should block deployment

## Best Practices for Secret Management

### Development
```bash
# Copy template and fill with real values
cp deployments/k8s/secret-prod.yaml.example deployments/k8s/secret-prod.yaml
# Edit secret-prod.yaml with real credentials
# File is in .gitignore - will NOT be committed
```

### Production Deployment Options

#### Option 1: Kubernetes Secrets (Manual)
```bash
kubectl create secret generic wedding-telegram-bot-secret \
  --from-literal=TELEGRAM_BOT_TOKEN=<token> \
  --from-literal=DATABASE_URL=<url> \
  -n dev-backend-services
```

#### Option 2: Sealed Secrets (Recommended)
```bash
# Install sealed-secrets controller in cluster
# Then encrypt secrets for safe git storage
kubeseal --format yaml < secret-prod.yaml > sealed-secret-prod.yaml
kubectl apply -f sealed-secret-prod.yaml
```

#### Option 3: HashiCorp Vault
```bash
# Store secrets in Vault
vault kv put secret/wedding-bot \
  telegram_token=<token> \
  database_url=<url>

# Use Vault agent or CSI driver to inject into pods
```

#### Option 4: GitHub Secrets (CI/CD only)
```yaml
# In GitHub Actions workflows
env:
  TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## CI/CD Security Checks

All pushes now trigger:
1. **Gitleaks** - Secret scanning (blocks merge if secrets found)
2. **Bandit** - Python security linting
3. **Safety** - Dependency vulnerability scanning
4. **CodeQL** - Code security analysis (GitHub default setup)

## Action Items for Future

- [ ] Implement Sealed Secrets or Vault for production
- [ ] Add pre-commit hooks for local secret scanning
- [ ] Set up secret rotation schedule (quarterly)
- [ ] Add security training for all contributors

## Timeline

- **2025-10-11 02:13 UTC**: Token committed in release v1.0.0
- **2025-10-11 16:00 UTC**: Token exposure discovered during security audit
- **2025-10-11 16:05 UTC**: Token revoked via @BotFather
- **2025-10-11 16:10 UTC**: New token generated and deployed
- **2025-10-11 16:30 UTC**: Gitleaks added to CI/CD
- **2025-10-11 16:35 UTC**: Repository cleaned, incident documented

## Sign-off

**Incident Handler**: Claude Code
**Reviewed By**: Felix Haffk
**Status**: CLOSED
**Date**: 2025-10-11

---

**Note**: This incident report is kept for transparency and learning purposes. All affected credentials have been rotated and are no longer valid.
