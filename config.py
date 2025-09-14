import os
import logging
from typing import List, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# .env faylini yuklash
load_dotenv()

class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass

class BotConfig:
    """Bot-related configuration."""
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    
    @classmethod
    def validate(cls) -> None:
        """Validates bot configuration."""
        if not cls.BOT_TOKEN:
            logger.error("BOT_TOKEN is not set in .env file")
            raise ConfigError("BOT_TOKEN must be provided in .env file")

class DatabaseConfig:
    """Database-related configuration."""
    DB_PATH: str = os.getenv("DB_PATH", "/home/kayszu/yandex_market_bot/database.db")
    REDIS_HOST: Optional[str] = os.getenv("REDIS_HOST")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    
    @classmethod
    def validate(cls) -> None:
        """Validates database configuration."""
        if not cls.DB_PATH:
            logger.error("DB_PATH is not set in .env file")
            raise ConfigError("DB_PATH must be provided in .env file")
        cls.DB_PATH = os.path.abspath(cls.DB_PATH)  # Absolute path for safety
        if cls.REDIS_HOST and cls.REDIS_PORT <= 0:
            logger.error(f"Invalid REDIS_PORT: {cls.REDIS_PORT}")
            raise ConfigError("REDIS_PORT must be a positive integer")

class AdminConfig:
    """Admin-related configuration."""
    ADMIN_IDS: List[int] = [
        int(x.strip()) for x in os.getenv("ADMIN_IDS", "1097943646,6668026635").split(",") if x.strip()
    ]
    ADMIN_PASSWORD: Optional[str] = os.getenv("ADMIN_PASSWORD")
    
    @classmethod
    def validate(cls) -> None:
        """Validates admin configuration."""
        if not cls.ADMIN_IDS:
            logger.error("No ADMIN_IDS provided in .env file")
            raise ConfigError("ADMIN_IDS must be provided in .env file")
        if cls.ADMIN_PASSWORD and len(cls.ADMIN_PASSWORD) < 8:
            logger.warning("ADMIN_PASSWORD is too short (minimum 8 characters)")

class ChannelConfig:
    """Channel-related configuration."""
    PROOF_CHANNEL_ID: Optional[str] = os.getenv("PROOF_CHANNEL_ID")
    PROOF_CHANNEL_USERNAME: Optional[str] = os.getenv("PROOF_CHANNEL_USERNAME", "@ProofChannel")
    SUPPORT_USERNAME: Optional[str] = os.getenv("SUPPORT_USERNAME", "@SupportBot")
    
    @classmethod
    def validate(cls) -> None:
        """Validates channel configuration."""
        if cls.PROOF_CHANNEL_ID and not cls.PROOF_CHANNEL_ID.startswith("-100"):
            logger.warning("PROOF_CHANNEL_ID should start with -100 for Telegram channels")
        if not cls.PROOF_CHANNEL_USERNAME:
            logger.error("PROOF_CHANNEL_USERNAME is not set in .env file")
            raise ConfigError("PROOF_CHANNEL_USERNAME must be provided in .env file")
        if not cls.SUPPORT_USERNAME:
            logger.error("SUPPORT_USERNAME is not set in .env file")
            raise ConfigError("SUPPORT_USERNAME must be provided in .env file")
        if cls.PROOF_CHANNEL_USERNAME and not cls.PROOF_CHANNEL_USERNAME.startswith("@"):
            logger.error(f"Invalid PROOF_CHANNEL_USERNAME: {cls.PROOF_CHANNEL_USERNAME}")
            raise ConfigError("PROOF_CHANNEL_USERNAME must start with @")
        if cls.SUPPORT_USERNAME and not cls.SUPPORT_USERNAME.startswith("@"):
            logger.error(f"Invalid SUPPORT_USERNAME: {cls.SUPPORT_USERNAME}")
            raise ConfigError("SUPPORT_USERNAME must start with @")

class RewardConfig:
    """Reward and referral configuration."""
    ZAKAZ_REWARD: int = int(os.getenv("ZAKAZ_REWARD", 10000))
    REFERRAL_PERCENT: float = float(os.getenv("REFERRAL_PERCENT", 0.10))
    MIN_WITHDRAW_AMOUNT: float = float(os.getenv("MIN_WITHDRAW_AMOUNT", 1000.0))
    
    @classmethod
    def validate(cls) -> None:
        """Validates reward configuration."""
        if cls.ZAKAZ_REWARD < 0:
            logger.error(f"Invalid ZAKAZ_REWARD: {cls.ZAKAZ_REWARD}")
            raise ConfigError("ZAKAZ_REWARD must be non-negative")
        if not 0 <= cls.REFERRAL_PERCENT <= 1:
            logger.error(f"Invalid REFERRAL_PERCENT: {cls.REFERRAL_PERCENT}")
            raise ConfigError("REFERRAL_PERCENT must be between 0 and 1")
        if cls.MIN_WITHDRAW_AMOUNT < 1000.0:
            logger.error(f"Invalid MIN_WITHDRAW_AMOUNT: {cls.MIN_WITHDRAW_AMOUNT}")
            raise ConfigError("MIN_WITHDRAW_AMOUNT must be at least 1000 so'm")

class LoggingConfig:
    """Logging-related configuration."""
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE: str = os.getenv("LOG_FILE", "/home/kayszu/yandex_market_bot/bot.log")
    
    @classmethod
    def validate(cls) -> None:
        """Validates logging configuration."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if cls.LOG_LEVEL not in valid_levels:
            logger.error(f"Invalid LOG_LEVEL: {cls.LOG_LEVEL}")
            raise ConfigError(f"LOG_LEVEL must be one of {valid_levels}")
        cls.LOG_FILE = os.path.abspath(cls.LOG_FILE)  # Absolute path for safety

class Config:
    """Main configuration class combining all config sections."""
    bot = BotConfig
    database = DatabaseConfig
    admin = AdminConfig
    channel = ChannelConfig
    reward = RewardConfig
    logging = LoggingConfig
    
    @classmethod
    def validate_all(cls) -> None:
        """Validates all configuration sections."""
        for section in (cls.bot, cls.database, cls.admin, cls.channel, cls.reward, cls.logging):
            section.validate()
        logger.info("All configurations validated successfully")

# Validate configurations on module import
try:
    Config.validate_all()
except ConfigError as e:
    logger.critical(f"Configuration error: {e}")
    raise