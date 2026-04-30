"""Tests for scripts/mood_timeline.py."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import mood_timeline  # noqa: E402
from export_journal import Entry  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(d: str, mood: str = "", text: str = "x", cat: str = "PERSONAL") -> Entry:
    return Entry(
        date=d, time="9:00 AM", category=cat, subcategory="",
        text=text, mood=mood,
    )


# ---------------------------------------------------------------------------
# build_timeline
# ---------------------------------------------------------------------------

class TestBuildTimeline:
    def test_empty_entries(self):
        out = mood_timeline.build_timeline([], date(2026, 4, 1), date(2026, 4, 7))
        assert out["moods"] == []
        assert out["totals"] == {}
        assert len(out["days"]) == 7  # Apr 1 to Apr 7 inclusive

    def test_skips_entries_without_mood(self):
        entries = [
            _entry("2026-04-15", mood=""),
            _entry("2026-04-15", mood="happy"),
        ]
        out = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        assert out["moods"] == ["happy"]
        assert out["totals"] == {"happy": 1}

    def test_groups_by_day(self):
        entries = [
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-16", mood="happy"),
        ]
        out = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 16))
        assert out["matrix"]["happy"]["2026-04-15"] == 2
        assert out["matrix"]["happy"]["2026-04-16"] == 1

    def test_sorts_moods_by_total_desc(self):
        entries = [
            _entry("2026-04-15", mood="rare"),
            _entry("2026-04-15", mood="common"),
            _entry("2026-04-16", mood="common"),
            _entry("2026-04-17", mood="common"),
        ]
        out = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 17))
        assert out["moods"] == ["common", "rare"]

    def test_alphabetical_tiebreak(self):
        entries = [
            _entry("2026-04-15", mood="zebra"),
            _entry("2026-04-15", mood="alpha"),
            _entry("2026-04-15", mood="beta"),
        ]
        out = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        assert out["moods"] == ["alpha", "beta", "zebra"]

    def test_days_list_covers_full_range(self):
        out = mood_timeline.build_timeline([], date(2026, 4, 1), date(2026, 4, 30))
        assert len(out["days"]) == 30
        assert out["days"][0] == "2026-04-01"
        assert out["days"][-1] == "2026-04-30"


# ---------------------------------------------------------------------------
# _bar
# ---------------------------------------------------------------------------

class TestBar:
    def test_zero_returns_dot(self):
        assert mood_timeline._bar(0) == "."

    def test_negative_returns_dot(self):
        assert mood_timeline._bar(-1) == "."

    def test_one_returns_first_bar(self):
        assert mood_timeline._bar(1) == mood_timeline._BARS[0]

    def test_eight_returns_top_bar(self):
        assert mood_timeline._bar(8) == mood_timeline._BARS[-1]

    def test_above_eight_saturates(self):
        assert mood_timeline._bar(50) == mood_timeline._BARS[-1]

    def test_three_returns_third_bar(self):
        assert mood_timeline._bar(3) == mood_timeline._BARS[2]


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_empty_moods_message(self):
        timeline = mood_timeline.build_timeline([], date(2026, 4, 1), date(2026, 4, 7))
        out = mood_timeline.render_text(timeline)
        assert "No mood-bearing entries" in out

    def test_includes_header_and_legend(self):
        entries = [_entry("2026-04-15", mood="happy")]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        out = mood_timeline.render_text(timeline)
        assert "Mood timeline" in out
        assert "Legend" in out
        assert "happy" in out

    def test_uses_short_date_for_long_ranges(self):
        entries = [_entry("2026-04-15", mood="happy")]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 1), date(2026, 4, 30))
        out = mood_timeline.render_text(timeline)
        # MM-DD format kicks in for >7 day ranges
        assert "04-15" in out
        # Should NOT include 2026 in the column headers (only in the title line)
        # Count occurrences: title says "2026-04-01 → 2026-04-30", that's 2.
        assert out.count("2026") == 2

    def test_uses_full_date_for_short_ranges(self):
        entries = [_entry("2026-04-15", mood="happy")]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 13), date(2026, 4, 15))
        out = mood_timeline.render_text(timeline)
        # YYYY-MM-DD format used; column header "2026-04-13" appears.
        assert "2026-04-13" in out

    def test_color_adds_ansi(self):
        entries = [_entry("2026-04-15", mood="happy")]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        plain = mood_timeline.render_text(timeline, use_color=False)
        colored = mood_timeline.render_text(timeline, use_color=True)
        assert "\033[1m" in colored
        assert "\033[1m" not in plain

    def test_total_in_row(self):
        entries = [
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-16", mood="happy"),
        ]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 16))
        out = mood_timeline.render_text(timeline)
        assert "(3)" in out


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_empty_moods_renders_message(self):
        timeline = mood_timeline.build_timeline([], date(2026, 4, 1), date(2026, 4, 7))
        out = mood_timeline.render_markdown(timeline)
        assert "No mood-bearing entries" in out

    def test_per_day_bullets(self):
        entries = [
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-15", mood="anxious"),
            _entry("2026-04-17", mood="happy"),
        ]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 17))
        out = mood_timeline.render_markdown(timeline)
        # Two days have entries — Apr 15 (happy + anxious) and Apr 17 (happy)
        assert "**2026-04-15**" in out
        assert "**2026-04-17**" in out
        # Apr 16 had no moods, should not appear as a bullet
        assert "**2026-04-16**" not in out

    def test_count_marker_for_repeats(self):
        entries = [
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-15", mood="happy"),
            _entry("2026-04-15", mood="anxious"),
        ]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        out = mood_timeline.render_markdown(timeline)
        # "happy ×2" expected; "anxious" without ×marker
        assert "happy ×2" in out
        assert "anxious" in out
        assert "anxious ×" not in out  # only when count > 1

    def test_includes_totals_section(self):
        entries = [_entry("2026-04-15", mood="happy")]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        out = mood_timeline.render_markdown(timeline)
        assert "## Totals" in out
        assert "happy: 1" in out


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------

class TestRenderJson:
    def test_round_trips(self):
        entries = [_entry("2026-04-15", mood="happy")]
        timeline = mood_timeline.build_timeline(entries, date(2026, 4, 15), date(2026, 4, 15))
        payload = json.loads(mood_timeline.render_json(timeline))
        assert payload["moods"] == ["happy"]
        assert payload["totals"] == {"happy": 1}
        assert payload["days"] == ["2026-04-15"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n## [WORK]\n\n## [PERSONAL]\n"
        "- [10:00 AM] [PERSONAL/family] Lunch with mom  *(mood: happy)*\n"
        "- [11:00 AM] [PERSONAL/health] Tired afternoon  *(mood: tired)*\n\n"
        "## [HABITS]\n\n## [FINANCE]\n"
    )
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n## [WORK]\n"
        "- [10:00 AM] [WORK/coding] Refactored API  *(mood: focused)*\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
    )
    return j


class TestCli:
    def test_text_default(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = mood_timeline.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-15",
            "--color", "never",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Mood timeline" in out
        assert "happy" in out
        assert "focused" in out

    def test_markdown_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = mood_timeline.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-15",
            "-f", "markdown",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("# Mood timeline")
        assert "**2026-04-13**" in out
        assert "## Totals" in out

    def test_json_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = mood_timeline.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-13",
            "--to", "2026-04-15",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert set(payload["moods"]) == {"happy", "tired", "focused"}
        assert payload["totals"]["happy"] == 1

    def test_default_range_is_30_days(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = mood_timeline.main([
            "--data-dir", str(journal_dir.parent),
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["days"]) == 30

    def test_inverted_range_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            mood_timeline.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])

    def test_since_shortcut(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = mood_timeline.main([
            "--data-dir", str(journal_dir.parent),
            "--since", "7d",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["days"]) == 8  # 7 days + today inclusive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
