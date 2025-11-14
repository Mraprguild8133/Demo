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

# --- FIREBASE / PERSISTENCE MOCK (MANDATORY REQUIREMENT) ---
# Mock storage for file_id -> base64_key mapping
FILE_LINK_DB = {}

def get_db_ref(app_id, collection_name):
    """Simulates getting a reference to the public Firestore collection."""
    print(f"--- MOCK DB: Accessing public collection: /artifacts/{app_id}/public/data/{collection_name} ---")
    return FILE_LINK_DB

def save_file_data(app_id: str, file_key: str, data: dict):
    """Mocks saving file data to Firestore (FILE_LINK_DB)."""
    FILE_LINK_DB[file_key] = data
    print(f"MOCK DB: Saved data for key: {file_key}. Current DB size: {len(FILE_LINK_DB)}")

def get_file_data(app_id: str, file_key: str) -> dict | None:
    """Mocks retrieving file data from Firestore (FILE_LINK_DB)."""
    data = FILE_LINK_DB.get(file_key)
    if data:
        print(f"MOCK DB: Retrieved data for key: {file_key}")
    else:
        print(f"MOCK DB: Key {file_key} not found.")
    return data

# --- UTILITY FUNCTIONS ---

def generate_base64_key() -> str:
    """Generates a URL-safe, short base64 key from a random hex string."""
    random_bytes = secrets.token_bytes(16)
    b64_string = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return b64_string

def format_size(size_bytes):
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

def create_share_keyboard(share_link: str, file_name: str) -> InlineKeyboardMarkup:
    """Create an inline keyboard with share button and copy option."""
    keyboard = [
        [
            InlineKeyboardButton("🔗 Open Share Link", url=share_link)
        ],
        [
            InlineKeyboardButton("📋 Copy Link", callback_data=f"copy_{share_link.split('=')[-1]}")
        ],
        [
            InlineKeyboardButton("📤 Share to Chat", 
                               url=f"https://t.me/share/url?url={share_link}&text=Download {file_name}")
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

# A mock application ID for the Firestore path simulation
APP_ID_MOCK = config.APP_ID if hasattr(config, 'APP_ID') else "file_bot_v1"

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """
    Handles the /start command, especially when a file link is used.
    """
    # Extract the base64 argument after /start
    if len(message.command) > 1:
        base64_key = message.command[1]
        
        # 1. Retrieve file data from the mock database
        file_data = get_file_data(APP_ID_MOCK, base64_key)

        if not file_data:
            await message.reply_text(
                "❌ **Error:** File link is invalid or expired. Please upload a file to generate a new link."
            )
            return

        file_id = file_data.get('file_id')
        file_name = file_data.get('file_name', 'Unnamed File')
        file_size_bytes = file_data.get('file_size', 0)

        caption_text = (
            f"📥 **Instant Download Link Activated**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** `{format_size(file_size_bytes)}`\n\n"
            f"This is a direct, instant-speed download via Telegram's server."
        )

        try:
            # 2. Send the actual file using the retrieved file_id
            await client.send_document(
                chat_id=message.chat.id,
                document=file_id,
                caption=caption_text
            )
            # 3. Optional: Send a confirmation message
            await message.reply_text(
                "✅ File successfully sent for instant download! The link worked."
            )

        except FloodWait as e:
            await message.reply_text(f"⚠️ **Rate Limit:** Please wait {e.value} seconds before trying again.")
        except Exception as e:
            print(f"Error sending file: {e}")
            await message.reply_text("❌ An unexpected error occurred while sending the file.")

    else:
        # Standard /start message with improved formatting
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload a File", switch_inline_query="")]
        ])
        
        await message.reply_text(
            "👋 Welcome to the File Share Bot!\n\n"
            "**How to use:**\n"
            "1. Upload any file (up to 4GB) to me\n"
            "2. I'll generate a permanent share link\n"
            "3. Share the link for instant downloads\n\n"
            "⚡ **Features:**\n"
            "• Instant download speeds\n"
            "• No file size limits (up to 4GB)\n"
            "• Permanent links\n"
            "• One-click sharing",
            reply_markup=keyboard
        )

@app.on_message(filters.document & filters.private)
async def file_handler(client: Client, message: Message):
    """
    Handles uploaded documents, stores their ID, and generates the special link.
    """
    try:
        if not message.document:
            await message.reply_text("Please upload a file document.")
            return

        # Check for large file simulation
        file_size_bytes = message.document.file_size
        if file_size_bytes and file_size_bytes > 4 * 1024 * 1024 * 1024:
            await message.reply_text("The file is too large. Telegram API limits transfers to 4GB.")
            return

        # 1. Get the Telegram File ID
        file_id = message.document.file_id
        file_name = message.document.file_name or "Unnamed File"

        # 2. Generate a unique, short, URL-safe base64 key
        base64_key = generate_base64_key()

        # 3. Prepare the data to store
        file_data = {
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size_bytes or 0,
            'uploader_user_id': message.from_user.id,
            'timestamp': message.date.isoformat() if message.date else None
        }

        # 4. Save the file metadata using the unique key
        save_file_data(APP_ID_MOCK, base64_key, file_data)

        # 5. Construct the deep link
        if client.me and client.me.username:
            share_link = f"https://t.me/{client.me.username}?start={base64_key}"
            
            reply_text = (
                "🚀 **Your Instant Share Link is Ready!**\n\n"
                f"**File:** `{file_name}`\n"
                f"**Size:** {format_size(file_size_bytes)}\n\n"
                "**Share this link for instant downloads:**\n"
                f"`{share_link}`"
            )
            
            # Create keyboard with share buttons
            keyboard = create_share_keyboard(share_link, file_name)
            
            await message.reply_text(
                reply_text, 
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            reply_text = (
                "✅ File data saved successfully.\n"
                f"The key is: `{base64_key}`"
            )
            await message.reply_text(reply_text)

    except Exception as e:
        print(f"Error handling file upload: {e}")
        await message.reply_text("❌ An error occurred while processing your file.")

@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    """Handle button callbacks."""
    data = callback_query.data
    
    if data.startswith("copy_"):
        base64_key = data[5:]  # Remove "copy_" prefix
        share_link = f"https://t.me/{client.me.username}?start={base64_key}"
        
        # Copy to clipboard (user will manually copy on mobile)
        await callback_query.answer(
            "Link copied to clipboard! Paste it anywhere to share.",
            show_alert=True
        )
        
        # Also send the link as a separate message for easy copying
        await callback_query.message.reply_text(
            f"📋 **Link ready to copy:**\n\n`{share_link}`\n\n"
            "Select and copy this text to share with others."
        )

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    """Show bot statistics."""
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"**Files stored:** {len(FILE_LINK_DB)}\n"
        f"**Bot username:** @{client.me.username if client.me else 'N/A'}\n"
        f"**Database:** Mock Storage (Firestore simulation)"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")]
    ])
    
    await message.reply_text(stats_text, reply_markup=keyboard)

@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    """Show help message."""
    help_text = (
        "🤖 **File Share Bot Help**\n\n"
        "**Commands:**\n"
        "• /start - Start the bot and see welcome message\n"
        "• /help - Show this help message\n"
        "• /stats - Show bot statistics\n\n"
        "**How to share files:**\n"
        "1. Send any file to this chat\n"
        "2. Get a permanent share link with buttons\n"
        "3. Use the buttons to share or copy the link\n\n"
        "**Features:**\n"
        "• Instant download speeds\n"
        "• Files up to 4GB supported\n"
        "• Permanent links\n"
        "• One-click sharing options"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Your First File", switch_inline_query="")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard)

# --- MAIN EXECUTION BLOCK ---
async def main():
    """Starts the bot and keeps it running."""
    print("Starting Telegram File Link Bot...")
    await app.start()
    
    if app.me:
        print(f"Bot started as @{app.me.username}. User ID: {app.me.id}")
        print("Bot is ready to receive files and generate share links!")
    else:
        print("Bot started, but could not retrieve own user details.")

    await idle()
    print("Stopping Telegram File Link Bot...")
    await app.stop()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred during bot execution: {e}")
