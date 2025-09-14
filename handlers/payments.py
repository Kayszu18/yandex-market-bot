import logging
import re
from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from database import (
    get_user_balance,
    create_withdraw_request,
    get_user_referrals,
    get_pending_withdraws,
    update_user_balance,
    set_withdraw_status,
    get_user,
    get_user_withdraw_history
)
from keyboards.user_keyboards import payment_menu_kb, make_main_menu_inline
from keyboards.admin_keyboards import withdraw_manage_inline_kb
from utils.filters import IsPrivateCallback, IsNotBlockedCallback, IsAdminCallback, IsAdmin
from config import Config

logger = logging.getLogger(__name__)

# States
class PaymentStates(StatesGroup):
    waiting_for_withdraw_type = State()
    waiting_for_withdraw_amount = State()
    waiting_for_card_number = State()
    waiting_for_phone_number = State()

# Validation functions
def validate_card_number(card_number: str) -> bool:
    """Validates a 16-digit card number."""
    return bool(re.match(r'^\d{16}$', card_number.replace(" ", "")))

def validate_phone_number(phone: str) -> bool:
    """Validates a phone number starting with +998 followed by 9 digits."""
    return bool(re.match(r'^\+998\d{9}$', phone.replace(" ", "")))

def mask_card_number(card_number: str) -> str:
    """Masks a card number, showing only the last 4 digits."""
    cleaned = card_number.replace(" ", "")
    return f"**** **** **** {cleaned[-4:]}"

# --- USER PAYMENTS MENU ---
async def show_balance(message: types.Message):
    """Displays the user's balance and referral stats."""
    try:
        user_id = message.from_user.id
        balance = get_user_balance(user_id)
        referrals = get_user_referrals(user_id)
        total_bonus = sum(ref['bonus'] for ref in referrals)

        text = (
            f"<b>💰 Sizning balansingiz:</b> {balance:.2f} so'm\n"
            f"<b>👥 Referallaringiz:</b> {len(referrals)} ta\n"
            f"<b>💸 Referral bonusi:</b> {total_bonus:.2f} so'm\n\n"
            "Menyudan kerakli amalni tanlang 👇"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=payment_menu_kb())
    except Exception as e:
        logger.exception(f"show_balance failed for user {user_id}: {e}")
        await message.answer("❌ Xato yuz berdi.", reply_markup=make_main_menu_inline())

# --- WITHDRAW REQUEST ---
async def ask_withdraw_type(message: types.Message, state: FSMContext):
    """Prompts the user to select a withdrawal method."""
    balance = get_user_balance(message.from_user.id)
    if balance < Config.reward.MIN_WITHDRAW_AMOUNT:
        await message.answer(
            f"❌ Yechib olish uchun balansingiz {Config.reward.MIN_WITHDRAW_AMOUNT:.2f} so'm dan yuqori bo'lishi kerak!",
            reply_markup=make_main_menu_inline()
        )
        await state.finish()
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💳 Plastik karta", callback_data="withdraw_card"),
        InlineKeyboardButton("📱 Telefon raqam", callback_data="withdraw_phone")
    )
    await state.set_state(PaymentStates.waiting_for_withdraw_type)
    await message.answer(
        f"💰 Yechib olish uchun balans: {balance:.2f} so'm\n"
        "Iltimos, yechib olish usulini tanlang:",
        reply_markup=kb
    )

async def process_withdraw_type(callback: types.CallbackQuery, state: FSMContext):
    """Processes the selected withdrawal type."""
    await callback.answer()
    withdraw_type = callback.data.split("_")[1]
    await state.update_data(withdraw_type=withdraw_type)

    user = get_user(callback.from_user.id)
    if withdraw_type == "phone" and user.get('phone'):
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Ha, shu raqam", callback_data=f"confirm_phone_{user['phone']}"),
            InlineKeyboardButton("🔄 Boshqa raqam", callback_data="new_phone")
        )
        await callback.message.edit_text(
            f"📱 Telefon raqamingiz: {user['phone']}\n"
            "Shu raqamga yechib olishni xohlaysizmi?",
            reply_markup=kb
        )
    else:
        await state.set_state(PaymentStates.waiting_for_withdraw_amount)
        await callback.message.edit_text(
            f"💸 Yechmoqchi bo'lgan summani kiriting (so'm, minimal {Config.reward.MIN_WITHDRAW_AMOUNT:.2f}):"
        )

async def process_withdraw_amount(message: types.Message, state: FSMContext):
    """Processes the withdrawal amount."""
    try:
        amount = float(message.text.replace(",", "."))
        balance = get_user_balance(message.from_user.id)
        if amount < Config.reward.MIN_WITHDRAW_AMOUNT:
            await message.answer(
                f"❌ Minimal yechish summasi {Config.reward.MIN_WITHDRAW_AMOUNT:.2f} so'm!"
            )
            return
        if amount <= 0:
            await message.answer("❌ Miqdor 0 dan katta bo‘lishi kerak!")
            return
        if amount > balance:
            await message.answer(
                f"❌ Sizning balansingiz yetarli emas! Joriy balans: {balance:.2f} so'm"
            )
            return
        await state.update_data(amount=amount)

        data = await state.get_data()
        withdraw_type = data.get("withdraw_type")
        if withdraw_type == "card":
            await state.set_state(PaymentStates.waiting_for_card_number)
            await message.answer(
                "💳 16 raqamli plastik karta raqamingizni yuboring:",
                reply_markup=ReplyKeyboardRemove()
            )
        elif withdraw_type == "phone":
            await state.set_state(PaymentStates.waiting_for_phone_number)
            await message.answer(
                "📱 Telefon raqamingizni yuboring (+998 bilan):",
                reply_markup=ReplyKeyboardRemove()
            )
    except ValueError:
        await message.answer("❌ Noto‘g‘ri raqam kiritildi! Iltimos, to‘g‘ri summa kiriting.")

async def process_card_number(message: types.Message, state: FSMContext):
    """Processes the card number for withdrawal."""
    card_number = message.text.strip()
    if not validate_card_number(card_number):
        await message.answer(
            "❌ Iltimos, to‘g‘ri 16 raqamli karta raqamini kiriting (bo‘shliqsiz).",
            reply_markup=make_main_menu_inline()
        )
        return
    await state.update_data(wallet=card_number)
    await save_withdraw_request(message, state)

async def process_phone_number(message: types.Message, state: FSMContext):
    """Processes the phone number for withdrawal."""
    phone_number = message.text.strip()
    if not validate_phone_number(phone_number):
        await message.answer(
            "❌ Iltimos, to‘g‘ri telefon raqamini kiriting (masalan, +998901234567).",
            reply_markup=make_main_menu_inline()
        )
        return
    await state.update_data(wallet=phone_number)
    await save_withdraw_request(message, state)

async def save_withdraw_request(message: types.Message, state: FSMContext):
    """Saves the withdrawal request."""
    data = await state.get_data()
    amount = data.get("amount")
    withdraw_type = data.get("withdraw_type")
    wallet = data.get("wallet")

    try:
        withdraw_id = create_withdraw_request(message.from_user.id, amount, wallet, withdraw_type)
        display_wallet = mask_card_number(wallet) if withdraw_type == "card" else wallet
        withdraw_type_emoji = '💳 Karta' if withdraw_type == 'card' else '📱 Telefon'
        await message.answer(
            f"✅ Pul yechish so'rovi yuborildi (ID: {withdraw_id})!\n"
            f"💸 Miqdor: {amount:.2f} so'm\n"
            f"{withdraw_type_emoji}: {display_wallet}\n\n"
            "Admin tasdiqlaganidan so'ng balansdan yechib olinadi.",
            reply_markup=make_main_menu_inline()
        )

        # Notify admin
        admin_chat = Config.channel.PROOF_CHANNEL_ID or Config.admin.ADMIN_IDS[0]
        user = get_user(message.from_user.id)
        text = (
            f"📢 Yangi pul yechish so'rovi #{withdraw_id}\n"
            f"👤 Foydalanuvchi: @{user.get('username', 'N/A')} (ID: {message.from_user.id})\n"
            f"💸 Miqdor: {amount:.2f} so'm\n"
            f"{withdraw_type_emoji}: {display_wallet}\n"
            f"📞 Telefon: {user.get('phone', 'Yoq')}"
        )
        try:
            await message.bot.send_message(
                admin_chat,
                text,
                parse_mode="HTML",
                reply_markup=withdraw_manage_inline_kb(withdraw_id)
            )
        except Exception as e:
            logger.exception(f"Admin notification for withdraw {withdraw_id} failed: {e}")
        await state.finish()
    except ValueError as e:
        if "Insufficient balance" in str(e):
            await message.answer(
                f"❌ Yetarli balans yo'q!\n"
                f"💸 So'ralgan miqdor: {amount:.2f} so'm\n"
                f"💰 Joriy balans: {get_user_balance(message.from_user.id):.2f} so'm",
                reply_markup=make_main_menu_inline()
            )
        else:
            await message.answer(
                f"❌ Xato: {str(e)}",
                reply_markup=make_main_menu_inline()
            )
    except Exception as e:
        logger.exception(f"Failed to create withdraw request for user {message.from_user.id}: {e}")
        await message.answer(
            "❌ Pul yechish so'rovini yaratishda xato yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
            reply_markup=make_main_menu_inline()
        )
    await state.finish()

async def confirm_phone(callback: types.CallbackQuery, state: FSMContext):
    """Confirms the existing phone number for withdrawal."""
    await callback.answer()
    phone = callback.data.split("_")[-1]
    await state.update_data(wallet=phone)
    await save_withdraw_request_from_callback(callback, state, phone)

async def new_phone(callback: types.CallbackQuery, state: FSMContext):
    """Prompts for a new phone number."""
    await callback.answer()
    await state.set_state(PaymentStates.waiting_for_phone_number)
    await callback.message.edit_text(
        "📱 Iltimos, yangi telefon raqamingizni yuboring (+998 bilan):"
    )

async def save_withdraw_request_from_callback(callback: types.CallbackQuery, state: FSMContext, wallet: str):
    """Saves the withdrawal request from a callback (e.g., confirmed phone)."""
    try:
        data = await state.get_data()
        amount = data.get("amount")
        withdraw_type = data.get("withdraw_type")
        withdraw_id = create_withdraw_request(callback.from_user.id, amount, wallet, withdraw_type)
        display_wallet = mask_card_number(wallet) if withdraw_type == "card" else wallet
        withdraw_type_emoji = '💳 Karta' if withdraw_type == 'card' else '📱 Telefon'
        await callback.message.edit_text(
            f"✅ Pul yechish so'rovi yuborildi (ID: {withdraw_id})!\n"
            f"💸 Miqdor: {amount:.2f} so'm\n"
            f"{withdraw_type_emoji}: {display_wallet}\n\n"
            "Admin tasdiqlaganidan so'ng balansdan yechib olinadi.",
            reply_markup=make_main_menu_inline()
        )

        # Notify admin
        admin_chat = Config.channel.PROOF_CHANNEL_ID or Config.admin.ADMIN_IDS[0]
        user = get_user(callback.from_user.id)
        text = (
            f"📢 Yangi pul yechish so'rovi #{withdraw_id}\n"
            f"👤 Foydalanuvchi: @{user.get('username', 'N/A')} (ID: {callback.from_user.id})\n"
            f"💸 Miqdor: {amount:.2f} so'm\n"
            f"{withdraw_type_emoji}: {display_wallet}\n"
            f"📞 Telefon: {user.get('phone', 'Yoq')}"
        )
        try:
            await callback.bot.send_message(
                admin_chat,
                text,
                parse_mode="HTML",
                reply_markup=withdraw_manage_inline_kb(withdraw_id)
            )
        except Exception as e:
            logger.exception(f"Admin notification for withdraw {withdraw_id} failed: {e}")
        await state.finish()
    except Exception as e:
        logger.exception(f"save_withdraw_request_from_callback failed for user {callback.from_user.id}: {e}")
        await callback.message.edit_text(
            "❌ So‘rovni saqlashda xato yuz berdi.",
            reply_markup=make_main_menu_inline()
        )
        await state.finish()

# --- WITHDRAW HISTORY ---
async def show_withdraw_history(message: types.Message):
    """Displays the user's withdrawal history."""
    try:
        withdraws = get_user_withdraw_history(message.from_user.id)
        if not withdraws:
            await message.answer(
                "📜 Sizda hali yechib olish so‘rovlari yo‘q.",
                reply_markup=make_main_menu_inline()
            )
            return

        text = "<b>📜 Yechib olish tarixi:</b>\n\n"
        status_map = {
            'pending': 'Kutilmoqda',
            'approved': 'Tasdiqlangan',
            'rejected': 'Rad etilgan'
        }
        for w in withdraws:
            display_wallet = mask_card_number(w['wallet']) if w['withdraw_type'] == 'card' else w['wallet']
            created_at = w.get('created_at')
            created_at_str = created_at if isinstance(created_at, str) else str(created_at)
            withdraw_type_emoji = '💳 Karta' if w['withdraw_type'] == 'card' else '📱 Telefon'
            text += (
                f"🆔 So'rov #{w['id']}\n"
                f"💸 Miqdor: {w['amount']:.2f} so'm\n"
                f"{withdraw_type_emoji}: {display_wallet}\n"
                f"📅 Sana: {created_at_str}\n"
                f"📊 Holat: {status_map.get(w['status'], 'Noma lum')}\n\n"
            )
        await message.answer(text, parse_mode="HTML", reply_markup=make_main_menu_inline())
    except Exception as e:
        logger.exception(f"show_withdraw_history failed for user {message.from_user.id}: {e}")
        await message.answer(
            "❌ Tarixni ko‘rsatishda xato yuz berdi.",
            reply_markup=make_main_menu_inline()
        )

# --- ADMIN WITHDRAW PANEL ---
async def admin_withdraw_panel(message: types.Message):
    """Displays pending withdraw requests to admins."""
    try:
        withdraws = get_pending_withdraws()
        if not withdraws:
            await message.answer(
                "✅ Hozircha kutayotgan yechib olish so‘rovlari yo‘q.",
                reply_markup=make_main_menu_inline()
            )
            return

        for w in withdraws:
            user = get_user(w['user_id'])
            display_wallet = mask_card_number(w['wallet']) if w['withdraw_type'] == 'card' else w['wallet']
            created_at = w.get('created_at')
            created_at_str = created_at if isinstance(created_at, str) else str(created_at)
            withdraw_type_emoji = '💳 Karta' if w['withdraw_type'] == 'card' else '📱 Telefon'
            text = (
                f"<b>💸 Yechib olish so'rovi #{w['id']}:</b>\n\n"
                f"👤 Foydalanuvchi: @{user.get('username', 'N/A')} (ID: {w['user_id']})\n"
                f"📞 Telefon: {user.get('phone', 'Yoq')}\n"
                f"💰 Miqdor: {w['amount']:.2f} so'm\n"
                f"{withdraw_type_emoji}: {display_wallet}\n"
                f"📅 Sana: {created_at_str}"
            )
            await message.answer(
                text,
                parse_mode="HTML",
                reply_markup=withdraw_manage_inline_kb(w['id'])
            )
    except Exception as e:
        logger.exception(f"admin_withdraw_panel failed: {e}")
        await message.answer(
            "❌ So‘rovlar ro‘yxatini ko‘rsatishda xato yuz berdi.",
            reply_markup=make_main_menu_inline()
        )

# --- ADMIN INLINE CALLBACKS ---
async def accept_withdraw(callback: types.CallbackQuery):
    """Approves a withdraw request and deducts the amount from the user's balance."""
    try:
        wid = int(callback.data.split("_")[2])
        withdraw = next((w for w in get_pending_withdraws() if w['id'] == wid), None)
        if not withdraw:
            await callback.message.edit_text(
                "❌ Yechib olish so‘rovi topilmadi!",
                reply_markup=make_main_menu_inline()
            )
            return

        user_id, amount = withdraw['user_id'], withdraw['amount']
        current_balance = get_user_balance(user_id)
        if amount > current_balance:
            await callback.message.edit_text(
                "❌ Foydalanuvchi balansi yetarli emas!",
                reply_markup=make_main_menu_inline()
            )
            return

        update_user_balance(user_id, current_balance - amount)
        set_withdraw_status(wid, "approved")
        display_wallet = mask_card_number(withdraw['wallet']) if withdraw['withdraw_type'] == 'card' else withdraw['wallet']
        withdraw_type_emoji = '💳 Karta' if withdraw['withdraw_type'] == 'card' else '📱 Telefon'
        await callback.message.edit_text(
            f"✅ Yechib olish so'rovi #{wid} tasdiqlandi!\n"
            f"💸 Miqdor: {amount:.2f} so'm\n"
            f"{withdraw_type_emoji}: {display_wallet}",
            parse_mode="HTML",
            reply_markup=make_main_menu_inline()
        )

        # Notify user
        try:
            await callback.bot.send_message(
                user_id,
                f"✅ Sizning yechib olish so'rovingiz #{wid} tasdiqlandi!\n"
                f"💸 Miqdor: {amount:.2f} so'm\n"
                f"{withdraw_type_emoji}: {display_wallet}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Failed to notify user {user_id} about approved withdraw: {e}")

    except Exception as e:
        logger.exception(f"accept_withdraw failed for withdraw {wid}: {e}")
        await callback.message.edit_text(
            "❌ So‘rovni tasdiqlashda xato yuz berdi.",
            reply_markup=make_main_menu_inline()
        )
    await callback.answer()

async def reject_withdraw(callback: types.CallbackQuery):
    """Rejects a withdraw request."""
    try:
        wid = int(callback.data.split("_")[2])
        set_withdraw_status(wid, "rejected")
        withdraw = next((w for w in get_pending_withdraws() if w['id'] == wid), None)
        if withdraw:
            display_wallet = mask_card_number(withdraw['wallet']) if withdraw['withdraw_type'] == 'card' else withdraw['wallet']
            withdraw_type_emoji = '💳 Karta' if withdraw['withdraw_type'] == 'card' else '📱 Telefon'
            await callback.message.edit_text(
                f"❌ Yechib olish so'rovi #{wid} rad etildi.\n"
                f"💸 Miqdor: {withdraw['amount']:.2f} so'm\n"
                f"{withdraw_type_emoji}: {display_wallet}\n"
                "Foydalanuvchiga sababni xabar qiling.",
                parse_mode="HTML",
                reply_markup=make_main_menu_inline()
            )

            # Notify user
            try:
                await callback.bot.send_message(
                    withdraw['user_id'],
                    f"❌ Sizning yechib olish so'rovingiz #{wid} rad etildi.\n"
                    f"💸 Miqdor: {withdraw['amount']:.2f} so'm\n"
                    "Sababni bilish uchun support bilan bog'laning.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {withdraw['user_id']} about rejected withdraw: {e}")
        else:
            await callback.message.edit_text(
                "❌ Yechib olish so‘rovi topilmadi!",
                reply_markup=make_main_menu_inline()
            )
    except Exception as e:
        logger.exception(f"reject_withdraw failed for withdraw {wid}: {e}")
        await callback.message.edit_text(
            "❌ So‘rovni rad etishda xato yuz berdi.",
            reply_markup=make_main_menu_inline()
        )
    await callback.answer()

# --- REGISTRATION FUNCTION ---
def register_handlers(dp: Dispatcher):
    """Registers all message and callback query handlers."""
    dp.register_message_handler(show_balance, Text(equals="💰 Balans"), state="*")
    dp.register_message_handler(ask_withdraw_type, Text(equals="💸 Pul yechish"), state="*")
    dp.register_message_handler(show_withdraw_history, Text(equals="📜 Yechib olish tarixi"), state="*")
    dp.register_message_handler(process_withdraw_amount, state=PaymentStates.waiting_for_withdraw_amount)
    dp.register_message_handler(
        process_card_number,
        state=PaymentStates.waiting_for_card_number
    )
    dp.register_message_handler(
        process_phone_number,
        state=PaymentStates.waiting_for_phone_number
    )
    dp.register_message_handler(
        admin_withdraw_panel,
        Text(equals="💸 Withdraw so'rovlar"),
        IsAdmin(),
        state="*"
    )
    dp.register_callback_query_handler(
        process_withdraw_type,
        Text(startswith="withdraw_"),
        IsPrivateCallback(),
        IsNotBlockedCallback(),
        state=PaymentStates.waiting_for_withdraw_type
    )
    dp.register_callback_query_handler(
        confirm_phone,
        Text(startswith="confirm_phone_"),
        IsPrivateCallback(),
        IsNotBlockedCallback(),
        state=PaymentStates.waiting_for_withdraw_type
    )
    dp.register_callback_query_handler(
        new_phone,
        Text(equals="new_phone"),
        IsPrivateCallback(),
        IsNotBlockedCallback(),
        state=PaymentStates.waiting_for_withdraw_type
    )
    dp.register_callback_query_handler(
        accept_withdraw,
        lambda c: c.data.startswith("withdraw_accept_"),
        IsPrivateCallback(),
        IsAdminCallback(),
        state="*"
    )
    dp.register_callback_query_handler(
        reject_withdraw,
        lambda c: c.data.startswith("withdraw_reject_"),
        IsPrivateCallback(),
        IsAdminCallback(),
        state="*"
    )