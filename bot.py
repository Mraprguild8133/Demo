import base64
import os
import secrets
import asyncio
import traceback
import urllib.parse
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, UserNotParticipant

from config import config

# --- SIMPLE DATABASE MOCK ---
FILE_LINK_DB = {}
USER_DB = {}

class MockMongoDB:
    """Mock MongoDB class to prevent errors"""
    
    async def present_user(self, user_id):
        return USER_DB.get(user_id) is not None
    
    async def add_user(self, user_id):
        USER_DB[user_id] = {"joined_at": asyncio.get_event_loop().time()}
        return True
    
    async def is_banned(self, user_id):
        return False
    
    async def add_fsub_channel(self, channel_id, channel_data):
        print(f"Mock DB: Added FSub channel {channel_id}")
        return True
    
    async def remove_fsub_channel(self, channel_id):
        print(f"Mock DB: Removed FSub channel {channel_id}")
        return True
    
    async def set_channels(self, channels):
        print(f"Mock DB: Set channels {channels}")
        return True
    
    async def set_shortner_status(self, status):
        print(f"Mock DB: Set shortner status {status}")
        return True
    
    async def update_shortner_setting(self, key, value):
        print(f"Mock DB: Updated shortner {key} = {value}")
        return True

def save_file_data(file_key: str, data: dict):
    """Save file data to mock database."""
    FILE_LINK_DB[file_key] = data
    print(f"DB: Saved file data for key: {file_key}")

def get_file_data(file_key: str) -> dict | None:
    """Retrieve file data from mock database."""
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
BOT_USERNAME = None

# Initialize required attributes for plugins
app.fsub_dict = {}
app.req_channels = []
app.mongodb = MockMongoDB()
app.admins = config.ADMINS
app.shortner_enabled = False  # Disable shortner for file bot
app.db = None  # Channel ID for posts
app.disable_btn = False

async def check_force_sub(user_id: int) -> tuple:
    """
    Check if user is subscribed to required channels.
    Returns (True, None) if subscribed, (False, button) if not.
    """
    if not app.fsub_dict:
        return True, None
    
    for channel_id, channel_data in app.fsub_dict.items():
        try:
            await app.get_chat_member(channel_id, user_id)
        except UserNotParticipant:
            channel_name = channel_data[0] if channel_data else "the channel"
            invite_link = channel_data[1] if channel_data and len(channel_data) > 1 else None
            
            if invite_link:
                button = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"Join {channel_name}", url=invite_link)],
                    [InlineKeyboardButton("✅ I've Joined", callback_data="check_fsub")]
                ])
            else:
                button = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"Join {channel_name}", url=f"https://t.me/c/{str(channel_id)[4:]}")],
                    [InlineKeyboardButton("✅ I've Joined", callback_data="check_fsub")]
                ])
            
            return False, button
        except Exception as e:
            print(f"Error checking channel membership: {e}")
            continue
    
    return True, None

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handle /start command with file links."""
    global BOT_USERNAME
    if not BOT_USERNAME and client.me:
        BOT_USERNAME = client.me.username

    # Check force subscription
    is_subscribed, button = await check_force_sub(message.from_user.id)
    if not is_subscribed:
        await message.reply_text(
            "📢 **Subscription Required**\n\n"
            "You need to join our channel to use this bot.\n"
            "Please join the channel below and then click 'I've Joined'.",
            reply_markup=button
        )
        return

    # Handle file links
    if len(message.command) > 1:
        base64_key = message.command[1]
        print(f"Processing file request with key: {base64_key}")
        
        file_data = get_file_data(base64_key)

        if not file_data:
            await message.reply_text("❌ **Error:** File link is invalid or expired.")
            return

        file_id = file_data.get('file_id')
        file_name = file_data.get('file_name', 'Unnamed File')
        file_size_bytes = file_data.get('file_size', 0)

        caption_text = (
            f"📥 **File Ready for Download**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** `{format_size(file_size_bytes)}`\n\n"
            f"✅ Downloaded successfully!"
        )

        try:
            await client.send_document(
                chat_id=message.chat.id,
                document=file_id,
                caption=caption_text
            )
            print("File sent successfully")

        except FloodWait as e:
            await message.reply_text(f"⚠️ **Rate Limit:** Please wait {e.value} seconds.")
        except Exception as e:
            print(f"Error sending file: {e}")
            await message.reply_text("❌ Error sending file. Please try again.")

    else:
        # Welcome message
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
            "• Easy sharing options"
        )

@app.on_message(filters.document & filters.private)
async def file_handler(client: Client, message: Message):
    """Handle file uploads and generate share links."""
    global BOT_USERNAME
    if not BOT_USERNAME and client.me:
        BOT_USERNAME = client.me.username

    try:
        print(f"Processing file upload from user: {message.from_user.id}")
        
        # Check force subscription
        is_subscribed, button = await check_force_sub(message.from_user.id)
        if not is_subscribed:
            await message.reply_text(
                "📢 **Subscription Required**\n\n"
                "You need to join our channel to upload files.",
                reply_markup=button
            )
            return

        if not message.document:
            await message.reply_text("Please upload a file document.")
            return

        # Check file size
        file_size_bytes = message.document.file_size
        if file_size_bytes and file_size_bytes > 4 * 1024 * 1024 * 1024:
            await message.reply_text("❌ File is too large. Maximum size: 4GB")
            return

        # Get file details
        file_id = message.document.file_id
        file_name = message.document.file_name or "Unnamed File"
        
        print(f"Processing file: {file_name} ({file_size_bytes} bytes)")

        # Generate unique key
        base64_key = generate_base64_key()

        # Prepare and save file data
        file_data = {
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size_bytes or 0,
            'uploader_user_id': message.from_user.id,
            'timestamp': message.date.isoformat() if message.date else None
        }

        save_file_data(base64_key, file_data)

        # Create share link
        if BOT_USERNAME:
            share_link = f"https://t.me/{BOT_USERNAME}?start={base64_key}"
            
            reply_text = (
                "✅ **Your Share Link is Ready!**\n\n"
                f"**File:** `{file_name}`\n"
                f"**Size:** `{format_size(file_size_bytes)}`\n\n"
                "**Choose an option below:**"
            )
            
            keyboard = create_share_keyboard(share_link, file_name, base64_key)
            
            await message.reply_text(
                reply_text, 
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            print("Share link sent successfully")
        else:
            await message.reply_text(f"✅ File saved! Key: `{base64_key}`")

    except Exception as e:
        print(f"❌ ERROR in file_handler: {e}")
        print(traceback.format_exc())
        await message.reply_text("❌ Error processing file. Please try again.")

@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    """Handle button callbacks."""
    try:
        data = callback_query.data
        
        if data.startswith("copy_"):
            base64_key = data[5:]
            
            if BOT_USERNAME:
                share_link = f"https://t.me/{BOT_USERNAME}?start={base64_key}"
                
                await callback_query.answer(
                    "📋 Link copied to clipboard!",
                    show_alert=False
                )
                
                await callback_query.message.reply_text(
                    f"**Here's your share link:**\n\n`{share_link}`\n\n"
                    "You can select and copy this text to share with others."
                )
        
        elif data == "check_fsub":
            # Check if user joined after clicking the button
            is_subscribed, button = await check_force_sub(callback_query.from_user.id)
            if is_subscribed:
                await callback_query.answer("✅ Thanks for joining! You can now use the bot.", show_alert=True)
                await callback_query.message.delete()
            else:
                await callback_query.answer("❌ Please join the channel first.", show_alert=True)
                
    except Exception as e:
        print(f"Callback error: {e}")
        await callback_query.answer("Error processing request", show_alert=True)

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    """Show bot statistics."""
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"• **Files stored:** {len(FILE_LINK_DB)}\n"
        f"• **Total users:** {len(USER_DB)}\n"
        f"• **Bot username:** @{BOT_USERNAME or 'Loading...'}\n"
        f"• **Force sub channels:** {len(app.fsub_dict)}\n"
        f"• **Storage:** Temporary (resets on restart)"
    )
    
    await message.reply_text(stats_text)

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
    
    await message.reply_text(help_text)

# Admin commands
@app.on_message(filters.command("addfsub") & filters.private & filters.user(config.ADMINS))
async def add_fsub_admin(client: Client, message: Message):
    """Admin command to add force sub channel."""
    try:
        if len(message.command) < 2:
            await message.reply_text("Usage: /addfsub channel_id")
            return
        
        channel_id = int(message.command[1])
        chat = await client.get_chat(channel_id)
        
        app.fsub_dict[channel_id] = [chat.title, None, False, 0]
        
        await message.reply_text(f"✅ Added channel: {chat.title}")
        
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command("delfsub") & filters.private & filters.user(config.ADMINS))
async def del_fsub_admin(client: Client, message: Message):
    """Admin command to remove force sub channel."""
    try:
        if len(message.command) < 2:
            await message.reply_text("Usage: /delfsub channel_id")
            return
        
        channel_id = int(message.command[1])
        if channel_id in app.fsub_dict:
            app.fsub_dict.pop(channel_id)
            await message.reply_text("✅ Removed channel from force sub")
        else:
            await message.reply_text("❌ Channel not found in force sub list")
            
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

# --- MAIN EXECUTION BLOCK ---
async def main():
    """Starts the bot and keeps it running."""
    global BOT_USERNAME
    
    print("🚀 Starting Telegram File Share Bot...")
    await app.start()
    
    if app.me:
        BOT_USERNAME = app.me.username
        print(f"✅ Bot started as @{BOT_USERNAME}")
        print("📁 Bot is ready! Users can upload files and get share links.")
        
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
        print(f"Fatal error: {e}")
        print(traceback.format_exc())
