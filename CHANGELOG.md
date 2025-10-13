# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-10-11

### Added
- Complete casino system with all 6 games (slots, dice, darts, basketball, bowling, football)
  - Proper payout multipliers based on Telegram Dice API values
  - 1 minute cooldown (removed in DEBUG mode)
  - Min/max bet limits (10-1000 diamonds)
- Children system (issue #24)
  - Birth methods: natural (10% on /makelove), IVF (5000 diamonds, 100%), adoption (500 diamonds)
  - Three age stages: infant → child → teen
  - Feeding system (50 diamonds, 3-day cooldown, dies after 5 days without food)
  - School system (500 diamonds/month, +50% work bonus for teens)
  - Teen work (30-60 diamonds, 24h cooldown, +50% if in school)
  - Babysitter service (1000 diamonds/week, auto-feeds all children)
  - Requirements: house + both partners working + different professions
- House system
  - 3 house types with different protection levels
  - Required for having children
  - Protects children from kidnapping (planned feature)
- Business system
  - 5 business types with passive weekly income
  - Purchase via /business menu
  - Automatic weekly payouts (planned)

### Changed
- Removed all cooldowns in DEBUG mode (DEV environment)
- Improved all text outputs to be more clear and informative (issue #29)
- Updated /makelove to show proper message when requirements not met for pregnancy

### Fixed
- Reverted selfmade flavor texts to original short versions (issue #30)
- Show proper message on /makelove when child requirements not met (issue #28)

## [1.0.0] - 2025-10-08

### Added
- Marriage system
  - /propose command (50 diamonds cost)
  - /marriage menu (gift, divorce, stats)
  - /gift command to transfer diamonds to spouse
  - /makelove command (24h cooldown, 10% pregnancy chance - placeholder)
  - /date command (10-50 diamonds, 12h cooldown)
  - /cheat command (30% risk of instant divorce)
- Job system with 6 professions (10 levels each, selfmade = 6)
  - Interpol: Fine players with reply (/job @username or reply)
  - Banker: Financial transactions
  - Infrastructure: Resource management
  - Court: Legal system
  - Culture: Events organization
  - Selfmade: Quick grind (30min cooldown, secret trap at level 7)
- Promotion system
  - Random chance: 5% (level 1) → 1.5% (level 10)
  - Guaranteed: after 20-60 works (depends on level)
- Interpol special mechanics
  - Fine = victim's ~one salary
  - Bonus +50% if interpol higher level than victim
  - 1 hour cooldown per victim
  - Protection: victim must have ≥50 diamonds
- Admin commands
  - /reset_cd (reset cooldown for any user)
  - /admin (admin panel in private chat)
  - /stats (bot statistics)
  - /user_info [id] (detailed user info)
  - /give [id] [amount] (give diamonds)
  - /take [id] [amount] (take diamonds)
  - /ban [id] (ban user)
  - /unban [id] (unban user)
  - /broadcast [message] (send to all users)
  - /maintenance on|off (toggle maintenance mode)
- CI/CD pipeline
  - Tests (pytest + PostgreSQL)
  - Linting (black, isort, flake8)
  - Docker multi-platform builds (amd64, arm64)
  - Security scanning (safety, bandit, CodeQL)
  - Automated dependency updates
- Deployment
  - Kubernetes manifests for dev/prod
  - Docker Compose for local development
  - GitHub Container Registry (ghcr.io)
  - Two bots: @wedding_telegram_bot (prod), @wedding_dev_bot (dev)

### Changed
- Migrated from SQLAlchemy 1.4 to 2.0
- Updated to python-telegram-bot 20.7 (async)
- Improved Russian word endings for diamonds (алмаз/алмаза/алмазов)
- Enhanced UX writing (WRITING_STYLE.md)
- Restructured project with proper separation of concerns

### Fixed
- Database connection handling with proper context managers
- Cooldown system using decorator pattern
- Button security with owner ID validation
- Timezone handling (UTC everywhere)

### Security
- Added security policy (SECURITY.md)
- Implemented input validation for all user commands
- Protected sensitive operations (admin commands, marriage, etc.)
- Rate limiting via cooldown system

## [0.1.0] - 2025-09-20

### Added
- Initial bot structure
- Basic registration system
- Profile command
- Balance tracking
- PostgreSQL database with SQLAlchemy
- Alembic migrations
- Docker support
- Basic CI/CD with GitHub Actions

---

## Future Plans (Roadmap)

### v1.2.0 (Planned)
- [ ] Complete kidnapping system
  - Kidnap children from other marriages
  - Ransom system
  - House protection mechanics
- [ ] Business weekly payout automation (APScheduler)
- [ ] Children death notifications to parents
- [ ] School expiration notifications
- [ ] Marriage anniversary celebrations
- [ ] Leaderboards (richest, most children, etc.)

### v1.3.0 (Planned)
- [ ] Achievements system
- [ ] Daily quests
- [ ] Marriage divorce settlement (split diamonds)
- [ ] Child emancipation at age 18
- [ ] Business upgrades and management
- [ ] Robbery system (risk vs reward)

### v2.0.0 (Ideas)
- [ ] Multi-language support (EN/RU)
- [ ] In-game events (holidays, competitions)
- [ ] Trading system between players
- [ ] Premium features (cosmetic only)
- [ ] Guilds/Families system
- [ ] PvP mechanics
