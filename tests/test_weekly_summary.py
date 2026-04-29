"""Tests for scripts/weekly_summary.py."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import weekly_summary  # noqa: E402
from export_journal import Entry  # noqa: E402


# ---------------------------------------------------------------------------
# parse_iso_week
# ---------------------------------------------------------------------------

class TestParseIsoWeek:
    def test_valid_week(self):
        # W16 of 2026 starts Monday 2026-04-13.
        start, end = weekly_summary.parse_iso_week("2026-W16")
        assert start == date(2026, 4, 13)
        assert end == date(2026, 4, 19)

    def test_single_digit_week(self):
        start, end = weekly_summary.parse_iso_week("2026-W1")
        assert start == date(2025, 12, 29)  # ISO W1 may start in prior year
        assert end == date(2026, 1, 4)

    def test_w53_in_long_year(self):
        # 2020 has 53 ISO weeks.
        start, end = weekly_summary.parse_iso_week("2020-W53")
        assert start == date(2020, 12, 28)
        assert end == date(2021, 1, 3)

    @pytest.mark.parametrize("bad", ["", "2026", "2026-17", "W16", "2026W16"])
    def test_rejects_malformed(self, bad: str):
        with pytest.raises(ValueError):
            weekly_summary.parse_iso_week(bad)

    @pytest.mark.parametrize("bad_week", ["2026-W0", "2026-W54", "2026-W99"])
    def test_rejects_out_of_range_week(self, bad_week: str):
        with pytest.raises(ValueError):
            weekly_summary.parse_iso_week(bad_week)


# ---------------------------------------------------------------------------
# truncate
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_text_unchanged(self):
        assert weekly_summary.truncate("hello", 100) == "hello"

    def test_long_text_truncated_with_ellipsis(self):
        result = weekly_summary.truncate("a" * 50, 10)
        assert result.endswith("…")
        assert len(result) == 10

    def test_exact_length_unchanged(self):
        assert weekly_summary.truncate("abcde", 5) == "abcde"


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

def _entry(d: str, cat: str, sub: str = "", text: str = "x", mood: str = "", time: str = "9:00 AM") -> Entry:
    return Entry(date=d, time=time, category=cat, subcategory=sub, text=text, mood=mood)


class TestRenderMarkdown:
    def test_empty_week(self):
        out = weekly_summary.render_markdown([], date(2026, 4, 13), date(2026, 4, 19))
        assert "Week of 2026-04-13" in out
        assert "No journal entries this week" in out

    def test_header_includes_range(self):
        entries = [_entry("2026-04-15", "WORK")]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert "# Week of 2026-04-13 → 2026-04-19" in out

    def test_active_days_summary(self):
        entries = [
            _entry("2026-04-13", "WORK"),
            _entry("2026-04-15", "WORK"),
            _entry("2026-04-15", "WORK"),  # same day, doesn't double-count
        ]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        # 3 entries, 2 days active out of 7
        assert "3 entries across 2 of 7 days" in out
        assert "29% active" in out  # 2/7

    def test_finance_section_appears_only_when_amounts(self):
        entries = [_entry("2026-04-15", "WORK", "coding", "Refactored API")]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert "## Finance" not in out

    def test_finance_section_renders(self):
        entries = [
            _entry("2026-04-13", "FINANCE", "food", "Spent ₹150 on lunch"),
            _entry("2026-04-14", "FINANCE", "food", "Coffee ₹80"),
            _entry("2026-04-15", "FINANCE", "transport", "Auto ₹100"),
        ]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert "## Finance — ₹330 total" in out
        assert "food: ₹230" in out
        assert "₹150 — Spent ₹150 on lunch" in out

    def test_habit_pluralization(self):
        entries = [
            _entry("2026-04-13", "HABITS", "exercise", "Gym 30m"),
            _entry("2026-04-14", "HABITS", "exercise", "Gym 45m"),
            _entry("2026-04-15", "HABITS", "exercise", "Gym 60m"),
            _entry("2026-04-13", "HABITS", "sleep", "8hr"),
        ]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert "exercise** — 3 entries (longest streak: 3 days)" in out
        assert "sleep** — 1 entry (longest streak: 1 day)" in out

    def test_moods_inline(self):
        entries = [
            _entry("2026-04-13", "WORK", mood="happy"),
            _entry("2026-04-14", "WORK", mood="happy"),
            _entry("2026-04-15", "WORK", mood="tired"),
        ]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert "## Moods this week" in out
        assert "happy (2)" in out
        assert "tired (1)" in out

    def test_notable_moments_capped_at_5(self):
        entries = [
            _entry(f"2026-04-{13 + i:02d}", "WORK", text=f"thought {i}", mood="reflective")
            for i in range(7)
        ]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        notable_lines = [l for l in out.splitlines() if l.startswith("- _(reflective)_")]
        assert len(notable_lines) == 5

    def test_notable_moments_only_with_mood(self):
        entries = [
            _entry("2026-04-15", "WORK", text="no mood here"),
            _entry("2026-04-15", "WORK", text="with mood", mood="focused"),
        ]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert "no mood here" not in out  # filtered out of notable section
        assert '_(focused)_ "with mood"' in out

    def test_notable_long_text_truncated(self):
        long_text = "x" * 200
        entries = [_entry("2026-04-15", "WORK", text=long_text, mood="bored")]
        out = weekly_summary.render_markdown(entries, date(2026, 4, 13), date(2026, 4, 19))
        # Should appear truncated with ellipsis
        assert "…" in out
        assert long_text not in out  # full text shouldn't appear


# ---------------------------------------------------------------------------
# default_range
# ---------------------------------------------------------------------------

class TestDefaultRange:
    def test_spans_seven_days_ending_today(self):
        start, end = weekly_summary.default_range()
        assert end == date.today()
        assert (end - start).days == 6


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n"
        "## [WORK]\n- [10:00 AM] [WORK/coding] Refactored module  *(mood: focused)*\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n"
        "- [7:00 AM] [HABITS/exercise] Gym 30 mins\n\n"
        "## [FINANCE]\n- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch\n"
    )
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n"
        "## [WORK]\n- [9:00 AM] [WORK/meetings] Standup\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n\n"
        "## [FINANCE]\n- [9:00 AM] [FINANCE/food] Coffee ₹80\n"
    )
    return j


class TestCli:
    def test_explicit_range(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = weekly_summary.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-19",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Week of 2026-04-13 → 2026-04-19" in out
        assert "₹230" in out  # 150 + 80

    def test_iso_week(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = weekly_summary.main([
            "--data-dir", str(journal_dir.parent),
            "--week", "2026-W16",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Week of 2026-04-13 → 2026-04-19" in out

    def test_iso_week_invalid_format(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            weekly_summary.main([
                "--data-dir", str(journal_dir.parent),
                "--week", "not-a-week",
            ])

    def test_writes_to_file(self, journal_dir: Path, tmp_path: Path):
        out_path = tmp_path / "out" / "weekly.md"
        rc = weekly_summary.main([
            "--data-dir", str(journal_dir.parent),
            "--week", "2026-W16",
            "-o", str(out_path),
        ])
        assert rc == 0
        assert out_path.exists()
        body = out_path.read_text()
        assert body.startswith("# Week of")
        # Parent dir should have been created
        assert out_path.parent.is_dir()

    def test_from_without_to_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            weekly_summary.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-13",
            ])

    def test_inverted_range_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            weekly_summary.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
