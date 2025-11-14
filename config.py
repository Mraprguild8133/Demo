import os
from typing import Dict, Any

class Config:
    """Configuration class for FileStore Bot"""
    
    def __init__(self):
        # Bot Configuration
        self.BOT_TOKEN = os.getenv('BOT_TOKEN', 'your_bot_token_here')
        self.ADMIN_ID = int(os.getenv('ADMIN_ID', '123456789'))
        
        # Database Configuration
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///file_store.db')
        self.DB_PATH = 'file_store.db'
        
        # Bot Settings
        self.MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB in bytes
        self.LINK_EXPIRY_DAYS = 365  # Link expiry in days
        self.HASH_LENGTH = 8  # Length of unique hash for links
        
        # Rate Limiting
        self.MAX_UPLOADS_PER_HOUR = 50
        self.MAX_STORAGE_PER_USER = 100 * 1024 * 1024 * 1024  # 100GB per user
        
        # Web Server for direct downloads (optional)
        self.WEB_SERVER_ENABLED = False
        self.WEB_SERVER_PORT = 8080
        
        # Security
        self.ALLOWED_FILE_TYPES = [
            'image/', 'video/', 'audio/', 'text/', 'application/'
        ]
        self.BLOCKED_EXTENSIONS = ['exe', 'bat', 'cmd', 'sh', 'php']

# Create global config instance
config = Config()
