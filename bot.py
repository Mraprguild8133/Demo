import base64
import os
import secrets
import asyncio
import traceback
import urllib.parse
import json
import time
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, UserNotParticipant

from config import config

# --- SIMPLE DATABASE MOCK ---
DB_FILE = "file_database.json"

def load_database():
    """Load database from JSON file."""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure the structure is correct
                if "files" not in data:
                    data["files"] = {}
                if "users" not in data:
                    data["users"] = {}
                return data
    except Exception as e:
        print(f"Error loading database: {e}")
    # Return empty database structure
    return {"files": {}, "users": {}}

def save_database(data):
    """Save database to JSON file."""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving database: {e}")
        return False

def save_file_data(file_key: str, data: dict):
    """Save file data to database."""
    try:
        db = load_database()
        db["files"][file_key] = data
        success = save_database(db)
        if success:
            print(f"✅ DB: Saved file data for key: {file_key}")
            print(f"📁 File: {data.get('file_name', 'Unknown')}")
            return True
        else:
            print(f"❌ DB: Failed to save file data for key: {file_key}")
            return False
    except Exception as e:
        print(f"❌ DB Error in save_file_data: {e}")
        return False

def get_file_data(file_key: str) -> dict | None:
    """Retrieve file data from database."""
    try:
        db = load_database()
        file_data = db["files"].get(file_key)
        if file_data:
            print(f"✅ DB: Retrieved file data for key: {file_key}")
            print(f"📁 File: {file_data.get('file_name', 'Unknown')}")
        else:
            print(f"❌ DB: No file data found for key: {file_key}")
        return file_data
    except Exception as e:
        print(f"❌ DB Error in get_file_data: {e}")
        return None

def get_database_stats():
    """Get database statistics."""
    try:
        db = load_database()
        file_keys = list(db["files"].keys())
        return {
            "total_files": len(db["files"]),
            "total_users": len(db["users"]),
            "file_keys": file_keys[:5]  # First 5 keys for debugging
        }
    except Exception as e:
        print(f"Error getting stats: {e}")
        return {"total_files": 0, "total_users": 0, "file_keys": []}

class MockMongoDB:
    """Mock MongoDB class to prevent errors"""
    
    async def present_user(self, user_id):
        db = load_database()
        return str(user_id) in db["users"]
    
    async def add_user(self, user_id):
        try:
            db = load_database()
            db["users"][str(user_id)] = {
                "joined_at": time.time(),
                "first_seen": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            save_database(db)
            print(f"✅ Added user: {user_id}")
            return True
        except Exception as e:
            print(f"❌ Error adding user: {e}")
            return False
    
    async def is_banned(self, user_id):
        return False

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
    share_text = f"📁 Download {file_name} via File Share Bot"
    
    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Get File Now", 
                url=share_link
            )
        ],
        [
            InlineKeyboardButton(
                "📋 Copy Link", 
                callback_data=f"copy_{base64_key}"
            )
        ],
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
BOT_USERNAME = config.BOT_USERNAME

# Initialize required attributes for plugins
app.fsub_dict = {}
app.req_channels = []
app.mongodb = MockMongoDB()
app.admins = config.ADMINS
app.shortner_enabled = False
app.db = None
app.disable_btn = False

def get_bot_username():
    """Get bot username with fallback handling."""
    global BOT_USERNAME
    if not BOT_USERNAME and app.me:
        BOT_USERNAME = app.me.username
        print(f"🤖 Bot username set to: @{BOT_USERNAME}")
    return BOT_USERNAME

async def check_force_sub(user_id: int) -> tuple:
    """Check force subscription."""
    if not app.fsub_dict:
        return True, None
    return True, None  # Temporarily disable force sub for testing

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handle /start command with file links."""
    bot_username = get_bot_username()
    
    if not bot_username:
        await message.reply_text("❌ Bot username not available. Please restart the bot.")
        return

    # Check force subscription
    is_subscribed, button = await check_force_sub(message.from_user.id)
    if not is_subscribed:
        await message.reply_text(
            "📢 **Subscription Required**\n\n"
            "You need to join our channel to use this bot.",
            reply_markup=button
        )
        return

    # Handle file links
    if len(message.command) > 1:
        base64_key = message.command[1]
        print(f"🔑 Processing file request with key: {base64_key}")
        
        # Debug: Show all available keys
        stats = get_database_stats()
        print(f"📊 Database stats: {stats['total_files']} files, Keys: {stats['file_keys']}")
        
        file_data = get_file_data(base64_key)

        if not file_data:
            await message.reply_text(
                "❌ **File Link Error**\n\n"
                "This file link is invalid or has expired.\n"
                "Please upload the file again to generate a new link."
            )
            return

        file_id = file_data.get('file_id')
        file_name = file_data.get('file_name', 'Unnamed File')
        file_size_bytes = file_data.get('file_size', 0)

        print(f"📁 Sending file: {file_name} (ID: {file_id})")

        try:
            # Send the file
            await client.send_document(
                chat_id=message.chat.id,
                document=file_id,
                caption=(
                    f"📥 **{file_name}**\n"
                    f"📦 **Size:** {format_size(file_size_bytes)}\n"
                    f"✅ **Downloaded successfully!**"
                )
            )
            print("✅ File sent successfully")

        except FloodWait as e:
            await message.reply_text(f"⚠️ **Rate Limit:** Please wait {e.value} seconds.")
        except Exception as e:
            print(f"❌ Error sending file: {e}")
            await message.reply_text(
                "❌ **Download Error**\n\n"
                "Failed to send the file. This might be due to:\n"
                "• File was deleted from Telegram servers\n"
                "• Network issues\n"
                "• File is too old\n\n"
                "Please upload the file again."
            )

    else:
        # Welcome message
        await message.reply_text(
            "👋 **Welcome to File Share Bot!** 🚀\n\n"
            "**How to use:**\n"
            "1. **Send me any file** (document, video, audio, etc.)\n"
            "2. **I'll generate a permanent share link**\n"
            "3. **Share the link** with anyone for instant downloads\n\n"
            "⚡ **Features:**\n"
            "• Instant download speeds\n"
            "• Files up to 4GB supported\n"
            "• Permanent links\n"
            "• Easy sharing options\n\n"
            "📤 **Just upload a file to get started!**"
        )

@app.on_message(filters.document & filters.private)
async def file_handler(client: Client, message: Message):
    """Handle file uploads and generate share links."""
    bot_username = get_bot_username()
    
    if not bot_username:
        await message.reply_text("❌ Bot username not available. Please restart the bot.")
        return

    try:
        print(f"👤 User {message.from_user.id} is uploading a file...")
        
        # Check force subscription
        is_subscribed, button = await check_force_sub(message.from_user.id)
        if not is_subscribed:
            await message.reply_text("📢 Subscription required to upload files.", reply_markup=button)
            return

        if not message.document:
            await message.reply_text("❌ Please upload a file document.")
            return

        # Get file details
        file_id = message.document.file_id
        file_name = message.document.file_name or "Unnamed File"
        file_size_bytes = message.document.file_size or 0
        
        print(f"📁 Processing file: {file_name} ({format_size(file_size_bytes)})")

        # Check file size
        if file_size_bytes > 4 * 1024 * 1024 * 1024:
            await message.reply_text("❌ File is too large. Maximum size: 4GB")
            return

        # Generate unique key
        base64_key = generate_base64_key()
        print(f"🔑 Generated key: {base64_key}")

        # Prepare file data
        file_data = {
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size_bytes,
            'uploader_user_id': message.from_user.id,
            'timestamp': time.time(),
            'date_added': time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # Save file data
        success = save_file_data(base64_key, file_data)
        
        if not success:
            await message.reply_text("❌ Error saving file data. Please try again.")
            return

        # Create share link
        share_link = f"https://t.me/{bot_username}?start={base64_key}"
        
        reply_text = (
            "✅ **Your Share Link is Ready!** 🎉\n\n"
            f"**📁 File:** `{file_name}`\n"
            f"**📦 Size:** `{format_size(file_size_bytes)}`\n\n"
            "**Choose an option below:** 👇"
        )
        
        keyboard = create_share_keyboard(share_link, file_name, base64_key)
        
        await message.reply_text(
            reply_text, 
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        print("✅ Share link sent successfully")

    except Exception as e:
        print(f"❌ ERROR in file_handler: {e}")
        print(traceback.format_exc())
        await message.reply_text(
            "❌ **Upload Error**\n\n"
            "An error occurred while processing your file.\n"
            "Please try again with a different file."
        )

@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    """Handle button callbacks."""
    try:
        data = callback_query.data
        
        if data.startswith("copy_"):
            base64_key = data[5:]
            bot_username = get_bot_username()
            
            if bot_username:
                share_link = f"https://t.me/{bot_username}?start={base64_key}"
                
                await callback_query.answer(
                    "📋 Link copied to clipboard!",
                    show_alert=False
                )
                
                await callback_query.message.reply_text(
                    f"**📋 Here's your share link:**\n\n`{share_link}`\n\n"
                    "You can select and copy this text to share with others."
                )
        
        elif data == "check_fsub":
            is_subscribed, button = await check_force_sub(callback_query.from_user.id)
            if is_subscribed:
                await callback_query.answer("✅ Thanks for joining! You can now use the bot.", show_alert=True)
                await callback_query.message.delete()
            else:
                await callback_query.answer("❌ Please join the channel first.", show_alert=True)
                
    except Exception as e:
        print(f"❌ Callback error: {e}")
        await callback_query.answer("Error processing request", show_alert=True)

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    """Show bot statistics."""
    stats = get_database_stats()
    bot_username = get_bot_username()
    
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"• **Files stored:** {stats['total_files']}\n"
        f"• **Total users:** {stats['total_users']}\n"
        f"• **Bot username:** @{bot_username or 'Loading...'}\n"
        f"• **Storage:** JSON file (persistent)\n"
        f"• **Last keys:** {', '.join(stats['file_keys']) if stats['file_keys'] else 'None'}"
    )
    
    await message.reply_text(stats_text)

@app.on_message(filters.command("debug") & filters.private & filters.user(config.ADMINS))
async def debug_handler(client: Client, message: Message):
    """Debug command for admins."""
    stats = get_database_stats()
    bot_username = get_bot_username()
    
    debug_text = (
        f"🔧 **Debug Information**\n\n"
        f"• **Bot username:** @{bot_username or 'None'}\n"
        f"• **Database file:** {DB_FILE}\n"
        f"• **Files in DB:** {stats['total_files']}\n"
        f"• **Users in DB:** {stats['total_users']}\n"
        f"• **All file keys:** {list(stats['file_keys'])}\n"
        f"• **Admins:** {config.ADMINS}\n"
        f"• **Force sub channels:** {len(app.fsub_dict)}"
    )
    
    await message.reply_text(debug_text)

# --- MAIN EXECUTION BLOCK ---
async def main():
    """Starts the bot and keeps it running."""
    global BOT_USERNAME
    
    print("🚀 Starting Telegram File Share Bot...")
    print("📁 Using persistent JSON database...")
    
    # Initialize database
    db = load_database()
    print(f"📊 Loaded database: {len(db['files'])} files, {len(db['users'])} users")
    
    await app.start()
    
    if app.me:
        BOT_USERNAME = app.me.username
        print(f"✅ Bot started as @{BOT_USERNAME}")
        print("🤖 Bot is ready! Users can upload files and get share links.")
        
        # Initialize admin user if needed
        if app.me.id not in app.admins:
            app.admins.append(app.me.id)
            
    else:
        print("❌ Bot started, but could not retrieve username.")

    await idle()
    print("🛑 Stopping bot...")
    await app.stop()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        print(traceback.format_exc())
