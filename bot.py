import os
import requests  # ← THIS WAS MISSING!
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import config

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GeminiTelegramBot:
    def __init__(self):
        self.application = None
        self.supported_models = {
            "gemini-2.0-flash-exp": "Gemini 2.0 Flash Experimental (Latest)",
            "gemini-flash-1.5": "Gemini 1.5 Flash (Fast & Efficient)",
            "gemini-pro-1.5": "Gemini 1.5 Pro (Most Capable)"
        }
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send welcome message when /start is issued."""
        user = update.effective_user
        model_name = config.AI_MODEL.split('/')[-1]
        model_description = self.supported_models.get(model_name, "Gemini AI")
        
        welcome_text = (
            f"👋 Hello {user.mention_markdown_v2()}!\n\n"
            f"🤖 I'm powered by *{model_description}* via OpenRouter.ai\n\n"
            "💬 *What I can do:*\n"
            "• Answer questions and have conversations\n"
            "• Help with writing and creativity\n"
            "• Assist with analysis and reasoning\n"
            "• Process and understand complex queries\n\n"
            "🚀 *Just send me a message to get started!*"
        )
        await update.message.reply_markdown_v2(welcome_text)
        logger.info(f"User {user.name} started the bot with {config.AI_MODEL}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send help message when /help is issued."""
        help_text = (
            "🤖 *Gemini AI Bot Help*\n\n"
            "💡 *Commands:*\n"
            "• /start - Start the bot\n"
            "• /help - Show this help message\n"
            "• /model - Show current AI model info\n"
            "• /models - List available Gemini models\n\n"
            "🔧 *Current Model:*\n"
            f"• `{config.AI_MODEL}`\n\n"
            "📝 *Just send me any message to chat!*"
        )
        await update.message.reply_markdown_v2(help_text)

    async def model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show current AI model information."""
        model_name = config.AI_MODEL.split('/')[-1]
        model_description = self.supported_models.get(model_name, "Gemini AI")
        
        model_info = (
            f"🤖 *Current AI Model*\n\n"
            f"• *Model:* `{config.AI_MODEL}`\n"
            f"• *Description:* {model_description}\n"
            f"• *Provider:* Google Gemini\n"
            f"• *Via:* OpenRouter.ai\n\n"
            "Use `/models` to see other available models"
        )
        await update.message.reply_markdown_v2(model_info)

    async def models_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List available Gemini models."""
        models_text = "🤖 *Available Gemini Models*\n\n"
        
        for model_key, description in self.supported_models.items():
            current_indicator = " ✅" if model_key in config.AI_MODEL else ""
            models_text += f"• `google/{model_key}` - {description}{current_indicator}\n"
        
        models_text += "\nTo change models, update the `AI_MODEL` in your .env file"
        await update.message.reply_markdown_v2(models_text)

    def get_gemini_response(self, user_message: str) -> str:
        """Get response from Gemini via OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/telegram-gemini-bot",
            "X-Title": "Telegram Gemini Bot"
        }
        
        # Optimized for Gemini models
        data = {
            "model": config.AI_MODEL,
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": config.GEMINI_CONFIG["max_tokens"],
            "temperature": config.GEMINI_CONFIG["temperature"],
            "top_p": config.GEMINI_CONFIG["top_p"],
            "stream": False
        }

        try:
            logger.info(f"Sending request to Gemini model: {config.AI_MODEL}")
            response = requests.post(
                config.OPENROUTER_API_URL,
                headers=headers,
                json=data,
                timeout=config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Log token usage for monitoring
            if "usage" in result:
                usage = result["usage"]
                logger.info(f"Tokens - Prompt: {usage.get('prompt_tokens', 'N/A')}, "
                           f"Completion: {usage.get('completion_tokens', 'N/A')}, "
                           f"Total: {usage.get('total_tokens', 'N/A')}")
            
            return result["choices"][0]["message"]["content"].strip()
            
        except requests.exceptions.Timeout:
            logger.warning("Gemini API request timed out")
            return "⏰ Gemini is taking longer than usual to respond. Please try again in a moment."
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Gemini API connection error: {e}")
            return "🔌 Unable to connect to Gemini AI. Please try again later."
            
        except KeyError as e:
            logger.error(f"Unexpected response format from Gemini: {e}")
            return "❌ Received an unexpected response from Gemini. Please try again."
            
        except Exception as e:
            logger.error(f"Unexpected error with Gemini: {e}")
            return "❌ An unexpected error occurred. Please try again."

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages with Gemini."""
        user_message = update.message.text
        
        # Validate message length
        if len(user_message) > 4000:
            await update.message.reply_text(
                "❌ Your message is too long. Please keep it under 4000 characters."
            )
            return
        
        logger.info(f"Received message from {update.effective_user.name}: {user_message[:100]}...")
        
        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action='typing'
        )
        
        # Get Gemini response
        ai_response = self.get_gemini_response(user_message)
        
        logger.info(f"Gemini response length: {len(ai_response)} characters")
        
        # Handle long responses by splitting them
        if len(ai_response) > config.MAX_MESSAGE_LENGTH:
            chunks = [
                ai_response[i:i + config.MAX_MESSAGE_LENGTH] 
                for i in range(0, len(ai_response), config.MAX_MESSAGE_LENGTH)
            ]
            for i, chunk in enumerate(chunks, 1):
                if len(chunks) > 1:
                    chunk = f"📝 Part {i}/{len(chunks)}:\n\n{chunk}"
                await update.message.reply_text(chunk)
                await asyncio.sleep(0.5)  # Small delay between chunks
        else:
            await update.message.reply_text(ai_response)

    def setup_handlers(self):
        """Setup bot command and message handlers."""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("model", self.model_command))
        self.application.add_handler(CommandHandler("models", self.models_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

    async def post_init(self, application: Application) -> None:
        """Run after application initialization."""
        logger.info(f"Gemini Telegram Bot started with model: {config.AI_MODEL}")
        
    async def post_shutdown(self, application: Application) -> None:
        """Run before application shutdown."""
        logger.info("Gemini Telegram Bot is shutting down...")

    def run(self):
        """Start the bot."""
        if not config.validate():
            logger.error("Configuration validation failed!")
            return
            
        # Create Application instance
        self.application = (
            Application.builder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .post_init(self.post_init)
            .post_shutdown(self.post_shutdown)
            .build()
        )
        
        # Setup handlers
        self.setup_handlers()
        
        # Start the bot
        logger.info(f"🚀 Starting Gemini Telegram Bot with model: {config.AI_MODEL}")
        self.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

def main():
    """Main function to start the Gemini bot."""
    bot = GeminiTelegramBot()
    bot.run()

if __name__ == "__main__":
    main()
