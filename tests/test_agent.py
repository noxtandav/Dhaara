"""Tests for src/ai/agent.py — focused on the telos_insights tool dispatch.

The full DhaaraAgent.__init__ wires up an AIProvider, the LangGraph state
machine, and a SQLite checkpointer — all things we don't want to mock for
a unit test of one tool method. We instantiate the agent via __new__ and
attach just the two attributes _tool_telos_insights touches:
self._store and self._telos_dir.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.ai.agent import DhaaraAgent
from src.context.telos import init_telos_files
from src.journal.store import JournalStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


@pytest.fixture
def agent(tmp_path: Path) -> DhaaraAgent:
    """A bare DhaaraAgent with only the two attrs telos_insights uses."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()  # JournalStore creates `journal/` but not its parent
    telos_dir = tmp_path / "_telos"
    init_telos_files(telos_dir)  # seeds work.md + personal.md

    a = DhaaraAgent.__new__(DhaaraAgent)
    a._store = JournalStore(data_dir)
    a._telos_dir = telos_dir
    return a


def _seed(agent: DhaaraAgent, date_str: str) -> None:
    agent._store.append_entry(
        category="WORK", text="some work", timestamp=_dt(date_str), subcategory="t",
    )


# ---------------------------------------------------------------------------
# _tool_telos_insights
# ---------------------------------------------------------------------------

class TestTelosInsights:
    def test_structure_contains_all_sections(self, agent: DhaaraAgent):
        for d in ("2026-04-13", "2026-04-14", "2026-04-15"):
            _seed(agent, d)

        out = agent._tool_telos_insights({"days": 7}, _dt("2026-04-15"))
        # Sections we always emit, in order.
        assert "## Data Coverage" in out
        assert "## TELOS Context" in out
        assert "## Journal Entries (7 days)" in out
        # Coverage line shows X/Y days.
        assert "3/7 days have entries" in out

    def test_telos_files_appear_in_context(self, agent: DhaaraAgent):
        _seed(agent, "2026-04-15")
        out = agent._tool_telos_insights({"days": 1}, _dt("2026-04-15"))
        # init_telos_files seeded these two markdown files; their headers
        # should land in the TELOS Context section.
        assert "WORK TELOS" in out
        assert "PERSONAL TELOS" in out

    # ----- Data quality warnings -----

    def test_insufficient_data_warning_under_3_days(self, agent: DhaaraAgent):
        # 2 days of entries in a 30-day window → < 3 → INSUFFICIENT.
        _seed(agent, "2026-04-14")
        _seed(agent, "2026-04-15")
        out = agent._tool_telos_insights({"days": 30}, _dt("2026-04-15"))
        assert "⚠ INSUFFICIENT DATA" in out
        assert "very limited data" in out

    def test_zero_days_is_insufficient(self, agent: DhaaraAgent):
        out = agent._tool_telos_insights({"days": 30}, _dt("2026-04-15"))
        assert "⚠ INSUFFICIENT DATA" in out
        assert "0 day(s)" in out

    def test_limited_data_warning_under_30_percent(self, agent: DhaaraAgent):
        # 5 days in a 30-day window → 16% → LIMITED (not INSUFFICIENT,
        # since 5 >= 3).
        for offset in range(5):
            _seed(agent, f"2026-04-{15 - offset:02d}")
        out = agent._tool_telos_insights({"days": 30}, _dt("2026-04-15"))
        assert "⚠ LIMITED DATA" in out
        assert "5 out of 30" in out
        assert "INSUFFICIENT" not in out

    def test_no_warning_when_above_30_percent(self, agent: DhaaraAgent):
        # 4 of 7 days = 57% — well above the 30% threshold.
        for d in ("2026-04-12", "2026-04-13", "2026-04-14", "2026-04-15"):
            _seed(agent, d)
        out = agent._tool_telos_insights({"days": 7}, _dt("2026-04-15"))
        assert "INSUFFICIENT" not in out
        assert "LIMITED DATA" not in out

    # ----- The 90-day cap -----

    def test_days_capped_at_90(self, agent: DhaaraAgent):
        _seed(agent, "2026-04-15")
        out = agent._tool_telos_insights({"days": 365}, _dt("2026-04-15"))
        # Header line should report the capped value, not 365.
        assert "(90 days)" in out
        assert "1/90 days have entries" in out

    def test_small_days_passed_through(self, agent: DhaaraAgent):
        _seed(agent, "2026-04-15")
        out = agent._tool_telos_insights({"days": 7}, _dt("2026-04-15"))
        assert "(7 days)" in out

    # ----- Dispatch wiring -----

    def test_dispatcher_routes_to_telos_insights(self, agent: DhaaraAgent):
        """The graph calls self._execute_tool by name; confirm the
        'telos_insights' name lands in our new method, not anywhere else."""
        _seed(agent, "2026-04-15")
        # _execute_tool is a bound method on the same instance.
        out = agent._execute_tool("telos_insights", {"days": 1}, _dt("2026-04-15"))
        # If routed correctly, the output has the new tool's signature
        # sections.
        assert "## Data Coverage" in out
        assert "## TELOS Context" in out

    def test_dispatcher_unknown_tool_unchanged(self, agent: DhaaraAgent):
        out = agent._execute_tool("not_a_real_tool", {}, _dt("2026-04-15"))
        assert "Unknown tool" in out

    def test_dispatcher_catches_tool_exceptions(self, agent: DhaaraAgent):
        # days=None will blow up at min(None, 90); _execute_tool's
        # try/except should turn that into a polite error string the
        # graph can pass back to the model.
        out = agent._execute_tool("telos_insights", {}, _dt("2026-04-15"))
        assert out.startswith("Error executing telos_insights:")
