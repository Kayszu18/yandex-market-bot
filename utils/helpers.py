import logging
import asyncio
from typing import Any, Union, Optional
from aiogram import Bot
from aiogram.utils.exceptions import BotBlocked, UserDeactivated, TelegramAPIError
from database import update_export_message_stats

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096  # Telegram matn uzunligi cheklovi

def _sanitize_text(text: str) -> str:
    """
    Sanitizes the input text to prevent injection and ensure length limit.
    Args:
        text: Input text to sanitize.
    Returns:
        Sanitized text.
    """
    if not text:
        return ""
    text = text.strip()[:MAX_MESSAGE_LENGTH]
    return text.replace("<script>", "").replace("</script>", "")  # Oddiy tozalash, bleach ishlatish mumkin

async def bot_send_safe(
    bot: Bot,
    user_id: int,
    text: str = "",
    export_id: Optional[int] = None,
    **kwargs: Any
) -> bool:
    """
    Safely sends a text message to a user, handling errors and logging.
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID.
        text: Message text to send (optional if reply_markup is provided).
        export_id: Optional export/broadcast ID for statistics tracking.
        **kwargs: Additional parameters for send_message (e.g., parse_mode, reply_markup).
    Returns:
        True if message was sent successfully, False otherwise.
    """
    try:
        text = _sanitize_text(text)
        if text or kwargs.get("reply_markup") is not None:
            await bot.send_message(user_id, text or " ", **kwargs)
            if export_id:
                update_export_message_stats(export_id, sent=1, failed=0)
            logger.debug(f"Message sent to user {user_id}")
            return True
        return False
    except (BotBlocked, UserDeactivated) as e:
        logger.debug(f"Failed to send message to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except TelegramAPIError as e:
        logger.error(f"Telegram API error sending message to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending message to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False

async def bot_send_photo_safe(
    bot: Bot,
    user_id: int,
    photo: str,
    caption: str = "",
    export_id: Optional[int] = None,
    **kwargs: Any
) -> bool:
    """
    Safely sends a photo to a user, handling errors and logging.
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID.
        photo: Photo file ID or URL.
        caption: Photo caption (optional).
        export_id: Optional export/broadcast ID for statistics tracking.
        **kwargs: Additional parameters for send_photo (e.g., parse_mode, reply_markup).
    Returns:
        True if photo was sent successfully, False otherwise.
    """
    try:
        caption = _sanitize_text(caption)
        await bot.send_photo(user_id, photo, caption=caption, **kwargs)
        if export_id:
            update_export_message_stats(export_id, sent=1, failed=0)
        logger.debug(f"Photo sent to user {user_id}")
        return True
    except (BotBlocked, UserDeactivated) as e:
        logger.debug(f"Failed to send photo to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except TelegramAPIError as e:
        logger.error(f"Telegram API error sending photo to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending photo to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False

async def bot_send_video_safe(
    bot: Bot,
    user_id: int,
    video: str,
    caption: str = "",
    export_id: Optional[int] = None,
    **kwargs: Any
) -> bool:
    """
    Safely sends a video to a user, handling errors and logging.
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID.
        video: Video file ID or URL.
        caption: Video caption (optional).
        export_id: Optional export/broadcast ID for statistics tracking.
        **kwargs: Additional parameters for send_video (e.g., parse_mode, reply_markup).
    Returns:
        True if video was sent successfully, False otherwise.
    """
    try:
        caption = _sanitize_text(caption)
        await bot.send_video(user_id, video, caption=caption, **kwargs)
        if export_id:
            update_export_message_stats(export_id, sent=1, failed=0)
        logger.debug(f"Video sent to user {user_id}")
        return True
    except (BotBlocked, UserDeactivated) as e:
        logger.debug(f"Failed to send video to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except TelegramAPIError as e:
        logger.error(f"Telegram API error sending video to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending video to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False

async def bot_send_document_safe(
    bot: Bot,
    user_id: int,
    document: str,
    caption: str = "",
    export_id: Optional[int] = None,
    **kwargs: Any
) -> bool:
    """
    Safely sends a document to a user, handling errors and logging.
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID.
        document: Document file ID or URL.
        caption: Document caption (optional).
        export_id: Optional export/broadcast ID for statistics tracking.
        **kwargs: Additional parameters for send_document (e.g., parse_mode, reply_markup).
    Returns:
        True if document was sent successfully, False otherwise.
    """
    try:
        caption = _sanitize_text(caption)
        await bot.send_document(user_id, document, caption=caption, **kwargs)
        if export_id:
            update_export_message_stats(export_id, sent=1, failed=0)
        logger.debug(f"Document sent to user {user_id}")
        return True
    except (BotBlocked, UserDeactivated) as e:
        logger.debug(f"Failed to send document to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except TelegramAPIError as e:
        logger.error(f"Telegram API error sending document to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending document to {user_id}: {e}")
        if export_id:
            update_export_message_stats(export_id, sent=0, failed=1)
        return False

async def bot_send_batch_safe(
    bot: Bot,
    user_ids: list[int],
    text: str = "",
    export_id: Optional[int] = None,
    rate_limit_delay: float = 0.05,
    **kwargs: Any
) -> tuple[int, int]:
    """
    Sends a batch of messages to multiple users with rate limiting.
    Args:
        bot: Aiogram Bot instance.
        user_ids: List of user IDs to send messages to.
        text: Message text to send (optional if reply_markup is provided).
        export_id: Optional export/broadcast ID for statistics tracking.
        rate_limit_delay: Delay between messages to avoid Telegram API limits.
        **kwargs: Additional parameters for send_message (e.g., parse_mode, reply_markup).
    Returns:
        Tuple of (sent_count, failed_count).
    """
    sent_count = 0
    failed_count = 0
    text = _sanitize_text(text)

    for user_id in user_ids:
        success = await bot_send_safe(bot, user_id, text, export_id, **kwargs)
        if success:
            sent_count += 1
        else:
            failed_count += 1
        await asyncio.sleep(rate_limit_delay)  # Telegram API rate limitlaridan qochish

    logger.info(f"Batch send completed: {sent_count} sent, {failed_count} failed")
    return sent_count, failed_count