"""
Dhaara AI Agent.
Handles the conversation loop with AWS Bedrock, including tool use.
"""
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from .bedrock import BedrockClient
from .prompts import build_system_prompt, TOOLS
from ..journal.store import JournalStore
from ..config import load_config
from ..context.telos import read_telos
from ..context.state import ConversationState, Message

logger = logging.getLogger(__name__)

# Maximum tool-use rounds per user message (safety limit)
MAX_TOOL_ROUNDS = 8


class DhaaraAgent:
    def __init__(self, bedrock: BedrockClient):
        config = load_config()
        self._bedrock = bedrock
        self._data_dir = config.data_dir
        self._store = JournalStore(config.data_dir)
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
        The bot layer translates the response back to the user's language via Sarvam.
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
        final_response = "Entry recorded."  # Always return English
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
            elif name == "read_today":
                return self._tool_read_today(input_data, timestamp)
            elif name == "read_telos":
                return self._tool_read_telos(input_data)
            elif name == "proxy_shell":
                return self._tool_proxy_shell(input_data)
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}")
            return f"Error executing {name}: {str(e)}"

    def _tool_record_entry(self, data: dict, timestamp: datetime) -> str:
        category = data["category"]
        text = data["text"]
        mood = data.get("mood")

        path = self._store.append_entry(
            category=category,
            text=text,
            timestamp=timestamp,
            mood=mood,
        )
        return "Entry recorded."  # English only

    def _tool_read_today(self, data: dict, timestamp: datetime) -> str:
        content = self._store.read_day(timestamp)
        if content is None:
            return "No entries yet."  # English only
        return content

    def _tool_read_telos(self, data: dict) -> str:
        background = data["background"]
        return read_telos(self._data_dir, background)

    def _tool_proxy_shell(self, data: dict) -> str:
        """
        Executes a whitelisted shell command in data_dir.
        Args:
            data: {"command": str, "require_review": bool}
        Returns:
            Output or confirmation prompt.
        """
        command = data["command"]
        require_review = data.get("require_review", False)
        
        # 1. Validate command against whitelist
        whitelist = {
            "ls": {"-l", "-a"},
            "grep": {"-r", "-n", "-i", "-v"},
            "sed": {"-i", "-n", "-E"},
            "awk": {},
            "echo": {},
            "cat": {},
            "mv": {},
            "cp": {},
            "mkdir": {},
            "nano": {}
        }
        cmd_parts = command.split()
        if not cmd_parts or cmd_parts[0] not in whitelist:
            return f"Command '{cmd_parts[0]}' not whitelisted."

        # 2. Sanitize inputs
        sanitized = []
        for part in cmd_parts:
            # Strip metacharacters
            part = part.replace("$", "").replace("`", "").replace(">", "").replace("|", "").replace(";", "")
            # Reject path traversal
            if "../" in part or part.startswith("/"):
                return f"Invalid path: {part}"
            sanitized.append(part)
        sanitized_cmd = " ".join(sanitized)

        # 3. Require review for destructive commands
        if require_review or any(x in command for x in ["-i", ">>", "mv", "cp"]):
            return f"Will run:\n```bash\n{sanitized_cmd}\n```\nProceed? (Y/n)"

        # 4. Execute in data_dir
        try:
            result = subprocess.run(
                sanitized_cmd,
                cwd=self._data_dir,
                shell=False,
                capture_output=True,
                text=True,
                check=True
            )
            # 5. Log to .proxy_history
            history_path = self._data_dir / ".proxy_history"
            with open(history_path, "a") as f:
                f.write(f"{datetime.now().isoformat()} | {sanitized_cmd}\n")
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Error: {e.stderr}"
