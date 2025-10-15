import os
from dataclasses import dataclass

@dataclass
class Config:
    """Configuration class for the Telegram bot."""
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "google/gemini-flash-1.5")
    OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    MAX_MESSAGE_LENGTH: int = 4096  # Telegram message limit

# Create config instance
config = Config()
