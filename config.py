import os
from typing import Optional

class Config:
    """Configuration class for the Telegram bot"""
    
    def __init__(self):
        # Required Telegram configuration
        self.API_ID = int(os.getenv('API_ID', 0))
        self.API_HASH = os.getenv('API_HASH', '')
        self.BOT_TOKEN = os.getenv('BOT_TOKEN', '')
        
        # Web server configuration (optional)
        self.WEB_HOST = os.getenv('WEB_HOST', 'localhost')
        self.WEB_PORT = int(os.getenv('WEB_PORT', 8080))
        self.ENABLE_WEB_SERVER = os.getenv('ENABLE_WEB_SERVER', 'true').lower() == 'true'
        
        # Domain for download links (optional)
        self.DOMAIN = os.getenv('DOMAIN', 'localhost:8080')
        
        # File handling configuration
        self.MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 4 * 1024 * 1024 * 1024))  # 4GB default
        self.FILE_LINK_TTL = int(os.getenv('FILE_LINK_TTL', 24 * 60 * 60))  # 24 hours default
        
        # Logging configuration
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')
        
    def validate(self) -> bool:
        """Validate required configuration"""
        required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
        for var in required_vars:
            if not getattr(self, var):
                return False
        return True

# Global config instance
config = Config()
