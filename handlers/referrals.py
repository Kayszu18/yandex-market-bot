import logging
from aiogram import types, Bot
from aiogram.dispatcher.filters import Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database import get_user_referrals, get_user, get_setting
from keyboards.user_keyboards import main_menu_kb
from utils.filters import IsPrivate, IsNotBlocked, IsPrivateCallback, IsNotBlockedCallback

logger = logging.getLogger(__name__)

def format_username(user: dict) -> str:
    """Formats the username or user ID for display."""
    return f"@{user['username']}" if user and user.get('username') else f"ID: {user['id']}"

async def send_referrals_stats(user_id: int, bot: Bot, message: types.Message = None, callback: types.CallbackQuery = None):
    """
    Sends referral statistics to the user.
    Args:
        user_id: ID of the user.
        bot: Telegram Bot instance.
        message: Message object for direct replies.
        callback: CallbackQuery object for inline updates.
    """
    try:
        referrals = get_user_referrals(user_id)
        total_referrals = len(referrals)
        total_bonus = sum(ref.get('bonus', 0) for ref in referrals)

        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

        text = (
            f"<b>👥 Referral statistikangiz:</b>\n\n"
            f"📊 Jami referallar: {total_referrals} ta\n"
            f"💸 Jami bonus: {total_bonus} so‘m\n"
            f"🔗 <a href='{ref_link}'>Sizning referral havolangiz</a>\n\n"
        )

        if referrals:
            text += "<b>📋 Referal foydalanuvchilar:</b>\n"
            for ref in referrals:
                referred_user = get_user(ref['referred_id'])
                username = format_username(referred_user)
                level = ref.get('level', 1)
                text += f"- {username} (Bonus: {ref['bonus']} so‘m, {level}-daraja)\n"
        else:
            text += "Hozircha referal foydalanuvchilar yo‘q. Do‘stlaringizni taklif qiling va bonus oling!"

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📋 Havolani nusxalash", callback_data="copy_ref_link"),
            InlineKeyboardButton("ℹ️ Referral haqida", callback_data="referral_info")
        )
        kb.add(InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main"))

        if callback:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            await callback.answer()
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

        # Notify admins about referral activity (optional)
        admin_chat = get_setting("admin_chat_id")
        if admin_chat and total_referrals > 0:
            try:
                await bot.send_message(
                    admin_chat,
                    f"📢 Foydalanuvchi {user_id} referral statistikasini ko‘rdi:\n"
                    f"Referallar: {total_referrals} ta, Jami bonus: {total_bonus} so‘m",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin about referral stats: {e}")

    except Exception as e:
        logger.exception(f"Referral stats failed for user {user_id}: {e}")
        error_text = "❌ Xato yuz berdi, iltimos qayta urinib ko‘ring."
        if callback:
            await callback.message.edit_text(error_text, reply_markup=main_menu_kb())
            await callback.answer()
        else:
            await message.answer(error_text, reply_markup=main_menu_kb())

async def cmd_referrals(message: types.Message):
    """Handles the /referrals command."""
    await send_referrals_stats(message.from_user.id, message.bot, message=message)

async def show_referrals(message: types.Message):
    """Handles the referrals menu button."""
    await send_referrals_stats(message.from_user.id, message.bot, message=message)

async def copy_ref_link(callback: types.CallbackQuery):
    """Handles the copy referral link action."""
    user_id = callback.from_user.id
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    await callback.message.answer(
        f"🔗 Referral havolangiz:\n{ref_link}\n\nHavolani nusxalash uchun bosing va do‘stlaringizga yuboring!",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )
    await callback.answer("✅ Havola nusxalash uchun tayyor!")

async def referral_info(callback: types.CallbackQuery):
    """Shows information about the referral program."""
    info_text = get_setting("referral_info_text") or (
        "<b>ℹ️ Referral dasturi haqida:</b>\n\n"
        "Do‘stlaringizni botga taklif qiling va har bir faol referal uchun bonus oling!\n"
        "- Har bir 1-daraja referal uchun: <b>500 so‘m</b>\n"
        "- Referal faol bo‘lsa (zakaz qilsa), qo‘shimcha bonuslar mavjud.\n"
        "Havolangizni do‘stlaringiz bilan ulashing va daromad oling!"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔙 Ortga", callback_data="referrals"),
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
    )
    await callback.message.edit_text(info_text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

async def back_to_main_menu(callback: types.CallbackQuery):
    """Returns to the main menu."""
    await callback.message.edit_text("🏠 Asosiy menyu:", reply_markup=main_menu_kb())
    await callback.answer()

def register_handlers(dp):
    """Registers all message and callback query handlers."""
    dp.register_message_handler(cmd_referrals, IsPrivate(), IsNotBlocked(), commands=['referrals'])
    dp.register_message_handler(show_referrals, IsPrivate(), IsNotBlocked(), Text(equals="👥 Referallar"), state='*')
    dp.register_callback_query_handler(copy_ref_link, IsPrivateCallback(), IsNotBlockedCallback(), Text(equals="copy_ref_link"), state='*')
    dp.register_callback_query_handler(referral_info, IsPrivateCallback(), IsNotBlockedCallback(), Text(equals="referral_info"), state='*')
    dp.register_callback_query_handler(back_to_main_menu, IsPrivateCallback(), IsNotBlockedCallback(), Text(equals="back_to_main"), state='*')