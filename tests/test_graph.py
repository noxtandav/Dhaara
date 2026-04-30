"""Tests for src/ai/graph.py.

This is the LangGraph state machine the bot runs on. The two pure node
functions — verify_response and route_after_llm — were extracted out of
the build_graph closure so they're testable without an LLM mock. The
closure-bound nodes (call_llm, execute_tools) need an AIProvider and a
tool dispatcher and are exercised end-to-end by the live bot's
PM2-managed startup; we don't mock-test them here.

Coverage focuses on the failure modes that have actually bitten the
project:

  - Iteration ec0eb9e ("prevent tool-call hallucination") added the
    _SUCCESS_CLAIM regex + check in verify_response.
  - Iteration 010eed3 (LOOP iter-19) relaxed the gate from
    `not mutating_tool_called` to `tool_round == 0` after the original
    over-fired on the read path.

Tests below pin both behaviors so neither regresses silently.
"""
from __future__ import annotations

import pytest

from src.ai.graph import (
    MAX_TOOL_ROUNDS,
    MUTATING_TOOLS,
    _FAILURE_RESPONSE,
    _SUCCESS_CLAIM,
    _append_and_trim,
    route_after_llm,
    verify_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_end_turn(text: str, *, tool_round: int = 0,
                    mutating: bool = False) -> dict:
    """Minimal AgentState shaped after an end_turn from the LLM."""
    return {
        "messages": [
            {"role": "user", "content": [{"text": "u"}]},
            {"role": "assistant", "content": [{"text": text}]},
        ],
        "last_stop_reason": "end_turn",
        "tool_round": tool_round,
        "mutating_tool_called": mutating,
    }


# ---------------------------------------------------------------------------
# verify_response
# ---------------------------------------------------------------------------

class TestVerifyResponseHappyPath:
    def test_passes_neutral_text_through(self):
        s = _state_end_turn("Here is what's on your plate this morning.")
        out = verify_response(s)
        assert out == {"final_response": "Here is what's on your plate this morning."}

    def test_text_with_claim_words_passes_when_a_tool_was_called(self):
        # iter-19 fix: read tools (tool_round > 0) make claim words OK.
        s = _state_end_turn(
            "Here are today's entries you recorded:\n- ...",
            tool_round=1,
            mutating=False,
        )
        out = verify_response(s)
        assert out == {"final_response": "Here are today's entries you recorded:\n- ..."}

    def test_text_with_claim_words_passes_after_mutation(self):
        s = _state_end_turn(
            "Done. Recorded to [FINANCE].",
            tool_round=1,
            mutating=True,
        )
        out = verify_response(s)
        assert out == {"final_response": "Done. Recorded to [FINANCE]."}

    def test_strips_whitespace(self):
        s = _state_end_turn("\n\n  reply  \n\n")
        out = verify_response(s)
        assert out == {"final_response": "reply"}

    def test_concatenates_multiple_text_blocks(self):
        s = {
            "messages": [
                {"role": "assistant", "content": [
                    {"text": "first part"},
                    {"text": "second part"},
                ]},
            ],
            "last_stop_reason": "end_turn",
            "tool_round": 1,
        }
        out = verify_response(s)
        assert out == {"final_response": "first part\nsecond part"}

    def test_ignores_non_text_blocks(self):
        # Real LLM responses can have toolUse blocks alongside text. The
        # joiner must skip those without exploding.
        s = {
            "messages": [
                {"role": "assistant", "content": [
                    {"text": "preamble"},
                    {"toolUse": {"name": "x", "input": {}, "toolUseId": "tu1"}},
                    {"text": "epilogue"},
                ]},
            ],
            "last_stop_reason": "end_turn",
            "tool_round": 1,
        }
        out = verify_response(s)
        assert out == {"final_response": "preamble\nepilogue"}

    def test_empty_text_falls_back_to_failure(self):
        s = _state_end_turn("", tool_round=1)
        out = verify_response(s)
        assert out == {"final_response": _FAILURE_RESPONSE}

    def test_only_whitespace_falls_back_to_failure(self):
        s = _state_end_turn("   \n  \t  ", tool_round=1)
        out = verify_response(s)
        assert out == {"final_response": _FAILURE_RESPONSE}


class TestVerifyResponseHallucinationGuard:
    """The iter-19 contract: fire the guard ONLY when tool_round == 0."""

    def test_fires_on_no_tool_plus_claim_word(self):
        # The exact failure mode iteration ec0eb9e was added to catch:
        # model fabricates a "recorded!" reply without calling any tool.
        s = _state_end_turn(
            "Recorded to [WORK].",
            tool_round=0,
            mutating=False,
        )
        out = verify_response(s)
        assert out["final_response"] == _FAILURE_RESPONSE
        # Also overwrites the message history so a follow-up call_llm
        # doesn't see the lie.
        assert out["messages"][0]["content"][0]["text"] == _FAILURE_RESPONSE

    @pytest.mark.parametrize("verb", [
        "recorded", "noted", "saved", "logged", "added",
        "updated", "edited", "deleted", "removed",
        "Recorded", "RECORDED",  # case-insensitive
    ])
    def test_each_claim_verb_triggers_when_no_tool(self, verb: str):
        s = _state_end_turn(f"Done. {verb} the entry.", tool_round=0)
        out = verify_response(s)
        assert out["final_response"] == _FAILURE_RESPONSE

    def test_no_fire_when_text_lacks_claim_words(self):
        # A no-tool reply without claim words is suspicious but not a
        # success-claim hallucination — pass it through. (The model
        # might just be answering "what time is it?" or similar.)
        s = _state_end_turn("I don't have enough context.", tool_round=0)
        out = verify_response(s)
        assert out == {"final_response": "I don't have enough context."}

    def test_partial_word_does_not_trigger(self):
        # \b word boundaries guard against e.g. "preloaded" matching
        # "loaded".
        s = _state_end_turn(
            "The preloaded data adds nothing here.",
            tool_round=0,
        )
        out = verify_response(s)
        # "loaded" is a word inside "preloaded" → \b means no match.
        # But "added" might match in a substring... let's be careful.
        # "adds" doesn't match "added" (different words) — so this is safe.
        assert out["final_response"].startswith("The preloaded")

    def test_no_fire_with_read_tool_call(self):
        # The original iter-19 regression: model calls list_entries,
        # gets back the day's data, replies "Here is the entry recorded".
        # With tool_round >= 1, the guard MUST not fire.
        s = _state_end_turn(
            "Here is the entry recorded today: ...",
            tool_round=1,
            mutating=False,  # read tools don't set mutating_tool_called
        )
        out = verify_response(s)
        assert out == {"final_response": "Here is the entry recorded today: ..."}


class TestVerifyResponseNonEndTurn:
    """When the model exits the loop with a non-`end_turn` reason
    (max_tokens, error, tool_use that the router didn't catch...), the
    response is unsafe to surface. Replace with the failure message."""

    @pytest.mark.parametrize("stop_reason", [
        "max_tokens", "error", "tool_use",  # tool_use means the loop bailed mid-decision
        "stop_sequence", "",
    ])
    def test_returns_failure_on_unrecognized_stop(self, stop_reason: str):
        s = {
            "messages": [
                {"role": "assistant", "content": [{"text": "anything"}]},
            ],
            "last_stop_reason": stop_reason,
            "tool_round": 0,
        }
        out = verify_response(s)
        assert out["final_response"] == _FAILURE_RESPONSE
        # And the failure response also shows up in the message history
        # so the next /clear works cleanly.
        assert out["messages"][0]["content"][0]["text"] == _FAILURE_RESPONSE


# ---------------------------------------------------------------------------
# route_after_llm
# ---------------------------------------------------------------------------

class TestRouteAfterLLM:
    def test_tool_use_routes_to_execute_tools(self):
        s = {"last_stop_reason": "tool_use", "tool_round": 0}
        assert route_after_llm(s) == "execute_tools"

    def test_under_cap_keeps_routing_to_execute_tools(self):
        s = {"last_stop_reason": "tool_use", "tool_round": MAX_TOOL_ROUNDS - 1}
        assert route_after_llm(s) == "execute_tools"

    def test_at_cap_routes_to_verify_response(self):
        # Hitting MAX_TOOL_ROUNDS forces the loop to terminate even if
        # the model wants another tool. Prevents runaway tool spirals.
        s = {"last_stop_reason": "tool_use", "tool_round": MAX_TOOL_ROUNDS}
        assert route_after_llm(s) == "verify_response"

    def test_above_cap_routes_to_verify_response(self):
        s = {"last_stop_reason": "tool_use", "tool_round": MAX_TOOL_ROUNDS + 5}
        assert route_after_llm(s) == "verify_response"

    @pytest.mark.parametrize("stop", [
        "end_turn", "max_tokens", "stop_sequence", "error", "",
    ])
    def test_non_tool_use_routes_to_verify_response(self, stop: str):
        s = {"last_stop_reason": stop, "tool_round": 0}
        assert route_after_llm(s) == "verify_response"

    def test_missing_tool_round_treated_as_zero(self):
        s = {"last_stop_reason": "tool_use"}  # no tool_round key
        # Defaults to 0 → still under the cap → keep looping.
        assert route_after_llm(s) == "execute_tools"


# ---------------------------------------------------------------------------
# _SUCCESS_CLAIM regex
# ---------------------------------------------------------------------------

class TestSuccessClaim:
    @pytest.mark.parametrize("text", [
        "recorded", "Recorded to FINANCE", "I have recorded that",
        "noted", "Noted with thanks", "noted!",
        "saved", "Saved successfully", "I've saved it",
        "logged", "Logged for today", "logged the workout",
        "added", "Added to the list", "I added that",
        "updated", "edited", "deleted", "removed",
        "RECORDED", "DELETED",  # case-insensitive
    ])
    def test_matches_success_verbs(self, text: str):
        assert _SUCCESS_CLAIM.search(text) is not None

    @pytest.mark.parametrize("text", [
        "I'll save that for you",        # future tense ≠ claim
        "Should I record this?",          # question
        "preloaded data",                 # \b boundary
        "discoloured walls",              # not a verb match
        "additional context",             # 'add' substring
        "",
        "I don't have enough context.",
    ])
    def test_no_match_on_unrelated_text(self, text: str):
        assert _SUCCESS_CLAIM.search(text) is None


# ---------------------------------------------------------------------------
# MUTATING_TOOLS
# ---------------------------------------------------------------------------

class TestMutatingTools:
    def test_set_contents(self):
        # Pin the contract — adding a new mutating tool is a deliberate
        # change that should also update this test.
        assert MUTATING_TOOLS == {"record_entry", "edit_entry", "delete_entry"}

    def test_does_not_include_read_tools(self):
        # read tools must NOT be in this set or the iter-19 fix loses
        # its meaning.
        for read_tool in (
            "read_today", "read_day", "read_telos",
            "list_entries", "telos_insights",
        ):
            assert read_tool not in MUTATING_TOOLS


# ---------------------------------------------------------------------------
# _append_and_trim reducer
# ---------------------------------------------------------------------------

class TestAppendAndTrim:
    def test_concatenates_lists(self):
        out = _append_and_trim([{"a": 1}], [{"b": 2}])
        assert out == [{"a": 1}, {"b": 2}]

    def test_empty_left(self):
        assert _append_and_trim([], [{"a": 1}]) == [{"a": 1}]

    def test_empty_right(self):
        assert _append_and_trim([{"a": 1}], []) == [{"a": 1}]

    def test_keeps_only_last_max_history(self):
        from src.ai.graph import MAX_HISTORY
        old = [{"i": i} for i in range(MAX_HISTORY)]
        new = [{"i": MAX_HISTORY}, {"i": MAX_HISTORY + 1}]
        out = _append_and_trim(old, new)
        # We added 2 → first 2 of `old` should drop off.
        assert len(out) == MAX_HISTORY
        assert out[0] == {"i": 2}
        assert out[-1] == {"i": MAX_HISTORY + 1}

    def test_under_cap_keeps_everything(self):
        from src.ai.graph import MAX_HISTORY
        out = _append_and_trim(
            [{"i": 0}], [{"i": i} for i in range(1, MAX_HISTORY - 1)]
        )
        assert len(out) == MAX_HISTORY - 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
