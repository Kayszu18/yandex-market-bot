import logging
import datetime
from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import BotBlocked, UserDeactivated
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import get_admin_list, get_user, insert_support_message, update_support_reply
from keyboards.user_keyboards import main_menu_kb, cancel_kb
from keyboards.admin_keyboards import support_reply_inline_kb
from utils.filters import IsPrivateCallback, IsNotBlockedCallback, IsAdminCallback

logger = logging.getLogger(__name__)

# States
class SupportStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_admin_reply = State()
    waiting_for_reply_preview = State()

# Maksimal xabar uzunligi
MAX_MESSAGE_LENGTH = 1000

def validate_message(text: str) -> bool:
    """Validates the support message length and content."""
    if not text or len(text.strip()) == 0:
        return False
    if len(text) > MAX_MESSAGE_LENGTH:
        return False
    return True

async def ask_support_message(message: types.Message, state: FSMContext):
    """Prompts the user to send a support message."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
        KeyboardButton("🏠 Asosiy menyu")
    )
    await message.answer(
        "✏️ Savolingizni yoki muammoingizni yozing (maksimal 1000 belgi).\n"
        "📎 Rasm yoki hujjat yuborishingiz mumkin.\n"
        "❌ Bekor qilish uchun /cancel bosing.",
        reply_markup=kb
    )
    await SupportStates.waiting_for_message.set()

async def forward_support_message(message: types.Message, state: FSMContext):
    """Forwards the user's support message to admins."""
    user_id = message.from_user.id
    support_id = f"SUP_{user_id}_{int(datetime.datetime.now().timestamp())}"
    text = message.html_text if message.text else ""
    file_id = None
    file_type = None

    # Validate message
    if text and not validate_message(text):
        await message.answer(
            "❌ Xabar 1000 belgidan oshmasligi kerak yoki bo‘sh bo‘lmasligi kerak.",
            reply_markup=main_menu_kb()
        )
        return

    # Check for file (photo or document)
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"

    # Save to database
    try:
        insert_support_message(user_id, support_id, text or "", file_id, file_type)
    except Exception as e:
        logger.exception(f"Failed to save support message {support_id}: {e}")
        await message.answer(
            "❌ Xabar yuborishda xato yuz berdi. Iltimos, qayta urinib ko‘ring.",
            reply_markup=main_menu_kb()
        )
        await state.finish()
        return

    # Forward to admins
    admins = get_admin_list()
    if not admins:
        await message.answer(
            "❌ Adminlar topilmadi. Iltimos, keyinroq qayta urinib ko‘ring.",
            reply_markup=main_menu_kb()
        )
        await state.finish()
        return

    user = get_user(user_id)
    user_info = (
        f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name} (@{message.from_user.username or 'N/A'}, ID: {user_id})\n"
        f"📞 <b>Telefon:</b> {user.get('phone', 'Yo‘q')}\n"
        f"💰 <b>Balans:</b> {user.get('balance', 0)} so‘m\n"
        f"💬 <b>Xabar:</b> {text or 'Fayl yuborildi'}\n"
        f"🆔 <b>Support ID:</b> {support_id}"
    )

    for admin_id in admins:
        try:
            if file_id and file_type == "photo":
                await message.bot.send_photo(
                    admin_id,
                    file_id,
                    caption=user_info,
                    parse_mode="HTML",
                    reply_markup=support_reply_inline_kb(user_id, support_id)
                )
            elif file_id and file_type == "document":
                await message.bot.send_document(
                    admin_id,
                    file_id,
                    caption=user_info,
                    parse_mode="HTML",
                    reply_markup=support_reply_inline_kb(user_id, support_id)
                )
            else:
                await message.bot.send_message(
                    admin_id,
                    user_info,
                    parse_mode="HTML",
                    reply_markup=support_reply_inline_kb(user_id, support_id)
                )
        except (BotBlocked, UserDeactivated):
            logger.warning(f"Failed to send support message to admin {admin_id}")
        except Exception as e:
            logger.error(f"Unexpected error sending to admin {admin_id}: {e}")

    await message.answer(
        f"✅ Xabaringiz adminlarga yuborildi (ID: {support_id}).\n"
        "Javobni shu yerda olasiz.",
        reply_markup=main_menu_kb()
    )
    await state.finish()

async def cancel_support(message: types.Message, state: FSMContext):
    """Cancels the support message process."""
    await state.finish()
    await message.answer("❌ Xabar yuborish bekor qilindi.", reply_markup=main_menu_kb())

async def ask_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    """Prompts the admin to reply to a support message."""
    data = callback.data.split("_")
    user_id = int(data[1])
    support_id = data[2] if len(data) > 2 else None
    await state.update_data(reply_to_user=user_id, support_id=support_id)

    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("📤 Oldindan ko‘rish", callback_data=f"preview_reply_{user_id}_{support_id}"),
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
    )
    await callback.message.answer(
        f"✏️ <b>{user_id}</b> foydalanuvchiga yuboriladigan javobni kiriting (HTML formatlash mumkin, maksimal 1000 belgi):\n"
        f"🆔 Support ID: {support_id}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await SupportStates.waiting_for_admin_reply.set()
    await callback.answer()

async def preview_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    """Shows a preview of the admin's reply."""
    data = await state.get_data()
    reply_text = data.get("admin_reply_text")
    if not reply_text:
        await callback.answer("⚠️ Oldin javob matnini kiriting!", show_alert=True)
        return
    user_id = data.get("reply_to_user")
    support_id = data.get("support_id")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Yuborish", callback_data=f"send_reply_{user_id}_{support_id}"),
        InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_reply_{user_id}_{support_id}"),
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
    )
    await callback.message.answer(
        f"📩 <b>Foydalanuvchiga yuboriladigan javob (ID: {support_id}):</b>\n\n{reply_text}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

async def send_admin_reply(message: types.Message, state: FSMContext):
    """Saves the admin's reply for preview."""
    reply_text = message.html_text
    if not validate_message(reply_text):
        await message.answer(
            "❌ Javob 1000 belgidan oshmasligi kerak yoki bo‘sh bo‘lmasligi kerak.",
            reply_markup=main_menu_kb()
        )
        return
    await state.update_data(admin_reply_text=reply_text)
    data = await state.get_data()
    user_id = data.get("reply_to_user")
    support_id = data.get("support_id")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Yuborish", callback_data=f"send_reply_{user_id}_{support_id}"),
        InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_reply_{user_id}_{support_id}"),
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
    )
    await message.answer(
        f"📩 <b>Foydalanuvchiga yuboriladigan javob (ID: {support_id}):</b>\n\n{reply_text}",
        parse_mode="HTML",
        reply_markup=kb
    )

async def confirm_send_reply(callback: types.CallbackQuery, state: FSMContext):
    """Sends the admin's reply to the user."""
    data = await state.get_data()
    user_id = data.get("reply_to_user")
    support_id = data.get("support_id")
    reply_text = data.get("admin_reply_text")

    try:
        await callback.bot.send_message(
            user_id,
            f"📩 <b>Admin javobi (ID: {support_id}):</b>\n\n{reply_text}",
            parse_mode="HTML"
        )
        await callback.message.edit_text("✅ Javob foydalanuvchiga yuborildi.", reply_markup=main_menu_kb())

        # Update database
        try:
            update_support_reply(support_id, reply_text)
        except Exception as e:
            logger.exception(f"Failed to update support reply {support_id}: {e}")

    except (BotBlocked, UserDeactivated):
        await callback.message.edit_text(
            "❌ Javob yuborilmadi (foydalanuvchi botni bloklagan bo‘lishi mumkin).",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        await callback.message.edit_text("❌ Xatolik yuz berdi.", reply_markup=main_menu_kb())
        logger.error(f"Unexpected error sending admin reply to {user_id}: {e}")

    await state.finish()
    await callback.answer()

async def edit_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    """Allows the admin to edit the reply."""
    data = await state.get_data()
    user_id = data.get("reply_to_user")
    support_id = data.get("support_id")
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("📤 Oldindan ko‘rish", callback_data=f"preview_reply_{user_id}_{support_id}"),
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
    )
    await callback.message.answer(
        f"✏️ <b>{user_id}</b> foydalanuvchiga yuboriladigan yangi javobni kiriting (HTML formatlash mumkin, maksimal 1000 belgi):\n"
        f"🆔 Support ID: {support_id}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await SupportStates.waiting_for_admin_reply.set()
    await callback.answer()

async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    """Returns to the main menu."""
    await state.finish()
    await callback.message.edit_text("🏠 Asosiy menyu:", reply_markup=main_menu_kb())
    await callback.answer()

def register_handlers(dp: Dispatcher):
    """Registers all message and callback query handlers."""
    dp.register_message_handler(ask_support_message, Text(equals="🆘 Support"), state="*")
    dp.register_message_handler(forward_support_message, content_types=['text', 'photo', 'document'], state=SupportStates.waiting_for_message)
    dp.register_message_handler(cancel_support, commands=["cancel"], state="*")
    dp.register_message_handler(cancel_support, Text(equals="🏠 Asosiy menyu"), state="*")
    dp.register_callback_query_handler(ask_admin_reply, lambda c: c.data.startswith("reply_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(send_admin_reply, content_types=['text'], state=SupportStates.waiting_for_admin_reply)
    dp.register_callback_query_handler(preview_admin_reply, lambda c: c.data.startswith("preview_reply_"), IsPrivateCallback(), IsAdminCallback(), state=SupportStates.waiting_for_admin_reply)
    dp.register_callback_query_handler(confirm_send_reply, lambda c: c.data.startswith("send_reply_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(edit_admin_reply, lambda c: c.data.startswith("edit_reply_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(back_to_main_menu, Text(equals="back_to_main"), IsPrivateCallback(), IsNotBlockedCallback(), state="*")