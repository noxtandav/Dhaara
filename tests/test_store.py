"""Tests for src/journal/store.py.

The full JournalStore predates this test file. Coverage here focuses on
read_journal_range, which is the multi-day reader powering the
telos_insights tool. The single-day primitives (read_day, append_entry,
edit_entry, delete_entry) are exercised indirectly by the script-level
tests (test_today.py, test_export_journal.py, etc.).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.journal.store import JournalStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(date_str: str) -> datetime:
    """ISO date → tz-aware datetime at midnight UTC. The store keys files
    by `strftime("%Y-%m-%d")` so the time component is irrelevant; we just
    need a real datetime."""
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path) -> JournalStore:
    return JournalStore(tmp_path)


def _seed(store: JournalStore, date_str: str, body: str = "x") -> None:
    """Write a minimal journal file for `date_str` so read_day finds it.

    Goes through the formatter so the file shape matches what the
    real bot produces (header + 4 sections + bullet)."""
    ts = _dt(date_str)
    store.append_entry(category="WORK", text=body, timestamp=ts, subcategory="t")


# ---------------------------------------------------------------------------
# read_journal_range
# ---------------------------------------------------------------------------

class TestReadJournalRange:
    def test_no_files_returns_empty_marker(self, store: JournalStore):
        result = store.read_journal_range(_dt("2026-04-30"), days=7)
        assert result["days_with_entries"] == 0
        assert result["days_requested"] == 7
        assert result["content"] == "(No entries found.)"

    def test_single_day_in_range(self, store: JournalStore):
        _seed(store, "2026-04-15", body="solo entry")
        result = store.read_journal_range(_dt("2026-04-15"), days=1)
        assert result["days_with_entries"] == 1
        assert result["days_requested"] == 1
        assert "solo entry" in result["content"]

    def test_skips_missing_days_but_counts_correctly(self, store: JournalStore):
        # Seed only 2 of the 5 days in the range.
        _seed(store, "2026-04-13", body="apr 13 work")
        _seed(store, "2026-04-15", body="apr 15 work")

        result = store.read_journal_range(_dt("2026-04-15"), days=5)
        assert result["days_with_entries"] == 2
        assert result["days_requested"] == 5
        assert "apr 13 work" in result["content"]
        assert "apr 15 work" in result["content"]

    def test_content_in_chronological_order(self, store: JournalStore):
        # Seed in reverse to confirm the reader sorts oldest-first.
        for day in ("2026-04-15", "2026-04-14", "2026-04-13"):
            _seed(store, day, body=f"body {day}")

        result = store.read_journal_range(_dt("2026-04-15"), days=3)
        # Each day's content includes a "# YYYY-MM-DD Journal" header from
        # format_day_header. Position of those headers tells us the order.
        idx_13 = result["content"].find("2026-04-13")
        idx_14 = result["content"].find("2026-04-14")
        idx_15 = result["content"].find("2026-04-15")
        assert -1 < idx_13 < idx_14 < idx_15

    def test_separator_between_days(self, store: JournalStore):
        _seed(store, "2026-04-13", body="x")
        _seed(store, "2026-04-14", body="y")
        result = store.read_journal_range(_dt("2026-04-14"), days=2)
        # Days are joined by "\n\n---\n\n"
        assert "\n\n---\n\n" in result["content"]

    def test_window_walks_back_inclusive_of_end_date(self, store: JournalStore):
        # days=5 ending at 2026-04-15 means days 11-15 inclusive.
        _seed(store, "2026-04-10", body="just outside")  # day -1, should be skipped
        _seed(store, "2026-04-11", body="day 1")
        _seed(store, "2026-04-15", body="day 5")

        result = store.read_journal_range(_dt("2026-04-15"), days=5)
        assert "day 1" in result["content"]
        assert "day 5" in result["content"]
        assert "just outside" not in result["content"]
        assert result["days_with_entries"] == 2

    def test_zero_days(self, store: JournalStore):
        result = store.read_journal_range(_dt("2026-04-15"), days=0)
        assert result["days_with_entries"] == 0
        assert result["days_requested"] == 0
        # Empty windows still get the empty marker, not an empty string.
        assert result["content"] == "(No entries found.)"

    def test_large_window_does_not_explode(self, store: JournalStore):
        # 90-day cap is enforced at the agent layer (telos_insights), but
        # the store itself should accept arbitrary `days`.
        _seed(store, "2026-04-15", body="lonely")
        result = store.read_journal_range(_dt("2026-04-15"), days=365)
        assert result["days_with_entries"] == 1
        assert result["days_requested"] == 365
