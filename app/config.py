"""Bot configuration."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Bot configuration."""

    # Telegram
    telegram_bot_token: str

    # Database
    database_url: str

    # Admin
    admin_user_id: int

    # Timezone
    timezone: str

    # Scheduler
    business_payout_day: int  # 0=Monday, 4=Friday
    business_payout_hour: int
    business_payout_minute: int

    # Logging
    log_level: str

    # Debug
    debug_chat_id: int  # Chat ID for debug purposes (no cooldowns)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            database_url=os.getenv("DATABASE_URL", "postgresql://wedding_bot:password@localhost:5432/wedding_bot"),
            admin_user_id=int(os.getenv("ADMIN_USER_ID", "710573786")),
            timezone=os.getenv("TZ", "Europe/Moscow"),
            business_payout_day=int(os.getenv("BUSINESS_PAYOUT_DAY", "4")),
            business_payout_hour=int(os.getenv("BUSINESS_PAYOUT_HOUR", "18")),
            business_payout_minute=int(os.getenv("BUSINESS_PAYOUT_MINUTE", "0")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            debug_chat_id=int(os.getenv("DEBUG_CHAT_ID", "-1003172144355")),
        )

    def validate(self):
        """Validate configuration."""
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")
        if self.admin_user_id <= 0:
            raise ValueError("ADMIN_USER_ID must be positive")


# Global config instance
config = Config.from_env()
