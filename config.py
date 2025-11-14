import os

class Config:
    """Configuration class for the Telegram File Share Bot."""
    
    # Telegram API credentials (REQUIRED)
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", 1234567))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "your_api_hash_here")
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here")
    
    # Bot username (will be set automatically)
    BOT_USERNAME: str = None
    
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

# Validate configuration
try:
    config.validate()
except ValueError as e:
    print(f"Configuration error: {e}")
