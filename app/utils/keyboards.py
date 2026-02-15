"""Inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Main menu hub — primary entry point."""
    keyboard = [
        [
            InlineKeyboardButton("💼 Работа", callback_data=f"menu:work:{user_id}"),
            InlineKeyboardButton("💍 Семья", callback_data=f"menu:marriage:{user_id}"),
        ],
        [
            InlineKeyboardButton("💰 Экономика", callback_data=f"menu:economy:{user_id}"),
            InlineKeyboardButton("🎰 Казино", callback_data=f"menu:casino:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎮 Игры", callback_data=f"menu:games:{user_id}"),
            InlineKeyboardButton("👥 Социальное", callback_data=f"menu:social:{user_id}"),
        ],
        [InlineKeyboardButton("👤 Профиль", callback_data=f"menu:profile:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def gender_selection_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Keyboard for gender selection."""
    keyboard = [
        [
            InlineKeyboardButton("Мужчина ♂️", callback_data=f"gender:male:{user_id}"),
            InlineKeyboardButton("Женщина ♀️", callback_data=f"gender:female:{user_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Keyboard for profile (quick access to main menus)."""
    keyboard = [
        [
            InlineKeyboardButton("💼 Работа", callback_data=f"menu:work:{user_id}"),
            InlineKeyboardButton("💍 Семья", callback_data=f"menu:marriage:{user_id}"),
        ],
        [
            InlineKeyboardButton("💰 Экономика", callback_data=f"menu:economy:{user_id}"),
            InlineKeyboardButton("🎰 Казино", callback_data=f"menu:casino:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎮 Игры", callback_data=f"menu:games:{user_id}"),
            InlineKeyboardButton("👥 Социальное", callback_data=f"menu:social:{user_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def work_menu_keyboard(has_job: bool = False, user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for work menu."""
    if has_job:
        keyboard = [
            [InlineKeyboardButton("💰 Работать", callback_data=f"work:do_job:{user_id}")],
            [InlineKeyboardButton("❌ Уволиться", callback_data=f"work:quit:{user_id}")],
            [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Выбрать профессию", callback_data=f"work:choose_profession:{user_id}")],
            [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
        ]
    return InlineKeyboardMarkup(keyboard)


def profession_selection_keyboard(user_id: int = 0, page: int = 1) -> InlineKeyboardMarkup:
    """Keyboard for profession selection (paginated, 18 professions)."""
    # All professions organized by category
    professions = [
        # Page 1: Government & Services (6)
        ("🚔 Интерпол", "interpol"),
        ("💳 Банкир", "banker"),
        ("🏗️ Инфраструктура", "infrastructure"),
        ("⚖️ Суд", "court"),
        ("🎭 Культура", "culture"),
        ("🏥 Медицина", "medic"),
        # Page 2: Professional (6)
        ("📚 Образование", "teacher"),
        ("📰 Журналистика", "journalist"),
        ("🚂 Транспорт", "transport"),
        ("🛡️ Охрана", "security"),
        ("👨‍🍳 Кулинария", "chef"),
        ("🎨 Искусство", "artist"),
        # Page 3: Modern & Fun (6)
        ("🔬 Наука", "scientist"),
        ("💻 IT", "programmer"),
        ("⚖️ Юрист", "lawyer"),
        ("🏆 Спорт", "athlete"),
        ("🎮 Стриминг", "streamer"),
        ("🐦 Селфмейд", "selfmade"),
    ]

    per_page = 6
    total_pages = 3
    start = (page - 1) * per_page
    end = start + per_page
    current_professions = professions[start:end]

    keyboard = []
    for name, code in current_professions:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"profession:{code}:{user_id}")])

    # Navigation row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"profession_page:{page - 1}:{user_id}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"profession_page:{page + 1}:{user_id}"))
    keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"menu:work:{user_id}")])

    return InlineKeyboardMarkup(keyboard)


def marriage_menu_keyboard(is_married: bool = False, user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for marriage menu."""
    if not is_married:
        keyboard = [
            [InlineKeyboardButton("💍 Найти пару", callback_data=f"marriage:info:{user_id}")],
            [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("🌙 Брачная ночь", callback_data=f"marriage:make_love:{user_id}"),
                InlineKeyboardButton("❤️ Свидание", callback_data=f"marriage:date:{user_id}"),
            ],
            [
                InlineKeyboardButton("💝 Подарить", callback_data=f"marriage_gift:{user_id}"),
                InlineKeyboardButton("👨‍👩‍👧‍👦 Дети", callback_data=f"menu:family:{user_id}"),
            ],
            [
                InlineKeyboardButton("📋 Инфо", callback_data=f"marriage:info:{user_id}"),
                InlineKeyboardButton("💔 Развод", callback_data=f"marriage:divorce:{user_id}"),
            ],
            [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
        ]
    return InlineKeyboardMarkup(keyboard)


def family_menu_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for family/children menu."""
    keyboard = [
        [
            InlineKeyboardButton("👶 Дети", callback_data=f"family:list:{user_id}"),
            InlineKeyboardButton("🍼 Родить", callback_data=f"family:birth_menu:{user_id}"),
        ],
        [
            InlineKeyboardButton("🍽️ Покормить", callback_data=f"family:feed_all:{user_id}"),
            InlineKeyboardButton("📈 Вырастить", callback_data=f"family:age_all:{user_id}"),
        ],
        [InlineKeyboardButton("👩‍🍼 Няня", callback_data=f"family:babysitter:{user_id}")],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def house_menu_keyboard(has_house: bool = False, user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for house menu."""
    if has_house:
        keyboard = [
            [InlineKeyboardButton("🏠 Мой дом", callback_data=f"house:info:{user_id}")],
            [InlineKeyboardButton("💰 Продать дом", callback_data=f"house:sell:{user_id}")],
            [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🏠 Купить дом", callback_data=f"house:buy:{user_id}")],
            [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
        ]
    return InlineKeyboardMarkup(keyboard)


def house_buy_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for buying houses."""
    keyboard = [
        [InlineKeyboardButton("🏚️ Хибара (1,000 💎)", callback_data=f"house:buy_confirm:1:{user_id}")],
        [InlineKeyboardButton("🏡 Деревянный домик (5,000 💎)", callback_data=f"house:buy_confirm:2:{user_id}")],
        [InlineKeyboardButton("🏠 Каменный дом (20,000 💎)", callback_data=f"house:buy_confirm:3:{user_id}")],
        [InlineKeyboardButton("🏘️ Коттедж (100,000 💎)", callback_data=f"house:buy_confirm:4:{user_id}")],
        [InlineKeyboardButton("🏰 Особняк (500,000 💎)", callback_data=f"house:buy_confirm:5:{user_id}")],
        [InlineKeyboardButton("🏯 Замок (2,000,000 💎)", callback_data=f"house:buy_confirm:6:{user_id}")],
        [InlineKeyboardButton("« Назад", callback_data=f"menu:house:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def business_menu_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for business menu."""
    keyboard = [
        [InlineKeyboardButton("📊 Мои бизнесы", callback_data=f"business:list:{user_id}")],
        [
            InlineKeyboardButton("🛒 Купить", callback_data=f"business:buy:{user_id}"),
            InlineKeyboardButton("💰 Продать", callback_data=f"business:sell:{user_id}"),
        ],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def business_buy_keyboard(user_id: int = 0, page: int = 1) -> InlineKeyboardMarkup:
    """Keyboard for buying businesses (paginated, 12 businesses)."""
    # All businesses organized by tier
    businesses = [
        # Tier 1: Starter
        (1, "🏪 Палатка на рынке", "1,000"),
        (2, "🌭 Киоск с хот-догами", "2,000"),
        (3, "☕ Кофейня", "3,500"),
        (4, "🏬 Магазин на спавне", "5,000"),
        # Tier 2: Medium
        (5, "🍕 Пиццерия", "10,000"),
        (6, "🎮 Игровой клуб", "20,000"),
        (7, "🏦 Филиал банка", "25,000"),
        (8, "🏨 Отель", "50,000"),
        # Tier 3: Premium
        (9, "🏙️ Свой город", "150,000"),
        (10, "🏭 Завод", "250,000"),
        (11, "✈️ Авиакомпания", "400,000"),
        (12, "🌐 IT-корпорация", "500,000"),
    ]

    per_page = 4
    total_pages = 3
    start = (page - 1) * per_page
    end = start + per_page
    current_businesses = businesses[start:end]

    keyboard = []
    for biz_id, name, price in current_businesses:
        keyboard.append(
            [InlineKeyboardButton(f"{name} ({price} 💎)", callback_data=f"business:buy_confirm:{biz_id}:{user_id}")]
        )

    # Navigation row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"business:buy_page:{page - 1}:{user_id}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"business:buy_page:{page + 1}:{user_id}"))
    keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"menu:business:{user_id}")])

    return InlineKeyboardMarkup(keyboard)


def confirm_keyboard(action: str, user_id: int = 0) -> InlineKeyboardMarkup:
    """Generic confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=f"work:{action}_confirmed:{user_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"work:{action}_cancelled:{user_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def casino_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Casino menu with game buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🎰 Слоты", callback_data=f"casino_info:slots:{user_id}"),
            InlineKeyboardButton("🎲 Кости", callback_data=f"casino_info:dice:{user_id}"),
            InlineKeyboardButton("🎯 Дартс", callback_data=f"casino_info:darts:{user_id}"),
        ],
        [
            InlineKeyboardButton("🃏 Блэкджек", callback_data=f"casino_info:blackjack:{user_id}"),
            InlineKeyboardButton("🎫 Скретч", callback_data=f"casino_info:scratch:{user_id}"),
        ],
        [
            InlineKeyboardButton("🪙 Монетка", callback_data=f"casino_info:coinflip:{user_id}"),
            InlineKeyboardButton("📊 Статистика", callback_data=f"casino_info:stats:{user_id}"),
        ],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def casino_after_game_keyboard(game_type: str, user_id: int, bet: int = None) -> InlineKeyboardMarkup:
    """Buttons after casino game: play again (same bet) + change bet + casino menu."""
    row = []
    if bet:
        row.append(InlineKeyboardButton(f"🔄 Ещё ({bet})", callback_data=f"cbet:{game_type}:{bet}:{user_id}"))
        row.append(InlineKeyboardButton("💰 Ставка", callback_data=f"casino_info:{game_type}:{user_id}"))
    else:
        row.append(InlineKeyboardButton("🔄 Ещё раз", callback_data=f"casino_info:{game_type}:{user_id}"))
    keyboard = [
        row,
        [InlineKeyboardButton("🎰 Казино", callback_data=f"menu:casino:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def bet_picker_keyboard(game: str, user_id: int, vip: bool = False) -> InlineKeyboardMarkup:
    """Universal bet picker for casino games. VIP users see higher bet options."""
    if vip:
        keyboard = [
            [
                InlineKeyboardButton("100", callback_data=f"cbet:{game}:100:{user_id}"),
                InlineKeyboardButton("250", callback_data=f"cbet:{game}:250:{user_id}"),
                InlineKeyboardButton("500", callback_data=f"cbet:{game}:500:{user_id}"),
            ],
            [
                InlineKeyboardButton("1000", callback_data=f"cbet:{game}:1000:{user_id}"),
                InlineKeyboardButton("2000", callback_data=f"cbet:{game}:2000:{user_id}"),
                InlineKeyboardButton("All-in", callback_data=f"cbet:{game}:all:{user_id}"),
            ],
            [InlineKeyboardButton("« Казино", callback_data=f"menu:casino:{user_id}")],
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("50", callback_data=f"cbet:{game}:50:{user_id}"),
                InlineKeyboardButton("100", callback_data=f"cbet:{game}:100:{user_id}"),
                InlineKeyboardButton("250", callback_data=f"cbet:{game}:250:{user_id}"),
            ],
            [
                InlineKeyboardButton("500", callback_data=f"cbet:{game}:500:{user_id}"),
                InlineKeyboardButton("1000", callback_data=f"cbet:{game}:1000:{user_id}"),
                InlineKeyboardButton("All-in", callback_data=f"cbet:{game}:all:{user_id}"),
            ],
            [InlineKeyboardButton("« Казино", callback_data=f"menu:casino:{user_id}")],
        ]
    return InlineKeyboardMarkup(keyboard)


def economy_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Economy submenu."""
    keyboard = [
        [
            InlineKeyboardButton("💼 Бизнес", callback_data=f"menu:business:{user_id}"),
            InlineKeyboardButton("🏠 Дом", callback_data=f"menu:house:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎁 Бонус", callback_data=f"econ:daily:{user_id}"),
            InlineKeyboardButton("🎟 Лотерея", callback_data=f"econ:lottery:{user_id}"),
        ],
        [
            InlineKeyboardButton("🏪 Магазин", callback_data=f"econ:shop:{user_id}"),
            InlineKeyboardButton("🔄 Престиж", callback_data=f"econ:prestige:{user_id}"),
        ],
        [
            InlineKeyboardButton("🏛 Налоги", callback_data=f"econ:tax:{user_id}"),
            InlineKeyboardButton("⭐ Премиум", callback_data=f"econ:premium:{user_id}"),
        ],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def games_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Games submenu."""
    keyboard = [
        [
            InlineKeyboardButton("🐾 Питомец", callback_data=f"econ:pet:{user_id}"),
            InlineKeyboardButton("🎣 Рыбалка", callback_data=f"econ:fish:{user_id}"),
        ],
        [
            InlineKeyboardButton("⛏️ Шахта", callback_data=f"econ:mine:{user_id}"),
            InlineKeyboardButton("🎡 Колесо", callback_data=f"econ:wheel:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎯 Квест", callback_data=f"econ:quest:{user_id}"),
            InlineKeyboardButton("⚔️ Дуэль", callback_data=f"econ:duel:{user_id}"),
        ],
        [
            InlineKeyboardButton("🔫 Ограбление", callback_data=f"econ:rob:{user_id}"),
            InlineKeyboardButton("🔫 Рулетка", callback_data=f"econ:roulette:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎁 Сундуки", callback_data=f"econ:crate:{user_id}"),
            InlineKeyboardButton("🛡 Страховка", callback_data=f"econ:insurance:{user_id}"),
        ],
        [
            InlineKeyboardButton("🏦 Ограбление банка", callback_data=f"econ:heist:{user_id}"),
        ],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def social_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Social submenu."""
    keyboard = [
        [
            InlineKeyboardButton("👥 Друзья", callback_data=f"econ:friends:{user_id}"),
            InlineKeyboardButton("🔫 Банда", callback_data=f"econ:gang:{user_id}"),
        ],
        [
            InlineKeyboardButton("💥 Рейд", callback_data=f"econ:raid:{user_id}"),
            InlineKeyboardButton("⚔️ Война кланов", callback_data=f"econ:clanwar:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎯 Награды", callback_data=f"econ:bounties:{user_id}"),
            InlineKeyboardButton("🏆 Достижения", callback_data=f"econ:achievements:{user_id}"),
        ],
        [
            InlineKeyboardButton("⭐ Рейтинг", callback_data=f"econ:rating:{user_id}"),
            InlineKeyboardButton("🏆 Топ", callback_data=f"econ:top:{user_id}"),
        ],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)
