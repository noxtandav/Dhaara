"""Tests for scripts/export_journal.py."""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# scripts/ is not a package — load by path so the test file works without
# needing to install the project.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import export_journal  # noqa: E402


SAMPLE_DAY_FILE = """\
# 2026-04-15 Journal

## [WORK]
- [10:32 AM] [WORK/meetings] Standup with team
- [2:15 PM] [WORK/coding] Refactored API  *(mood: satisfied)*

## [PERSONAL]
- [9:00 AM] [PERSONAL/family] Breakfast with family  *(mood: happy)*

## [HABITS]
- [7:00 AM] [HABITS/exercise] Gym 45 mins

## [FINANCE]
- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch
- [6:00 PM] [FINANCE/groceries] Bought vegetables ₹300
"""


@pytest.fixture
def day_file(tmp_path: Path) -> Path:
    path = tmp_path / "2026-04-15.md"
    path.write_text(SAMPLE_DAY_FILE)
    return path


@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    """Build a fake data_dir/journal/ with three day-files."""
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n## [WORK]\n- [9:00 AM] [WORK/coding] Old work\n"
    )
    (j / "2026-04-15.md").write_text(SAMPLE_DAY_FILE)
    (j / "2026-04-17.md").write_text(
        "# 2026-04-17 Journal\n\n## [FINANCE]\n- [12:07 AM] [FINANCE/food] Late dinner\n"
    )
    # A non-day file that should be ignored
    (j / "notes.md").write_text("# random notes\n- [1:00 PM] [WORK/random] should be skipped")
    return j


class TestParseDayFile:
    def test_parses_all_six_entries(self, day_file: Path):
        entries = export_journal.parse_day_file(day_file)
        assert len(entries) == 6

    def test_extracts_date_from_filename(self, day_file: Path):
        entries = export_journal.parse_day_file(day_file)
        assert all(e.date == "2026-04-15" for e in entries)

    def test_splits_category_and_subcategory(self, day_file: Path):
        entries = export_journal.parse_day_file(day_file)
        first = entries[0]
        assert first.category == "WORK"
        assert first.subcategory == "meetings"
        assert first.text == "Standup with team"
        assert first.time == "10:32 AM"

    def test_extracts_mood_when_present(self, day_file: Path):
        entries = export_journal.parse_day_file(day_file)
        moods = {e.text: e.mood for e in entries}
        assert moods["Refactored API"] == "satisfied"
        assert moods["Breakfast with family"] == "happy"
        assert moods["Standup with team"] == ""

    def test_unicode_preserved(self, day_file: Path):
        entries = export_journal.parse_day_file(day_file)
        finance = [e for e in entries if e.category == "FINANCE"]
        assert any("₹150" in e.text for e in finance)

    def test_skips_non_day_files(self, tmp_path: Path):
        bogus = tmp_path / "notes.md"
        bogus.write_text("- [1:00 PM] [WORK/x] should not be parsed")
        assert export_journal.parse_day_file(bogus) == []

    def test_handles_entries_without_subcategory(self, tmp_path: Path):
        path = tmp_path / "2026-04-15.md"
        path.write_text("# 2026-04-15 Journal\n\n## [WORK]\n- [10:00 AM] [WORK] No sub\n")
        entries = export_journal.parse_day_file(path)
        assert len(entries) == 1
        assert entries[0].category == "WORK"
        assert entries[0].subcategory == ""

    def test_skips_section_headers_and_blank_lines(self, day_file: Path):
        entries = export_journal.parse_day_file(day_file)
        # No entry's text should be a section header
        assert all("##" not in e.text for e in entries)


class TestEntryDatetimeIso:
    def test_combines_date_and_12h_time(self):
        e = export_journal.Entry(
            date="2026-04-15", time="2:15 PM", category="WORK",
            subcategory="coding", text="x", mood="",
        )
        assert e.datetime_iso == "2026-04-15T14:15:00"

    def test_handles_midnight(self):
        e = export_journal.Entry(
            date="2026-04-17", time="12:07 AM", category="FINANCE",
            subcategory="food", text="x", mood="",
        )
        assert e.datetime_iso == "2026-04-17T00:07:00"

    def test_handles_noon(self):
        e = export_journal.Entry(
            date="2026-04-17", time="12:04 PM", category="FINANCE",
            subcategory="food", text="x", mood="",
        )
        assert e.datetime_iso == "2026-04-17T12:04:00"

    def test_falls_back_to_date_for_unparseable_time(self):
        e = export_journal.Entry(
            date="2026-04-15", time="garbage", category="WORK",
            subcategory="", text="x", mood="",
        )
        assert e.datetime_iso == "2026-04-15"


class TestParseSince:
    def test_days(self):
        assert export_journal.parse_since("7d") == date.today() - timedelta(days=7)

    def test_weeks(self):
        assert export_journal.parse_since("4w") == date.today() - timedelta(days=28)

    def test_months_treated_as_30_days(self):
        assert export_journal.parse_since("6m") == date.today() - timedelta(days=180)

    def test_absolute_iso_date(self):
        assert export_journal.parse_since("2026-01-15") == date(2026, 1, 15)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            export_journal.parse_since("nonsense")


class TestCollectEntries:
    def test_no_filters_returns_all_entries(self, journal_dir: Path):
        entries = export_journal.collect_entries(journal_dir, None, None, None)
        # 1 (Apr 13) + 6 (Apr 15) + 1 (Apr 17) = 8
        assert len(entries) == 8

    def test_date_range_inclusive(self, journal_dir: Path):
        entries = export_journal.collect_entries(
            journal_dir, date(2026, 4, 15), date(2026, 4, 15), None,
        )
        assert len(entries) == 6
        assert {e.date for e in entries} == {"2026-04-15"}

    def test_start_only(self, journal_dir: Path):
        entries = export_journal.collect_entries(
            journal_dir, date(2026, 4, 15), None, None,
        )
        assert {e.date for e in entries} == {"2026-04-15", "2026-04-17"}

    def test_end_only(self, journal_dir: Path):
        entries = export_journal.collect_entries(
            journal_dir, None, date(2026, 4, 15), None,
        )
        assert {e.date for e in entries} == {"2026-04-13", "2026-04-15"}

    def test_category_filter(self, journal_dir: Path):
        entries = export_journal.collect_entries(journal_dir, None, None, "FINANCE")
        assert len(entries) == 3  # 2 from Apr 15 + 1 from Apr 17
        assert all(e.category == "FINANCE" for e in entries)

    def test_category_filter_case_insensitive(self, journal_dir: Path):
        entries = export_journal.collect_entries(journal_dir, None, None, "finance")
        assert all(e.category == "FINANCE" for e in entries)

    def test_missing_journal_dir_raises_systemexit(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            export_journal.collect_entries(tmp_path / "nope", None, None, None)

    def test_skips_non_day_files(self, journal_dir: Path):
        entries = export_journal.collect_entries(journal_dir, None, None, None)
        assert all("should be skipped" not in e.text for e in entries)


class TestWriteCsv:
    def test_header_and_rows(self, journal_dir: Path):
        entries = export_journal.collect_entries(
            journal_dir, date(2026, 4, 15), date(2026, 4, 15), "FINANCE",
        )
        buf = io.StringIO()
        export_journal.write_csv(entries, buf)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        assert rows[0] == ["date", "time", "datetime_iso", "category", "subcategory", "text", "mood"]
        assert len(rows) == 3  # header + 2 finance entries on Apr 15
        assert all(r[3] == "FINANCE" for r in rows[1:])


class TestWriteJson:
    def test_emits_valid_json_array(self, journal_dir: Path):
        entries = export_journal.collect_entries(
            journal_dir, date(2026, 4, 15), date(2026, 4, 15), "FINANCE",
        )
        buf = io.StringIO()
        export_journal.write_json(entries, buf)
        payload = json.loads(buf.getvalue())
        assert isinstance(payload, list)
        assert len(payload) == 2
        for record in payload:
            assert set(record.keys()) >= {
                "date", "time", "category", "subcategory", "text", "mood", "datetime_iso",
            }


class TestMainCli:
    def test_cli_csv_to_stdout(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = export_journal.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-15",
            "--to", "2026-04-15",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("date,time,datetime_iso")
        assert "Standup with team" in out

    def test_cli_json_to_file(self, journal_dir: Path, tmp_path: Path):
        out_path = tmp_path / "out.json"
        rc = export_journal.main([
            "--data-dir", str(journal_dir.parent),
            "--category", "FINANCE",
            "-f", "json",
            "-o", str(out_path),
        ])
        assert rc == 0
        payload = json.loads(out_path.read_text())
        assert all(r["category"] == "FINANCE" for r in payload)

    def test_cli_rejects_unknown_category(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            export_journal.main([
                "--data-dir", str(journal_dir.parent),
                "--category", "BOGUS",
            ])

    def test_cli_rejects_inverted_range(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            export_journal.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
