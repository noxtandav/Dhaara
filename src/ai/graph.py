"""
LangGraph state machine for the Dhaara agent loop.

Replaces the hand-rolled while-loop with a typed StateGraph:

    START → call_llm → (tool_use)  → execute_tools → call_llm
                     → (end_turn)  → verify_response → END
                     → (other)     → verify_response → END  (honest failure)

State is persisted per-chat via SqliteSaver, keyed by thread_id=str(chat_id).
This survives bot restarts and preserves tool turns (toolUse / toolResult)
across user messages — preventing the history-stripping that fed tool
hallucinations in the previous loop.
"""
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from .provider import AIProvider
from .prompts import TOOLS

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
MAX_HISTORY = 60

MUTATING_TOOLS = {"record_entry", "edit_entry", "delete_entry"}

_FAILURE_RESPONSE = "I couldn't save that — please try again."

_SUCCESS_CLAIM = re.compile(
    r"\b(recorded|noted|saved|logged|added|updated|edited|deleted|removed)\b",
    re.IGNORECASE,
)


def _append_and_trim(left: list[dict], right: list[dict]) -> list[dict]:
    """Reducer: append new turns to history, keep the last MAX_HISTORY."""
    return (left + right)[-MAX_HISTORY:]


class AgentState(TypedDict, total=False):
    messages: Annotated[list[dict], _append_and_trim]
    system_prompt: str
    timestamp_iso: str
    tool_round: int
    mutating_tool_called: bool
    last_stop_reason: str
    final_response: str | None


def build_graph(
    ai: AIProvider,
    execute_tool: Callable[[str, dict, datetime], str],
    checkpoint_path: Path,
):
    """
    Construct and compile the Dhaara agent graph.

    `execute_tool(name, input, timestamp)` is injected so the graph stays
    decoupled from JournalStore — DhaaraAgent passes its own dispatch.
    """

    def call_llm(state: AgentState) -> dict:
        response = ai.converse(
            messages=[
                {"role": m["role"], "content": m["content"]}
                for m in state["messages"]
            ],
            system_prompt=state["system_prompt"],
            tools=TOOLS,
        )
        stop = ai.stop_reason(response)
        assistant_content = (
            response.get("output", {}).get("message", {}).get("content", [])
        )
        return {
            "messages": [{"role": "assistant", "content": assistant_content}],
            "last_stop_reason": stop,
        }

    def execute_tools(state: AgentState) -> dict:
        last = state["messages"][-1]
        tool_uses = [b["toolUse"] for b in last["content"] if "toolUse" in b]
        timestamp = datetime.fromisoformat(state["timestamp_iso"])
        mutating = state.get("mutating_tool_called", False)

        tool_results = []
        for tu in tool_uses:
            if tu["name"] in MUTATING_TOOLS:
                mutating = True
            result = execute_tool(tu["name"], tu["input"], timestamp)
            tool_results.append({
                "toolUseId": tu["toolUseId"],
                "content": [{"text": result}],
            })

        return {
            "messages": [{
                "role": "user",
                "content": [{"toolResult": tr} for tr in tool_results],
            }],
            "tool_round": state.get("tool_round", 0) + 1,
            "mutating_tool_called": mutating,
        }

    def verify_response(state: AgentState) -> dict:
        stop = state.get("last_stop_reason", "")

        if stop == "end_turn":
            last = state["messages"][-1]
            text_parts = [b["text"] for b in last["content"] if "text" in b]
            final = "\n".join(text_parts).strip()

            if not state.get("mutating_tool_called") and _SUCCESS_CLAIM.search(final):
                logger.warning(
                    "Tool hallucination: claimed success without mutating tool. text=%r",
                    final,
                )
                final = _FAILURE_RESPONSE
                return {
                    "messages": [
                        {"role": "assistant", "content": [{"text": final}]}
                    ],
                    "final_response": final,
                }

            return {"final_response": final or _FAILURE_RESPONSE}

        logger.warning(
            "Loop exited without end_turn: stop=%r tool_round=%d",
            stop, state.get("tool_round", 0),
        )
        return {
            "messages": [
                {"role": "assistant", "content": [{"text": _FAILURE_RESPONSE}]}
            ],
            "final_response": _FAILURE_RESPONSE,
        }

    def route_after_llm(state: AgentState) -> str:
        stop = state.get("last_stop_reason", "")
        if stop == "tool_use" and state.get("tool_round", 0) < MAX_TOOL_ROUNDS:
            return "execute_tools"
        return "verify_response"

    builder = StateGraph(AgentState)
    builder.add_node("call_llm", call_llm)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("verify_response", verify_response)

    builder.add_edge(START, "call_llm")
    builder.add_conditional_edges(
        "call_llm",
        route_after_llm,
        {"execute_tools": "execute_tools", "verify_response": "verify_response"},
    )
    builder.add_edge("execute_tools", "call_llm")
    builder.add_edge("verify_response", END)

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return builder.compile(checkpointer=checkpointer)
