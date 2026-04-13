"""
Abstract base class for language providers (STT + translation).
Implement this to add new language backends (e.g. Google Cloud Speech, Azure, etc.).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProcessedInput:
    english_text: str       # Always English for the agent
    language_code: str      # BCP-47, e.g. "hi-IN", "en-IN"
    original_text: str      # Original transcription/text before translation


class LanguageProvider(ABC):
    @abstractmethod
    def process_voice(self, audio_bytes: bytes, audio_format: str = "ogg") -> ProcessedInput:
        """Process a voice message: transcribe and translate to English."""
        ...

    @abstractmethod
    def process_text(self, text: str) -> ProcessedInput:
        """Process a text message: detect language and translate to English if needed."""
        ...

    @abstractmethod
    def translate_to_language(self, text: str, target_lang_code: str) -> str:
        """Translate English text to the target language for bot responses."""
        ...
