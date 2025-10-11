# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.1.x   | :white_check_mark: |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of Wedding Telegram Bot seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please DO NOT:

- Open a public GitHub issue for security vulnerabilities
- Discuss the vulnerability in public channels (Discord, Telegram, etc.)

### Please DO:

1. **Report via GitHub Security Advisories** (preferred):
   - Go to https://github.com/digitaldrugstech/wedding-telegram-bot/security/advisories
   - Click "Report a vulnerability"
   - Fill in the details

2. **Or contact us directly**:
   - Email: [security contact needed]
   - Include detailed description and steps to reproduce
   - Include version information (`app/__version__.py`)

### What to expect:

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**:
  - Critical: 1-7 days
  - High: 7-14 days
  - Medium: 14-30 days
  - Low: Best effort

### Disclosure Policy:

- Security advisories will be published after fixes are released
- We follow coordinated disclosure practices
- Credit will be given to security researchers (unless they prefer to remain anonymous)

## Security Best Practices

When deploying this bot:

### 1. Environment Variables
- Never commit `.env` files
- Use strong, random values for secrets
- Rotate credentials regularly
- Use Vault/Secrets Manager in production

### 2. Database
- Use strong database passwords
- Enable SSL/TLS for database connections
- Regular backups with encryption
- Limit database user permissions

### 3. Telegram Bot Token
- Keep `TELEGRAM_BOT_TOKEN` secret
- Never expose in logs or error messages
- Use separate bots for dev/staging/prod
- Revoke compromised tokens immediately via @BotFather

### 4. Admin Access
- Limit `ADMIN_USER_ID` to trusted users only
- Monitor admin command usage
- Regular security audits

### 5. Dependencies
- Keep dependencies updated
- Enable Dependabot alerts
- Review security advisories regularly
- Pin versions in production

### 6. Deployment
- Run bot with minimal privileges
- Use container security scanning
- Enable network policies (Kubernetes)
- Regular security updates for base images

## Known Security Considerations

### Rate Limiting
- Currently relies on Telegram's built-in rate limiting
- Additional rate limiting recommended for production

### Input Validation
- User input is validated before database operations
- SQLAlchemy ORM prevents SQL injection
- Regex patterns sanitized

### Authentication
- Bot uses Telegram's authentication
- User IDs used as primary identifiers
- No password storage required

## Security Features

✅ **Implemented:**
- SQL injection protection (SQLAlchemy ORM)
- XSS protection (HTML escaping in messages)
- Command authorization (@admin_only decorator)
- Button ownership validation (@button_owner_only)
- Cooldown system to prevent spam
- Structured logging (no sensitive data in logs)
- Secret scanning (gitleaks workflow)
- Dependency scanning (safety, bandit, CodeQL)

## Vulnerability Scanning

We use automated security scanning:
- **GitHub CodeQL**: Static analysis
- **Dependabot**: Dependency vulnerabilities
- **gitleaks**: Secret detection
- **safety**: Python package vulnerabilities
- **bandit**: Python security linter

## Security Updates

Security updates are released as patch versions (e.g., 1.1.1) and announced via:
- GitHub Security Advisories
- CHANGELOG.md
- GitHub Releases

Subscribe to repository notifications to stay informed.

## Compliance

This project follows:
- OWASP Top 10 guidelines
- Python security best practices
- Telegram Bot API security recommendations
- GitHub security best practices

## Contact

For security concerns that are not vulnerabilities (questions, suggestions), please:
- Open a [Discussion](https://github.com/digitaldrugstech/wedding-telegram-bot/discussions)
- Use the [Question template](https://github.com/digitaldrugstech/wedding-telegram-bot/issues/new?template=question.md)

Thank you for helping keep Wedding Telegram Bot and its users safe!
