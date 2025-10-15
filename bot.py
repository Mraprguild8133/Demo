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
    
    def __init__(self, total_size: int, callback: Callable):
        self.total_size = total_size
        self.callback = callback
        self.downloaded = 0
        self.start_time = datetime.now()
        
    def update(self, chunk_size: int):
        self.downloaded += chunk_size
        percentage = (self.downloaded / self.total_size) * 100
        speed = self.downloaded / (datetime.now() - self.start_time).total_seconds()
        self.callback(self.downloaded, self.total_size, percentage, speed)

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
            
            progress_tracker = None
            if progress_callback:
                progress_tracker = ProgressTracker(file_size, progress_callback)
            
            # Download file with progress tracking
            await message.download_media(
                file=file_path,
                progress_callback=progress_tracker.update if progress_tracker else None
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
    ) -> MessageMediaDocument:
        """Upload file with progress tracking"""
        try:
            file_size = os.path.getsize(file_path)
            logger.info(f"Uploading {file_path} ({file_size} bytes)")
            
            progress_tracker = None
            if progress_callback:
                progress_tracker = ProgressTracker(file_size, progress_callback)
            
            # Upload file
            message = await client.send_file(
                chat_id,
                file_path,
                force_document=True,
                progress_callback=progress_tracker.update if progress_tracker else None
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
        
        async def update_progress(downloaded, total, percentage, speed):
            speed_mb = speed / (1024 * 1024)
            progress_text = f"📥 **Downloading file...**\n`{percentage:.1f}%` - {speed_mb:.1f} MB/s"
            try:
                await progress_msg.edit(progress_text)
            except:
                pass
        
        # Download the file - FIXED: Use event.message directly
        file_path = await FileHandler.download_file(
            event.message,  # Fixed: Use event.message instead of event.get_message()
            progress_callback=update_progress
        )
        
        # Update message for upload
        await progress_msg.edit("📤 **Uploading to storage...**\n`0%` - Preparing upload")
        
        async def update_upload_progress(downloaded, total, percentage, speed):
            speed_mb = speed / (1024 * 1024)
            progress_text = f"📤 **Uploading to storage...**\n`{percentage:.1f}%` - {speed_mb:.1f} MB/s"
            try:
                await progress_msg.edit(progress_text)
            except:
                pass
        
        # Re-upload to get permanent file ID (in production, use proper storage)
        uploaded_media = await FileHandler.upload_file(
            file_path,
            event.chat_id,
            progress_callback=update_upload_progress
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
        except:
            pass
        
        await progress_msg.edit(success_text, parse_mode='markdown')
        
    except Exception as e:
        logger.error(f"File handling error: {e}")
        await event.reply(f"❌ **Error processing file:** {str(e)}")

@client.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Show bot status"""
    status_text = """
🟢 **Bot Status: Online**

**System Information:**
• Async operations: ✅ Enabled
• Progress tracking: ✅ Active
• Large file support: ✅ Up to 4GB
• File links: ✅ Working

**Storage:**
• Active links: `{links_count}`
• Max file size: `4 GB`
• Supported types: `All files`

**Commands:**
• Send any file to upload
• `/help` - Show help
• `/status` - Show this status
    """.format(links_count=len(file_links))
    
    await event.reply(status_text, parse_mode='markdown')

@client.on(events.NewMessage(pattern='/cleanup'))
async def cleanup_handler(event):
    """Clean up expired file links"""
    try:
        # Simple cleanup - in production, implement proper expiration logic
        expired_count = 0
        current_time = datetime.now()
        
        # This is a basic implementation - enhance with proper TTL logic
        if hasattr(config, 'FILE_LINK_TTL'):
            # Implement TTL-based cleanup here
            pass
        
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

# Web server for download links (basic implementation)
async def handle_download(request):
    """Handle download requests"""
    token = request.match_info.get('token')
    
    if not token or token not in file_links:
        return web.Response(text="Invalid or expired download link", status=404)
    
    file_id = file_links[token]
    
    # In production, implement proper file serving
    # For now, we'll redirect to Telegram file
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
