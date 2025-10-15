import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class optimized for Gemini models."""
    def __init__(self):
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        self.AI_MODEL = os.getenv("AI_MODEL", "google/gemini-2.0-flash-exp")
        self.OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
        self.REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
        self.MAX_MESSAGE_LENGTH = 4096
        
        # Gemini-specific parameters
        self.GEMINI_CONFIG = {
            "max_tokens": 4000,
            "temperature": 0.7,
            "top_p": 0.9,
        }
        
    def validate(self) -> bool:
        """Validate that all required configs are present."""
        required_vars = {
            "TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN,
            "OPENROUTER_API_KEY": self.OPENROUTER_API_KEY
        }
        
        missing = [var for var, value in required_vars.items() if not value]
        if missing:
            print(f"❌ Missing required environment variables: {', '.join(missing)}")
            return False
        return True

# Create global config instance
config = Config()
