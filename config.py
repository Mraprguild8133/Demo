import os

class Config:
    """Configuration class for the Telegram File Share Bot."""
    
    # Telegram API credentials (REQUIRED)
    API_ID = int(os.getenv("TELEGRAM_API_ID", 1234567))
    API_HASH = os.getenv("TELEGRAM_API_HASH", "your_api_hash_here")
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here")
    
    # Bot settings
    ADMINS = [int(x) for x in os.getenv("ADMINS", "").split()] if os.getenv("ADMINS") else []
    
    # Bot username (will be set automatically, but you can force it here if needed)
    BOT_USERNAME = os.getenv("BOT_USERNAME", "")  # Optional: set your bot username here
    
    # Shortner settings (optional)
    SHORT_URL = os.getenv("SHORT_URL", "inshorturl.com")
    SHORT_API = os.getenv("SHORT_API", "")
    
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
    print("Please set the required environment variables")
