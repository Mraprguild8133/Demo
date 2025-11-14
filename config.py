import os
from typing import Optional

class Config:
    """Configuration class for the Telegram File Share Bot."""
    
    # Telegram API credentials (REQUIRED)
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", 1234567))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "your_api_hash_here")
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here")
    
    # Application ID for Firestore path simulation
    APP_ID: str = os.getenv("APP_ID", "file_bot_v1")
    
    # Optional: Maximum file size in bytes (4GB default)
    MAX_FILE_SIZE: int = 4 * 1024 * 1024 * 1024
    
    # Optional: Database configuration for future use
    USE_REAL_FIRESTORE: bool = os.getenv("USE_REAL_FIRESTORE", "false").lower() == "true"
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        required_vars = {
            "API_ID": cls.API_ID,
            "API_HASH": cls.API_HASH,
            "BOT_TOKEN": cls.BOT_TOKEN
        }
        
        missing = [var for var, value in required_vars.items() 
                  if not value or str(value).startswith("your_")]
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

# Create config instance
config = Config()

# Validate configuration on import
try:
    config.validate()
except ValueError as e:
    print(f"Configuration error: {e}")
    print("Please set the required environment variables or update config.py")
