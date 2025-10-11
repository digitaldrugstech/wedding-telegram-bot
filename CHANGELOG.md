# Changelog

## [1.1.1] - 2025-10-11

### Security
- 🔒 **CRITICAL**: Удалены закоммиченные bot tokens из репозитория
- 🛡️ Добавлен Gitleaks secret scanning в CI/CD pipeline
- 🔐 Все tokens переведены на environment variables
- 📝 Создан SECURITY_INCIDENT.md с best practices

### Added
- 🚀 Production и Development окружения с раздельными конфигурациями
  - `deployment-dev.yaml` - развертывание для dev бота
  - `deployment-prod.yaml` - развертывание для prod бота
  - `secret-dev.yaml.example` - template для dev secrets
  - `secret-prod.yaml.example` - template для prod secrets
- 📚 DEPLOYMENT_GUIDE.md - quick reference для деплоя
- 🐳 Docker Compose с environment variables (`.env.dev`, `.env.prod`)
- 🔍 `.gitleaks.toml` - конфигурация secret scanning с custom rules

### Changed
- 🐳 Docker Compose файлы переведены на env vars (токены не в файлах!)
- 📖 DEPLOYMENT.md обновлен с "Security First" секцией
- 📖 CLAUDE.md обновлен с prod/dev bot IDs и deployment командами
- 🔧 `.gitignore` расширен для secrets (`.env.dev`, `.env.prod`, `*secret*.yaml`)

### Fixed
- ✅ Security Scanning workflow работает корректно (Gitleaks + Bandit + Safety)
- ✅ CodeQL конфликт устранен (используется GitHub default setup)
- ✅ Docker images используют GHCR registry: `ghcr.io/digitaldrugstech/wedding-telegram-bot:latest`

### Documentation
- 📄 SECURITY_INCIDENT.md - incident report с timeline и remediation steps
- 📄 DEPLOYMENT_GUIDE.md - пошаговые инструкции для dev/prod deploy
- 🔄 Обновлены все deployment документы

## [1.1.0] - 2025-10-11

### Added
- 💍 Система брака реализована полностью
  - `/propose` - предложение руки и сердца (50 💎)
  - `/propose @username` - альтернативный синтаксис
  - Кнопка "💍 Брак" в профиле
  - `/gift [amount]` - подарить алмазы супругу
  - `/makelove` - заняться любовью (кулдаун 24ч)
  - `/date` - свидание (кулдаун 12ч, 10-50 💎)
  - `/cheat` - измена (риск 30%)
  - `/cheat @username` - альтернативный синтаксис
- 🚔 Поддержка @username для Интерпола (`/job @username`)

### Changed
- 🗑️ Удалена команда `/start` - регистрация теперь показывается при любой команде
- 📝 Все тексты переписаны по принципам сильного текста (короче, яснее)
- 💰 Убрано отображение баланса в `/job` (только заработок)

### Fixed
- ✅ Автообновление username при командах
- ✅ Кнопки предложения брака работают корректно
- ✅ SQLAlchemy session management исправлен
