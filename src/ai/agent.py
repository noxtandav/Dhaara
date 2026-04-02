"""
Dhaara AI Agent.
Handles the conversation loop with AWS Bedrock, including tool use.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from .bedrock import BedrockClient
from .prompts import build_system_prompt, TOOLS
from ..journal.store import JournalStore
from ..journal.silos import list_silos, create_silo
from ..context.telos import read_telos
from ..context.state import ConversationState, Message

logger = logging.getLogger(__name__)

# Maximum tool-use rounds per user message (safety limit)
MAX_TOOL_ROUNDS = 8


class DhaaraAgent:
    def __init__(self, bedrock: BedrockClient, data_dir: Path):
        self._bedrock = bedrock
        self._data_dir = data_dir
        self._store = JournalStore(data_dir)
        self._state = ConversationState()

    def handle_message(
        self,
        chat_id: int,
        user_text: str,
        timestamp: datetime,
        detected_lang: str = "en-IN",
    ) -> str:
        """
        Process a user message (already in English) and return the agent's response (in English).
        The bot layer handles translating the response back to the user's language.
        """
        # Add user message to history
        self._state.add_message(chat_id, "user", user_text)
        self._state.set_language(chat_id, detected_lang)

        # Build Bedrock message list from history
        messages = self._build_messages(chat_id)

        # Build system prompt with current silos + TELOS
        system_prompt = build_system_prompt(self._data_dir)

        # Agentic loop: run until end_turn or max rounds
        tool_round = 0
        while tool_round < MAX_TOOL_ROUNDS:
            response = self._bedrock.converse(
                messages=messages,
                system_prompt=system_prompt,
                tools=TOOLS,
            )

            stop = self._bedrock.stop_reason(response)
            assistant_content = response.get("output", {}).get("message", {}).get("content", [])

            # Append assistant turn to messages
            messages.append({"role": "assistant", "content": assistant_content})

            if stop == "end_turn":
                # Extract final text response
                text_parts = [b["text"] for b in assistant_content if "text" in b]
                final_response = "\n".join(text_parts)
                # Save to conversation history
                self._state.add_message(chat_id, "assistant", final_response)
                return final_response

            elif stop == "tool_use":
                tool_uses = self._bedrock.extract_tool_uses(response)
                tool_results = []

                for tool_use in tool_uses:
                    result = self._execute_tool(
                        name=tool_use["name"],
                        input_data=tool_use["input"],
                        timestamp=timestamp,
                    )
                    tool_results.append({
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"text": result}],
                    })

                # Add tool results as user turn
                messages.append({
                    "role": "user",
                    "content": [{"toolResult": tr} for tr in tool_results],
                })
                tool_round += 1

            else:
                # Unexpected stop reason
                break

        # Fallback if we hit max rounds
        final_response = "I've processed your entry. Let me know if you'd like any changes."
        self._state.add_message(chat_id, "assistant", final_response)
        return final_response

    def _build_messages(self, chat_id: int) -> list[dict]:
        """Convert conversation history to Bedrock message format."""
        history = self._state.get_history(chat_id)
        messages = []
        for msg in history:
            messages.append({
                "role": msg.role,
                "content": [{"text": msg.content}],
            })
        return messages

    def _execute_tool(self, name: str, input_data: dict, timestamp: datetime) -> str:
        """Execute a tool call and return the result as a string."""
        try:
            if name == "record_entry":
                return self._tool_record_entry(input_data, timestamp)
            elif name == "read_today_entries":
                return self._tool_read_today_entries(input_data, timestamp)
            elif name == "list_silos":
                return self._tool_list_silos()
            elif name == "create_silo":
                return self._tool_create_silo(input_data)
            elif name == "read_telos":
                return self._tool_read_telos(input_data)
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}")
            return f"Error executing {name}: {str(e)}"

    def _tool_record_entry(self, data: dict, timestamp: datetime) -> str:
        silo = data["silo"]
        text = data["text"]
        mood = data.get("mood")
        tags = data.get("tags", [])
        finance_items = data.get("finance_items")

        path = self._store.append_entry(
            silo=silo,
            text=text,
            timestamp=timestamp,
            mood=mood,
            tags=tags,
            finance_items=finance_items,
        )
        return f"Entry recorded in {silo} silo ({path.name})."

    def _tool_read_today_entries(self, data: dict, timestamp: datetime) -> str:
        silo = data["silo"]
        content = self._store.read_day(silo, timestamp)
        if content is None:
            return f"No entries yet today in {silo} silo."
        return content

    def _tool_list_silos(self) -> str:
        silos = list_silos(self._data_dir)
        if not silos:
            return "No silos found."
        lines = [f"- {s['name']}: {s['description']}" for s in silos]
        return "Available silos:\n" + "\n".join(lines)

    def _tool_create_silo(self, data: dict) -> str:
        name = data["name"]
        description = data["description"]
        create_silo(self._data_dir, name, description)
        return f"Silo '{name}' created successfully."

    def _tool_read_telos(self, data: dict) -> str:
        background = data["background"]
        return read_telos(self._data_dir, background)
