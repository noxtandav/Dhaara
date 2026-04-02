"""
In-memory conversation state per Telegram chat session.
Stores recent message history for multi-turn context.
Cleared on bot restart — no persistence needed in Phase 1.
"""
from collections import defaultdict
from dataclasses import dataclass, field


# Keep last N messages in context to avoid blowing up the prompt
MAX_HISTORY = 20


@dataclass
class Message:
    role: str   # "user" or "assistant"
    content: str


class ConversationState:
    def __init__(self):
        # chat_id -> list of Message
        self._history: dict[int, list[Message]] = defaultdict(list)
        # chat_id -> detected language code (e.g. "hi", "en")
        self._lang: dict[int, str] = {}

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        self._history[chat_id].append(Message(role=role, content=content))
        # Trim to last MAX_HISTORY messages
        if len(self._history[chat_id]) > MAX_HISTORY:
            self._history[chat_id] = self._history[chat_id][-MAX_HISTORY:]

    def get_history(self, chat_id: int) -> list[Message]:
        return self._history[chat_id]

    def set_language(self, chat_id: int, lang_code: str) -> None:
        self._lang[chat_id] = lang_code

    def get_language(self, chat_id: int) -> str:
        """Return detected language code, defaulting to 'en'."""
        return self._lang.get(chat_id, "en")

    def clear(self, chat_id: int) -> None:
        self._history[chat_id] = []
        self._lang.pop(chat_id, None)
