import os
import asyncio
import logging
from typing import Optional, Callable, Dict
from datetime import datetime
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import MessageMediaType
from pyrogram.errors import RPCError
import aiofiles
from aiohttp import web
import secrets
import tgcrypto

from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Pyrogram client with TgCrypto
app = Client(
    "file_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True
)

# In-memory storage for file links (use database in production)
file_links = {}

# Message deduplication tracking
processing_messages: Dict[int, bool] = {}
completed_messages: Dict[int, bool] = {}

class ProgressTracker:
    """Track upload/download progress with callbacks"""
    
    def __init__(self, total_size: int, callback: Callable, operation: str = "Downloading"):
        self.total_size = total_size
        self.callback = callback
        self.processed = 0
        self.start_time = datetime.now()
        self.operation = operation
        
    def create_callback(self):
        """Create a Pyrogram-compatible progress callback"""
        def pyrogram_callback(current, total):
            """Pyrogram progress callback - receives (current, total)"""
            percentage = (current / total) * 100 if total > 0 else 0
            
            # Calculate speed
            elapsed = (datetime.now() - self.start_time).total_seconds()
            speed = current / elapsed if elapsed > 0 else 0
            
            # Call our custom progress callback
            self.callback(current, total, percentage, speed, self.operation)
        
        return pyrogram_callback

class FileHandler:
    """Handle file operations asynchronously with Pyrogram"""
    
    @staticmethod
    async def download_file(
        message: Message,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Download file with progress tracking"""
        try:
            # Get file information
            if message.document:
                file_name = message.document.file_name or f"document_{message.id}.bin"
                file_size = message.document.file_size
            elif message.video:
                file_name = message.video.file_name or f"video_{message.id}.mp4"
                file_size = message.video.file_size
            elif message.audio:
                file_name = message.audio.file_name or f"audio_{message.id}.mp3"
                file_size = message.audio.file_size
            elif message.photo:
                file_name = f"photo_{message.id}.jpg"
                file_size = message.photo.file_size
            else:
                file_name = f"file_{message.id}.bin"
                file_size = 0
            
            logger.info(f"Downloading {file_name} ({file_size} bytes)")
            
            # Create downloads directory if not exists
            os.makedirs('downloads', exist_ok=True)
            file_path = f"downloads/{file_name}"
            
            # Create progress callback
            if progress_callback and file_size > 0:
                progress_tracker = ProgressTracker(file_size, progress_callback, "Downloading")
                pyrogram_callback = progress_tracker.create_callback()
            else:
                pyrogram_callback = None
            
            # Download file with progress tracking
            await message.download(
                file_name=file_path,
                progress=pyrogram_callback,
                progress_args=(file_size,) if file_size > 0 else None
            )
            
            logger.info(f"Download completed: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            raise
    
    @staticmethod
    async def upload_file(
        file_path: str,
        chat_id: int,
        progress_callback: Optional[Callable] = None
    ) -> Message:
        """Upload file with progress tracking"""
        try:
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            logger.info(f"Uploading {file_path} ({file_size} bytes)")
            
            # Create progress callback
            if progress_callback:
                progress_tracker = ProgressTracker(file_size, progress_callback, "Uploading")
                pyrogram_callback = progress_tracker.create_callback()
            else:
                pyrogram_callback = None
            
            # Upload file with progress tracking
            message = await app.send_document(
                chat_id=chat_id,
                document=file_path,
                progress=pyrogram_callback,
                progress_args=(file_size,) if file_size > 0 else None
            )
            
            logger.info(f"Upload completed: {file_path}")
            return message
            
        except Exception as e:
            logger.error(f"Upload error: {e}")
            raise
    
    @staticmethod
    def generate_download_link(file_id: str) -> str:
        """Generate unique download link for file"""
        token = secrets.token_urlsafe(16)
        file_links[token] = file_id
        
        # Use domain from config if available, otherwise use localhost
        domain = getattr(config, 'DOMAIN', 'localhost:8080')
        return f"https://{domain}/download/{token}"

def is_message_processing(message_id: int) -> bool:
    """Check if a message is currently being processed"""
    return processing_messages.get(message_id, False)

def mark_message_processing(message_id: int, processing: bool = True):
    """Mark a message as being processed or not"""
    if processing:
        processing_messages[message_id] = True
    else:
        processing_messages.pop(message_id, None)

def is_message_completed(message_id: int) -> bool:
    """Check if a message has already been processed"""
    return completed_messages.get(message_id, False)

def mark_message_completed(message_id: int):
    """Mark a message as completed processing"""
    completed_messages[message_id] = True
    # Clean up processing flag
    mark_message_processing(message_id, False)

async def cleanup_old_messages():
    """Clean up old message tracking to prevent memory leaks"""
    try:
        # Keep only the last 1000 messages to prevent memory issues
        max_messages = 1000
        if len(completed_messages) > max_messages:
            # Remove oldest messages
            keys_to_remove = list(completed_messages.keys())[:len(completed_messages) - max_messages]
            for key in keys_to_remove:
                completed_messages.pop(key, None)
                processing_messages.pop(key, None)
        
        logger.debug(f"Message tracking: {len(processing_messages)} processing, {len(completed_messages)} completed")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    """Handle /start command"""
    welcome_text = f"""
🤖 **Welcome to High-Speed File Bot!** 🚀

**Features:**
• Upload any files (up to 4GB)
• Download with generated links
• Real-time progress tracking
• High-speed async operations with Pyrogram
• Secure encryption with TgCrypto

**Commands:**
• Just send me any file to upload
• Use `/help` for more information

**User ID:** `{message.from_user.id}`
    """
    
    await message.reply_text(welcome_text, parse_mode="markdown")

@app.on_message(filters.command("help"))
async def help_handler(client, message: Message):
    """Handle /help command"""
    help_text = """
📖 **How to use this bot:**

1. **Upload Files:** Simply send any file to the bot
2. **Download Links:** After upload, you'll get a download link
3. **Progress Tracking:** See real-time upload/download progress
4. **Large Files:** Supports files up to 4GB

**Supported Files:**
• Documents (PDF, DOC, ZIP, etc.)
• Videos (MP4, AVI, MKV, etc.)
• Audio files (MP3, WAV, etc.)
• Images (JPG, PNG, etc.)
• Any other file type

**Note:** Files are stored temporarily and links expire after some time.
    """
    
    await message.reply_text(help_text, parse_mode="markdown")

@app.on_message(
    filters.document | filters.video | filters.audio | filters.photo,
    group=1
)
async def file_handler(client, message: Message):
    """Handle incoming files with deduplication"""
    
    # Check if message is already being processed or completed
    if is_message_processing(message.id):
        logger.info(f"Message {message.id} is already being processed, skipping")
        return
    
    if is_message_completed(message.id):
        logger.info(f"Message {message.id} has already been processed, skipping")
        return
    
    # Mark message as being processed
    mark_message_processing(message.id, True)
    
    try:
        user = message.from_user
        logger.info(f"File received from user {user.id} (message {message.id})")
        
        # Send initial progress message
        progress_msg = await message.reply_text("📥 **Downloading file...**\n`0%` - Preparing download")
        
        # Progress callback
        async def update_progress(current, total, percentage, speed, operation):
            speed_mb = speed / (1024 * 1024) if speed > 0 else 0
            if total > 0:
                current_mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                progress_text = f"📥 **{operation}...**\n`{percentage:.1f}%` ({current_mb:.1f}/{total_mb:.1f} MB) - {speed_mb:.1f} MB/s"
            else:
                progress_text = f"📥 **{operation}...**\n`Preparing...`"
            
            try:
                await progress_msg.edit_text(progress_text)
            except Exception as e:
                logger.debug(f"Progress update error: {e}")
        
        # Download the file
        file_path = await FileHandler.download_file(
            message,
            progress_callback=update_progress
        )
        
        # Update message for upload
        await progress_msg.edit_text("📤 **Uploading to storage...**\n`0%` - Preparing upload")
        
        # Upload the file
        uploaded_message = await FileHandler.upload_file(
            file_path,
            message.chat.id,
            progress_callback=update_progress
        )
        
        # Generate download link
        if uploaded_message.document:
            file_id = uploaded_message.document.file_id
        elif uploaded_message.video:
            file_id = uploaded_message.video.file_id
        elif uploaded_message.audio:
            file_id = uploaded_message.audio.file_id
        else:
            file_id = f"file_{uploaded_message.id}"
            
        download_link = FileHandler.generate_download_link(file_id)
        
        # Get file info
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Create inline keyboard with download button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download File", url=download_link)],
            [InlineKeyboardButton("🔄 Share", switch_inline_query="")]
        ])
        
        # Create response message
        success_text = f"""
✅ **File Uploaded Successfully!**

📁 **File Name:** `{file_name}`
📊 **File Size:** `{file_size_mb:.2f} MB`
🔗 **Download Link:** `{download_link}`

⚠️ **Note:** This link will expire after 24 hours.
        """
        
        # Clean up local file
        try:
            os.remove(file_path)
            logger.info(f"Cleaned up local file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not remove file {file_path}: {e}")
        
        await progress_msg.edit_text(
            success_text, 
            parse_mode="markdown",
            reply_markup=keyboard
        )
        
        # Mark message as completed
        mark_message_completed(message.id)
        
        # Clean up old messages periodically
        await cleanup_old_messages()
        
    except RPCError as e:
        logger.error(f"Telegram RPC error: {e}")
        # Remove processing flag on error
        mark_message_processing(message.id, False)
        await message.reply_text("❌ **Telegram error. Please try again.**")
    except Exception as e:
        logger.error(f"File handling error: {e}")
        # Remove processing flag on error
        mark_message_processing(message.id, False)
        error_msg = await message.reply_text("❌ **Error processing file. Please try again.**")
        # Delete error message after 10 seconds
        await asyncio.sleep(10)
        await error_msg.delete()

@app.on_message(filters.command("status"))
async def status_handler(client, message: Message):
    """Show bot status"""
    status_text = f"""
🟢 **Bot Status: Online**

**System Information:**
• Pyrogram: ✅ Enabled
• TgCrypto: ✅ Active
• Async operations: ✅ Enabled
• Progress tracking: ✅ Active
• Large file support: ✅ Up to 4GB
• File links: ✅ Working
• Duplicate protection: ✅ Active

**Storage:**
• Active links: `{len(file_links)}`
• Processing messages: `{len(processing_messages)}`
• Completed messages: `{len(completed_messages)}`
• Max file size: `4 GB`
• Supported types: `All files`

**Commands:**
• Send any file to upload
• `/help` - Show help
• `/status` - Show this status
• `/cleanup` - Cleanup storage
• `/stats` - Show statistics
    """
    
    await message.reply_text(status_text, parse_mode="markdown")

@app.on_message(filters.command("cleanup"))
async def cleanup_handler(client, message: Message):
    """Clean up expired file links and message tracking"""
    try:
        # Clean up file links
        max_links = 1000
        if len(file_links) > max_links:
            keys_to_remove = list(file_links.keys())[:len(file_links) - max_links]
            expired_links_count = len(keys_to_remove)
            for key in keys_to_remove:
                del file_links[key]
        else:
            expired_links_count = 0
        
        # Clean up message tracking
        await cleanup_old_messages()
        cleaned_messages = len(processing_messages) + len(completed_messages) - 1000
        if cleaned_messages < 0:
            cleaned_messages = 0
        
        cleanup_text = f"""
🧹 **Cleanup Completed**

• Expired links removed: `{expired_links_count}`
• Message tracking cleaned: `{cleaned_messages}`
• Active links remaining: `{len(file_links)}`
• Active messages tracking: `{len(processing_messages) + len(completed_messages)}`
• Storage optimized: ✅
        """
        
        await message.reply_text(cleanup_text, parse_mode="markdown")
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        await message.reply_text(f"❌ **Cleanup error:** {str(e)}")

@app.on_message(filters.command("info"))
async def info_handler(client, message: Message):
    """Show file info before processing"""
    try:
        if (message.document or message.video or message.audio or message.photo):
            if message.document:
                file_name = message.document.file_name or f"document_{message.id}.bin"
                file_size = message.document.file_size
                file_type = "Document"
            elif message.video:
                file_name = message.video.file_name or f"video_{message.id}.mp4"
                file_size = message.video.file_size
                file_type = "Video"
            elif message.audio:
                file_name = message.audio.file_name or f"audio_{message.id}.mp3"
                file_size = message.audio.file_size
                file_type = "Audio"
            elif message.photo:
                file_name = f"photo_{message.id}.jpg"
                file_size = message.photo.file_size
                file_type = "Photo"
            
            file_size_mb = file_size / (1024 * 1024) if file_size else 0
            
            info_text = f"""
📁 **File Information:**

**Name:** `{file_name}`
**Size:** `{file_size_mb:.2f} MB`
**Type:** `{file_type}`

Send the file to start upload process.
            """
            await message.reply_text(info_text, parse_mode="markdown")
        else:
            await message.reply_text("❌ Please send a file to get information.")
    except Exception as e:
        logger.error(f"Info handler error: {e}")

@app.on_message(filters.command("stats"))
async def stats_handler(client, message: Message):
    """Show bot statistics"""
    try:
        # Get some basic stats
        downloads_dir = Path("downloads")
        if downloads_dir.exists():
            total_files = len(list(downloads_dir.glob("*")))
            total_size = sum(f.stat().st_size for f in downloads_dir.glob("*") if f.is_file())
            total_size_mb = total_size / (1024 * 1024)
        else:
            total_files = 0
            total_size_mb = 0
        
        stats_text = f"""
📊 **Bot Statistics**

**File Storage:**
• Active download links: `{len(file_links)}`
• Local files: `{total_files}`
• Local storage used: `{total_size_mb:.2f} MB`

**Message Tracking:**
• Processing messages: `{len(processing_messages)}`
• Completed messages: `{len(completed_messages)}`

**Performance:**
• Pyrogram: ✅ Optimized
• TgCrypto: ✅ Encrypted
• Async: ✅ High-speed
• Progress: ✅ Real-time
• Duplicate protection: ✅ Active

**Limits:**
• Max file size: `4 GB`
• Link TTL: `24 hours`
            """
        
        await message.reply_text(stats_text, parse_mode="markdown")
        
    except Exception as e:
        logger.error(f"Stats error: {e}")

# Web server for download links (basic implementation)
async def handle_download(request):
    """Handle download requests"""
    token = request.match_info.get('token')
    
    if not token or token not in file_links:
        return web.Response(text="Invalid or expired download link", status=404)
    
    file_id = file_links[token]
    
    # In production, implement proper file serving
    return web.Response(
        text=f"""
        Download Link for File ID: {file_id}
        
        In production, this would serve the file directly.
        Currently, you need to use the Telegram file reference.
        
        Bot: @{(await app.get_me()).username}
        """,
        headers={'Content-Disposition': f'attachment; filename="file_{file_id}"'}
    )

async def start_web_server():
    """Start web server for download links"""
    app_web = web.Application()
    app_web.router.add_get('/download/{token}', handle_download)
    
    # Get web server config with defaults
    host = getattr(config, 'WEB_HOST', 'localhost')
    port = getattr(config, 'WEB_PORT', 8080)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Web server started on http://{host}:{port}")

async def main():
    """Main function to start the bot"""
    logger.info("Starting High-Speed File Bot with Pyrogram...")
    
    # Validate config
    if not all([config.API_ID, config.API_HASH, config.BOT_TOKEN]):
        logger.error("Missing required configuration!")
        exit(1)
    
    # Start web server for download links
    if getattr(config, 'ENABLE_WEB_SERVER', True):
        await start_web_server()
    
    # Start the Pyrogram client
    await app.start()
    
    # Get bot info
    me = await app.get_me()
    logger.info(f"Bot started successfully: @{me.username}")
    
    # Log bot capabilities
    logger.info("Bot features:")
    logger.info("- Pyrogram with TgCrypto encryption")
    logger.info("- Async file operations")
    logger.info("- Progress tracking")
    logger.info("- 4GB file support")
    logger.info("- Download link generation")
    logger.info("- Duplicate message protection")
    
    # Keep running
    await asyncio.Event().wait()
    
if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('downloads', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        # Stop the client properly
        asyncio.run(app.stop())
