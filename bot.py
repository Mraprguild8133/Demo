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

from config import config

# [Keep all your existing database and utility functions...]

# --- BOT COMMANDS SETUP ---
async def set_bot_commands(client: Client):
    """Set bot commands menu."""
    commands = [
        BotCommand("start", "Start the bot and get welcome message"),
        BotCommand("help", "Show help instructions"),
        BotCommand("stats", "Show bot statistics")
    ]
    
    # Admin commands (only visible to admins)
    admin_commands = [
        BotCommand("debug", "Show detailed debug information"),
        BotCommand("addfsub", "Add force subscription channel"),
        BotCommand("delfsub", "Remove force subscription channel")
    ]
    
    try:
        await client.set_bot_commands(commands)
        print("✅ Bot commands set successfully!")
    except Exception as e:
        print(f"❌ Error setting bot commands: {e}")

# --- COMMAND HANDLERS ---

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
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Your First File", switch_inline_query="")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard, disable_web_page_preview=True)

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
        f"• **Storage:** JSON file (persistent)\n"
        f"• **Database file:** `{DB_FILE}`\n\n"
        
        "**💡 Info:**\n"
        "Files are stored permanently until the bot is reset.\n"
        "All links remain active indefinitely."
    )
    
    await message.reply_text(stats_text)

# Admin Commands
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
        f"• **All file keys:** {list(db['files'].keys())}\n"
        f"• **Force sub channels:** {len(app.fsub_dict)}\n\n"
        
        "**System:**\n"
        f"• **Python:** {os.sys.version}\n"
        f"• **Pyrogram:** {getattr(Client, '__version__', 'Unknown')}"
    )
    
    await message.reply_text(debug_text)

@app.on_message(filters.command("addfsub") & filters.private & filters.user(config.ADMINS))
async def add_fsub_admin(client: Client, message: Message):
    """Admin command to add force sub channel."""
    try:
        if len(message.command) < 2:
            await message.reply_text(
                "**Usage:** `/addfsub channel_id`\n\n"
                "**Example:** `/addfsub -1001234567890`\n\n"
                "To get channel ID, forward a message from the channel to @userinfobot"
            )
            return
        
        channel_id = int(message.command[1])
        
        # Verify channel exists and bot is admin
        try:
            chat = await client.get_chat(channel_id)
            await client.get_chat_member(channel_id, app.me.id)
        except Exception as e:
            await message.reply_text(f"❌ Cannot access channel: {e}")
            return
        
        app.fsub_dict[channel_id] = [chat.title, None, False, 0]
        
        await message.reply_text(
            f"✅ **Force Subscription Added**\n\n"
            f"**Channel:** {chat.title}\n"
            f"**ID:** `{channel_id}`\n\n"
            "Users will now need to join this channel to use the bot."
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
            await message.reply_text(
                "**Usage:** `/delfsub channel_id`\n\n"
                "**Example:** `/delfsub -1001234567890`"
            )
            return
        
        channel_id = int(message.command[1])
        if channel_id in app.fsub_dict:
            channel_name = app.fsub_dict[channel_id][0]
            app.fsub_dict.pop(channel_id)
            await message.reply_text(
                f"✅ **Force Subscription Removed**\n\n"
                f"**Channel:** {channel_name}\n"
                f"**ID:** `{channel_id}`\n\n"
                "Users no longer need to join this channel."
            )
        else:
            await message.reply_text("❌ Channel not found in force sub list")
            
    except ValueError:
        await message.reply_text("❌ Invalid channel ID.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

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
        
        # Set bot commands
        await set_bot_commands(app)
        
        print("🤖 Bot is ready! Commands:")
        print("   • /start - Welcome message")
        print("   • /help - Help guide") 
        print("   • /stats - Statistics")
        print("   • Upload any file to get share link")
        
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
