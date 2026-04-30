"""Tests for scripts/today.py."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import today  # noqa: E402
from export_journal import Entry  # noqa: E402


def _entry(time: str, cat: str, sub: str = "", text: str = "x", mood: str = "") -> Entry:
    return Entry(
        date="2026-04-15", time=time, category=cat, subcategory=sub,
        text=text, mood=mood,
    )


# ---------------------------------------------------------------------------
# _parse_time
# ---------------------------------------------------------------------------

class TestParseTime:
    @pytest.mark.parametrize("text,expected", [
        ("9:00 AM", 9 * 60),
        ("12:00 AM", 0),
        ("12:30 PM", 12 * 60 + 30),
        ("11:59 PM", 23 * 60 + 59),
        ("2:15 PM", 14 * 60 + 15),
    ])
    def test_known_times(self, text: str, expected: int):
        assert today._parse_time(text) == expected

    def test_garbage_returns_zero(self):
        assert today._parse_time("garbage") == 0


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_empty_entries(self):
        report = today.build_report([], date(2026, 4, 30))
        assert report["date"] == "2026-04-30"
        assert report["dow"] == "Thursday"
        assert report["total_entries"] == 0
        assert report["by_category"] == {}
        assert report["finance_total"] == 0.0
        assert report["moods"] == []

    def test_groups_by_category_in_canonical_order(self):
        entries = [
            _entry("9:00 AM", "FINANCE", "food", "Lunch ₹150"),
            _entry("8:00 AM", "WORK", "coding", "Refactor"),
        ]
        report = today.build_report(entries, date(2026, 4, 15))
        # WORK should come before FINANCE in dict key order.
        assert list(report["by_category"]) == ["WORK", "FINANCE"]

    def test_orders_entries_within_category_by_time(self):
        entries = [
            _entry("2:15 PM", "WORK", text="afternoon"),
            _entry("9:00 AM", "WORK", text="morning"),
        ]
        report = today.build_report(entries, date(2026, 4, 15))
        work = report["by_category"]["WORK"]
        assert work[0]["text"] == "morning"
        assert work[1]["text"] == "afternoon"

    def test_finance_subtotal(self):
        entries = [
            _entry("9:00 AM", "FINANCE", "food", "Spent ₹150 on lunch"),
            _entry("1:00 PM", "FINANCE", "transport", "Auto ₹100"),
            _entry("3:00 PM", "FINANCE", "x", "no number here"),
        ]
        report = today.build_report(entries, date(2026, 4, 15))
        assert report["finance_total"] == 250.0

    def test_unique_moods_in_first_seen_order(self):
        entries = [
            _entry("9:00 AM", "WORK", mood="focused"),
            _entry("10:00 AM", "WORK", mood="happy"),
            _entry("11:00 AM", "WORK", mood="focused"),  # duplicate
        ]
        report = today.build_report(entries, date(2026, 4, 15))
        assert report["moods"] == ["focused", "happy"]

    def test_unknown_category_falls_through(self):
        entries = [_entry("9:00 AM", "REFLECT", text="meta")]
        report = today.build_report(entries, date(2026, 4, 15))
        assert "REFLECT" in report["by_category"]


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_empty_message(self):
        report = today.build_report([], date(2026, 4, 30))
        out = today.render_text(report, [])
        assert "Nothing recorded yet" in out
        assert "Thursday" in out

    def test_header_includes_date_and_dow_and_count(self):
        entries = [_entry("9:00 AM", "WORK", text="morning")]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_text(report, entries)
        assert "2026-04-15" in out
        assert "Wednesday" in out
        assert "1 entry" in out

    def test_singular_vs_plural_count(self):
        # 1 entry → "1 entry"
        entries = [_entry("9:00 AM", "WORK")]
        report = today.build_report(entries, date(2026, 4, 15))
        assert "1 entry" in today.render_text(report, entries)
        # 2 entries → "2 entries"
        entries.append(_entry("10:00 AM", "WORK"))
        report = today.build_report(entries, date(2026, 4, 15))
        assert "2 entries" in today.render_text(report, entries)

    def test_finance_subtotal_in_header(self):
        entries = [_entry("9:00 AM", "FINANCE", "food", "Spent ₹150 on lunch")]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_text(report, entries)
        assert "FINANCE (1) — ₹150 today" in out

    def test_omits_finance_subtotal_when_zero(self):
        entries = [_entry("9:00 AM", "FINANCE", "x", "no amount mentioned")]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_text(report, entries)
        # Section header still shows count but not the total line
        assert "FINANCE (1)" in out
        assert "₹" not in out  # no rupee sign anywhere

    def test_moods_line_at_bottom(self):
        entries = [
            _entry("9:00 AM", "WORK", mood="focused"),
            _entry("11:00 AM", "WORK", mood="happy"),
        ]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_text(report, entries)
        assert "Moods today: focused, happy" in out

    def test_no_mood_message_when_empty(self):
        entries = [_entry("9:00 AM", "WORK", text="quiet day")]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_text(report, entries)
        assert "(no moods tagged)" in out

    def test_empty_subcategory_doesnt_show_brackets(self):
        entries = [_entry("9:00 AM", "WORK", sub="", text="bare")]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_text(report, entries)
        assert "[]" not in out


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_empty_message(self):
        report = today.build_report([], date(2026, 4, 30))
        out = today.render_markdown(report, [])
        assert "_Nothing recorded yet._" in out
        assert "# 2026-04-30" in out

    def test_full_structure(self):
        entries = [
            _entry("9:00 AM", "WORK", "coding", "Refactor", mood="focused"),
            _entry("1:30 PM", "FINANCE", "food", "Spent ₹150 on lunch"),
        ]
        report = today.build_report(entries, date(2026, 4, 15))
        out = today.render_markdown(report, entries)
        assert "# 2026-04-15 (Wednesday)" in out
        assert "## WORK (1)" in out
        assert "## FINANCE (1) — ₹150" in out
        assert "**9:00 AM** `coding` Refactor *(focused)*" in out
        assert "**Moods today**: focused" in out


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------

class TestRenderJson:
    def test_round_trips(self):
        entries = [_entry("9:00 AM", "WORK", "coding", "Refactor", mood="focused")]
        report = today.build_report(entries, date(2026, 4, 15))
        payload = json.loads(today.render_json(report))
        assert payload["date"] == "2026-04-15"
        assert payload["dow"] == "Wednesday"
        assert payload["total_entries"] == 1
        assert payload["moods"] == ["focused"]
        assert "WORK" in payload["by_category"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n## [WORK]\n"
        "- [9:00 AM] [WORK/coding] Refactored API  *(mood: focused)*\n"
        "- [2:15 PM] [WORK/meetings] Standup\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n\n"
        "## [FINANCE]\n- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch\n"
    )
    return j


class TestCli:
    def test_text_default(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(journal_dir.parent),
            "--date", "2026-04-15",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "📓 2026-04-15" in out
        assert "WORK (2)" in out
        assert "FINANCE (1) — ₹150" in out

    def test_markdown_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(journal_dir.parent),
            "--date", "2026-04-15",
            "-f", "markdown",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("# 2026-04-15")
        assert "## WORK (2)" in out

    def test_json_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(journal_dir.parent),
            "--date", "2026-04-15",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_entries"] == 3
        assert payload["finance_total"] == 150.0

    def test_missing_day_file(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(journal_dir.parent),
            "--date", "2099-12-31",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Nothing recorded yet" in out

    def test_invalid_date_string(self, journal_dir: Path):
        with pytest.raises(ValueError):
            today.main([
                "--data-dir", str(journal_dir.parent),
                "--date", "not-a-date",
            ])


# ---------------------------------------------------------------------------
# find_last_entry_on_or_before
# ---------------------------------------------------------------------------

@pytest.fixture
def data_dir_with_entries(tmp_path: Path) -> Path:
    j = tmp_path / "journal"
    j.mkdir()
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n## [WORK]\n"
        "- [10:00 AM] [WORK/coding] morning work\n"
        "- [4:30 PM] [WORK/meetings] afternoon meeting\n\n"
        "## [PERSONAL]\n## [HABITS]\n## [FINANCE]\n"
    )
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n## [WORK]\n\n"
        "## [PERSONAL]\n- [9:30 PM] [PERSONAL/family] evening note\n\n"
        "## [HABITS]\n## [FINANCE]\n"
    )
    return tmp_path


class TestFindLastEntry:
    def test_returns_most_recent_overall(self, data_dir_with_entries: Path):
        last = today.find_last_entry_on_or_before(
            data_dir_with_entries, date(2026, 4, 30)
        )
        assert last is not None
        assert last.date == "2026-04-15"
        assert last.time == "9:30 PM"

    def test_picks_latest_time_within_a_day(self, data_dir_with_entries: Path):
        # Limit to 2026-04-13 — should return the 4:30 PM entry, not the 10 AM one.
        last = today.find_last_entry_on_or_before(
            data_dir_with_entries, date(2026, 4, 13)
        )
        assert last is not None
        assert last.date == "2026-04-13"
        assert last.time == "4:30 PM"

    def test_returns_none_when_no_entries(self, tmp_path: Path):
        (tmp_path / "journal").mkdir()
        assert today.find_last_entry_on_or_before(tmp_path, date(2026, 4, 30)) is None

    def test_returns_none_when_journal_dir_missing(self, tmp_path: Path):
        assert today.find_last_entry_on_or_before(tmp_path, date(2026, 4, 30)) is None

    def test_excludes_entries_after_target(self, data_dir_with_entries: Path):
        # Target before 2026-04-15 — should not find the Apr 15 entry.
        last = today.find_last_entry_on_or_before(
            data_dir_with_entries, date(2026, 4, 14)
        )
        assert last is not None
        assert last.date == "2026-04-13"


# ---------------------------------------------------------------------------
# _format_gap
# ---------------------------------------------------------------------------

class TestFormatGap:
    def test_same_day(self):
        assert today._format_gap(date(2026, 4, 30), "2026-04-30") == "today"

    def test_yesterday(self):
        assert today._format_gap(date(2026, 4, 30), "2026-04-29") == "yesterday"

    def test_n_days(self):
        assert today._format_gap(date(2026, 4, 30), "2026-04-15") == "15 days ago"

    def test_zero_for_future_date(self):
        # Defensive: if last_entry is somehow after target, don't say "-1 days ago"
        assert today._format_gap(date(2026, 4, 15), "2026-04-30") == "today"


# ---------------------------------------------------------------------------
# build_report.last_entry
# ---------------------------------------------------------------------------

class TestBuildReportLastEntry:
    def test_no_last_entry_when_target_has_entries(self):
        # Even if last_entry is provided, it should not appear when target has entries.
        from export_journal import Entry
        last = Entry(
            date="2026-04-10", time="9:00 AM", category="WORK",
            subcategory="x", text="prior", mood="",
        )
        report = today.build_report(
            [_entry("9:00 AM", "WORK", text="now")],
            date(2026, 4, 15), last_entry=last,
        )
        assert report["last_entry"] is None

    def test_no_last_entry_when_none_passed(self):
        report = today.build_report([], date(2026, 4, 30))
        assert report["last_entry"] is None

    def test_last_entry_populated_when_empty_target(self):
        from export_journal import Entry
        last = Entry(
            date="2026-04-17", time="12:04 PM", category="FINANCE",
            subcategory="maintenance", text="x", mood="",
        )
        report = today.build_report([], date(2026, 4, 30), last_entry=last)
        assert report["last_entry"] == {
            "date": "2026-04-17",
            "time": "12:04 PM",
            "category": "FINANCE",
            "subcategory": "maintenance",
            "gap": "13 days ago",
        }


# ---------------------------------------------------------------------------
# Renderers — empty path with last_entry
# ---------------------------------------------------------------------------

class TestEmptyDayRenderingWithLastEntry:
    def _empty_report(self, target: date, last_entry: dict | None) -> dict:
        return {
            "date": target.isoformat(),
            "dow": target.strftime("%A"),
            "total_entries": 0,
            "by_category": {},
            "finance_total": 0.0,
            "moods": [],
            "last_entry": last_entry,
        }

    def test_text_no_prior_entries_message(self):
        out = today.render_text(self._empty_report(date(2026, 4, 30), None), [])
        assert "Nothing recorded yet" in out
        assert "No journal entries yet anywhere" in out

    def test_text_includes_gap_when_last_known(self):
        last = {
            "date": "2026-04-17", "time": "12:04 PM",
            "category": "FINANCE", "subcategory": "x",
            "gap": "13 days ago",
        }
        out = today.render_text(self._empty_report(date(2026, 4, 30), last), [])
        assert "Nothing recorded yet" in out
        assert "Last entry: 13 days ago" in out
        assert "2026-04-17" in out
        assert "12:04 PM" in out

    def test_markdown_no_prior_entries(self):
        out = today.render_markdown(self._empty_report(date(2026, 4, 30), None), [])
        assert "_Nothing recorded yet._" in out
        assert "No journal entries yet anywhere" in out

    def test_markdown_includes_gap_line(self):
        last = {
            "date": "2026-04-17", "time": "12:04 PM",
            "category": "FINANCE", "subcategory": "x",
            "gap": "13 days ago",
        }
        out = today.render_markdown(self._empty_report(date(2026, 4, 30), last), [])
        assert "_Nothing recorded yet._" in out
        assert "_Last entry: 13 days ago" in out
        assert "`2026-04-17`" in out


# ---------------------------------------------------------------------------
# CLI — empty-day nudge integration
# ---------------------------------------------------------------------------

class TestCliEmptyDayNudge:
    def test_empty_day_with_prior_history(self, data_dir_with_entries: Path,
                                          capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(data_dir_with_entries),
            "--date", "2026-04-30",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Nothing recorded yet" in out
        assert "Last entry: 15 days ago" in out
        assert "2026-04-15" in out

    def test_empty_day_with_no_prior_history(self, tmp_path: Path,
                                             capsys: pytest.CaptureFixture):
        (tmp_path / "journal").mkdir()
        rc = today.main([
            "--data-dir", str(tmp_path),
            "--date", "2026-04-30",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Nothing recorded yet" in out
        assert "No journal entries yet anywhere" in out

    def test_active_day_unchanged(self, data_dir_with_entries: Path,
                                  capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(data_dir_with_entries),
            "--date", "2026-04-13",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        # Active day should NOT include the "Last entry: X days ago" hint
        # (the entry times in the body already convey the same info).
        assert "Last entry:" not in out

    def test_json_includes_last_entry_struct(self, data_dir_with_entries: Path,
                                             capsys: pytest.CaptureFixture):
        rc = today.main([
            "--data-dir", str(data_dir_with_entries),
            "--date", "2026-04-30",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["last_entry"]["date"] == "2026-04-15"
        assert payload["last_entry"]["gap"] == "15 days ago"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
