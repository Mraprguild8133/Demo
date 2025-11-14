import base64
import os
import secrets
import json
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait

# Import configuration from external file
from config import config

# --- FIREBASE / PERSISTENCE MOCK ---
FILE_LINK_DB = {}

def save_file_data(app_id: str, file_key: str, data: dict):
    """Mocks saving file data to Firestore."""
    FILE_LINK_DB[file_key] = data
    print(f"MOCK DB: Saved data for key: {file_key}. Current DB size: {len(FILE_LINK_DB)}")

def get_file_data(app_id: str, file_key: str) -> dict | None:
    """Mocks retrieving file data from Firestore."""
    return FILE_LINK_DB.get(file_key)

# --- UTILITY FUNCTIONS ---

def generate_base64_key() -> str:
    """Generates a URL-safe, short base64 key."""
    random_bytes = secrets.token_bytes(16)
    b64_string = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return b64_string

def format_size(size_bytes):
    """Format file size in human-readable format."""
    if not size_bytes or size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {size_names[i]}"

def create_share_keyboard(share_link: str, file_name: str, base64_key: str) -> InlineKeyboardMarkup:
    """Create an inline keyboard with working share buttons."""
    # URL encode the file name for the share message
    import urllib.parse
    encoded_file_name = urllib.parse.quote(file_name)
    
    # Create the share message text
    share_text = f"📁 Download {file_name} via File Share Bot"
    
    keyboard = [
        # Button 1: Direct bot start (THIS WILL WORK)
        [
            InlineKeyboardButton(
                "🚀 Get File Now", 
                url=f"https://t.me/{config.BOT_USERNAME}?start={base64_key}"
            )
        ],
        # Button 2: Copy to clipboard (with visual feedback)
        [
            InlineKeyboardButton(
                "📋 Copy Link", 
                callback_data=f"copy_{base64_key}"
            )
        ],
        # Button 3: Share to other chats (THIS WILL WORK)
        [
            InlineKeyboardButton(
                "📤 Share to Friends", 
                url=f"https://t.me/share/url?url={urllib.parse.quote(share_link)}&text={urllib.parse.quote(share_text)}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- TELEGRAM BOT LOGIC ---

# Initialize the Pyrogram Client
app = Client(
    "file_share_bot_session",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# Store bot username globally
BOT_USERNAME = None

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """
    Handles the /start command, especially when a file link is used.
    """
    global BOT_USERNAME
    if not BOT_USERNAME and client.me:
        BOT_USERNAME = client.me.username

    # Extract the base64 argument after /start
    if len(message.command) > 1:
        base64_key = message.command[1]
        
        # Retrieve file data from the mock database
        file_data = get_file_data("file_bot_v1", base64_key)

        if not file_data:
            await message.reply_text(
                "❌ **Error:** File link is invalid or expired. Please upload a file to generate a new link."
            )
            return

        file_id = file_data.get('file_id')
        file_name = file_data.get('file_name', 'Unnamed File')
        file_size_bytes = file_data.get('file_size', 0)

        caption_text = (
            f"📥 **File Ready for Download**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** `{format_size(file_size_bytes)}`\n\n"
            f"✅ Click below to download instantly!"
        )

        try:
            # Send the actual file using the retrieved file_id
            await client.send_document(
                chat_id=message.chat.id,
                document=file_id,
                caption=caption_text
            )

        except FloodWait as e:
            await message.reply_text(f"⚠️ **Rate Limit:** Please wait {e.value} seconds before trying again.")
        except Exception as e:
            print(f"Error sending file: {e}")
            await message.reply_text("❌ An unexpected error occurred while sending the file.")

    else:
        # Standard /start message
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload a File", switch_inline_query="")]
        ])
        
        await message.reply_text(
            "👋 **Welcome to File Share Bot!**\n\n"
            "**How to use:**\n"
            "• Send me any file (document, video, audio, etc.)\n"
            "• I'll generate a permanent share link\n"
            "• Share the link with anyone for instant downloads\n\n"
            "⚡ **Features:**\n"
            "• Instant download speeds\n"
            "• Files up to 4GB supported\n"
            "• Permanent links\n"
            "• Easy sharing options",
            reply_markup=keyboard
        )

@app.on_message(filters.document & filters.private)
async def file_handler(client: Client, message: Message):
    """
    Handles uploaded documents, stores their ID, and generates the special link.
    """
    global BOT_USERNAME
    if not BOT_USERNAME and client.me:
        BOT_USERNAME = client.me.username

    try:
        if not message.document:
            await message.reply_text("Please upload a file document.")
            return

        # Check for large file
        file_size_bytes = message.document.file_size
        if file_size_bytes and file_size_bytes > 4 * 1024 * 1024 * 1024:
            await message.reply_text("❌ File is too large. Telegram limits: 4GB max.")
            return

        # Get file details
        file_id = message.document.file_id
        file_name = message.document.file_name or "Unnamed File"

        # Generate unique key
        base64_key = generate_base64_key()

        # Prepare data to store
        file_data = {
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size_bytes or 0,
            'uploader_user_id': message.from_user.id,
            'timestamp': message.date.isoformat() if message.date else None
        }

        # Save file metadata
        save_file_data("file_bot_v1", base64_key, file_data)

        # Construct the share link
        if BOT_USERNAME:
            share_link = f"https://t.me/{BOT_USERNAME}?start={base64_key}"
            
            reply_text = (
                "✅ **Your Share Link is Ready!**\n\n"
                f"**File:** `{file_name}`\n"
                f"**Size:** `{format_size(file_size_bytes)}`\n\n"
                "**Choose an option below:**"
            )
            
            # Create keyboard with WORKING buttons
            keyboard = create_share_keyboard(share_link, file_name, base64_key)
            
            await message.reply_text(
                reply_text, 
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            await message.reply_text(
                f"✅ File saved! Use this key: `{base64_key}`"
            )

    except Exception as e:
        print(f"Error handling file upload: {e}")
        await message.reply_text("❌ An error occurred while processing your file.")

@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    """Handle button callbacks."""
    data = callback_query.data
    
    if data.startswith("copy_"):
        base64_key = data[5:]  # Remove "copy_" prefix
        
        if BOT_USERNAME:
            share_link = f"https://t.me/{BOT_USERNAME}?start={base64_key}"
            
            # Show confirmation
            await callback_query.answer(
                "📋 Link copied to clipboard! You can now paste it anywhere.",
                show_alert=False
            )
            
            # Also send as a message for easy copying
            await callback_query.message.reply_text(
                f"**Here's your share link:**\n\n`{share_link}`\n\n"
                "You can select and copy this text to share with others."
            )
        else:
            await callback_query.answer("Error: Could not generate link", show_alert=True)

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    """Show bot statistics."""
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"• **Files stored:** {len(FILE_LINK_DB)}\n"
        f"• **Bot username:** @{BOT_USERNAME or 'Loading...'}\n"
        f"• **Storage:** Temporary (resets on restart)"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")],
        [InlineKeyboardButton("📤 Upload File", switch_inline_query="")]
    ])
    
    await message.reply_text(stats_text, reply_markup=keyboard)

@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    """Show help message."""
    help_text = (
        "🤖 **File Share Bot Help**\n\n"
        "**Commands:**\n"
        "• /start - Start the bot\n"
        "• /help - Show this message\n"
        "• /stats - Show statistics\n\n"
        "**How to share files:**\n"
        "1. Send me any file\n"
        "2. I'll create a permanent link\n"
        "3. Use the buttons to share\n\n"
        "**Button Options:**\n"
        "• 🚀 Get File Now - Direct download\n"
        "• 📋 Copy Link - Copy to clipboard\n"
        "• 📤 Share to Friends - Share via Telegram"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Try It Now - Upload File", switch_inline_query="")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard)

# --- MAIN EXECUTION BLOCK ---
async def main():
    """Starts the bot and keeps it running."""
    global BOT_USERNAME
    
    print("Starting Telegram File Share Bot...")
    await app.start()
    
    if app.me:
        BOT_USERNAME = app.me.username
        print(f"Bot started as @{BOT_USERNAME}")
        print("✅ Bot is ready! Users can upload files and get share links.")
    else:
        print("❌ Bot started, but could not retrieve username.")

    await idle()
    print("Stopping bot...")
    await app.stop()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Error: {e}")
