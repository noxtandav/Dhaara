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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
