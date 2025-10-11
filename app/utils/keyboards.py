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


def profile_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for profile (quick access to main menus)."""
    keyboard = [
        [InlineKeyboardButton("💼 Работа", callback_data="menu:work")],
        [InlineKeyboardButton("💍 Брак", callback_data="menu:marriage")],
        [InlineKeyboardButton("👨‍👩‍👧‍👦 Семья [Не реализовано]", callback_data="menu:family")],
        [InlineKeyboardButton("🏠 Дом [Не реализовано]", callback_data="menu:house")],
        [InlineKeyboardButton("💼 Бизнес [Не реализовано]", callback_data="menu:business")],
    ]
    return InlineKeyboardMarkup(keyboard)


def work_menu_keyboard(has_job: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for work menu."""
    if has_job:
        keyboard = [
            [InlineKeyboardButton("💰 Работать", callback_data="work:do_job")],
            [InlineKeyboardButton("❌ Уволиться", callback_data="work:quit")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Выбрать профессию", callback_data="work:choose_profession")],
        ]
    return InlineKeyboardMarkup(keyboard)


def profession_selection_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for profession selection."""
    keyboard = [
        [InlineKeyboardButton("🚔 Интерпол", callback_data="profession:interpol")],
        [InlineKeyboardButton("💳 Банкир", callback_data="profession:banker")],
        [InlineKeyboardButton("🏗️ Инфраструктура", callback_data="profession:infrastructure")],
        [InlineKeyboardButton("⚖️ Суд", callback_data="profession:court")],
        [InlineKeyboardButton("🎭 Культура", callback_data="profession:culture")],
        [InlineKeyboardButton("🐦 Селфмейд", callback_data="profession:selfmade")],
        [InlineKeyboardButton("« Назад", callback_data="menu:work")],
    ]
    return InlineKeyboardMarkup(keyboard)


def marriage_menu_keyboard(is_married: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for marriage menu."""
    if not is_married:
        keyboard = [
            [InlineKeyboardButton("💍 Найти пару", callback_data="marriage:info")],
            [InlineKeyboardButton("« Назад", callback_data="menu:profile")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🌙 Брачная ночь", callback_data="marriage:make_love")],
            [InlineKeyboardButton("❤️ Свидание", callback_data="marriage:date")],
            [InlineKeyboardButton("💔 Изменить", callback_data="marriage:cheat")],
            [InlineKeyboardButton("📋 Инфо о браке", callback_data="marriage:info")],
            [InlineKeyboardButton("👥 Семья", callback_data="marriage:family")],
            [InlineKeyboardButton("💰 Бюджет", callback_data="marriage:budget")],
            [InlineKeyboardButton("✏️ Фамилия", callback_data="marriage:set_family_name")],
            [InlineKeyboardButton("💔 Развестись", callback_data="marriage:divorce")],
            [InlineKeyboardButton("« Назад", callback_data="menu:profile")],
        ]
    return InlineKeyboardMarkup(keyboard)


def family_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for family/children menu."""
    keyboard = [
        [InlineKeyboardButton("👶 Список детей", callback_data="family:list_children")],
        [InlineKeyboardButton("🍼 Родить ребёнка", callback_data="family:have_child")],
        [InlineKeyboardButton("🍽️ Покормить всех", callback_data="family:feed_all")],
        [InlineKeyboardButton("📈 Вырастить всех", callback_data="family:age_all")],
        [InlineKeyboardButton("👩‍🍼 Няня", callback_data="family:babysitter")],
        [InlineKeyboardButton("« Назад", callback_data="menu:profile")],
    ]
    return InlineKeyboardMarkup(keyboard)


def house_menu_keyboard(has_house: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for house menu."""
    if has_house:
        keyboard = [
            [InlineKeyboardButton("🏠 Мой дом", callback_data="house:info")],
            [InlineKeyboardButton("💰 Продать дом", callback_data="house:sell")],
            [InlineKeyboardButton("« Назад", callback_data="menu:profile")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🏠 Купить дом", callback_data="house:buy")],
            [InlineKeyboardButton("« Назад", callback_data="menu:profile")],
        ]
    return InlineKeyboardMarkup(keyboard)


def house_buy_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for buying houses."""
    keyboard = [
        [InlineKeyboardButton("🏚️ Хибара (1,000 💎)", callback_data="house:buy:1")],
        [InlineKeyboardButton("🏡 Деревянный домик (5,000 💎)", callback_data="house:buy:2")],
        [InlineKeyboardButton("🏠 Каменный дом (20,000 💎)", callback_data="house:buy:3")],
        [InlineKeyboardButton("🏘️ Коттедж (100,000 💎)", callback_data="house:buy:4")],
        [InlineKeyboardButton("🏰 Особняк (500,000 💎)", callback_data="house:buy:5")],
        [InlineKeyboardButton("🏯 Замок (2,000,000 💎)", callback_data="house:buy:6")],
        [InlineKeyboardButton("« Назад", callback_data="menu:house")],
    ]
    return InlineKeyboardMarkup(keyboard)


def business_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for business menu."""
    keyboard = [
        [InlineKeyboardButton("📊 Мои бизнесы", callback_data="business:list")],
        [InlineKeyboardButton("🛒 Купить бизнес", callback_data="business:buy")],
        [InlineKeyboardButton("💰 Продать бизнес", callback_data="business:sell")],
        [InlineKeyboardButton("« Назад", callback_data="menu:profile")],
    ]
    return InlineKeyboardMarkup(keyboard)


def business_buy_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for buying businesses."""
    keyboard = [
        [InlineKeyboardButton("🏪 Палатка на рынке (1,000 💎)", callback_data="business:buy:1")],
        [InlineKeyboardButton("🏬 Магазин на спавне (5,000 💎)", callback_data="business:buy:2")],
        [InlineKeyboardButton("🏦 Филиал банка (25,000 💎)", callback_data="business:buy:3")],
        [InlineKeyboardButton("🏙️ Свой город (150,000 💎)", callback_data="business:buy:4")],
        [InlineKeyboardButton("« Назад", callback_data="menu:business")],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Generic confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=f"work:{action}_confirmed"),
            InlineKeyboardButton("❌ Нет", callback_data=f"work:{action}_cancelled"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
