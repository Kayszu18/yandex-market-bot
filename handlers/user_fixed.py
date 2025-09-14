import logging
import re
from urllib.parse import urlparse

from aiogram import types, Bot
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import CommandStart, Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import (
    upsert_user,
    get_user,
    get_setting,
    get_user_orders,
    get_user_referrals,
    cancel_order as db_cancel_order,
    create_order,
    create_withdraw_request,
    get_or_create_user,
    get_help_video_file_id,
)
from keyboards.user_keyboards import main_menu_kb, payment_menu_kb
from utils.filters import IsPrivate, IsNotBlocked
from utils.helpers import bot_send_safe, bot_send_video_safe
from config import Config

logger = logging.getLogger(__name__)

# States for FSM
class UserStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_photo = State()
    waiting_for_wallet = State()
    waiting_for_withdraw_type = State()
    waiting_for_withdraw_amount = State()

def validate_card_number(card_number: str) -> bool:
    """Validates a 16-digit card number."""
    return bool(re.match(r'^\d{16}$', card_number.replace(" ", "")))

def validate_phone_number(phone: str) -> bool:
    """Validates a phone number starting with +998 followed by 9 digits."""
    return bool(re.match(r'^\+998\d{9}$', phone.replace(" ", "")))

def validate_trc20_address(wallet: str) -> bool:
    """Validates a TRC20 wallet address."""
    return bool(re.match(r'^T[1-9A-HJ-NP-Za-km-z]{33}$', wallet.strip()))

async def send_main_menu(user_id: int, bot: Bot):
    """Sends the main menu to the user."""
    await bot_send_safe(
        bot=bot,
        user_id=user_id,
        text="🏠 Asosiy menyu",
        reply_markup=main_menu_kb()
    )

async def cmd_start(message: types.Message):
    """
    Handles the /start command, registers the user, sends a welcome video, and shows the main menu.
    """
    user_id = message.from_user.id
    username = message.from_user.username
    logger.debug(f"Processing /start command for user {user_id}")

    # Handle referral if provided
    args = message.get_args()
    if args and args.startswith("ref_"):
        referrer_id = args.split("_")[1]
        try:
            get_or_create_user(user_id, username, referrer_id=int(referrer_id))
        except Exception as e:
            logger.warning(f"Failed to process referral for user {user_id}: {e}")
    else:
        get_or_create_user(user_id, username)

    # Help video file ID
    video_file_id = get_help_video_file_id()
    welcome_text = (
        f"Xush kelibsiz, {username or 'foydalanuvchi'}! 🎉\n"
        f"Botimizga xush kelibsiz! Quyida qo'llanma videoni ko'rishingiz mumkin.\n"
        f"To'lovlarni {Config.channel.PROOF_CHANNEL_USERNAME} kanalida ko'rishingiz mumkin.\n"
        f"Har qanday savol uchun {Config.channel.SUPPORT_USERNAME} bilan bog'laning."
    )

    # Send video or fallback to text
    try:
        if video_file_id:
            success = await bot_send_video_safe(
                bot=message.bot,
                user_id=user_id,
                video=video_file_id,
                caption=welcome_text,
                reply_markup=main_menu_kb()
            )
            if not success:
                logger.warning(f"Failed to send welcome video to user {user_id}")
                await bot_send_safe(
                    bot=message.bot,
                    user_id=user_id,
                    text=f"{welcome_text}\n⚠️ Qo'llanma videoni yuborishda xato yuz berdi.",
                    reply_markup=main_menu_kb()
                )
        else:
            logger.warning("Help video file ID not set in settings")
            await bot_send_safe(
                bot=message.bot,
                user_id=user_id,
                text=f"{welcome_text}\n⚠️ Qo'llanma video hali sozlanmagan.",
                reply_markup=main_menu_kb()
            )
    except Exception as e:
        logger.exception(f"Error in cmd_start for user {user_id}: {e}")
        await bot_send_safe(
            bot=message.bot,
            user_id=user_id,
            text="❌ Xato yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
            reply_markup=main_menu_kb()
        )

async def cmd_balance(message: types.Message):
    """Handles the /balance command to show user balance."""
    user = get_user(message.from_user.id)
    if user:
        balance = user.get('balance', 0)
        await message.answer(f"💰 Sizning balansingiz: {balance} so'm", reply_markup=payment_menu_kb())
    else:
        await message.answer("❌ Foydalanuvchi ma'lumotlari topilmadi.", reply_markup=main_menu_kb())

async def cmd_my_orders(message: types.Message):
    """Handles the /my_orders command, lists orders with cancel buttons for pending ones."""
    try:
        orders = get_user_orders(message.from_user.id)
        if not orders:
            await message.answer("📦 Sizda hali zakazlar yo'q.", reply_markup=main_menu_kb())
            return

        status_map = {
            'pending': 'Kutilmoqda',
            'approved': 'Tasdiqlangan',
            'rejected': 'Rad etilgan'
        }

        text = "📦 Sizning zakazlaringiz:\n\n"
        kb = InlineKeyboardMarkup(row_width=1)

        for order in orders:
            status = status_map.get(order['status'], "Noma'lum")
            text += f"Zakaz #{order['id']} - Holat: {status}\n"
            text += f"URL: {order['product_url']}\n\n"
            if order['status'] == 'pending':
                kb.add(InlineKeyboardButton(f"❌ Bekor qilish #{order['id']}", callback_data=f"cancel_order_{order['id']}"))
        kb.add(InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main"))

        await message.answer(text, parse_mode="HTML", reply_markup=kb if kb.inline_keyboard else main_menu_kb())
    except Exception as e:
        logger.exception(f"Error in cmd_my_orders for user {message.from_user.id}: {e}")
        await message.answer("❌ Zakazlarni ko'rsatishda xato yuz berdi.", reply_markup=main_menu_kb())

async def cmd_referrals(message: types.Message):
    """Handles the /referrals command to show referral info."""
    try:
        referrals = get_user_referrals(message.from_user.id)
        bot_info = await message.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
        total_bonus = sum(ref.get('bonus', 0) for ref in referrals)
        text = (
            f"👥 Sizning referallaringiz: {len(referrals)} ta\n"
            f"💸 Jami bonus: {total_bonus} so'm\n"
            f"🔗 Referral havolangiz: {ref_link}\n\n"
        )
        if referrals:
            text += "Referal foydalanuvchilar:\n"
            for ref in referrals:
                referred_user = get_user(ref['referred_id'])
                username = f"@{referred_user['username']}" if referred_user and referred_user.get('username') else f"ID: {ref['referred_id']}"
                text += f"- {username} (Bonus: {ref['bonus']} so'm)\n"
        else:
            text += "Hozircha referal foydalanuvchilar yo'q."

        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main"))
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.exception(f"Error in cmd_referrals for user {message.from_user.id}: {e}")
        await message.answer("❌ Referallar ma'lumotlarini ko'rsatishda xato yuz berdi.", reply_markup=main_menu_kb())

async def process_order(message: types.Message, state: FSMContext):
    """Starts the order process by automatically setting the Yandex Market URL."""
    try:
        # Predefined Yandex Market URL for wireless headphones M10
        yandex_market_url = "https://market.yandex.uz/card/besprovodnyye-naushniki-m10/4591765711?do-waremd5=xUwa_LZ8sDvgfu6PoGxQZw&cpc=M-FlYaOgf0DWvjCgIUd8xpU-AGo0-83Sf8wXWhG5qj-6hjPrxABz5Hcv6a-YbnyWIDIYrK-BFpxeRnox88bZWfpygLY_JSdII3rE8HLz3YJVeOMqJ1zlcY-SG8ZEpPFMOMuCdH6OKShCpOuiDeRVWSeE7SnU3gg4UjcjrDc6TGBGuIF9ARq0PWGyNsOGNSGgsPYwfgsu1VnPZva5pBZUzih95szELAdNO9PwsNZvPPnIaa-tAmHT6FTYXkHz4IWLN79xmcvzqX4h28Q5tLa0ZNV3G5faoHFwVJ8gCJkIMbbc5spYxey5sbDBJtJSA-izqGzzKJHHKNLADinX27y0_i6iIKLgLz883el3ZtbpbRYREus0BPf7JEVJSGqCnO_AnomimgEYCpeRGSb7o6S700zxnsOhOiJfj-AI-PVpXdGmAU6hyl7DpKtPmV2QnobvrLU67jh8rtU3_CdkcX-E-hV7NrePTjAYDKH2sLg5XS4rLFY_HN5KuksR1DXudaB-5MnDh-mZ-fjAJzttIAYo4RmFYHQ34O52sUy52xbem-AIGZ0noUk_sLHg5VWLO30h&ogV=-3"

        # Set the URL in state data
        await state.update_data(product_url=yandex_market_url)

        # Move to photo state
        await state.set_state(UserStates.waiting_for_photo)

        kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("🏠 Asosiy menyu"))
        await message.answer(
            f"✅ Mahsulot URL avtomatik ravishda o'rnatildi!\n"
            f"🔗 Mahsulot: {yandex_market_url}\n\n"
            f"📸 Endi mahsulot skrinshotini yuboring:",
            reply_markup=kb
        )
    except Exception as e:
        logger.exception(f"Error in process_order for user {message.from_user.id}: {e}")
        await message.answer("❌ Zakaz jarayonini boshlashda xato yuz berdi.", reply_markup=main_menu_kb())
        await state.finish()

async def process_order_photo(message: types.Message, state: FSMContext):
    """Processes the order photo and creates the order."""
    try:
        if not message.photo:
            await message.answer("❌ Iltimos, rasm yuboring!")
            return

        data = await state.get_data()
        product_url = data.get('product_url')
        
        if not product_url:
            await message.answer("❌ Mahsulot URL topilmadi. Qaytadan urinib ko'ring.", reply_markup=main_menu_kb())
            await state.finish()
            return

        # Create order
        order_id = create_order(
            user_id=message.from_user.id,
            product_url=product_url,
            photo_id=message.photo[-1].file_id
        )

        await message.answer(
            f"✅ Zakaz qabul qilindi!\n"
            f"🆔 Zakaz raqami: #{order_id}\n"
            f"📊 Holat: Kutilmoqda\n\n"
            f"Zakazingiz admin tomonidan tekshiriladi va tasdiqlanadi.",
            reply_markup=main_menu_kb()
        )
        await state.finish()
    except Exception as e:
        logger.exception(f"Error in process_order_photo for user {message.from_user.id}: {e}")
        await message.answer("❌ Zakaz yaratishda xato yuz berdi.", reply_markup=main_menu_kb())
        await state.finish()

async def process_withdraw_type(message: types.Message, state: FSMContext):
    """Processes the withdrawal type selection."""
    try:
        withdraw_type = message.text
        if withdraw_type not in ["💳 Karta", "📱 Telefon", "💰 USDT TRC20"]:
            await message.answer("❌ Noto'g'ri tanlov! Iltimos, tugmalardan birini tanlang.")
            return

        await state.update_data(withdraw_type=withdraw_type)
        await state.set_state(UserStates.waiting_for_wallet)
        
        if withdraw_type == "💳 Karta":
            await message.answer("💳 Karta raqamini kiriting (16 ta raqam):", reply_markup=ReplyKeyboardRemove())
        elif withdraw_type == "📱 Telefon":
            await message.answer("📱 Telefon raqamini kiriting (+998XXXXXXXXX):", reply_markup=ReplyKeyboardRemove())
        else:  # USDT TRC20
            await message.answer("💰 USDT TRC20 manzilini kiriting:", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logger.exception(f"Error in process_withdraw_type for user {message.from_user.id}: {e}")
        await message.answer("❌ Xato yuz berdi.", reply_markup=main_menu_kb())
        await state.finish()

async def process_wallet(message: types.Message, state: FSMContext):
    """Processes the wallet information."""
    try:
        data = await state.get_data()
        withdraw_type = data.get('withdraw_type')
        wallet = message.text.strip()

        # Validate based on type
        if withdraw_type == "💳 Karta" and not validate_card_number(wallet):
            await message.answer("❌ Noto'g'ri karta raqami! 16 ta raqam kiriting.")
            return
        elif withdraw_type == "📱 Telefon" and not validate_phone_number(wallet):
            await message.answer("❌ Noto'g'ri telefon raqami! +998XXXXXXXXX formatida kiriting.")
            return
        elif withdraw_type == "💰 USDT TRC20" and not validate_trc20_address(wallet):
            await message.answer("❌ Noto'g'ri USDT TRC20 manzil! T bilan boshlanuvchi 34 belgili manzil kiriting.")
            return

        await state.update_data(wallet=wallet)
        await state.set_state(UserStates.waiting_for_withdraw_amount)
        
        user = get_user(message.from_user.id)
        balance = user.get('balance', 0) if user else 0
        
        await message.answer(
            f"💰 Sizning balansingiz: {balance} so'm\n"
            f"💸 Yechib olish miqdorini kiriting:"
        )
    except Exception as e:
        logger.exception(f"Error in process_wallet for user {message.from_user.id}: {e}")
        await message.answer("❌ Xato yuz berdi.", reply_markup=main_menu_kb())
        await state.finish()

async def process_withdraw_amount(message: types.Message, state: FSMContext):
    """Processes the withdrawal amount."""
    try:
        try:
            amount = float(message.text)
        except ValueError:
            await message.answer("❌ Noto'g'ri miqdor! Faqat raqam kiriting.")
            return

        if amount <= 0:
            await message.answer("❌ Miqdor 0 dan katta bo'lishi kerak!")
            return

        user = get_user(message.from_user.id)
        balance = user.get('balance', 0) if user else 0
        
        if amount > balance:
            await message.answer(f"❌ Yetarli mablag' yo'q! Sizning balansingiz: {balance} so'm")
            return

        data = await state.get_data()
        withdraw_type = data.get('withdraw_type')
        wallet = data.get('wallet')

        # Create withdraw request
        request_id = create_withdraw_request(
            user_id=message.from_user.id,
            amount=amount,
            wallet=wallet,
            withdraw_type=withdraw_type
        )

        await message.answer(
            f"✅ Yechib olish so'rovi yuborildi!\n"
            f"🆔 So'rov raqami: #{request_id}\n"
            f"💰 Miqdor: {amount} so'm\n"
            f"📊 Holat: Kutilmoqda\n\n"
            f"So'rovingiz admin tomonidan tekshiriladi.",
            reply_markup=main_menu_kb()
        )
        await state.finish()
    except Exception as e:
        logger.exception(f"Error in process_withdraw_amount for user {message.from_user.id}: {e}")
        await message.answer("❌ Xato yuz berdi.", reply_markup=main_menu_kb())
        await state.finish()

async def cancel_order_callback(callback: types.CallbackQuery):
    """Handles order cancellation."""
    try:
        order_id = int(callback.data.split("_")[2])
        db_cancel_order(callback.from_user.id, order_id)
        await callback.message.edit_text("✅ Zakaz bekor qilindi.", reply_markup=main_menu_kb())
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in cancel_order_callback for user {callback.from_user.id}: {e}")
        await callback.answer("❌ Xato yuz berdi.")

async def back_to_main_menu(callback: types.CallbackQuery):
    """Handles back to main menu callback."""
    try:
        await callback.message.edit_text("🏠 Asosiy menyu", reply_markup=None)
        await callback.bot.send_message(
            callback.from_user.id,
            "🏠 Asosiy menyu",
            reply_markup=main_menu_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Error in back_to_main_menu for user {callback.from_user.id}: {e}")
        await callback.answer("❌ Xato yuz berdi.")

async def back_to_main_menu_text(message: types.Message):
    """Handles back to main menu text message."""
    try:
        await message.answer("🏠 Asosiy menyu", reply_markup=main_menu_kb())
    except Exception as e:
        logger.exception(f"Error in back_to_main_menu_text for user {message.from_user.id}: {e}")

def register_handlers(dp):
    """Registers all message and callback query handlers."""
    # Command handlers
    dp.register_message_handler(cmd_start, CommandStart(), IsPrivate(), IsNotBlocked())
    dp.register_message_handler(cmd_balance, Text(equals="💰 Balans"), IsPrivate(), IsNotBlocked())
    dp.register_message_handler(cmd_my_orders, Text(equals="📦 Mening zakazlarim"), IsPrivate(), IsNotBlocked())
    dp.register_message_handler(cmd_referrals, Text(equals="👥 Referallar"), IsPrivate(), IsNotBlocked())
    
    # Order process handlers
    dp.register_message_handler(process_order, Text(equals="🛒 Zakaz berish"), IsPrivate(), IsNotBlocked(), state="*")
    dp.register_message_handler(process_order_photo, IsPrivate(), IsNotBlocked(), state=UserStates.waiting_for_photo, content_types=['photo'])
    
    # Withdraw process handlers
    dp.register_message_handler(process_withdraw_type, Text(equals="💸 Yechib olish"), IsPrivate(), IsNotBlocked(), state="*")
    dp.register_message_handler(process_wallet, IsPrivate(), IsNotBlocked(), state=UserStates.waiting_for_wallet)
    dp.register_message_handler(process_withdraw_amount, IsPrivate(), IsNotBlocked(), state=UserStates.waiting_for_withdraw_amount)
    
    # Callback handlers
    dp.register_callback_query_handler(cancel_order_callback, lambda c: c.data.startswith("cancel_order_"), state="*")
    dp.register_callback_query_handler(back_to_main_menu, lambda c: c.data == "back_to_main", state="*")
    dp.register_message_handler(back_to_main_menu_text, Text(equals="🏠 Asosiy menyu"), IsPrivate(), IsNotBlocked(), state="*")
    
    logger.debug("User handlers registered")
