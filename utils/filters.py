import logging
from typing import Union
from aiogram import types
from aiogram.dispatcher.filters import BoundFilter
from database import is_user_blocked, is_admin, user_exists, get_user_balance

logger = logging.getLogger(__name__)

class IsPrivate(BoundFilter):
    """
    Filter to check if the message is sent in a private chat.
    """
    async def check(self, message: types.Message) -> bool:
        is_private = message.chat.type == types.ChatType.PRIVATE
        if not is_private:
            logger.debug(f"User {message.from_user.id} attempted non-private chat action in {message.chat.type}")
            await message.answer(
                "❌ Bu buyruq faqat shaxsiy chatda ishlaydi! Iltimos, bot bilan shaxsiy chatda yozing.",
                reply_markup=types.ReplyKeyboardRemove()
            )
        return is_private

class IsNotBlocked(BoundFilter):
    """
    Filter to check if the user is not blocked.
    """
    async def check(self, message: types.Message) -> bool:
        try:
            user_id = message.from_user.id
            is_blocked = is_user_blocked(user_id)
            if is_blocked:
                logger.debug(f"Blocked user {user_id} attempted to interact")
                await message.answer(
                    "🚫 Siz botdan foydalana olmaysiz, chunki bloklangansiz. Sababni bilish uchun support bilan bog‘laning.",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            return not is_blocked
        except Exception as e:
            logger.error(f"Failed to check block status for user {user_id}: {e}")
            await message.answer(
                "❌ Xato yuz berdi. Iltimos, keyinroq qayta urinib ko‘ring.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return False  # Fail-closed for security

class IsAdmin(BoundFilter):
    """
    Filter to check if the user is an admin.
    """
    async def check(self, message: types.Message) -> bool:
        try:
            user_id = message.from_user.id
            is_admin_user = is_admin(user_id)
            if not is_admin_user:
                logger.debug(f"Non-admin user {user_id} attempted admin action")
                await message.answer(
                    "❌ Siz admin emassiz! Bu buyruq faqat administratorlar uchun.",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            return is_admin_user
        except Exception as e:
            logger.error(f"Failed to check admin status for user {user_id}: {e}")
            await message.answer(
                "❌ Xato yuz berdi. Iltimos, keyinroq qayta urinib ko‘ring.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return False  # Fail-closed for security

class IsRegistered(BoundFilter):
    """
    Filter to check if the user is registered in the database.
    """
    async def check(self, message: types.Message) -> bool:
        try:
            user_id = message.from_user.id
            exists = user_exists(user_id)
            if not exists:
                logger.debug(f"Unregistered user {user_id} attempted action")
                await message.answer(
                    "❌ Siz ro‘yxatdan o‘tmagansiz! Iltimos, avval ro‘yxatdan o‘ting (/start).",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            return exists
        except Exception as e:
            logger.error(f"Failed to check registration for user {user_id}: {e}")
            await message.answer(
                "❌ Xato yuz berdi. Iltimos, keyinroq qayta urinib ko‘ring.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return False  # Fail-closed for security

class HasSufficientBalance(BoundFilter):
    """
    Filter to check if the user has sufficient balance for withdrawal.
    Args:
        min_balance: Minimum required balance in USDT.
    """
    def __init__(self, min_balance: float = 10.0):
        self.min_balance = min_balance

    async def check(self, message: types.Message) -> bool:
        try:
            user_id = message.from_user.id
            balance = get_user_balance(user_id)
            sufficient = balance >= self.min_balance
            if not sufficient:
                logger.debug(f"User {user_id} has insufficient balance: {balance} USDT")
                await message.answer(
                    f"❌ Balansingiz yetarli emas! Minimal yechib olish summasi: {self.min_balance} USDT. Hozirgi balans: {balance:.2f} USDT.",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            return sufficient
        except Exception as e:
            logger.error(f"Failed to check balance for user {user_id}: {e}")
            await message.answer(
                "❌ Xato yuz berdi. Iltimos, keyinroq qayta urinib ko‘ring.",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return False  # Fail-closed for security

class IsGroup(BoundFilter):
    """
    Filter to check if the message is sent in a group or supergroup chat.
    """
    async def check(self, message: types.Message) -> bool:
        is_group = message.chat.type in (types.ChatType.GROUP, types.ChatType.SUPERGROUP)
        if not is_group:
            logger.debug(f"User {message.from_user.id} attempted group action in {message.chat.type}")
            await message.answer(
                "❌ Bu buyruq faqat guruh chatlarida ishlaydi!",
                reply_markup=types.ReplyKeyboardRemove()
            )
        return is_group

# Callback Query Filters
class IsPrivateCallback(BoundFilter):
    """
    Filter to check if the callback query is from a private chat.
    """
    async def check(self, callback: types.CallbackQuery) -> bool:
        is_private = callback.message.chat.type == types.ChatType.PRIVATE
        if not is_private:
            logger.debug(f"User {callback.from_user.id} attempted non-private callback in {callback.message.chat.type}")
            await callback.answer("❌ Bu buyruq faqat shaxsiy chatda ishlaydi!")
        return is_private

class IsNotBlockedCallback(BoundFilter):
    """
    Filter to check if the user is not blocked (for callback queries).
    """
    async def check(self, callback: types.CallbackQuery) -> bool:
        try:
            user_id = callback.from_user.id
            is_blocked = is_user_blocked(user_id)
            if is_blocked:
                logger.debug(f"Blocked user {user_id} attempted callback interaction")
                await callback.answer("🚫 Siz botdan foydalana olmaysiz, chunki bloklangansiz.")
            return not is_blocked
        except Exception as e:
            logger.error(f"Failed to check block status for user {user_id}: {e}")
            await callback.answer("❌ Xato yuz berdi.")
            return False

class IsAdminCallback(BoundFilter):
    """
    Filter to check if the user is an admin (for callback queries).
    """
    async def check(self, callback: types.CallbackQuery) -> bool:
        try:
            user_id = callback.from_user.id
            is_admin_user = is_admin(user_id)
            if not is_admin_user:
                logger.debug(f"Non-admin user {user_id} attempted admin callback")
                await callback.answer("❌ Siz admin emassiz!")
            return is_admin_user
        except Exception as e:
            logger.error(f"Failed to check admin status for user {user_id}: {e}")
            await callback.answer("❌ Xato yuz berdi.")
            return False