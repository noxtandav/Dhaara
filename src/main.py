"""
Dhaara - AI Journal Agent
Entry point. Starts the Telegram bot.

Usage:
  1. Copy config.example.yaml to config.yaml and fill in your values
  2. Activate venv: source venv/bin/activate
  3. Run: python -m src.main
"""
import logging
import sys
from pathlib import Path

from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters

from .config import load_config
from .voice.sarvam import SarvamClient
from .ai.bedrock import BedrockClient
from .ai.agent import DhaaraAgent
from .bot.handler import make_handlers
from .context.telos import init_telos_files

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
# Silence noisy HTTP polling logs from httpx and telegram
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main():
    # Load config
    config = load_config()
    logger.info(f"Starting Dhaara. Data dir: {config.data_dir}")

    # Initialize data directory structure
    init_telos_files(config.data_dir)
    logger.info("Data directory initialized.")

    # Initialize services
    sarvam = SarvamClient(api_key=config.sarvam.api_key)
    bedrock = BedrockClient(
        model_id=config.bedrock.model_id,
        region=config.bedrock.region,
        aws_profile=config.bedrock.aws_profile,
    )
    agent = DhaaraAgent(bedrock=bedrock)
    logger.info(f"Using Bedrock model: {config.bedrock.model_id}")

    # Build Telegram app
    app = ApplicationBuilder().token(config.telegram.bot_token).build()

    # Wire handlers
    uid = config.telegram.authorized_user_id
    handle_text, handle_voice, handle_start, handle_clear = make_handlers(
        authorized_user_id=uid,
        sarvam=sarvam,
        agent=agent,
    )

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logger.info(f"Bot started. Authorized user: {uid}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
