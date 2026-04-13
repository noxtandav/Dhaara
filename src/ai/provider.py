"""
Abstract base class for AI providers.
Implement this to add new AI backends (e.g. OpenRouter, Anthropic direct, etc.).
"""
from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def converse(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a conversation turn and return the raw provider response."""
        ...

    @abstractmethod
    def extract_tool_uses(self, response: dict) -> list[dict]:
        """Extract tool use blocks from the response.
        Returns list of {"toolUseId": str, "name": str, "input": dict}.
        """
        ...

    @abstractmethod
    def extract_text(self, response: dict) -> str:
        """Extract plain text from the response."""
        ...

    @abstractmethod
    def stop_reason(self, response: dict) -> str:
        """Return stop reason: 'end_turn', 'tool_use', etc."""
        ...
