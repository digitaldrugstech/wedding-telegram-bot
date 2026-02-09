"""Global constants for Wedding Telegram Bot."""

# Debug
DEBUG_CHAT_ID = -1003172144355

# Production chat for announcements
PRODUCTION_CHAT_ID = -1003086018945

# Interpol Fines
INTERPOL_MIN_VICTIM_BALANCE = 50  # Minimum victim balance to fine
INTERPOL_VICTIM_COOLDOWN_HOURS = 1  # Hours before can fine same victim again
INTERPOL_BONUS_MAX_PERCENTAGE = 0.5  # Max 50% bonus for "говновызов"

# Selfmade Easter Egg
SELFMADE_TRAP_LEVEL = 6  # Level at which trap triggers (on promotion to 7)

# Transfer System
TRANSFER_FEE_RATE = 5  # Transfer fee percentage

# Rob System
ROB_SUCCESS_CHANCE = 30  # Success chance percentage
ROB_MIN_STEAL_RATE = 10  # Minimum steal percentage
ROB_MAX_STEAL_RATE = 30  # Maximum steal percentage
ROB_FAIL_PENALTY_RATE = 20  # Penalty on failure percentage
ROB_MIN_VICTIM_BALANCE = 100  # Minimum victim balance to rob
ROB_COOLDOWN_HOURS = 4  # Cooldown in hours

# Tax System
TAX_THRESHOLD = 50000  # Tax applies to balance above this amount
TAX_RATE = 0.05  # 5% tax rate

# Insurance
INSURANCE_WEEKLY_COST = 500  # Weekly insurance cost
INSURANCE_DURATION_DAYS = 7  # Insurance duration in days

# Referral System
REFERRAL_INVITER_REWARD = 500  # Diamonds for inviter when referral completes 3 active days
REFERRAL_INVITEE_REWARD = 200  # Diamonds for invitee on registration via referral
REFERRAL_ACTIVE_DAYS_REQUIRED = 3  # Days the invitee must play before inviter gets reward
REFERRAL_SHARE_REWARD = 50  # Diamonds for sharing a win/event
