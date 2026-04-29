"""Tests for scripts/stats.py."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import stats  # noqa: E402
from export_journal import Entry  # noqa: E402


# ---------------------------------------------------------------------------
# extract_amount
# ---------------------------------------------------------------------------

class TestExtractAmount:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Spent ₹150 on lunch", 150.0),
            ("Paid ₹1,970 for electricity", 1970.0),
            ("Paid ₹55,292 on Avila home loan", 55292.0),
            ("Bought milk Rs 60", 60.0),
            ("Subscription cost Rs. 295", 295.0),
            ("Lunch $12.50", 12.5),
            ("Invested 60k INR in stocks", 60_000.0),
            ("Paid 3750 to cook Sangita for monthly payment", 3750.0),
            ("Paid 1.5lakh for advance", 150_000.0),
            ("Bought 4 bananas for ₹40", 40.0),  # currency wins over bare number
            ("Spent 5 lac on car deposit", 500_000.0),
            ("2cr investment in mutual fund", 20_000_000.0),
        ],
    )
    def test_parses_known_shapes(self, text: str, expected: float):
        assert stats.extract_amount(text) == expected

    def test_returns_none_when_no_amount(self):
        assert stats.extract_amount("Had a great day") is None

    def test_rejects_tiny_bare_numbers(self):
        # "9 mins" should not be interpreted as ₹9.
        assert stats.extract_amount("Gym 9 mins") is None

    def test_picks_largest_when_multiple(self):
        # Two bare numbers: should return the larger of the two.
        assert stats.extract_amount("Bought 2 books for 500") == 500.0

    def test_currency_marker_wins_over_larger_bare(self):
        # ₹150 should beat the bare 999 since the currency marker is high-confidence.
        assert stats.extract_amount("₹150 on lunch (999 calories)") == 150.0


# ---------------------------------------------------------------------------
# longest_streak
# ---------------------------------------------------------------------------

class TestLongestStreak:
    def test_empty_set(self):
        assert stats.longest_streak(set()) == 0

    def test_single_day(self):
        assert stats.longest_streak({date(2026, 4, 15)}) == 1

    def test_consecutive_run(self):
        days = {date(2026, 4, d) for d in (1, 2, 3, 4)}
        assert stats.longest_streak(days) == 4

    def test_picks_longest_of_multiple_runs(self):
        # 1-2 (run 2), gap, 5-6-7-8 (run 4), gap, 12 (run 1)
        days = {date(2026, 4, d) for d in (1, 2, 5, 6, 7, 8, 12)}
        assert stats.longest_streak(days) == 4

    def test_unordered_input(self):
        days = {date(2026, 4, d) for d in (8, 5, 7, 6)}
        assert stats.longest_streak(days) == 4


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------

def _entry(d: str, cat: str, sub: str = "", text: str = "x", mood: str = "", time: str = "9:00 AM") -> Entry:
    return Entry(date=d, time=time, category=cat, subcategory=sub, text=text, mood=mood)


class TestComputeStats:
    def test_empty_input(self):
        result = stats.compute_stats([])
        assert result["total_entries"] == 0
        assert result["days_with_entries"] == 0
        assert result["by_category"] == {}
        assert result["finance"]["total"] == 0.0

    def test_category_counts(self):
        entries = [
            _entry("2026-04-15", "WORK"),
            _entry("2026-04-15", "WORK"),
            _entry("2026-04-15", "FINANCE", "food", "Lunch ₹150"),
        ]
        result = stats.compute_stats(entries)
        assert result["by_category"] == {"WORK": 2, "FINANCE": 1}
        assert result["total_entries"] == 3

    def test_finance_total_and_breakdown(self):
        entries = [
            _entry("2026-04-15", "FINANCE", "food", "Lunch ₹150"),
            _entry("2026-04-15", "FINANCE", "food", "Snack ₹50"),
            _entry("2026-04-15", "FINANCE", "transport", "Auto ₹100"),
        ]
        result = stats.compute_stats(entries)["finance"]
        assert result["total"] == 300.0
        assert result["by_subcategory"]["food"] == 200.0
        assert result["by_subcategory"]["transport"] == 100.0

    def test_finance_top_expenses_sorted_desc(self):
        entries = [
            _entry("2026-04-15", "FINANCE", "x", "Spent ₹100"),
            _entry("2026-04-15", "FINANCE", "x", "Spent ₹500"),
            _entry("2026-04-15", "FINANCE", "x", "Spent ₹300"),
        ]
        result = stats.compute_stats(entries)["finance"]["top_expenses"]
        amounts = [e["amount"] for e in result]
        assert amounts == [500.0, 300.0, 100.0]

    def test_finance_top_expenses_capped_at_5(self):
        entries = [
            _entry("2026-04-15", "FINANCE", "x", f"Spent ₹{i*100}") for i in range(1, 11)
        ]
        result = stats.compute_stats(entries)["finance"]["top_expenses"]
        assert len(result) == 5

    def test_finance_skips_unparseable(self):
        entries = [
            _entry("2026-04-15", "FINANCE", "x", "Need to budget more"),  # no number
            _entry("2026-04-15", "FINANCE", "x", "Spent ₹100"),
        ]
        assert stats.compute_stats(entries)["finance"]["total"] == 100.0

    def test_habit_streaks(self):
        entries = [
            _entry("2026-04-13", "HABITS", "exercise", "Gym 30m"),
            _entry("2026-04-14", "HABITS", "exercise", "Gym 45m"),
            _entry("2026-04-15", "HABITS", "exercise", "Gym 60m"),
            _entry("2026-04-13", "HABITS", "sleep", "8hr"),  # one-off
        ]
        result = stats.compute_stats(entries)["habits"]
        assert result["streaks"]["exercise"] == 3
        assert result["streaks"]["sleep"] == 1
        assert result["by_subcategory"]["exercise"] == 3

    def test_mood_distribution(self):
        entries = [
            _entry("2026-04-15", "WORK", mood="satisfied"),
            _entry("2026-04-15", "PERSONAL", mood="happy"),
            _entry("2026-04-15", "WORK", mood="satisfied"),
            _entry("2026-04-15", "FINANCE", "x", "Spent ₹100", mood=""),
        ]
        result = stats.compute_stats(entries)["moods"]
        assert result == {"satisfied": 2, "happy": 1}

    def test_first_last_dates(self):
        entries = [
            _entry("2026-04-17", "WORK"),
            _entry("2026-04-13", "WORK"),
            _entry("2026-04-15", "WORK"),
        ]
        result = stats.compute_stats(entries)
        assert result["first_date"] == "2026-04-13"
        assert result["last_date"] == "2026-04-17"
        assert result["days_with_entries"] == 3


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_empty_message(self):
        out = stats.render_text(stats.compute_stats([]))
        assert "No entries" in out

    def test_includes_period_and_finance(self):
        entries = [
            _entry("2026-04-15", "FINANCE", "food", "Lunch ₹150"),
            _entry("2026-04-16", "WORK", "coding", "Refactor"),
        ]
        out = stats.render_text(stats.compute_stats(entries))
        assert "2 entries across 2 day(s)" in out
        assert "FINANCE" in out
        assert "WORK" in out
        assert "₹150" in out

    def test_skips_finance_section_when_no_amounts(self):
        entries = [_entry("2026-04-15", "WORK", "coding", "Refactor")]
        out = stats.render_text(stats.compute_stats(entries))
        assert "Finance" not in out
        assert "WORK" in out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n"
        "## [WORK]\n- [10:00 AM] [WORK/coding] Worked on dhaara  *(mood: focused)*\n\n"
        "## [PERSONAL]\n\n"
        "## [HABITS]\n- [7:00 AM] [HABITS/exercise] Gym 45 mins\n\n"
        "## [FINANCE]\n- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch\n"
    )
    (j / "2026-04-16.md").write_text(
        "# 2026-04-16 Journal\n\n"
        "## [WORK]\n\n## [PERSONAL]\n\n## [HABITS]\n"
        "- [7:00 AM] [HABITS/exercise] Gym 30 mins\n\n"
        "## [FINANCE]\n- [9:00 AM] [FINANCE/food] Coffee ₹80\n"
    )
    return j


class TestCli:
    def test_text_default(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = stats.main(["--data-dir", str(journal_dir.parent)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "5 entries" in out
        assert "FINANCE" in out
        assert "₹230" in out  # 150 + 80

    def test_json_output(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = stats.main(["--data-dir", str(journal_dir.parent), "-f", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_entries"] == 5
        assert payload["finance"]["total"] == 230.0
        assert payload["habits"]["streaks"]["exercise"] == 2

    def test_category_filter(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = stats.main([
            "--data-dir", str(journal_dir.parent),
            "--category", "FINANCE",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_entries"] == 2
        assert set(payload["by_category"]) == {"FINANCE"}

    def test_rejects_bad_category(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            stats.main(["--data-dir", str(journal_dir.parent), "--category", "BOGUS"])

    def test_rejects_inverted_range(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            stats.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
