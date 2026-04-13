"""
Telegram message handlers for text and voice input.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from .auth import authorized_only
from ..voice.provider import LanguageProvider

logger = logging.getLogger(__name__)


def make_handlers(
    authorized_user_id: int,
    sarvam: LanguageProvider,
    agent: "DhaaraAgent",
    tz: ZoneInfo,
):
    """
    Returns (text_handler, voice_handler) coroutines bound to the given services.
    """

    @authorized_only(authorized_user_id)
    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message or not message.text:
            return

        chat_id = message.chat_id
        raw_text = message.text.strip()
        # Telegram sends UTC; convert to configured local timezone
        utc_dt = message.date or datetime.now(timezone.utc)
        timestamp = utc_dt.astimezone(tz)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # Detect language and translate to English if needed
        processed = sarvam.process_text(raw_text)

        # Run agent
        english_response = agent.handle_message(
            chat_id=chat_id,
            user_text=processed.english_text,
            timestamp=timestamp,
            detected_lang=processed.language_code,
        )

        # Always translate response via Sarvam
        if processed.language_code:
            reply = sarvam.translate_to_language(english_response, processed.language_code)
        else:
            reply = english_response  # Fallback to English

        await message.reply_text(reply)

    @authorized_only(authorized_user_id)
    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message or not message.voice:
            return

        chat_id = message.chat_id
        utc_dt = message.date or datetime.now(timezone.utc)
        timestamp = utc_dt.astimezone(tz)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # Download voice file
        voice_file = await message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        # STT + translation via Sarvam
        try:
            processed = sarvam.process_voice(bytes(audio_bytes), audio_format="ogg")
        except RuntimeError as e:
            logger.error(f"Voice processing error: {e}")
            await message.reply_text(
                "Sorry, I couldn't process your voice message. Please try again or type your entry."
            )
            return

        if not processed.english_text:
            await message.reply_text("I couldn't understand the audio. Please try again.")
            return

        # Run agent with English text
        english_response = agent.handle_message(
            chat_id=chat_id,
            user_text=processed.english_text,
            timestamp=timestamp,
            detected_lang=processed.language_code,
        )

        # Always translate response via Sarvam
        if processed.language_code:
            reply = sarvam.translate_to_language(english_response, processed.language_code)
        else:
            reply = english_response  # Fallback to English

        await message.reply_text(reply)

    @authorized_only(authorized_user_id)
    async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if update.message:
            await update.message.reply_text(
                "Hi! I'm Dhaara, your personal journal assistant.\n\n"
                "Just tell me about your day — what you did, how you feel, money spent, "
                "books read, or anything else. I'll record it in the right place.\n\n"
                "You can also send voice messages. I understand Indian languages too!"
            )

    @authorized_only(authorized_user_id)
    async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command — clears conversation history."""
        if update.message:
            agent._state.clear(update.message.chat_id)
            await update.message.reply_text("Conversation history cleared.")

    return handle_text, handle_voice, handle_start, handle_clear
