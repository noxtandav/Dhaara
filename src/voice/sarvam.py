"""
Sarvam AI client for voice and text processing.

Voice flow:
  - Audio (ogg from Telegram) -> STT with saaras:v3 mode="transcribe" -> get transcript + language_code
  - If not English, also call mode="translate" to get English text
  - Return: (english_text, detected_lang_code, original_transcript)

Text flow:
  - Detect language via LID API
  - If not English, translate to English via translate API
  - Return: (english_text, detected_lang_code, original_text)
"""
import io
import tempfile
import os
from dataclasses import dataclass
from pathlib import Path

from sarvamai import SarvamAI
from sarvamai.core.api_error import ApiError


@dataclass
class ProcessedInput:
    english_text: str
    language_code: str     # BCP-47, e.g. "hi-IN", "en-IN"
    original_text: str     # Original transcription/text before translation


class SarvamClient:
    def __init__(self, api_key: str):
        self._client = SarvamAI(api_subscription_key=api_key)

    def process_voice(self, audio_bytes: bytes, audio_format: str = "ogg") -> ProcessedInput:
        """
        Process a voice message.
        audio_bytes: raw audio bytes (Telegram sends .oga/ogg)
        audio_format: file extension hint

        Strategy:
        1. Transcribe with saaras:v3 to get original text + language
        2. If not English, translate separately
        """
        # Write to temp file — Sarvam needs a file-like object
        suffix = f".{audio_format}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # Step 1: Transcribe to get original language text + language code
            with open(tmp_path, "rb") as f:
                transcribe_resp = self._client.speech_to_text.transcribe(
                    file=f,
                    model="saaras:v3",
                    mode="transcribe",
                )

            original_text = transcribe_resp.transcript or ""
            lang_code = transcribe_resp.language_code or "en-IN"

            # Step 2: If not English, get English translation
            if lang_code and not lang_code.startswith("en"):
                with open(tmp_path, "rb") as f:
                    translate_resp = self._client.speech_to_text.transcribe(
                        file=f,
                        model="saaras:v3",
                        mode="translate",
                    )
                english_text = translate_resp.transcript or original_text
            else:
                english_text = original_text

        except ApiError as e:
            raise RuntimeError(f"Sarvam STT error {e.status_code}: {e.body}") from e
        finally:
            os.unlink(tmp_path)

        return ProcessedInput(
            english_text=english_text.strip(),
            language_code=lang_code,
            original_text=original_text.strip(),
        )

    def process_text(self, text: str) -> ProcessedInput:
        """
        Process a text message.
        Detect language, translate to English if needed.
        """
        try:
            lid_resp = self._client.text.identify_language(input=text[:1000])
            lang_code = lid_resp.language_code or "en-IN"
        except ApiError:
            # If LID fails, assume English
            lang_code = "en-IN"

        if lang_code and not lang_code.startswith("en"):
            try:
                trans_resp = self._client.text.translate(
                    input=text,
                    source_language_code=lang_code,
                    target_language_code="en-IN",
                    model="mayura:v1",
                    mode="modern-colloquial",
                )
                english_text = trans_resp.translated_text or text
            except ApiError:
                english_text = text
        else:
            english_text = text

        return ProcessedInput(
            english_text=english_text.strip(),
            language_code=lang_code,
            original_text=text.strip(),
        )

    def translate_to_language(self, text: str, target_lang_code: str) -> str:
        """
        Translate English text to a target Indian language for bot responses.
        Returns original text if translation fails or target is English.
        """
        if not target_lang_code or target_lang_code.startswith("en"):
            return text
        try:
            resp = self._client.text.translate(
                input=text,
                source_language_code="en-IN",
                target_language_code=target_lang_code,
                model="mayura:v1",
                mode="modern-colloquial",
            )
            return resp.translated_text or text
        except ApiError:
            return text
