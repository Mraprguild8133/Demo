import os
import sqlite3
import logging
import secrets
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    MessageEntity
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    ContextTypes, 
    filters, 
    CallbackQueryHandler
)

from config import config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manage database operations"""
    
    def __init__(self):
        self.db_path = config.DB_PATH
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT,
                caption TEXT,
                uploader_id INTEGER NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                last_accessed TIMESTAMP
            )
        ''')
        
        # File links table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                unique_hash TEXT UNIQUE NOT NULL,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expiry_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE
            )
        ''')
        
        # User stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_uploads INTEGER DEFAULT 0,
                total_storage_used INTEGER DEFAULT 0,
                last_upload_date TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def add_file(self, file_data: Dict) -> int:
        """Add file to database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO files 
            (file_id, file_name, file_type, file_size, mime_type, caption, uploader_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            file_data['file_id'],
            file_data['file_name'],
            file_data['file_type'],
            file_data['file_size'],
            file_data.get('mime_type'),
            file_data.get('caption'),
            file_data['uploader_id']
        ))
        
        file_id = cursor.lastrowid
        
        # Update user stats
        cursor.execute('''
            INSERT OR REPLACE INTO user_stats 
            (user_id, total_uploads, total_storage_used, last_upload_date)
            VALUES (?, 
                    COALESCE((SELECT total_uploads FROM user_stats WHERE user_id = ?), 0) + 1,
                    COALESCE((SELECT total_storage_used FROM user_stats WHERE user_id = ?), 0) + ?,
                    ?)
        ''', (
            file_data['uploader_id'],
            file_data['uploader_id'],
            file_data['uploader_id'],
            file_data['file_size'],
            datetime.now()
        ))
        
        conn.commit()
        conn.close()
        return file_id
    
    def create_file_link(self, file_id: int, hash_length: int = 8) -> str:
        """Create unique link for file"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        unique_hash = secrets.token_urlsafe(hash_length)
        expiry_date = datetime.now() + timedelta(days=config.LINK_EXPIRY_DAYS)
        
        cursor.execute('''
            INSERT INTO file_links (file_id, unique_hash, expiry_date)
            VALUES (?, ?, ?)
        ''', (file_id, unique_hash, expiry_date))
        
        conn.commit()
        conn.close()
        return unique_hash
    
    def get_user_files(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get files uploaded by user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT f.id, f.file_name, f.file_type, f.file_size, f.upload_date, 
                   f.access_count, fl.unique_hash
            FROM files f
            LEFT JOIN file_links fl ON f.id = fl.file_id AND fl.is_active = TRUE
            WHERE f.uploader_id = ? AND f.is_active = TRUE
            ORDER BY f.upload_date DESC
            LIMIT ?
        ''', (user_id, limit))
        
        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row[0],
                'file_name': row[1],
                'file_type': row[2],
                'file_size': row[3],
                'upload_date': row[4],
                'access_count': row[5],
                'unique_hash': row[6]
            })
        
        conn.close()
        return files
    
    def get_file_by_hash(self, unique_hash: str) -> Optional[Dict]:
        """Get file details by unique hash"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT f.file_id, f.file_name, f.file_type, f.file_size, f.mime_type, 
                   f.caption, f.access_count, fl.expiry_date
            FROM files f
            JOIN file_links fl ON f.id = fl.file_id
            WHERE fl.unique_hash = ? AND fl.is_active = TRUE AND f.is_active = TRUE
        ''', (unique_hash,))
        
        row = cursor.fetchone()
        if row:
            # Update access count
            cursor.execute('''
                UPDATE files 
                SET access_count = access_count + 1, last_accessed = ?
                WHERE file_id = ?
            ''', (datetime.now(), row[0]))
            
            conn.commit()
            conn.close()
            
            return {
                'file_id': row[0],
                'file_name': row[1],
                'file_type': row[2],
                'file_size': row[3],
                'mime_type': row[4],
                'caption': row[5],
                'access_count': row[6] + 1,
                'expiry_date': row[7]
            }
        
        conn.close()
        return None

class FileStoreBot:
    """Main bot class"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.app = Application.builder().token(config.BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot handlers"""
        # Command handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("mystorage", self.my_storage))
        self.app.add_handler(CommandHandler("stats", self.user_stats))
        
        # Message handlers
        self.app.add_handler(MessageHandler(
            filters.Document | filters.VIDEO | filters.AUDIO | filters.PHOTO, 
            self.handle_file
        ))
        
        # Callback query handler for buttons
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        welcome_text = """
🤖 **Welcome to FileStore Bot!**

📁 **Features:**
• Store files up to 4GB
• Generate shareable links
• No premium account required
• Fast and secure

📤 **How to use:**
1. Send any file (document, photo, video, audio)
2. Bot will store it and generate a unique link
3. Share the link with anyone

🔧 **Commands:**
/start - Show this message
/mystorage - Show your stored files
/stats - Your upload statistics
/help - Get help

⚠️ **Note:** Large files may take time to upload/download.
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message"""
        help_text = """
📖 **Bot Help Guide**

📤 **Uploading Files:**
Simply send any file to the bot. Maximum file size: 4GB

🔗 **Generating Links:**
After uploading, the bot automatically generates a unique link.

📊 **Managing Files:**
Use /mystorage to view and manage your uploaded files.

📈 **Statistics:**
Use /stats to see your upload statistics.

🛡️ **Privacy:**
Only people with your generated links can access your files.

❓ **Supported Files:**
• Documents (PDF, ZIP, RAR, DOC, XLS, etc.)
• Photos (JPEG, PNG, WEBP, etc.)
• Videos (MP4, AVI, MKV, MOV, etc.)
• Audio (MP3, WAV, OGG, etc.)
• Any other file type

📞 **Support:**
Contact admin for any issues.
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    def format_file_size(self, size_bytes):
        """Format file size to human readable format"""
        if size_bytes is None:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming files"""
        user_id = update.effective_user.id
        message = update.message
        
        try:
            # Determine file type and get file object
            if message.document:
                file_obj = message.document
                file_type = "document"
            elif message.video:
                file_obj = message.video
                file_type = "video"
            elif message.audio:
                file_obj = message.audio
                file_type = "audio"
            elif message.photo:
                file_obj = message.photo[-1]  # Highest resolution
                file_type = "photo"
            else:
                await message.reply_text("❌ Unsupported file type!")
                return
            
            # Get file details
            file_id = file_obj.file_id
            file_name = getattr(file_obj, 'file_name', f'{file_type}_{file_id}')
            file_size = file_obj.file_size
            mime_type = getattr(file_obj, 'mime_type', 'unknown')
            caption = message.caption
            
            # Check file size
            if file_size and file_size > config.MAX_FILE_SIZE:
                await message.reply_text("❌ File size exceeds 4GB limit!")
                return
            
            # Check if file type is allowed
            if any(ext in file_name.lower() for ext in config.BLOCKED_EXTENSIONS):
                await message.reply_text("❌ This file type is not allowed for security reasons!")
                return
            
            # Prepare file data
            file_data = {
                'file_id': file_id,
                'file_name': file_name,
                'file_type': file_type,
                'file_size': file_size,
                'mime_type': mime_type,
                'caption': caption,
                'uploader_id': user_id
            }
            
            # Store file in database
            file_db_id = self.db.add_file(file_data)
            
            # Generate unique link
            unique_hash = self.db.create_file_link(file_db_id, config.HASH_LENGTH)
            
            # Create shareable link
            bot_username = (await self.app.bot.get_me()).username
            file_link = f"https://t.me/{bot_username}?start={unique_hash}"
            
            # Prepare response message
            response_text = f"""
✅ **File Successfully Stored!**

📁 **File Name:** `{file_name}`
📊 **File Size:** {self.format_file_size(file_size)}
📝 **Type:** {file_type.title()}
🔗 **Shareable Link:** {file_link}

💡 **Tip:** Share this link with anyone to allow them to download the file.
            """
            
            keyboard = [
                [InlineKeyboardButton("📁 Open File", url=file_link)],
                [InlineKeyboardButton("🗂️ My Storage", callback_data="mystorage")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text(
                response_text, 
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error handling file: {e}")
            await message.reply_text("❌ An error occurred while processing your file. Please try again.")
    
    async def my_storage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's stored files"""
        user_id = update.effective_user.id
        
        try:
            files = self.db.get_user_files(user_id)
            
            if not files:
                await update.message.reply_text("📭 You haven't uploaded any files yet.")
                return
            
            response_text = "📁 **Your Stored Files:**\n\n"
            
            for i, file in enumerate(files[:10], 1):  # Show first 10 files
                file_size = self.format_file_size(file['file_size'])
                upload_date = file['upload_date'][:10] if file['upload_date'] else "Unknown"
                
                response_text += f"{i}. **{file['file_name']}**\n"
                response_text += f"   📊 Size: {file_size} | 📅 {upload_date}\n"
                response_text += f"   👁️ Views: {file['access_count']}\n"
                
                if file['unique_hash']:
                    bot_username = (await self.app.bot.get_me()).username
                    file_link = f"https://t.me/{bot_username}?start={file['unique_hash']}"
                    response_text += f"   🔗 `{file_link}`\n"
                
                response_text += "\n"
            
            if len(files) > 10:
                response_text += f"\n📋 Showing 10 out of {len(files)} files. Use buttons below to navigate."
            
            # Create navigation buttons
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_storage")],
                [InlineKeyboardButton("📊 Statistics", callback_data="user_stats")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                response_text, 
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error showing storage: {e}")
            await update.message.reply_text("❌ An error occurred while retrieving your files.")
    
    async def user_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        user_id = update.effective_user.id
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT total_uploads, total_storage_used, last_upload_date
                FROM user_stats WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                await update.message.reply_text("📊 You haven't uploaded any files yet.")
                return
            
            total_uploads, total_storage, last_upload = row
            
            stats_text = f"""
📊 **Your Statistics**

📤 **Total Uploads:** {total_uploads}
💾 **Storage Used:** {self.format_file_size(total_storage)}
📅 **Last Upload:** {last_upload[:10] if last_upload else 'Never'}

⚡ **File Size Limit:** {self.format_file_size(config.MAX_FILE_SIZE)}
            """
            
            keyboard = [
                [InlineKeyboardButton("📁 My Storage", callback_data="mystorage")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                stats_text, 
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error showing stats: {e}")
            await update.message.reply_text("❌ An error occurred while retrieving statistics.")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if query.data == "mystorage":
            # Create a temporary message to simulate my_storage command
            class MockMessage:
                def __init__(self, user_id, chat_id):
                    self.from_user = type('obj', (object,), {'id': user_id})()
                    self.chat = type('obj', (object,), {'id': chat_id})()
                    self.reply_text = query.edit_message_text
            
            mock_update = Update(update.update_id, message=MockMessage(user_id, query.message.chat_id))
            await self.my_storage(mock_update, context)
            
        elif query.data == "user_stats":
            class MockMessage:
                def __init__(self, user_id, chat_id):
                    self.from_user = type('obj', (object,), {'id': user_id})()
                    self.chat = type('obj', (object,), {'id': chat_id})()
                    self.reply_text = query.edit_message_text
            
            mock_update = Update(update.update_id, message=MockMessage(user_id, query.message.chat_id))
            await self.user_stats(mock_update, context)
            
        elif query.data == "refresh_storage":
            await query.edit_message_text("🔄 Refreshing...")
            class MockMessage:
                def __init__(self, user_id, chat_id):
                    self.from_user = type('obj', (object,), {'id': user_id})()
                    self.chat = type('obj', (object,), {'id': chat_id})()
                    self.reply_text = query.edit_message_text
            
            mock_update = Update(update.update_id, message=MockMessage(user_id, query.message.chat_id))
            await self.my_storage(mock_update, context)
            
        elif query.data == "refresh_stats":
            await query.edit_message_text("🔄 Refreshing...")
            class MockMessage:
                def __init__(self, user_id, chat_id):
                    self.from_user = type('obj', (object,), {'id': user_id})()
                    self.chat = type('obj', (object,), {'id': chat_id})()
                    self.reply_text = query.edit_message_text
            
            mock_update = Update(update.update_id, message=MockMessage(user_id, query.message.chat_id))
            await self.user_stats(mock_update, context)
    
    def run(self):
        """Start the bot"""
        logger.info("Starting FileStore Bot...")
        self.app.run_polling()

# Main execution
if __name__ == "__main__":
    bot 
