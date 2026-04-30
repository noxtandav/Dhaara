"""Tests for scripts/activity_heatmap.py."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import activity_heatmap as heatmap  # noqa: E402
from export_journal import Entry  # noqa: E402


def _entry(d: str, cat: str = "WORK") -> Entry:
    return Entry(
        date=d, time="9:00 AM", category=cat, subcategory="",
        text="x", mood="",
    )


# ---------------------------------------------------------------------------
# _bucket
# ---------------------------------------------------------------------------

class TestBucket:
    @pytest.mark.parametrize("count,expected", [
        (0, "."),
        (-3, "."),  # defensive
        (1, "▁"),
        (2, "▁"),
        (3, "▃"),
        (5, "▃"),
        (6, "▅"),
        (9, "▅"),
        (10, "▆"),
        (14, "▆"),
        (15, "▇"),
        (50, "▇"),
    ])
    def test_thresholds(self, count: int, expected: str):
        assert heatmap._bucket(count) == expected


# ---------------------------------------------------------------------------
# _week_start
# ---------------------------------------------------------------------------

class TestWeekStart:
    def test_monday_is_self(self):
        assert heatmap._week_start(date(2026, 4, 13)) == date(2026, 4, 13)

    def test_sunday_returns_prior_monday(self):
        # 2026-04-19 is a Sunday; ISO week 16 starts Mon 2026-04-13.
        assert heatmap._week_start(date(2026, 4, 19)) == date(2026, 4, 13)

    def test_wednesday(self):
        assert heatmap._week_start(date(2026, 4, 15)) == date(2026, 4, 13)


# ---------------------------------------------------------------------------
# build_calendar
# ---------------------------------------------------------------------------

class TestBuildCalendar:
    def test_empty_entries(self):
        cal = heatmap.build_calendar([], date(2026, 4, 1), date(2026, 4, 7))
        assert cal["total_entries"] == 0
        assert cal["active_days"] == 0
        assert cal["longest_streak"] == 0
        assert cal["current_streak"] == 0
        assert cal["best_day"] is None

    def test_counts_per_day(self):
        entries = [_entry("2026-04-15"), _entry("2026-04-15"), _entry("2026-04-16")]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        # Find the row for week starting 2026-04-13
        week = next(w for w in cal["weeks"] if w["week_start"] == "2026-04-13")
        days = {d["date"]: d["count"] for d in week["days"]}
        assert days["2026-04-15"] == 2
        assert days["2026-04-16"] == 1
        assert days["2026-04-13"] == 0

    def test_longest_streak(self):
        # Three consecutive days, then a gap, then two consecutive.
        entries = [
            _entry("2026-04-13"),
            _entry("2026-04-14"),
            _entry("2026-04-15"),
            _entry("2026-04-17"),
            _entry("2026-04-18"),
        ]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert cal["longest_streak"] == 3

    def test_current_streak_at_end(self):
        # The last 4 days of the range have entries.
        entries = [_entry(f"2026-04-{d}") for d in (16, 17, 18, 19)]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert cal["current_streak"] == 4

    def test_current_streak_zero_when_last_day_empty(self):
        entries = [_entry("2026-04-13"), _entry("2026-04-14")]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert cal["current_streak"] == 0
        assert cal["longest_streak"] == 2

    def test_best_day(self):
        entries = [
            _entry("2026-04-13"),
            _entry("2026-04-15"),
            _entry("2026-04-15"),
            _entry("2026-04-15"),
            _entry("2026-04-16"),
            _entry("2026-04-16"),
        ]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert cal["best_day"] == {"date": "2026-04-15", "count": 3}

    def test_active_days_count(self):
        entries = [_entry("2026-04-13"), _entry("2026-04-15"), _entry("2026-04-15")]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        assert cal["active_days"] == 2  # two distinct dates
        assert cal["span_days"] == 7

    def test_weeks_anchored_on_monday(self):
        # 2026-04-15 is a Wednesday; its row should start on Mon 2026-04-13.
        cal = heatmap.build_calendar([_entry("2026-04-15")], date(2026, 4, 15), date(2026, 4, 15))
        assert len(cal["weeks"]) == 1
        assert cal["weeks"][0]["week_start"] == "2026-04-13"
        # Mon-Tue should be flagged out-of-range.
        days = cal["weeks"][0]["days"]
        assert days[0]["in_range"] is False  # Mon = 2026-04-13
        assert days[1]["in_range"] is False  # Tue = 2026-04-14
        assert days[2]["in_range"] is True   # Wed = 2026-04-15
        assert days[3]["in_range"] is False  # Thu = 2026-04-16

    def test_total_per_week_sums_in_range_only(self):
        # Range starts mid-week and crosses into next week.
        entries = [
            _entry("2026-04-15"),  # Wed of W16
            _entry("2026-04-15"),
            _entry("2026-04-21"),  # Tue of W17
        ]
        cal = heatmap.build_calendar(entries, date(2026, 4, 15), date(2026, 4, 21))
        totals = {w["week_start"]: w["total"] for w in cal["weeks"]}
        assert totals["2026-04-13"] == 2
        assert totals["2026-04-20"] == 1


# ---------------------------------------------------------------------------
# render_text / render_markdown
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_empty_message(self):
        cal = heatmap.build_calendar([], date(2026, 4, 1), date(2026, 4, 7))
        out = heatmap.render_text(cal)
        assert "No entries between" in out

    def test_includes_summary_and_legend(self):
        entries = [_entry("2026-04-15") for _ in range(3)]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        out = heatmap.render_text(cal)
        assert "Activity calendar" in out
        assert "longest streak" in out
        assert "Legend" in out

    def test_uses_correct_bucket(self):
        # 3 entries on a single day → ▃ bucket.
        entries = [_entry("2026-04-15") for _ in range(3)]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        out = heatmap.render_text(cal)
        assert "▃" in out

    def test_omits_current_streak_when_zero(self):
        entries = [_entry("2026-04-13"), _entry("2026-04-14")]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        out = heatmap.render_text(cal)
        assert "current streak" not in out


class TestRenderMarkdown:
    def test_empty_returns_no_entries(self):
        cal = heatmap.build_calendar([], date(2026, 4, 1), date(2026, 4, 7))
        out = heatmap.render_markdown(cal)
        assert "_No entries in this period._" in out

    def test_table_structure(self):
        entries = [_entry("2026-04-15") for _ in range(3)]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        out = heatmap.render_markdown(cal)
        assert "| Week of |" in out
        assert "| Mon | Tue |" in out
        assert "Legend" in out

    def test_includes_summary_line(self):
        entries = [_entry("2026-04-15"), _entry("2026-04-16")]
        cal = heatmap.build_calendar(entries, date(2026, 4, 13), date(2026, 4, 19))
        out = heatmap.render_markdown(cal)
        assert "2 entries across 2/7 days" in out


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------

class TestRenderJson:
    def test_round_trips(self):
        entries = [_entry("2026-04-15")]
        cal = heatmap.build_calendar(entries, date(2026, 4, 15), date(2026, 4, 15))
        payload = json.loads(heatmap.render_json(cal))
        assert payload["total_entries"] == 1
        assert payload["weeks"][0]["week_start"] == "2026-04-13"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n## [WORK]\n- [10:00 AM] [WORK/coding] x\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
    )
    (j / "2026-04-14.md").write_text(
        "# 2026-04-14 Journal\n\n## [WORK]\n- [10:00 AM] [WORK/coding] y\n"
        "- [11:00 AM] [WORK/meetings] z\n\n## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
    )
    return j


class TestCli:
    def test_text_default(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = heatmap.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-19",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Activity calendar" in out
        assert "3 entries across 2/7 days" in out

    def test_markdown_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = heatmap.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-19",
            "-f", "markdown",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("# Activity calendar")
        assert "| Week of |" in out

    def test_json_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = heatmap.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-19",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_entries"] == 3
        assert payload["active_days"] == 2

    def test_default_range_is_12_weeks(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = heatmap.main([
            "--data-dir", str(journal_dir.parent),
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # 12 weeks back from today = 84 days (today inclusive) - 1 = 83-day span +1
        # The exact span depends on today's date; just sanity-check it's >=80 and <=85.
        assert 80 <= payload["span_days"] <= 85

    def test_inverted_range_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            heatmap.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])

    def test_since_shortcut(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = heatmap.main([
            "--data-dir", str(journal_dir.parent),
            "--since", "30d",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["span_days"] == 31  # 30 days + today


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
