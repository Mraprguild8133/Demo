import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import config

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Functions ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    logger.info(f"User {update.effective_user.name} started the bot.")
    welcome_text = (
        "🤖 Hello! I'm an AI assistant powered by OpenRouter.ai\n\n"
        "💬 Send me any message, and I'll do my best to respond!\n"
        "⚙️ Current model: {config.AI_MODEL}\n\n"
        "You can chat with me about anything!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message when the /help command is issued."""
    help_text = (
        "📖 **Bot Help**\n\n"
        "• Just send me a message and I'll respond\n"
        "• I use {config.AI_MODEL} model\n"
        "• I can handle text conversations on various topics\n"
        "• My responses might be limited by the AI's capabilities\n\n"
        "Start by saying hello! 👋"
    )
    await update.message.reply_text(help_text)

def get_ai_response(user_message: str) -> str:
    """
    Connects to the OpenRouter API to get a response from the specified AI model.
    """
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo/telegram-ai-bot",  # OpenRouter requires this
        "X-Title": "Telegram AI Bot"
    }
    
    data = {
        "model": config.AI_MODEL,
        "messages": [
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 1000,
        "temperature": 0.7
    }

    try:
        response = requests.post(
            config.OPENROUTER_API_URL, 
            headers=headers, 
            json=data, 
            timeout=config.REQUEST_TIMEOUT
        )
        response.raise_for_status()

        response_json = response.json()
        if "choices" in response_json and len(response_json["choices"]) > 0:
            ai_message = response_json["choices"][0]["message"]["content"]
            return ai_message.strip()
        else:
            logger.error(f"Invalid response from API: {response_json}")
            return "❌ Sorry, I received an unexpected response from the AI. Please try again."

    except requests.exceptions.Timeout:
        logger.error("API request timed out")
        return "⏰ The AI service is taking too long to respond. Please try again."
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request failed: {e}")
        return "🔌 Sorry, I couldn't connect to the AI service. Please try again later."
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return "❌ Sorry, an unexpected error occurred. Please check the logs."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming text messages and responds using the AI."""
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user_name = update.effective_user.name

    # Check if message is too long
    if len(user_message) > 4000:
        await update.message.reply_text("❌ Your message is too long. Please keep it under 4000 characters.")
        return

    logger.info(f"Received message from {user_name}: '{user_message}'")

    # Let the user know the bot is thinking
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    # Get the response from the AI
    ai_response = get_ai_response(user_message)

    # Handle long responses by splitting them
    if len(ai_response) > config.MAX_MESSAGE_LENGTH:
        chunks = [ai_response[i:i+config.MAX_MESSAGE_LENGTH] for i in range(0, len(ai_response), config.MAX_MESSAGE_LENGTH)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
            await asyncio.sleep(0.5)  # Small delay between chunks
    else:
        await update.message.reply_text(ai_response)

    logger.info(f"Sent AI response to {user_name}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates."""
    logger.error(f"Exception while handling an update: {context.error}")

def validate_config() -> bool:
    """Validate that all required configuration is present."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set!")
        return False
    if not config.OPENROUTER_API_KEY:
        logger.critical("OPENROUTER_API_KEY environment variable not set!")
        return False
    return True

def main() -> None:
    """Starts the bot and listens for messages."""
    # Validate configuration
    if not validate_config():
        return

    logger.info("Bot starting...")
    logger.info(f"Using AI Model: {config.AI_MODEL}")

    # --- Bot Setup ---
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Error handler
    application.add_error_handler(error_handler)

    # Run the bot until you press Ctrl-C
    logger.info("Bot is now running...")
    application.run_polling()

if __name__ == '__main__':
    main()
