import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.executor import start_polling
from config import Config
from database import init_db, run_migrations, get_admin_list
from handlers import user, admin, payments, referrals, support
from utils.helpers import bot_send_safe
from utils.filters import IsPrivate, IsNotBlocked, IsAdmin, IsRegistered, HasSufficientBalance, IsGroup, IsPrivateCallback, IsNotBlockedCallback, IsAdminCallback

# Logging configuration
class UnicodeSafeStreamHandler(logging.StreamHandler):
    """Custom StreamHandler to handle Unicode characters safely."""
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            # Fallback to ASCII-only logging
            msg = self.format(record).encode('ascii', errors='replace').decode('ascii')
            stream.write(msg + self.terminator)
            self.flush()

logging.basicConfig(
    level=getattr(logging, Config.logging.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(Config.logging.LOG_FILE, encoding='utf-8'),  # Faylga UTF-8 bilan yozish
        UnicodeSafeStreamHandler()  # Konsolga xavfsiz chiqarish
    ]
)
logger = logging.getLogger(__name__)

# Initialize bot and storage
bot = Bot(token=Config.bot.BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()  # PythonAnywhere bepul tierda redis yo'q
dp = Dispatcher(bot, storage=storage)

# Register handlers and filters
def register_handlers_and_filters(dp: Dispatcher) -> None:
    """
    Registers all handlers and filters for the bot.
    Args:
        dp: Aiogram Dispatcher instance.
    """
    dp.filters_factory.bind(IsPrivate)
    dp.filters_factory.bind(IsNotBlocked)
    dp.filters_factory.bind(IsAdmin)
    dp.filters_factory.bind(IsRegistered)
    dp.filters_factory.bind(HasSufficientBalance)
    dp.filters_factory.bind(IsGroup)
    dp.filters_factory.bind(IsPrivateCallback)
    dp.filters_factory.bind(IsNotBlockedCallback)
    dp.filters_factory.bind(IsAdminCallback)
    user.register_handlers(dp)
    admin.register_handlers(dp)
    payments.register_handlers(dp)
    referrals.register_handlers(dp)
    support.register_handlers(dp)
    logger.info("All handlers and filters registered successfully")

async def notify_admins(bot: Bot, message: str) -> None:
    """
    Sends a notification to all admins.
    Args:
        bot: Aiogram Bot instance.
        message: Message to send to admins.
    """
    admins = get_admin_list()
    for admin_id in admins:
        try:
            await bot_send_safe(bot, admin_id, message, parse_mode="HTML")
            await asyncio.sleep(0.05)  # Rate limitdan qochish
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

async def on_startup(dp: Dispatcher) -> None:
    """
    Executes on bot startup.
    Args:
        dp: Aiogram Dispatcher instance.
    """
    logger.info("Starting bot initialization...")
    
    # Initialize database and run migrations
    try:
        init_db()
        run_migrations()
        logger.info("Database initialized and migrations applied")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        await notify_admins(bot, f"❌ Bot ishga tushishda xato: Ma'lumotlar bazasi ulanishi muvaffaqiyatsiz.\nXato: {e}")
        raise
    
    logger.info("Starting bot in polling mode")
    await notify_admins(bot, "✅ Bot polling orqali ishga tushdi!")
    logger.info("Bot fully started")

async def on_shutdown(dp: Dispatcher) -> None:
    """
    Executes on bot shutdown.
    Args:
        dp: Aiogram Dispatcher instance.
    """
    logger.info("Shutting down bot...")
    await notify_admins(bot, "🛑 Bot to‘xtatildi.")
    await storage.close()
    await bot.session.close()
    logger.info("Bot shutdown complete")

def main() -> None:
    """
    Main function to start the bot in polling mode.
    """
    try:
        register_handlers_and_filters(dp)
        logger.info("Starting polling mode")
        start_polling(
            dispatcher=dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise

if __name__ == "__main__":
    main()