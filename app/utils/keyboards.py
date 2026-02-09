"""Inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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
        [InlineKeyboardButton("💼 Работа", callback_data=f"menu:work:{user_id}")],
        [InlineKeyboardButton("💍 Брак", callback_data=f"menu:marriage:{user_id}")],
        [InlineKeyboardButton("👨‍👩‍👧‍👦 Семья", callback_data=f"menu:family:{user_id}")],
        [InlineKeyboardButton("🏠 Дом", callback_data=f"menu:house:{user_id}")],
        [InlineKeyboardButton("💼 Бизнес", callback_data=f"menu:business:{user_id}")],
        [InlineKeyboardButton("🎰 Казино", callback_data=f"menu:casino:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def work_menu_keyboard(has_job: bool = False, user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for work menu."""
    if has_job:
        keyboard = [
            [InlineKeyboardButton("💰 Работать", callback_data=f"work:do_job:{user_id}")],
            [InlineKeyboardButton("❌ Уволиться", callback_data=f"work:quit:{user_id}")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Выбрать профессию", callback_data=f"work:choose_profession:{user_id}")],
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
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🌙 Брачная ночь", callback_data=f"marriage:make_love:{user_id}")],
            [InlineKeyboardButton("❤️ Свидание", callback_data=f"marriage:date:{user_id}")],
            [InlineKeyboardButton("💔 Изменить", callback_data=f"marriage:cheat:{user_id}")],
            [InlineKeyboardButton("📋 Инфо о браке", callback_data=f"marriage:info:{user_id}")],
            [InlineKeyboardButton("👥 Семья", callback_data=f"marriage:family:{user_id}")],
            [InlineKeyboardButton("💰 Бюджет", callback_data=f"marriage:budget:{user_id}")],
            [InlineKeyboardButton("✏️ Фамилия", callback_data=f"marriage:set_family_name:{user_id}")],
            [InlineKeyboardButton("💔 Развестись", callback_data=f"marriage:divorce:{user_id}")],
        ]
    return InlineKeyboardMarkup(keyboard)


def family_menu_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for family/children menu."""
    keyboard = [
        [InlineKeyboardButton("👶 Список детей", callback_data=f"family:list_children:{user_id}")],
        [InlineKeyboardButton("🍼 Родить ребёнка", callback_data=f"family:have_child:{user_id}")],
        [InlineKeyboardButton("🍽️ Покормить всех", callback_data=f"family:feed_all:{user_id}")],
        [InlineKeyboardButton("📈 Вырастить всех", callback_data=f"family:age_all:{user_id}")],
        [InlineKeyboardButton("👩‍🍼 Няня", callback_data=f"family:babysitter:{user_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def house_menu_keyboard(has_house: bool = False, user_id: int = 0) -> InlineKeyboardMarkup:
    """Keyboard for house menu."""
    if has_house:
        keyboard = [
            [InlineKeyboardButton("🏠 Мой дом", callback_data=f"house:info:{user_id}")],
            [InlineKeyboardButton("💰 Продать дом", callback_data=f"house:sell:{user_id}")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🏠 Купить дом", callback_data=f"house:buy:{user_id}")],
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
        [InlineKeyboardButton("🛒 Купить бизнес", callback_data=f"business:buy:{user_id}")],
        [InlineKeyboardButton("💰 Продать бизнес", callback_data=f"business:sell:{user_id}")],
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
