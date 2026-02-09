"""Global constants for Wedding Telegram Bot."""

# Debug
DEBUG_CHAT_ID = -1003172144355

# Interpol Fines
INTERPOL_MIN_VICTIM_BALANCE = 50  # Minimum victim balance to fine
INTERPOL_VICTIM_COOLDOWN_HOURS = 1  # Hours before can fine same victim again
INTERPOL_BONUS_MAX_PERCENTAGE = 0.5  # Max 50% bonus for "говновызов"

# Selfmade Easter Egg
SELFMADE_TRAP_LEVEL = 6  # Level at which trap triggers (on promotion to 7)

# Loan System
LOAN_MIN_AMOUNT = 100  # Minimum loan amount
LOAN_MAX_AMOUNT = 10000  # Maximum loan amount
LOAN_INTEREST_RATE = 20  # Interest rate percentage per week
LOAN_DURATION_WEEKS = 2  # Loan duration in weeks
LOAN_PENALTY_RATE = 50  # Penalty rate percentage if overdue

# Transfer System
TRANSFER_MIN_AMOUNT = 10  # Minimum transfer amount
TRANSFER_FEE_RATE = 5  # Transfer fee percentage

# Rob System
ROB_SUCCESS_CHANCE = 30  # Success chance percentage
ROB_MIN_STEAL_RATE = 10  # Minimum steal percentage
ROB_MAX_STEAL_RATE = 30  # Maximum steal percentage
ROB_FAIL_PENALTY_RATE = 20  # Penalty on failure percentage
ROB_MIN_VICTIM_BALANCE = 100  # Minimum victim balance to rob
ROB_COOLDOWN_HOURS = 4  # Cooldown in hours

# Daily Reward System
DAILY_MIN_REWARD = 50  # Minimum daily reward
DAILY_MAX_REWARD = 100  # Maximum daily reward
DAILY_STREAK_BONUS_RATE = 10  # Bonus percentage per streak day
DAILY_MAX_STREAK_BONUS = 100  # Maximum streak bonus percentage

# Lottery System
LOTTERY_TICKET_PRICE = 100  # Lottery ticket price
LOTTERY_MIN_TICKETS = 10  # Minimum tickets to draw
LOTTERY_DRAW_HOURS = 6  # Draw every N hours
LOTTERY_WINNER_PAYOUT_RATE = 80  # Winner gets 80% of jackpot
LOTTERY_HOUSE_FEE_RATE = 20  # House takes 20%

# Investment
INVESTMENT_MIN_AMOUNT = 1000  # Minimum investment amount
INVESTMENT_DURATION_DAYS = 7  # Investment duration in days
INVESTMENT_MIN_RETURN = -20  # Minimum return percentage
INVESTMENT_MAX_RETURN = 50  # Maximum return percentage

# Stock Exchange
STOCK_COMPANIES = ["PRDX Corp", "Diamond Mining", "Family Business", "Casino Royal", "Real Estate"]
STOCK_INITIAL_PRICE = 100  # Initial stock price
STOCK_PRICE_CHANGE_PERCENTAGE = 10  # Max price change percentage per hour
STOCK_MIN_PRICE = 10  # Minimum stock price
STOCK_MAX_PRICE = 500  # Maximum stock price

# Auction
AUCTION_DURATION_HOURS = 24  # Auction duration in hours
AUCTION_ITEMS = {
    "vip_status": {"name": "VIP статус", "emoji": "👑", "effect_days": 7},
    "double_salary": {"name": "Двойная зарплата", "emoji": "💰", "effect_days": 7},
    "lucky_charm": {"name": "Талисман удачи", "emoji": "🍀", "effect_days": 7},
}

# Tax System
TAX_THRESHOLD = 50000  # Tax applies to balance above this amount
TAX_RATE = 0.05  # 5% tax rate

# Insurance
INSURANCE_WEEKLY_COST = 500  # Weekly insurance cost
INSURANCE_DURATION_DAYS = 7  # Insurance duration in days
