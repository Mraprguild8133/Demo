import base64
import os
import secrets
import asyncio
import traceback
import urllib.parse
import json
import time
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from pyrogram.errors import FloodWait, UserNotParticipant
from flask import Flask, render_template, jsonify, request, redirect, url_for

from config import config

# -----------------------------
# Flask Web Server Setup
# -----------------------------
flask_app = Flask(__name__, template_folder="templates")

@flask_app.route("/")
def index():
    """Main website page"""
    return render_template("index.html")

@flask_app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": time.time()})

@flask_app.route("/stats")
def web_stats():
    """Web statistics page"""
    stats = get_database_stats()
    return jsonify({
        "status": "ok",
        "total_files": stats["total_files"],
        "total_users": stats["total_users"],
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S")
    })

@flask_app.route("/file/<file_key>")
def file_info(file_key):
    """Get file information via web"""
    file_data = get_file_data(file_key)
    if not file_data:
        return jsonify({"error": "File not found"}), 404
    
    return jsonify({
        "file_name": file_data.get('file_name'),
        "file_size": file_data.get('file_size'),
        "file_size_formatted": format_size(file_data.get('file_size', 0)),
        "date_added": file_data.get('date_added'),
        "telegram_link": f"https://t.me/{BOT_USERNAME}?start={file_key}" if BOT_USERNAME else None
    })

def run_flask():
    """Run Flask web server"""
    print("🌐 Starting Flask web server on port 8000...")
    flask_app.run(host="0.0.0.0", port=8000)

# -----------------------------
# SIMPLE DATABASE MOCK
# -----------------------------
DB_FILE = "file_database.json"

def load_database():
    """Load database from JSON file."""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "files" not in data:
                    data["files"] = {}
                if "users" not in data:
                    data["users"] = {}
                return data
    except Exception as e:
        print(f"Error loading database: {e}")
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
            "file_keys": file_keys[:5]
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
            return True
        except Exception as e:
            print(f"❌ Error adding user: {e}")
            return False
    
    async def is_banned(self, user_id):
        return False

# -----------------------------
# UTILITY FUNCTIONS
# -----------------------------

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

# -----------------------------
# TELEGRAM BOT LOGIC
# -----------------------------

# Initialize the Pyrogram Client FIRST
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

async def set_bot_commands(client: Client):
    """Set bot commands menu."""
    commands = [
        BotCommand("start", "Start the bot and get welcome message"),
        BotCommand("help", "Show help instructions"),
        BotCommand("stats", "Show bot statistics")
    ]
    
    try:
        await client.set_bot_commands(commands)
        print("✅ Bot commands set successfully!")
    except Exception as e:
        print(f"❌ Error setting bot commands: {e}")

# -----------------------------
# COMMAND HANDLERS
# -----------------------------

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handle /start command."""
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
        
        stats = get_database_stats()
        print(f"📊 Database stats: {stats['total_files']} files")
        
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

        print(f"📁 Sending file: {file_name}")

        try:
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
            await message.reply_text("❌ Failed to send file. Please upload again.")

    else:
        # Welcome message with commands
        welcome_text = (
            "👋 **Welcome to File Share Bot!** 🚀\n\n"
            "**Available Commands:**\n"
            "• /start - Show this welcome message\n"
            "• /help - Detailed help instructions\n"
            "• /stats - Bot statistics\n\n"
            "**Quick Start:**\n"
            "Just send me any file and I'll generate a shareable link!\n\n"
            "📤 **Upload a file to get started!**"
        )
        
        await message.reply_text(welcome_text)

@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    """Show detailed help message."""
    help_text = (
        "🤖 **File Share Bot - Help Guide**\n\n"
        
        "**📋 Available Commands:**\n"
        "• `/start` - Start the bot and see welcome message\n"
        "• `/help` - Show this help guide\n"
        "• `/stats` - View bot statistics\n\n"
        
        "**🚀 How to Share Files:**\n"
        "1. **Upload** any file (document, video, audio, etc.)\n"
        "2. **Get Link** - I'll generate a permanent share link\n"
        "3. **Share** - Use the buttons to share with anyone\n\n"
        
        "**📁 Supported Files:**\n"
        "• Documents (PDF, ZIP, EXE, etc.)\n"
        "• Videos (MP4, AVI, MKV, etc.)\n"
        "• Audio files (MP3, WAV, etc.)\n"
        "• Images (as documents)\n"
        "• Any file up to 4GB\n\n"
        
        "**⚡ Features:**\n"
        "• Instant download speeds\n"
        "• Permanent links\n"
        "• One-click sharing\n"
        "• No registration required\n\n"
        
        "**🎯 Quick Tip:**\n"
        "Just upload a file to begin! The bot will automatically create a share link."
    )
    
    await message.reply_text(help_text, disable_web_page_preview=True)

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    """Show bot statistics."""
    stats = get_database_stats()
    bot_username = get_bot_username()
    
    stats_text = (
        "📊 **Bot Statistics**\n\n"
        f"• **Files stored:** `{stats['total_files']}`\n"
        f"• **Total users:** `{stats['total_users']}`\n"
        f"• **Bot username:** @{bot_username or 'Loading...'}\n"
        f"• **Storage:** JSON file (persistent)\n\n"
        
        "**💡 Info:**\n"
        "Files are stored permanently until the bot is reset.\n"
        "All links remain active indefinitely."
    )
    
    await message.reply_text(stats_text)

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
            f"📦 **Size:** `{format_size(file_size_bytes)}`\n\n"
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

# -----------------------------
# ADMIN COMMANDS
# -----------------------------

@app.on_message(filters.command("debug") & filters.private & filters.user(config.ADMINS))
async def debug_handler(client: Client, message: Message):
    """Debug command for admins."""
    stats = get_database_stats()
    bot_username = get_bot_username()
    db = load_database()
    
    debug_text = (
        "🔧 **Debug Information**\n\n"
        f"• **Bot username:** @{bot_username or 'None'}\n"
        f"• **Bot ID:** {app.me.id if app.me else 'None'}\n"
        f"• **Admins:** {config.ADMINS}\n"
        f"• **Your ID:** {message.from_user.id}\n\n"
        
        f"• **Database file:** {DB_FILE}\n"
        f"• **Files in DB:** {stats['total_files']}\n"
        f"• **Users in DB:** {stats['total_users']}\n"
        f"• **Force sub channels:** {len(app.fsub_dict)}"
    )
    
    await message.reply_text(debug_text)

@app.on_message(filters.command("addfsub") & filters.private & filters.user(config.ADMINS))
async def add_fsub_admin(client: Client, message: Message):
    """Admin command to add force sub channel."""
    try:
        if len(message.command) < 2:
            await message.reply_text(
                "**Usage:** `/addfsub channel_id`\n\n"
                "**Example:** `/addfsub -1001234567890`"
            )
            return
        
        channel_id = int(message.command[1])
        
        try:
            chat = await client.get_chat(channel_id)
        except Exception as e:
            await message.reply_text(f"❌ Cannot access channel: {e}")
            return
        
        app.fsub_dict[channel_id] = [chat.title, None, False, 0]
        
        await message.reply_text(
            f"✅ **Force Subscription Added**\n\n"
            f"**Channel:** {chat.title}\n"
            f"**ID:** `{channel_id}`"
        )
        
    except ValueError:
        await message.reply_text("❌ Invalid channel ID. Must be a negative integer.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command("delfsub") & filters.private & filters.user(config.ADMINS))
async def del_fsub_admin(client: Client, message: Message):
    """Admin command to remove force sub channel."""
    try:
        if len(message.command) < 2:
            await message.reply_text("**Usage:** `/delfsub channel_id`")
            return
        
        channel_id = int(message.command[1])
        if channel_id in app.fsub_dict:
            channel_name = app.fsub_dict[channel_id][0]
            app.fsub_dict.pop(channel_id)
            await message.reply_text(
                f"✅ **Force Subscription Removed**\n\n"
                f"**Channel:** {channel_name}\n"
                f"**ID:** `{channel_id}`"
            )
        else:
            await message.reply_text("❌ Channel not found in force sub list")
            
    except ValueError:
        await message.reply_text("❌ Invalid channel ID.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

# -----------------------------
# MAIN EXECUTION BLOCK
# -----------------------------

async def run_bot():
    """Starts the Telegram bot."""
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
        
        # Set bot commands
        await set_bot_commands(app)
        
        print("🤖 Bot is ready! Commands:")
        print("   • /start - Welcome message")
        print("   • /help - Help guide") 
        print("   • /stats - Statistics")
        print("   • Upload any file to get share link")
        
    else:
        print("❌ Bot started, but could not retrieve username.")

    await idle()
    print("🛑 Stopping bot...")
    await app.stop()

def run_web_server():
    """Run Flask web server in a separate thread."""
    import threading
    
    def start_flask():
        flask_app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    print("🌐 Flask web server started on http://0.0.0.0:8000")

async def main():
    """Main function to run both bot and web server."""
    # Start web server
    run_web_server()
    
    # Start Telegram bot
    await run_bot()

if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    os.makedirs("templates", exist_ok=True)
    
    # Create a simple index.html if it doesn't exist
    if not os.path.exists("templates/index.html"):
        with open("templates/index.html", "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Share Bot</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .stats {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 5px;
        }
        .btn:hover {
            background: #0056b3;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 File Share Bot</h1>
        <p>Welcome to the File Share Bot web interface!</p>
        
        <div class="stats">
            <h3>📊 Live Statistics</h3>
            <div id="stats">Loading...</div>
        </div>
        
        <h3>🚀 How to Use</h3>
        <ol>
            <li>Open Telegram and search for our bot</li>
            <li>Send any file to the bot</li>
            <li>Get a permanent shareable link</li>
            <li>Share the link with anyone</li>
        </ol>
        
        <p>
            <a href="https://t.me/your_bot_username" class="btn" target="_blank">Open in Telegram</a>
            <a href="/health" class="btn">Health Check</a>
            <a href="/stats" class="btn">API Stats</a>
        </p>
    </div>

    <script>
        // Load stats dynamically
        fetch('/stats')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'ok') {
                    document.getElementById('stats').innerHTML = `
                        <p>📁 Total Files: <strong>${data.total_files}</strong></p>
                        <p>👥 Total Users: <strong>${data.total_users}</strong></p>
                        <p>🕒 Server Time: ${data.server_time}</p>
                    `;
                }
            })
            .catch(error => {
                document.getElementById('stats').innerHTML = 'Error loading statistics';
            });
    </script>
</body>
</html>""")
        print("📄 Created default index.html template")

    try:
        # Run both bot and web server
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        print(traceback.format_exc())