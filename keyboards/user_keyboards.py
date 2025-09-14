from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_setting, get_user_balance

# --- HELPER FUNCTION ---
def _create_inline_kb(buttons: list[tuple[str, str | dict]], row_width: int = 2) -> InlineKeyboardMarkup:
    """
    Creates an inline keyboard with the given buttons.
    Args:
        buttons: List of tuples (text, callback_data or URL dict).
        row_width: Number of buttons per row.
    Returns:
        InlineKeyboardMarkup object.
    """
    kb = InlineKeyboardMarkup(row_width=row_width)
    for text, data in buttons:
        if isinstance(data, dict) and "url" in data:
            kb.add(InlineKeyboardButton(text=text, url=data["url"]))
        else:
            kb.add(InlineKeyboardButton(text=text, callback_data=data))
    kb.add(InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main"))
    return kb

# --- USER MAIN MENU ---
def main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Creates the main user menu keyboard.
    Uses settings from the database for button text.
    """
    buttons = [
        [
            KeyboardButton(text=get_setting("user_menu_order") or "🛒 Zakaz berish")
        ],
        [
            KeyboardButton(text=get_setting("user_menu_balance") or "💰 Balans"),
            KeyboardButton(text=get_setting("user_menu_referrals") or "👥 Referallar")
        ],
        [
            KeyboardButton(text=get_setting("user_menu_withdraw") or "💸 Pul yechish"),
            KeyboardButton(text=get_setting("user_menu_support") or "🆘 Support")
        ],
        [
            KeyboardButton(text=get_setting("user_menu_withdraw_history") or "📜 Yechib olish tarixi"),
            KeyboardButton(text=get_setting("user_menu_support_history") or "📋 Support tarixi")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

# --- CANCEL KEYBOARD ---
def cancel_kb() -> ReplyKeyboardMarkup:
    """
    Creates the cancel keyboard.
    """
    buttons = [
        [
            KeyboardButton(text=get_setting("cancel_button") or "❌ Bekor qilish"),
            KeyboardButton(text=get_setting("user_menu_back") or "🏠 Asosiy menyu")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

# --- INLINE TUTORIAL BUTTONS ---
def tutorial_inline_kb() -> InlineKeyboardMarkup:
    """
    Creates the tutorial inline keyboard.
    """
    buttons = [
        ("📹 Qo‘llanma videoni ko‘rish", "watch_tutorial"),
        ("🔁 Yana ko‘rsat", "repeat_tutorial")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- INLINE REFERRAL BUTTONS ---
def referral_inline_kb(ref_link: str) -> InlineKeyboardMarkup:
    """
    Creates the referral sharing inline keyboard.
    Args:
        ref_link: The referral link to share.
    """
    buttons = [
        ("📤 Telegram'da ulashish", {"url": f"https://t.me/share/url?url={ref_link}"}),
        ("📱 WhatsApp'da ulashish", {"url": f"https://wa.me/?text={ref_link}"}),
        ("🔗 Havolani nusxalash", "copy_ref_link")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- REFERRAL MENU KEYBOARD ---
def referral_menu_kb() -> ReplyKeyboardMarkup:
    """
    Creates the referral menu keyboard.
    """
    buttons = [
        [KeyboardButton(text=get_setting("user_menu_back") or "🏠 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

# --- PAYMENT MENU KEYBOARD ---
def payment_menu_kb(user_id: int = None) -> ReplyKeyboardMarkup:
    """
    Creates the payment menu keyboard.
    Dynamically hides the withdraw button if balance is insufficient.
    Args:
        user_id: Optional user ID to check balance.
    """
    buttons = [
        [KeyboardButton(text=get_setting("user_menu_referrals") or "👥 Referallar")]
    ]
    if user_id and get_user_balance(user_id) >= 1000:  # Minimal yechib olish summasi 1000 so‘m
        buttons.insert(0, [KeyboardButton(text=get_setting("user_menu_withdraw") or "💸 Pul yechish")])
    buttons.append([KeyboardButton(text=get_setting("user_menu_back") or "🏠 Asosiy menyu")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

# --- WITHDRAW HISTORY KEYBOARD ---
def withdraw_history_kb() -> InlineKeyboardMarkup:
    """
    Creates the withdraw history inline keyboard.
    """
    buttons = [
        ("🔄 Yangilash", "refresh_withdraw_history")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- SUPPORT HISTORY KEYBOARD ---
def support_history_kb() -> InlineKeyboardMarkup:
    """
    Creates the support history inline keyboard.
    """
    buttons = [
        ("🔄 Yangilash", "refresh_support_history"),
        ("🆘 Yangi so‘rov", "new_support_request")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- Backward compatibility wrappers ---
def make_main_menu_inline() -> ReplyKeyboardMarkup:
    """
    Wrapper for main menu keyboard (backward compatibility).
    """
    return main_menu_kb()

def make_balance_menu_inline() -> ReplyKeyboardMarkup:
    """
    Wrapper for payment menu keyboard (backward compatibility).
    """
    return payment_menu_kb()