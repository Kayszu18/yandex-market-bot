from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_setting, is_user_blocked

# --- HELPER FUNCTION ---
def _create_inline_kb(buttons: list[tuple[str, str]], row_width: int = 2) -> InlineKeyboardMarkup:
    """
    Creates an inline keyboard with the given buttons.
    Args:
        buttons: List of tuples (text, callback_data).
        row_width: Number of buttons per row.
    Returns:
        InlineKeyboardMarkup object.
    """
    kb = InlineKeyboardMarkup(row_width=row_width)
    for text, callback_data in buttons:
        kb.add(InlineKeyboardButton(text=text, callback_data=callback_data))
    kb.add(InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main"))
    return kb

# --- ADMIN MAIN MENU ---
def admin_main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Creates the main admin menu keyboard.
    Uses settings from the database for button text.
    """
    buttons = [
        [
            KeyboardButton(text=get_setting("admin_menu_stats") or "📊 Statistika"),
            KeyboardButton(text=get_setting("admin_menu_export") or "📂 Excel eksport")
        ],
        [
            KeyboardButton(text=get_setting("admin_menu_broadcast") or "📨 Xabar yuborish"),
            KeyboardButton(text=get_setting("admin_menu_user_manage") or "👤 Foydalanuvchi boshqaruvi"),
            KeyboardButton(text=get_setting("admin_menu_users_list") or "👥 Foydalanuvchilar ro'yxati")
        ],
        [
            KeyboardButton(text=get_setting("admin_menu_orders") or "📦 Zakazlarni boshqarish"),
            KeyboardButton(text=get_setting("admin_menu_withdraws") or "💸 Pul yechib olish so'rovlari")
        ],
        [
            KeyboardButton(text=get_setting("admin_menu_ad_text") or "📝 Reklama matnini o'zgartirish")
        ],
        [
            KeyboardButton(text=get_setting("admin_menu_guide_video") or "📹 Qo'llanma video yuklash")
        ],
        [KeyboardButton(text=get_setting("admin_menu_back") or "🔙 Oddiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

# --- INLINE KEYBOARDS ---

# Xabar yuborish turini tanlash
def broadcast_inline_kb() -> InlineKeyboardMarkup:
    """
    Creates the broadcast selection keyboard.
    """
    buttons = [
        ("📢 Hamma foydalanuvchilarga", "broadcast_all"),
        ("✉️ Bitta foydalanuvchiga", "broadcast_one"),
        ("❌ Bekor qilish", "cancel_broadcast")
    ]
    return _create_inline_kb(buttons, row_width=2)

# Foydalanuvchi boshqaruvi
def user_manage_inline_kb(user_id: int) -> InlineKeyboardMarkup:
    """
    Creates the user management keyboard.
    Dynamically adjusts block/unblock button based on user status.
    Args:
        user_id: ID of the user to manage.
    """
    is_blocked = is_user_blocked(user_id)
    buttons = [
        ("🚫 Bloklash" if not is_blocked else "✅ Blokdan chiqarish", f"{'block' if not is_blocked else 'unblock'}_{user_id}"),
        ("📩 Xabar yuborish", f"send_message_{user_id}")
    ]
    return _create_inline_kb(buttons, row_width=2)

# Reklama matnini o‘zgartirish
def ad_text_change_inline_kb() -> InlineKeyboardMarkup:
    """
    Creates the ad text change keyboard.
    """
    buttons = [
        ("✏️ Matnni o‘zgartirish", "edit_ad_text")
    ]
    return _create_inline_kb(buttons, row_width=2)

# Qo‘llanma video yuklash
def guide_video_inline_kb() -> InlineKeyboardMarkup:
    """
    Creates the guide video upload keyboard.
    """
    buttons = [
        ("📤 Yangi video yuklash", "upload_guide_video")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- SUPPORT REPLY INLINE KEYBOARD ---
def support_reply_inline_kb(user_id: int, support_id: str = None) -> InlineKeyboardMarkup:
    """
    Creates the support reply keyboard.
    Args:
        user_id: ID of the user to reply to.
        support_id: Optional support request ID.
    """
    callback_data = f"reply_{user_id}_{support_id}" if support_id else f"reply_{user_id}"
    buttons = [
        ("✏️ Javob yozish", callback_data)
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- WITHDRAW MANAGE INLINE KEYBOARD ---
def withdraw_manage_inline_kb(withdraw_id: int) -> InlineKeyboardMarkup:
    """
    Creates the withdraw request management keyboard.
    Args:
        withdraw_id: ID of the withdraw request.
    """
    buttons = [
        ("✅ Tasdiqlash", f"withdraw_accept_{withdraw_id}"),
        ("❌ Rad etish", f"withdraw_reject_{withdraw_id}")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- BROADCAST PREVIEW KEYBOARD ---
def broadcast_preview_inline_kb(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Creates the broadcast preview keyboard.
    Args:
        broadcast_id: ID of the broadcast message.
    """
    buttons = [
        ("📤 Oldindan ko'rish", f"preview_broadcast_{broadcast_id}"),
        ("✅ Yuborish", f"send_broadcast_{broadcast_id}"),
        ("✏️ Tahrirlash", "edit_broadcast"),
        ("❌ Bekor qilish", "cancel_broadcast")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- USERS LIST KEYBOARD ---
def users_list_inline_kb() -> InlineKeyboardMarkup:
    """
    Creates the users list keyboard.
    """
    buttons = [
        ("📋 Barcha foydalanuvchilar", "view_all_users"),
        ("📅 Bugungi foydalanuvchilar", "view_today_users"),
        ("📊 Faol foydalanuvchilar", "view_active_users"),
        ("📤 Excel export", "export_users_excel")
    ]
    return _create_inline_kb(buttons, row_width=2)

# --- USER PAGINATION KEYBOARD ---
def user_pagination_inline_kb(page: int, total_pages: int, action: str) -> InlineKeyboardMarkup:
    """
    Creates the user pagination keyboard.
    Args:
        page: Current page number.
        total_pages: Total number of pages.
        action: Action prefix for callback data.
    """
    buttons = []
    
    # Previous page button
    if page > 1:
        buttons.append(("⬅️ Oldingi", f"{action}_page_{page-1}"))
    
    # Next page button
    if page < total_pages:
        buttons.append(("➡️ Keyingi", f"{action}_page_{page+1}"))
    
    # Page info
    buttons.append((f"📄 {page}/{total_pages}", "noop"))
    
    return _create_inline_kb(buttons, row_width=3)