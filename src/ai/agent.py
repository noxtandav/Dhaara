"""
Dhaara AI Agent.

Thin wrapper that builds the LangGraph state machine in `graph.py` and
exposes per-tool implementations + a `handle_message` entry point for the
Telegram bot layer. The agent loop logic lives in the graph; this module
owns tool dispatch, language tracking, and the journal store.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .provider import AIProvider
from .prompts import build_system_prompt
from .graph import build_graph
from ..journal.store import JournalStore
from ..config import load_config
from ..context.telos import read_telos

logger = logging.getLogger(__name__)


class DhaaraAgent:
    def __init__(self, ai: AIProvider, tz: ZoneInfo):
        config = load_config()
        self._ai = ai
        self._tz = tz
        self._data_dir = config.data_dir
        self._telos_dir = config.telos_dir
        self._store = JournalStore(config.data_dir)
        self._lang: dict[int, str] = {}

        checkpoint_path = config.data_dir / "checkpoints.db"
        self._graph = build_graph(
            ai=ai,
            execute_tool=self._execute_tool,
            checkpoint_path=checkpoint_path,
        )

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
        self._lang[chat_id] = detected_lang

        # Per-message inputs: append the user turn (reducer concatenates),
        # reset per-call counters, and overwrite the system prompt + timestamp.
        graph_input = {
            "messages": [{"role": "user", "content": [{"text": user_text}]}],
            "system_prompt": build_system_prompt(self._tz),
            "timestamp_iso": timestamp.isoformat(),
            "tool_round": 0,
            "mutating_tool_called": False,
            "last_stop_reason": "",
            "final_response": None,
        }
        config = {"configurable": {"thread_id": str(chat_id)}}

        final_state = self._graph.invoke(graph_input, config=config)
        return final_state.get("final_response") or "I couldn't save that — please try again."

    def get_language(self, chat_id: int) -> str:
        return self._lang.get(chat_id, "en")

    def clear_history(self, chat_id: int) -> None:
        """Drop the persisted conversation thread for this chat."""
        self._graph.checkpointer.delete_thread(str(chat_id))
        self._lang.pop(chat_id, None)

    def _execute_tool(self, name: str, input_data: dict, timestamp: datetime) -> str:
        """Execute a tool call and return the result as a string."""
        try:
            if name == "record_entry":
                return self._tool_record_entry(input_data, timestamp)
            elif name == "read_today":
                return self._tool_read_today(input_data, timestamp)
            elif name == "read_day":
                return self._tool_read_day(input_data)
            elif name == "read_telos":
                return self._tool_read_telos(input_data)
            elif name == "list_entries":
                return self._tool_list_entries(input_data, timestamp)
            elif name == "edit_entry":
                return self._tool_edit_entry(input_data, timestamp)
            elif name == "delete_entry":
                return self._tool_delete_entry(input_data, timestamp)
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}")
            return f"Error executing {name}: {str(e)}"

    def _tool_record_entry(self, data: dict, timestamp: datetime) -> str:
        self._store.append_entry(
            category=data["category"],
            text=data["text"],
            timestamp=timestamp,
            subcategory=data.get("subcategory"),
            mood=data.get("mood"),
        )
        return "Entry recorded."

    def _tool_read_today(self, data: dict, timestamp: datetime) -> str:
        content = self._store.read_day(timestamp)
        return content if content is not None else "No entries yet."

    def _tool_read_day(self, data: dict) -> str:
        date = self._parse_date(data["date"])
        if date is None:
            return f"Invalid date format: '{data['date']}'. Use YYYY-MM-DD."
        content = self._store.read_day(date)
        return content if content is not None else f"No entries for {data['date']}."

    def _tool_read_telos(self, data: dict) -> str:
        return read_telos(self._telos_dir, data["background"])

    def _tool_list_entries(self, data: dict, timestamp: datetime) -> str:
        date_str = data.get("date")
        if date_str:
            date = self._parse_date(date_str)
            if date is None:
                return f"Invalid date format: '{date_str}'. Use YYYY-MM-DD."
            return self._store.list_entries(date)
        return self._store.list_entries(timestamp)

    def _parse_date(self, date_str: str) -> datetime | None:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=self._tz)
        except (ValueError, TypeError):
            return None

    def _tool_edit_entry(self, data: dict, timestamp: datetime) -> str:
        target = self._resolve_target_date(data.get("date"), timestamp)
        if isinstance(target, str):
            return target
        return self._store.edit_entry(target, data["line_number"], data["new_text"])

    def _tool_delete_entry(self, data: dict, timestamp: datetime) -> str:
        target = self._resolve_target_date(data.get("date"), timestamp)
        if isinstance(target, str):
            return target
        return self._store.delete_entry(target, data["line_number"])

    def _resolve_target_date(self, date_str: str | None, fallback: datetime) -> datetime | str:
        """Parse a YYYY-MM-DD `date` arg, falling back to today's timestamp if omitted.
        Returns a datetime on success, or an error string the tool result can pass back."""
        if not date_str:
            return fallback
        parsed = self._parse_date(date_str)
        if parsed is None:
            return f"Invalid date format: '{date_str}'. Use YYYY-MM-DD."
        return parsed
