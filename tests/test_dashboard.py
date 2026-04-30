"""Tests for scripts/dashboard.py."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import dashboard  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A real-looking data dir with a small but content-rich week of entries."""
    journal = tmp_path / "journal"
    journal.mkdir()
    (journal / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n## [WORK]\n"
        "- [10:00 AM] [WORK/coding] Refactored API  *(mood: focused)*\n\n"
        "## [PERSONAL]\n- [9:00 AM] [PERSONAL/family] Lunch with mom  *(mood: happy)*\n\n"
        "## [HABITS]\n- [7:00 AM] [HABITS/exercise] Gym 45 mins\n\n"
        "## [FINANCE]\n- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch\n"
    )
    (journal / "2026-04-14.md").write_text(
        "# 2026-04-14 Journal\n\n## [WORK]\n"
        "- [10:00 AM] [WORK/coding] More work  *(mood: tired)*\n\n"
        "## [PERSONAL]\n\n"
        "## [HABITS]\n- [7:00 AM] [HABITS/exercise] Gym 30 mins\n\n"
        "## [FINANCE]\n- [9:00 AM] [FINANCE/food] Coffee ₹80\n"
    )
    return tmp_path


@pytest.fixture
def empty_data_dir(tmp_path: Path) -> Path:
    (tmp_path / "journal").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Section builders — each returns a list[str] that can be ""-joined
# ---------------------------------------------------------------------------

class TestSectionStreak:
    def test_active_streak_today(self, tmp_path: Path):
        journal = tmp_path / "journal"
        journal.mkdir()
        for d in ("2026-04-28", "2026-04-29", "2026-04-30"):
            (journal / f"{d}.md").write_text(
                f"# {d} Journal\n\n## [WORK]\n- [9:00 AM] [WORK/x] x\n"
                "## [PERSONAL]\n## [HABITS]\n## [FINANCE]\n"
            )
        out = "\n".join(dashboard.section_streak(tmp_path, today=date(2026, 4, 30)))
        assert "## Streak" in out
        assert "🔥" in out and "3 days" in out
        assert "today" in out

    def test_no_entries_at_all(self, empty_data_dir: Path):
        out = "\n".join(dashboard.section_streak(empty_data_dir, today=date(2026, 4, 30)))
        assert "## Streak" in out
        assert "start today" in out

    def test_broken_streak(self, data_dir: Path):
        out = "\n".join(dashboard.section_streak(data_dir, today=date(2026, 4, 30)))
        assert "## Streak" in out
        assert "No active streak" in out
        assert "Longest streak" in out


class TestSectionToday:
    def test_day_with_entries(self, data_dir: Path):
        out = "\n".join(dashboard.section_today(data_dir, date(2026, 4, 13)))
        assert "Snapshot: 2026-04-13" in out
        assert "Monday" in out
        assert "4 entries" in out
        assert "Spending today" in out
        assert "Moods today" in out

    def test_empty_day(self, data_dir: Path):
        out = "\n".join(dashboard.section_today(data_dir, date(2026, 4, 25)))
        assert "Nothing recorded on this day" in out

    def test_no_finance_no_moods(self, tmp_path: Path):
        journal = tmp_path / "journal"
        journal.mkdir()
        (journal / "2026-04-15.md").write_text(
            "# 2026-04-15 Journal\n\n## [WORK]\n- [9:00 AM] [WORK/x] note\n"
            "## [PERSONAL]\n## [HABITS]\n## [FINANCE]\n"
        )
        out = "\n".join(dashboard.section_today(tmp_path, date(2026, 4, 15)))
        assert "1 entry" in out
        assert "Spending today" not in out
        assert "Moods today" not in out


class TestSectionPeriodSummary:
    def test_with_entries(self):
        stats = {
            "total_entries": 31,
            "days_with_entries": 5,
            "by_category": {"FINANCE": 16, "WORK": 5, "PERSONAL": 5, "HABITS": 5},
        }
        out = "\n".join(dashboard.section_period_summary(stats, span_days=7))
        assert "31 entries across 5 of 7 days" in out
        assert "71% active" in out
        assert "FINANCE" in out and "16 entries" in out

    def test_empty_period(self):
        stats = {"total_entries": 0, "days_with_entries": 0, "by_category": {}}
        out = "\n".join(dashboard.section_period_summary(stats, span_days=7))
        assert "_No entries in this period._" in out

    def test_singular_entry_count(self):
        stats = {
            "total_entries": 1,
            "days_with_entries": 1,
            "by_category": {"WORK": 1},
        }
        out = "\n".join(dashboard.section_period_summary(stats, span_days=7))
        assert "WORK** — 1 entry" in out


class TestSectionFinance:
    def test_renders_total_top_subs_and_expenses(self):
        stats = {
            "finance": {
                "total": 56168.0,
                "by_subcategory": {
                    "medical": 11686.0, "subscriptions": 10948.0,
                    "appliances": 9098.0, "shopping": 8528.0,
                    "travel": 7361.0, "other": 100.0,
                },
                "top_expenses": [
                    {"amount": 10948.0, "date": "2026-04-13", "subcategory": "subs",
                     "text": "Spent ₹10,948 on Claude Monthly plan"},
                ],
            }
        }
        out = "\n".join(dashboard.section_finance(stats))
        assert "Finance — ₹56,168 total" in out
        # Top categories capped at 5
        assert "other" not in out
        assert "Top expenses" in out
        assert "Claude" in out

    def test_empty_when_no_finance(self):
        stats = {"finance": {"total": 0.0, "by_subcategory": {}, "top_expenses": []}}
        assert dashboard.section_finance(stats) == []


class TestSectionHabits:
    def test_renders_habits_with_streaks(self):
        stats = {"habits": {"by_subcategory": {"exercise": 3, "sleep": 1},
                            "streaks": {"exercise": 3, "sleep": 1}}}
        out = "\n".join(dashboard.section_habits(stats))
        assert "exercise** — 3 entries (longest streak: 3 days)" in out
        assert "sleep** — 1 entry (longest streak: 1 day)" in out

    def test_empty(self):
        stats = {"habits": {"by_subcategory": {}, "streaks": {}}}
        assert dashboard.section_habits(stats) == []


class TestSectionMoods:
    def test_distribution_and_timeline(self, data_dir: Path):
        from export_journal import collect_entries
        entries = collect_entries(
            data_dir / "journal", date(2026, 4, 13), date(2026, 4, 14), None,
        )
        stats = {"moods": {"focused": 1, "happy": 1, "tired": 1}}
        out = "\n".join(dashboard.section_moods(
            entries, stats, date(2026, 4, 13), date(2026, 4, 14),
        ))
        assert "Distribution" in out
        assert "focused (1)" in out
        assert "Timeline" in out
        assert "**2026-04-13**" in out

    def test_no_moods_returns_empty(self):
        out = dashboard.section_moods([], {"moods": {}}, date(2026, 4, 1), date(2026, 4, 7))
        assert out == []


class TestSectionNotable:
    def test_caps_at_5_and_sorts_by_date(self):
        from export_journal import Entry
        entries = [
            Entry(date=f"2026-04-{15 - i:02d}", time="9:00 AM", category="WORK",
                  subcategory="x", text=f"thought {i}", mood="reflective")
            for i in range(7)
        ]
        out = "\n".join(dashboard.section_notable(entries))
        notable_lines = [l for l in out.splitlines() if l.startswith("- _(reflective)_")]
        assert len(notable_lines) == 5
        # Sorted by date ascending — first line should mention the earliest date.
        assert "2026-04-09" in notable_lines[0]

    def test_empty_when_no_moods(self):
        from export_journal import Entry
        entries = [Entry(date="2026-04-15", time="9:00 AM", category="WORK",
                         subcategory="", text="quiet", mood="")]
        assert dashboard.section_notable(entries) == []


# ---------------------------------------------------------------------------
# build_dashboard top-level
# ---------------------------------------------------------------------------

class TestBuildDashboard:
    def test_full_document_shape(self, data_dir: Path):
        body = dashboard.build_dashboard(
            data_dir, date(2026, 4, 13), date(2026, 4, 14),
            now=datetime(2026, 4, 30, 14, 30),
        )
        # Title + period subtitle with timestamp
        assert body.startswith("# Dhaara Dashboard")
        assert "2026-04-13 → 2026-04-14" in body
        assert "2026-04-30 14:30" in body
        # Each section heading
        for heading in (
            "## Streak",
            "## Snapshot:",
            "## Period summary",
            "## Activity",
            "## Finance",
            "## Habits",
            "## Moods",
            "## Notable moments",
        ):
            assert heading in body

    def test_section_ordering(self, data_dir: Path):
        body = dashboard.build_dashboard(
            data_dir, date(2026, 4, 13), date(2026, 4, 14),
            now=datetime(2026, 4, 30, 14, 30),
        )
        positions = [
            body.find("## Streak"),
            body.find("## Snapshot"),
            body.find("## Period summary"),
            body.find("## Activity"),
            body.find("## Finance"),
            body.find("## Habits"),
            body.find("## Moods"),
            body.find("## Notable moments"),
        ]
        assert all(p >= 0 for p in positions)
        assert positions == sorted(positions)

    def test_empty_period_drops_optional_sections(self, empty_data_dir: Path):
        body = dashboard.build_dashboard(
            empty_data_dir, date(2026, 4, 1), date(2026, 4, 7),
            now=datetime(2026, 4, 30, 14, 30),
        )
        # Streak section + snapshot + period summary always render.
        assert "## Streak" in body
        assert "## Snapshot:" in body
        assert "## Period summary" in body
        assert "_No entries in this period._" in body
        # Optional sections should not appear when empty.
        assert "## Activity" not in body
        assert "## Finance" not in body
        assert "## Habits" not in body
        assert "## Moods" not in body
        assert "## Notable moments" not in body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_explicit_range_to_stdout(self, data_dir: Path, capsys: pytest.CaptureFixture):
        rc = dashboard.main([
            "--data-dir", str(data_dir),
            "--from", "2026-04-13",
            "--to", "2026-04-14",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("# Dhaara Dashboard")

    def test_writes_to_file(self, data_dir: Path, tmp_path: Path):
        out_path = tmp_path / "nested" / "dash.md"
        rc = dashboard.main([
            "--data-dir", str(data_dir),
            "--from", "2026-04-13",
            "--to", "2026-04-14",
            "-o", str(out_path),
        ])
        assert rc == 0
        assert out_path.exists()
        body = out_path.read_text()
        assert body.startswith("# Dhaara Dashboard")

    def test_default_range_last_7_days(self, data_dir: Path, capsys: pytest.CaptureFixture):
        rc = dashboard.main(["--data-dir", str(data_dir)])
        assert rc == 0
        # Default range ends today; we just sanity-check the dashboard headed correctly.
        assert capsys.readouterr().out.startswith("# Dhaara Dashboard")

    def test_inverted_range_errors(self, data_dir: Path):
        with pytest.raises(SystemExit):
            dashboard.main([
                "--data-dir", str(data_dir),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])

    def test_since_shortcut(self, data_dir: Path, capsys: pytest.CaptureFixture):
        rc = dashboard.main([
            "--data-dir", str(data_dir),
            "--since", "30d",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("# Dhaara Dashboard")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
