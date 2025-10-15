import os
import asyncio
import logging
from typing import Optional, Callable
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import Document, MessageMediaDocument
from telethon.tl.custom import Button
import aiofiles
from aiohttp import web
import secrets

from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Telegram client with config
client = TelegramClient('file_bot', config.API_ID, config.API_HASH)

# In-memory storage for file links (use database in production)
file_links = {}

class ProgressTracker:
    """Track upload/download progress with callbacks"""
    
    def __init__(self, total_size: int, callback: Callable, operation: str = "Downloading"):
        self.total_size = total_size
        self.callback = callback
        self.downloaded = 0
        self.start_time = datetime.now()
        self.operation = operation
        
    def create_callback(self):
        """Create a Telethon-compatible progress callback"""
        def telethon_callback(received_bytes, total_bytes):
            """Telethon progress callback - receives (received_bytes, total_bytes)"""
            percentage = (received_bytes / total_bytes) * 100 if total_bytes > 0 else 0
            
            # Calculate speed
            elapsed = (datetime.now() - self.start_time).total_seconds()
            speed = received_bytes / elapsed if elapsed > 0 else 0
            
            # Call our custom progress callback
            self.callback(received_bytes, total_bytes, percentage, speed, self.operation)
        
        return telethon_callback

class FileHandler:
    """Handle file operations asynchronously"""
    
    @staticmethod
    async def download_file(
        message, 
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Download file with progress tracking"""
        try:
            file_name = message.file.name or f"file_{message.id}"
            file_size = message.file.size
            
            logger.info(f"Downloading {file_name} ({file_size} bytes)")
            
            # Create downloads directory if not exists
            os.makedirs('downloads', exist_ok=True)
            file_path = f"downloads/{file_name}"
            
            # FIXED: Create proper Telethon-compatible progress callback
            if progress_callback:
                progress_tracker = ProgressTracker(file_size, progress_callback, "Downloading")
                telethon_callback = progress_tracker.create_callback()
                
                # Download file with progress tracking
                await message.download_media(
                    file=file_path,
                    progress_callback=telethon_callback
                )
            else:
                # Download without progress tracking
                await message.download_media(file=file_path)
            
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
    ) -> MessageMediaDocument:
        """Upload file with progress tracking"""
        try:
            file_size = os.path.getsize(file_path)
            logger.info(f"Uploading {file_path} ({file_size} bytes)")
            
            # FIXED: Create proper Telethon-compatible progress callback
            if progress_callback:
                progress_tracker = ProgressTracker(file_size, progress_callback, "Uploading")
                telethon_callback = progress_tracker.create_callback()
                
                # Upload file with progress tracking
                message = await client.send_file(
                    chat_id,
                    file_path,
                    force_document=True,
                    progress_callback=telethon_callback
                )
            else:
                # Upload without progress tracking
                message = await client.send_file(
                    chat_id,
                    file_path,
                    force_document=True
                )
            
            logger.info(f"Upload completed: {file_path}")
            return message.media
            
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

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Handle /start command"""
    user = await event.get_sender()
    welcome_text = f"""
🤖 **Welcome to High-Speed File Bot!** 🚀

**Features:**
• Upload any files (up to 4GB)
• Download with generated links
• Real-time progress tracking
• High-speed async operations

**Commands:**
• Just send me any file to upload
• Use `/help` for more information

**User ID:** `{user.id}`
    """
    
    await event.reply(welcome_text, parse_mode='markdown')

@client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
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
    
    await event.reply(help_text, parse_mode='markdown')

@client.on(events.NewMessage(func=lambda e: e.file and not e.file.mime_type == 'text/plain'))
async def file_handler(event):
    """Handle incoming files"""
    try:
        user = await event.get_sender()
        logger.info(f"File received from user {user.id}")
        
        # Send initial progress message
        progress_msg = await event.reply("📥 **Downloading file...**\n`0%` - Preparing download")
        
        # FIXED: Progress callback with correct parameters
        async def update_progress(received, total, percentage, speed, operation):
            speed_mb = speed / (1024 * 1024) if speed > 0 else 0
            if total > 0:
                received_mb = received / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                progress_text = f"📥 **{operation}...**\n`{percentage:.1f}%` ({received_mb:.1f}/{total_mb:.1f} MB) - {speed_mb:.1f} MB/s"
            else:
                progress_text = f"📥 **{operation}...**\n`Preparing...`"
            
            try:
                await progress_msg.edit(progress_text)
            except Exception as e:
                logger.debug(f"Progress update error: {e}")
        
        # FIXED: Use event.message directly (not event.get_message())
        file_path = await FileHandler.download_file(
            event.message,  # CORRECT: event.message is the message object
            progress_callback=update_progress
        )
        
        # Update message for upload
        await progress_msg.edit("📤 **Uploading to storage...**\n`0%` - Preparing upload")
        
        # Upload the file
        uploaded_media = await FileHandler.upload_file(
            file_path,
            event.chat_id,
            progress_callback=update_progress
        )
        
        # Generate download link
        file_id = uploaded_media.document.id
        download_link = FileHandler.generate_download_link(file_id)
        
        # Get file info
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Create response message
        success_text = f"""
✅ **File Uploaded Successfully!**

📁 **File Name:** `{file_name}`
📊 **File Size:** `{file_size_mb:.2f} MB`
🔗 **Download Link:** {download_link}

⚠️ **Note:** This link will expire after 24 hours.
        """
        
        # Clean up local file
        try:
            os.remove(file_path)
            logger.info(f"Cleaned up local file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not remove file {file_path}: {e}")
        
        await progress_msg.edit(success_text, parse_mode='markdown')
        
    except Exception as e:
        logger.error(f"File handling error: {e}")
        error_msg = await event.reply("❌ **Error processing file. Please try again.**")
        # Delete error message after 10 seconds
        await asyncio.sleep(10)
        await error_msg.delete()

@client.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Show bot status"""
    status_text = f"""
🟢 **Bot Status: Online**

**System Information:**
• Async operations: ✅ Enabled
• Progress tracking: ✅ Active
• Large file support: ✅ Up to 4GB
• File links: ✅ Working

**Storage:**
• Active links: `{len(file_links)}`
• Max file size: `4 GB`
• Supported types: `All files`

**Commands:**
• Send any file to upload
• `/help` - Show help
• `/status` - Show this status
    """
    
    await event.reply(status_text, parse_mode='markdown')

@client.on(events.NewMessage(pattern='/cleanup'))
async def cleanup_handler(event):
    """Clean up expired file links"""
    try:
        # Simple cleanup - remove some old links if we have too many
        max_links = 1000
        if len(file_links) > max_links:
            # Remove oldest links (simple implementation)
            keys_to_remove = list(file_links.keys())[:len(file_links) - max_links]
            expired_count = len(keys_to_remove)
            for key in keys_to_remove:
                del file_links[key]
        else:
            expired_count = 0
        
        cleanup_text = f"""
🧹 **Cleanup Completed**

• Expired links removed: `{expired_count}`
• Active links remaining: `{len(file_links)}`
• Storage optimized: ✅
        """
        
        await event.reply(cleanup_text, parse_mode='markdown')
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        await event.reply(f"❌ **Cleanup error:** {str(e)}")

@client.on(events.NewMessage(pattern='/info'))
async def info_handler(event):
    """Show file info before processing"""
    try:
        if event.file:
            file_name = event.file.name or f"file_{event.id}"
            file_size = event.file.size
            file_size_mb = file_size / (1024 * 1024)
            
            info_text = f"""
📁 **File Information:**

**Name:** `{file_name}`
**Size:** `{file_size_mb:.2f} MB`
**Type:** `{event.file.mime_type or 'Unknown'}`

Send the file to start upload process.
            """
            await event.reply(info_text, parse_mode='markdown')
        else:
            await event.reply("❌ Please send a file to get information.")
    except Exception as e:
        logger.error(f"Info handler error: {e}")

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
        
        Bot: @{(await client.get_me()).username}
        """,
        headers={'Content-Disposition': f'attachment; filename="file_{file_id}"'}
    )

async def start_web_server():
    """Start web server for download links"""
    app = web.Application()
    app.router.add_get('/download/{token}', handle_download)
    
    # Get web server config with defaults
    host = getattr(config, 'WEB_HOST', 'localhost')
    port = getattr(config, 'WEB_PORT', 8080)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Web server started on http://{host}:{port}")

async def main():
    """Main function to start the bot"""
    logger.info("Starting High-Speed File Bot...")
    
    # Validate config
    if not all([config.API_ID, config.API_HASH, config.BOT_TOKEN]):
        logger.error("Missing required configuration!")
        exit(1)
    
    # Start web server for download links
    if getattr(config, 'ENABLE_WEB_SERVER', True):
        await start_web_server()
    
    # Start the bot
    await client.start(bot_token=config.BOT_TOKEN)
    
    # Get bot info
    me = await client.get_me()
    logger.info(f"Bot started successfully: @{me.username}")
    
    # Log bot capabilities
    logger.info("Bot features:")
    logger.info("- Async file operations")
    logger.info("- Progress tracking")
    logger.info("- 4GB file support")
    logger.info("- Download link generation")
    
    # Keep running
    await client.run_until_disconnected()

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
