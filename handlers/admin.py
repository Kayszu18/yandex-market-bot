import logging
import datetime
import asyncio
from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import Command, Text, Regexp
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import BotBlocked, UserDeactivated
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from utils.filters import IsPrivateCallback, IsNotBlockedCallback, IsAdminCallback

from database import (
    get_all_users,
    get_all_users_detailed,
    get_users_by_date_range,
    block_user,
    unblock_user,
    get_stats,
    update_setting,
    get_setting,
    get_admin_list,
    is_user_blocked,
    user_exists,
    get_user,
    get_user_balance,
    get_user_referrals,
    get_all_orders,
    update_order_status,
    add_user_balance,
    get_pending_withdraw_requests,
    update_withdraw_request_status,
    reject_withdraw_request_and_refund
)
from utils.excel_export import export_orders_excel, export_users_excel
from keyboards.admin_keyboards import (
    admin_main_menu_kb,
    broadcast_inline_kb,
    user_manage_inline_kb,
    ad_text_change_inline_kb,
    guide_video_inline_kb,
    users_list_inline_kb,
    user_pagination_inline_kb
)
from keyboards.user_keyboards import make_main_menu_inline

logger = logging.getLogger(__name__)

# States
class AdminStates(StatesGroup):
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_preview = State()
    waiting_for_single_user_id = State()
    waiting_for_single_message = State()
    waiting_for_new_ad_text = State()
    waiting_for_video_upload = State()
    waiting_for_user_details = State()

# Validation
MAX_MESSAGE_LENGTH = 4096

def validate_message(text: str) -> bool:
    """Validates message length for broadcasts."""
    return text and len(text.strip()) <= MAX_MESSAGE_LENGTH

# --- ADMIN PANEL ---
async def admin_panel(message: types.Message):
    """Opens the admin panel."""
    if message.from_user.id not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    await message.answer(
        "<b>🔧 Admin panelga xush kelibsiz!</b>\n\n"
        "Quyidagi funksiyalardan birini tanlang 👇",
        parse_mode="HTML",
        reply_markup=admin_main_menu_kb()
    )

# --- STATISTIKA ---
async def show_stats(message: types.Message):
    """Displays bot statistics."""
    try:
        stats = get_stats()
        text = (
            f"<b>📊 Bot statistikasi:</b>\n\n"
            f"👥 Jami foydalanuvchilar: {stats['total_users']}\n"
            f"🚫 Bloklanganlar: {stats['blocked_users']}\n"
            f"🛒 Bugungi zakazlar: {stats['today_orders']}\n"
            f"💸 Kutilayotgan withdraw so‘rovlari: {stats['pending_withdraws']}\n"
            f"💰 Jami balanslar: {stats.get('total_balance', 0):.2f} USDT"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=admin_main_menu_kb())
    except Exception as e:
        logger.exception(f"show_stats failed: {e}")
        await message.answer("❌ Statistikani ko‘rsatishda xato yuz berdi.", reply_markup=admin_main_menu_kb())

# --- EXCEL EXPORT ---
async def export_excel(message: types.Message):
    """Exports orders to Excel."""
    try:
        file_path = export_orders_excel()
        await message.answer_document(
            types.FSInputFile(file_path),
            caption="📂 Bugungi zakazlar ro‘yxati (Excel formatda).",
            reply_markup=admin_main_menu_kb()
        )
    except Exception as e:
        logger.exception(f"export_excel failed: {e}")
        await message.answer("❌ Excel faylini yaratishda xato yuz berdi.", reply_markup=admin_main_menu_kb())

# --- BROADCAST (HAMMA FOYDALANUVCHILARGA) ---
async def start_broadcast(message: types.Message, state: FSMContext):
    """Initiates the broadcast process."""
    if str(message.from_user.id) not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    await message.answer(
        "<b>📨 Xabar yuborish:</b>\nKimga xabar yuborishni tanlang:",
        parse_mode="HTML",
        reply_markup=broadcast_inline_kb()
    )

async def broadcast_all_start(callback: types.CallbackQuery, state: FSMContext):
    """Prompts for broadcast message."""
    await callback.answer()
    await callback.message.answer(
        "✏️ Xabar matnini yuboring (maksimal 4096 belgi, HTML formatlash mumkin).\n"
        "📎 Rasm yoki video qo‘shishingiz mumkin.",
        reply_markup=ReplyKeyboardRemove()
    )
    await AdminStates.waiting_for_broadcast_text.set()

async def process_broadcast_text(message: types.Message, state: FSMContext):
    """Processes broadcast message and offers preview."""
    text = message.html_text if message.text else ""
    file_id = None
    file_type = None

    if not validate_message(text):
        await message.answer(
            "❌ Xabar 4096 belgidan oshmasligi kerak yoki bo‘sh bo‘lmasligi kerak!",
            reply_markup=admin_main_menu_kb()
        )
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"

    await state.update_data(broadcast_text=text, file_id=file_id, file_type=file_type)
    # Generate an in-memory broadcast id
    broadcast_id = int(datetime.datetime.now().timestamp())
    await state.update_data(broadcast_id=broadcast_id)

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📤 Oldindan ko‘rish", callback_data=f"preview_broadcast_{broadcast_id}"),
        InlineKeyboardButton("✅ Yuborish", callback_data=f"send_broadcast_{broadcast_id}"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_broadcast")
    )
    await message.answer(
        f"<b>📨 Broadcast xabari (ID: {broadcast_id}):</b>\n\n{text}",
        parse_mode="HTML",
        reply_markup=kb
    )

async def preview_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """Previews the broadcast message."""
    data = await state.get_data()
    text = data.get("broadcast_text")
    file_id = data.get("file_id")
    file_type = data.get("file_type")
    broadcast_id = data.get("broadcast_id")

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Yuborish", callback_data=f"send_broadcast_{broadcast_id}"),
        InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_broadcast"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_broadcast")
    )

    try:
        if file_type == "photo":
            await callback.message.answer_photo(file_id, caption=text, parse_mode="HTML", reply_markup=kb)
        elif file_type == "video":
            await callback.message.answer_video(file_id, caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logger.exception(f"preview_broadcast failed: {e}")
        await callback.message.answer("❌ Oldindan ko‘rishda xato yuz berdi.", reply_markup=admin_main_menu_kb())
        await state.finish()

async def send_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """Sends the broadcast to all users."""
    data = await state.get_data()
    text = data.get("broadcast_text")
    file_id = data.get("file_id")
    file_type = data.get("file_type")
    broadcast_id = data.get("broadcast_id")

    users = [uid for uid in get_all_users() if not is_user_blocked(uid)]
    sent = 0
    failed = 0

    for user_id in users:
        try:
            if file_type == "photo":
                await callback.bot.send_photo(user_id, file_id, caption=text, parse_mode="HTML")
            elif file_type == "video":
                await callback.bot.send_video(user_id, file_id, caption=text, parse_mode="HTML")
            else:
                await callback.bot.send_message(user_id, text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # API limitlaridan qochish
        except (BotBlocked, UserDeactivated):
            failed += 1
            logger.debug(f"Failed to send broadcast to {user_id}")
        except Exception as e:
            failed += 1
            logger.error(f"Unexpected error in broadcast to {user_id}: {e}")

    # No persistent stats storage; logging instead
    logger.info(f"Broadcast {broadcast_id} summary: sent={sent}, failed={failed}")

    await callback.message.edit_text(
        f"✅ Xabar {sent} foydalanuvchiga yuborildi, {failed} ta muvaffaqiyatsiz.\n"
        f"🆔 Broadcast ID: {broadcast_id}",
        parse_mode="HTML",
        reply_markup=admin_main_menu_kb()
    )
    await state.finish()
    await callback.answer()

async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """Cancels the broadcast process."""
    await state.finish()
    await callback.message.edit_text("❌ Broadcast bekor qilindi.", reply_markup=admin_main_menu_kb())
    await callback.answer()

async def edit_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """Allows editing the broadcast message."""
    await callback.message.answer(
        "✏️ Yangi xabar matnini yuboring (maksimal 4096 belgi, HTML formatlash mumkin):",
        reply_markup=ReplyKeyboardRemove()
    )
    await AdminStates.waiting_for_broadcast_text.set()
    await callback.answer()

# --- BIR FOYDALANUVCHIGA XABAR ---
async def ask_user_id(callback: types.CallbackQuery, state: FSMContext):
    """Prompts for user ID for single message."""
    await callback.answer()
    await callback.message.answer("✏️ Foydalanuvchi ID sini kiriting:", reply_markup=ReplyKeyboardRemove())
    await AdminStates.waiting_for_single_user_id.set()

async def get_user_id_for_message(message: types.Message, state: FSMContext):
    """Processes the user ID for single message."""
    try:
        user_id = int(message.text)
        if not user_exists(user_id):
            await message.answer("❌ Bunday foydalanuvchi mavjud emas!", reply_markup=admin_main_menu_kb())
            return
        await state.update_data(target_user_id=user_id)
        await message.answer("📨 Xabar matnini yuboring (HTML formatlash mumkin):")
        await AdminStates.waiting_for_single_message.set()
    except ValueError:
        await message.answer("❌ Noto‘g‘ri ID kiritildi! Faqat raqam kiriting.")

async def send_single_message(message: types.Message, state: FSMContext):
    """Sends a message to a single user."""
    data = await state.get_data()
    user_id = data.get("target_user_id")
    text = message.html_text if message.text else ""

    if not validate_message(text):
        await message.answer("❌ Xabar 4096 belgidan oshmasligi kerak yoki bo‘sh bo‘lmasligi kerak!")
        return

    try:
        await message.bot.send_message(user_id, text, parse_mode="HTML")
        await message.answer("✅ Xabar yuborildi!", reply_markup=admin_main_menu_kb())
    except (BotBlocked, UserDeactivated):
        await message.answer("❌ Xabar yuborilmadi (foydalanuvchi botni bloklagan bo‘lishi mumkin).")
        logger.debug(f"Failed to send single message to {user_id}")
    except Exception as e:
        await message.answer("❌ Xatolik yuz berdi.")
        logger.error(f"Unexpected error sending single message to {user_id}: {e}")
    await state.finish()

# --- FOYDALANUVCHI BOSHQARISH ---
async def ask_user_for_manage(message: types.Message, state: FSMContext):
    """Prompts for user ID for management."""
    if message.from_user.id not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    await message.answer("👤 Foydalanuvchi ID sini kiriting (bloklash/ochish/ma'lumot):", reply_markup=ReplyKeyboardRemove())
    await AdminStates.waiting_for_user_details.set()

async def manage_user(message: types.Message, state: FSMContext):
    """Manages user actions (block, unblock, details)."""
    try:
        user_id = int(message.text)
        if not user_exists(user_id):
            await message.answer("❌ Bunday foydalanuvchi mavjud emas!", reply_markup=admin_main_menu_kb())
            await state.finish()
            return

        user = get_user(user_id) or {}
        referrals = get_user_referrals(user_id)
        text = (
            f"<b>👤 Foydalanuvchi ma'lumotlari (ID: {user_id}):</b>\n\n"
            f"📛 Ism: @{user.get('username', 'N/A')}\n"
            f"📞 Telefon: {user.get('phone', 'Yo‘q')}\n"
            f"💰 Balans: {get_user_balance(user_id):.2f} so'm\n"
            f"👥 Referallar: {len(referrals)} ta\n"
            f"🚫 Holat: {'Bloklangan' if is_user_blocked(user_id) else 'Faol'}\n"
            f"📅 Ro‘yxatdan o‘tgan: {user.get('created_at', 'N/A')}"
        )
        kb = user_manage_inline_kb(user_id)
        kb.add(InlineKeyboardButton("📩 Xabar yuborish", callback_data=f"send_message_{user_id}"))
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        await state.finish()
    except ValueError:
        await message.answer("❌ Noto‘g‘ri ID kiritildi! Faqat raqam kiriting.")

async def block_user_cb(callback: types.CallbackQuery):
    """Blocks a user."""
    user_id = int(callback.data.split("_")[1])
    block_user(user_id)
    await callback.message.edit_text(f"🚫 Foydalanuvchi {user_id} bloklandi.", reply_markup=admin_main_menu_kb())
    await callback.answer()

async def unblock_user_cb(callback: types.CallbackQuery):
    """Unblocks a user."""
    user_id = int(callback.data.split("_")[1])
    unblock_user(user_id)
    await callback.message.edit_text(f"✅ Foydalanuvchi {user_id} blokdan chiqarildi.", reply_markup=admin_main_menu_kb())
    await callback.answer()

# --- REKLAMA MATNINI O‘ZGARTIRISH ---
async def edit_ad_text(message: types.Message, state: FSMContext):
    """Prompts for new ad text."""
    if message.from_user.id not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    current_text = get_setting("ad_text") or "Hozircha reklama matni yo‘q."
    await message.answer(
        f"<b>📝 Joriy reklama matni:</b>\n\n{current_text}",
        parse_mode="HTML",
        reply_markup=ad_text_change_inline_kb()
    )

async def wait_new_ad_text(callback: types.CallbackQuery, state: FSMContext):
    """Waits for new ad text."""
    await callback.answer()
    await callback.message.answer(
        "✏️ Yangi reklama matnini yuboring (HTML formatlash mumkin):",
        reply_markup=ReplyKeyboardRemove()
    )
    await AdminStates.waiting_for_new_ad_text.set()

async def save_new_ad_text(message: types.Message, state: FSMContext):
    """Saves the new ad text."""
    text = message.html_text if message.text else ""
    if not validate_message(text):
        await message.answer("❌ Matn 4096 belgidan oshmasligi kerak yoki bo‘sh bo‘lmasligi kerak!")
        return
    update_setting("ad_text", text)
    await message.answer("✅ Reklama matni yangilandi!", reply_markup=admin_main_menu_kb())
    await state.finish()

# --- QO‘LLANMA VIDEO ---
async def ask_video_upload(message: types.Message, state: FSMContext):
    """Prompts for guide video upload."""
    if message.from_user.id not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    current_video = get_setting("help_video_file_id")
    if current_video:
        await message.answer("📹 Joriy qo‘llanma video:", reply_markup=guide_video_inline_kb())
        await message.bot.send_video(message.from_user.id, current_video)
    else:
        await message.answer("📹 Hozircha qo‘llanma video yo‘q. Yangi videoni yuboring:")
    await AdminStates.waiting_for_video_upload.set()

async def save_guide_video(message: types.Message, state: FSMContext):
    """Saves the new guide video."""
    if not message.video:
        await message.answer("❌ Iltimos, video yuboring!")
        return
    video_id = message.video.file_id
    update_setting("help_video_file_id", video_id)
    await message.answer("✅ Qo‘llanma video yangilandi!", reply_markup=admin_main_menu_kb())
    await state.finish()

# --- ZAKAZLARNI BOSHQARISH ---
async def manage_orders(message: types.Message):
    """Shows pending orders for admin approval."""
    if message.from_user.id not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    
    orders = get_all_orders()
    pending_orders = [order for order in orders if order['status'] == 'pending']
    
    if not pending_orders:
        await message.answer("📦 Hozircha kutilayotgan zakazlar yo'q.", reply_markup=admin_main_menu_kb())
        return
    
    text = f"📦 Kutilayotgan zakazlar ({len(pending_orders)} ta):\n\n"
    kb = InlineKeyboardMarkup(row_width=1)
    
    for order in pending_orders[:10]:  # Faqat birinchi 10 ta zakazni ko'rsatish
        text += f"🆔 Zakaz #{order['id']}\n"
        text += f"👤 Foydalanuvchi: @{order.get('username', 'N/A')} (ID: {order['user_id']})\n"
        text += f"🔗 URL: {order['product_url'][:50]}...\n"
        text += f"📅 Sana: {order['created_at']}\n\n"
        
        kb.add(InlineKeyboardButton(
            f"📋 Zakaz #{order['id']} ko'rish", 
            callback_data=f"view_order_{order['id']}"
        ))
    
    if len(pending_orders) > 10:
        text += f"... va yana {len(pending_orders) - 10} ta zakaz"
    
    await message.answer(text, reply_markup=kb)

async def view_order(callback: types.CallbackQuery):
    """Shows detailed order information with photo."""
    order_id = int(callback.data.split("_")[2])
    orders = get_all_orders()
    order = next((o for o in orders if o['id'] == order_id), None)
    
    if not order:
        await callback.answer("❌ Zakaz topilmadi!")
        return
    
    text = (
        f"📋 <b>Zakaz #{order['id']} ma'lumotlari:</b>\n\n"
        f"👤 Foydalanuvchi: @{order.get('username', 'N/A')} (ID: {order['user_id']})\n"
        f"🔗 Mahsulot URL: {order['product_url']}\n"
        f"📅 Yaratilgan: {order['created_at']}\n"
        f"📊 Holat: {order['status']}"
    )
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_order_{order_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_order_{order_id}")
    )
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_orders"))
    
    # Skrinshotni yuborish
    if order.get('photo_id'):
        try:
            await callback.bot.send_photo(
                callback.from_user.id,
                order['photo_id'],
                caption=text,
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Failed to send photo for order {order_id}: {e}")
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    
    await callback.answer()

async def approve_order(callback: types.CallbackQuery):
    """Approves an order and adds balance to user."""
    order_id = int(callback.data.split("_")[2])
    update_order_status(order_id, "approved")
    
    # Foydalanuvchiga balans qo'shish
    orders = get_all_orders()
    order = next((o for o in orders if o['id'] == order_id), None)
    if order:
        # 10000 so'm balans qo'shish
        add_user_balance(order['user_id'], 10000)
        
        try:
            await callback.bot.send_message(
                order['user_id'],
                f"✅ Sizning zakaz #{order_id} tasdiqlandi!\n"
                f"💰 Balansingizga 10000 so'm qo'shildi!\n"
                f"💰 Jami balans: {get_user_balance(order['user_id'])} so'm"
            )
        except Exception as e:
            logger.error(f"Failed to notify user about order approval: {e}")
    
    await callback.message.edit_text(f"✅ Zakaz #{order_id} tasdiqlandi va foydalanuvchiga 10000 so'm qo'shildi!")
    await callback.answer()

async def reject_order(callback: types.CallbackQuery):
    """Rejects an order."""
    order_id = int(callback.data.split("_")[2])
    update_order_status(order_id, "rejected")
    
    # Foydalanuvchiga xabar yuborish
    orders = get_all_orders()
    order = next((o for o in orders if o['id'] == order_id), None)
    if order:
        try:
            await callback.bot.send_message(
                order['user_id'],
                f"❌ Sizning zakaz #{order_id} rad etildi."
            )
        except Exception as e:
            logger.error(f"Failed to notify user about order rejection: {e}")
    
    await callback.message.edit_text(f"❌ Zakaz #{order_id} rad etildi!")
    await callback.answer()

async def back_to_orders(callback: types.CallbackQuery):
    """Returns to orders list."""
    await callback.message.edit_text("📦 Zakazlarni boshqarish:", reply_markup=admin_main_menu_kb())
    await callback.answer()

# --- PUL YECHIB OLISH SO'ROVLARI ---
async def manage_withdraw_requests(message: types.Message):
    """Shows pending withdraw requests for admin approval."""
    if message.from_user.id not in get_admin_list():
        await message.answer("❌ Siz admin emassiz!", reply_markup=make_main_menu_inline())
        return
    
    requests = get_pending_withdraw_requests()
    
    if not requests:
        await message.answer("💸 Hozircha kutilayotgan pul yechib olish so'rovlari yo'q.", reply_markup=admin_main_menu_kb())
        return
    
    text = f"💸 Kutilayotgan pul yechib olish so'rovlari ({len(requests)} ta):\n\n"
    kb = InlineKeyboardMarkup(row_width=1)
    
    for req in requests[:10]:  # Faqat birinchi 10 ta so'rovni ko'rsatish
        text += f"🆔 So'rov #{req['id']}\n"
        text += f"👤 Foydalanuvchi: @{req.get('username', 'N/A')} (ID: {req['user_id']})\n"
        text += f"💰 Miqdor: {req['amount']} so'm\n"
        text += f"💳 Usul: {req['withdraw_type']}\n"
        text += f"📝 Manzil: {req['wallet']}\n"
        text += f"📅 Sana: {req['created_at']}\n\n"
        
        kb.add(InlineKeyboardButton(
            f"📋 So'rov #{req['id']} ko'rish", 
            callback_data=f"view_withdraw_{req['id']}"
        ))
    
    if len(requests) > 10:
        text += f"... va yana {len(requests) - 10} ta so'rov"
    
    await message.answer(text, reply_markup=kb)

async def view_withdraw_request(callback: types.CallbackQuery):
    """Shows detailed withdraw request information."""
    request_id = int(callback.data.split("_")[2])
    requests = get_pending_withdraw_requests()
    req = next((r for r in requests if r['id'] == request_id), None)
    
    if not req:
        await callback.answer("❌ So'rov topilmadi!")
        return
    
    text = (
        f"📋 <b>Pul yechib olish so'rovi #{req['id']} ma'lumotlari:</b>\n\n"
        f"👤 Foydalanuvchi: @{req.get('username', 'N/A')} (ID: {req['user_id']})\n"
        f"💰 Miqdor: {req['amount']} so'm\n"
        f"💳 To'lov usuli: {req['withdraw_type']}\n"
        f"📝 To'lov manzili: {req['wallet']}\n"
        f"📅 Yaratilgan: {req['created_at']}\n"
        f"📊 Holat: {req['status']}"
    )
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ To'lov qilish", callback_data=f"process_payment_{request_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_withdraw_{request_id}")
    )
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_withdraws"))
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

async def process_payment(callback: types.CallbackQuery):
    """Processes the payment for withdraw request."""
    request_id = int(callback.data.split("_")[2])
    requests = get_pending_withdraw_requests()
    req = next((r for r in requests if r['id'] == request_id), None)
    
    if not req:
        await callback.answer("❌ So'rov topilmadi!")
        return
    
    # So'rovni tasdiqlash
    update_withdraw_request_status(request_id, "approved")
    
    # Foydalanuvchiga xabar yuborish
    try:
        await callback.bot.send_message(
            req['user_id'],
            f"✅ Sizning pul yechib olish so'rovingiz #{request_id} tasdiqlandi!\n"
            f"💰 Miqdor: {req['amount']} so'm\n"
            f"💳 To'lov usuli: {req['withdraw_type']}\n"
            f"📝 To'lov manzili: {req['wallet']}\n\n"
            f"To'lov tez orada amalga oshiriladi."
        )
    except Exception as e:
        logger.error(f"Failed to notify user about payment processing: {e}")
    
    await callback.message.edit_text(f"✅ To'lov #{request_id} amalga oshirildi!")
    await callback.answer()

async def reject_withdraw_request(callback: types.CallbackQuery):
    """Rejects a withdraw request."""
    request_id = int(callback.data.split("_")[2])
    requests = get_pending_withdraw_requests()
    req = next((r for r in requests if r['id'] == request_id), None)
    
    if not req:
        await callback.answer("❌ So'rov topilmadi!")
        return
    
    try:
        # So'rovni rad etish va balansni qaytarish - bir xil transaction ichida
        reject_withdraw_request_and_refund(request_id)
        
        # Foydalanuvchiga xabar yuborish
        try:
            await callback.bot.send_message(
                req['user_id'],
                f"❌ Sizning pul yechib olish so'rovingiz #{request_id} rad etildi.\n"
                f"💰 {req['amount']} so'm balansingizga qaytarildi."
            )
        except Exception as e:
            logger.error(f"Failed to notify user about withdraw rejection: {e}")
        
        await callback.message.edit_text(f"❌ So'rov #{request_id} rad etildi va balans qaytarildi!")
        
    except Exception as e:
        logger.error(f"Failed to reject withdraw request {request_id}: {e}")
        await callback.message.edit_text(f"❌ So'rovni rad etishda xato yuz berdi: {str(e)}")
    
    await callback.answer()

async def back_to_withdraws(callback: types.CallbackQuery):
    """Returns to withdraw requests list."""
    await callback.message.edit_text("💸 Pul yechib olish so'rovlari:", reply_markup=admin_main_menu_kb())
    await callback.answer()

# --- USERS LIST FUNCTIONS ---
async def show_users_list(message: types.Message):
    """Shows the users list menu."""
    await message.answer(
        "👥 Foydalanuvchilar ro'yxati:\n\n"
        "Quyidagi variantlardan birini tanlang:",
        reply_markup=users_list_inline_kb()
    )

async def view_all_users(callback: types.CallbackQuery):
    """Shows all users with pagination."""
    users = get_all_users_detailed()
    if not users:
        await callback.message.edit_text("❌ Hech qanday foydalanuvchi topilmadi.")
        await callback.answer()
        return
    
    # Pagination
    page = 1
    users_per_page = 10
    total_pages = (len(users) + users_per_page - 1) // users_per_page
    
    await show_users_page(callback, users, page, total_pages, "all_users")

async def view_today_users(callback: types.CallbackQuery):
    """Shows users registered today."""
    today = datetime.date.today()
    users = get_users_by_date_range(start_date=today, end_date=today)
    
    if not users:
        await callback.message.edit_text("❌ Bugun hech qanday foydalanuvchi ro'yxatdan o'tmagan.")
        await callback.answer()
        return
    
    await show_users_list_direct(callback, users, "Bugungi foydalanuvchilar")

async def view_active_users(callback: types.CallbackQuery):
    """Shows active users (with balance > 0 or orders)."""
    all_users = get_all_users_detailed()
    active_users = []
    
    for user in all_users:
        if user['balance'] > 0 or user['is_blocked'] == 0:
            active_users.append(user)
    
    if not active_users:
        await callback.message.edit_text("❌ Faol foydalanuvchilar topilmadi.")
        await callback.answer()
        return
    
    await show_users_list_direct(callback, active_users, "Faol foydalanuvchilar")

async def show_users_page(callback: types.CallbackQuery, users: list, page: int, total_pages: int, action: str):
    """Shows a page of users with pagination."""
    users_per_page = 10
    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users[start_idx:end_idx]
    
    text = f"👥 Foydalanuvchilar ro'yxati (Sahifa {page}/{total_pages}):\n\n"
    
    for i, user in enumerate(page_users, start=start_idx + 1):
        username = user['username'] or "Username yo'q"
        balance = user['balance']
        is_blocked = "🚫" if user['is_blocked'] else "✅"
        created_at = user['created_at']
        
        text += f"{i}. {is_blocked} @{username}\n"
        text += f"   ID: {user['user_id']}\n"
        text += f"   Balans: {balance} so'm\n"
        text += f"   Ro'yxatdan o'tgan: {created_at}\n\n"
        
        if len(text) > 3000:  # Telegram message limit
            text += "... (qolgan foydalanuvchilar keyingi sahifada)"
            break
    
    keyboard = user_pagination_inline_kb(page, total_pages, action)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

async def show_users_list_direct(callback: types.CallbackQuery, users: list, title: str):
    """Shows users list directly without pagination."""
    text = f"👥 {title}:\n\n"
    
    for i, user in enumerate(users[:20], 1):  # Limit to 20 users
        username = user['username'] or "Username yo'q"
        balance = user['balance']
        is_blocked = "🚫" if user['is_blocked'] else "✅"
        created_at = user['created_at']
        
        text += f"{i}. {is_blocked} @{username}\n"
        text += f"   ID: {user['user_id']}\n"
        text += f"   Balans: {balance} so'm\n"
        text += f"   Ro'yxatdan o'tgan: {created_at}\n\n"
    
    if len(users) > 20:
        text += f"... va yana {len(users) - 20} ta foydalanuvchi"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_users_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

async def handle_user_pagination(callback: types.CallbackQuery):
    """Handles user pagination."""
    data = callback.data.split("_")
    action = data[0] + "_" + data[1]  # all_users, today_users, etc.
    page = int(data[3])
    
    if action == "all_users":
        users = get_all_users_detailed()
        total_pages = (len(users) + 9) // 10
        await show_users_page(callback, users, page, total_pages, "all_users")
    else:
        await callback.answer("❌ Xato!")

async def back_to_users_menu(callback: types.CallbackQuery):
    """Returns to users menu."""
    await callback.message.edit_text(
        "👥 Foydalanuvchilar ro'yxati:\n\n"
        "Quyidagi variantlardan birini tanlang:",
        reply_markup=users_list_inline_kb()
    )
    await callback.answer()

async def export_users_excel_handler(callback: types.CallbackQuery):
    """Exports users to Excel file."""
    try:
        await callback.answer("📤 Foydalanuvchilar Excel faylga export qilinmoqda...")
        
        file_path = export_users_excel(
            admin_id=callback.from_user.id,
            file_format="xlsx"
        )
        
        # Send the file to admin
        with open(file_path, 'rb') as file:
            await callback.bot.send_document(
                chat_id=callback.from_user.id,
                document=file,
                caption="📊 Foydalanuvchilar ro'yxati Excel faylga export qilindi!"
            )
        
        await callback.message.edit_text("✅ Foydalanuvchilar muvaffaqiyatli export qilindi!")
        
    except Exception as e:
        logger.error(f"Failed to export users: {e}")
        await callback.message.edit_text(f"❌ Export qilishda xato yuz berdi: {str(e)}")
        await callback.answer()

# --- REGISTRATION FUNCTION ---
def register_handlers(dp: Dispatcher):
    """Registers all message and callback query handlers."""
    dp.register_message_handler(admin_panel, commands=["admin"], state="*")
    dp.register_message_handler(show_stats, Text(equals="📊 Statistika"), state="*")
    dp.register_message_handler(export_excel, Text(equals="📂 Excel export"), state="*")
    dp.register_message_handler(start_broadcast, Text(equals="📨 Xabar yuborish"), state="*")
    dp.register_callback_query_handler(broadcast_all_start, lambda c: c.data == "broadcast_all", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(process_broadcast_text, content_types=['text', 'photo', 'video'], state=AdminStates.waiting_for_broadcast_text)
    dp.register_callback_query_handler(preview_broadcast, lambda c: c.data.startswith("preview_broadcast_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(send_broadcast, lambda c: c.data.startswith("send_broadcast_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(cancel_broadcast, lambda c: c.data == "cancel_broadcast", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(edit_broadcast, lambda c: c.data == "edit_broadcast", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(ask_user_id, lambda c: c.data == "broadcast_one", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(get_user_id_for_message, state=AdminStates.waiting_for_single_user_id)
    dp.register_message_handler(send_single_message, state=AdminStates.waiting_for_single_message)
    dp.register_message_handler(ask_user_for_manage, Text(equals="👤 Foydalanuvchi boshqaruvi"), state="*")
    dp.register_message_handler(manage_user, Regexp(r"^\d+$"), state=AdminStates.waiting_for_user_details)
    dp.register_callback_query_handler(block_user_cb, lambda c: c.data.startswith("block_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(unblock_user_cb, lambda c: c.data.startswith("unblock_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(ask_user_id, lambda c: c.data.startswith("send_message_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(edit_ad_text, Text(equals="📝 Reklama matnini o‘zgartirish"), state="*")
    dp.register_callback_query_handler(wait_new_ad_text, lambda c: c.data == "edit_ad_text", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(save_new_ad_text, state=AdminStates.waiting_for_new_ad_text)
    dp.register_message_handler(ask_video_upload, Text(equals="📹 Qo'llanma video yuklash"), state="*")
    dp.register_message_handler(save_guide_video, content_types=types.ContentType.VIDEO, state=AdminStates.waiting_for_video_upload)
    dp.register_message_handler(manage_orders, Text(equals="📦 Zakazlarni boshqarish"), state="*")
    dp.register_callback_query_handler(view_order, lambda c: c.data.startswith("view_order_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(approve_order, lambda c: c.data.startswith("approve_order_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(reject_order, lambda c: c.data.startswith("reject_order_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(back_to_orders, lambda c: c.data == "back_to_orders", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(manage_withdraw_requests, Text(equals="💸 Pul yechib olish so'rovlari"), state="*")
    dp.register_callback_query_handler(view_withdraw_request, lambda c: c.data.startswith("view_withdraw_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(process_payment, lambda c: c.data.startswith("process_payment_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(reject_withdraw_request, lambda c: c.data.startswith("reject_withdraw_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(back_to_withdraws, lambda c: c.data == "back_to_withdraws", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_message_handler(show_users_list, Text(equals="👥 Foydalanuvchilar ro'yxati"), state="*")
    dp.register_callback_query_handler(view_all_users, lambda c: c.data == "view_all_users", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(view_today_users, lambda c: c.data == "view_today_users", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(view_active_users, lambda c: c.data == "view_active_users", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(handle_user_pagination, lambda c: c.data.startswith("all_users_page_"), IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(back_to_users_menu, lambda c: c.data == "back_to_users_menu", IsPrivateCallback(), IsAdminCallback(), state="*")
    dp.register_callback_query_handler(export_users_excel_handler, lambda c: c.data == "export_users_excel", IsPrivateCallback(), IsAdminCallback(), state="*")