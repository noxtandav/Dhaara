"""Tests for scripts/streak.py."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import streak  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_day(journal_dir: Path, day: date, count: int = 1) -> None:
    """Write a journal file with `count` bullet entries on `day`."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    bullets = "\n".join(
        f"- [10:{i:02d} AM] [WORK/coding] entry {i}"
        for i in range(count)
    )
    (journal_dir / f"{day.isoformat()}.md").write_text(
        f"# {day.isoformat()} Journal\n\n## [WORK]\n{bullets}\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
    )


@pytest.fixture
def empty_data_dir(tmp_path: Path) -> Path:
    (tmp_path / "journal").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# compute_streak_info
# ---------------------------------------------------------------------------

class TestComputeStreakInfo:
    def test_no_entries(self, empty_data_dir: Path):
        today = date(2026, 4, 30)
        info = streak.compute_streak_info(empty_data_dir, today=today)
        assert info["current_streak"] == 0
        assert info["longest_streak"] == 0
        assert info["last_entry"] is None
        assert info["days_since_last"] is None
        assert info["total_entries"] == 0

    def test_active_streak_today(self, empty_data_dir: Path):
        today = date(2026, 4, 30)
        for d in (date(2026, 4, 28), date(2026, 4, 29), date(2026, 4, 30)):
            write_day(empty_data_dir / "journal", d)
        info = streak.compute_streak_info(empty_data_dir, today=today)
        assert info["current_streak"] == 3
        assert info["longest_streak"] == 3
        assert info["last_entry"] == "2026-04-30"
        assert info["days_since_last"] == 0

    def test_streak_broken_yesterday(self, empty_data_dir: Path):
        today = date(2026, 4, 30)
        # Last entry on Apr 28 → 2 days ago, no entry today or yesterday.
        for d in (date(2026, 4, 25), date(2026, 4, 26), date(2026, 4, 27), date(2026, 4, 28)):
            write_day(empty_data_dir / "journal", d)
        info = streak.compute_streak_info(empty_data_dir, today=today)
        assert info["current_streak"] == 0
        assert info["longest_streak"] == 4
        assert info["last_entry"] == "2026-04-28"
        assert info["days_since_last"] == 2

    def test_longest_separate_from_current(self, empty_data_dir: Path):
        today = date(2026, 4, 30)
        # Long historical streak, then a gap, then a fresh shorter streak.
        old_streak = [date(2026, 3, 1) + timedelta(days=i) for i in range(7)]
        new_streak = [date(2026, 4, 29), date(2026, 4, 30)]
        for d in old_streak + new_streak:
            write_day(empty_data_dir / "journal", d)
        info = streak.compute_streak_info(empty_data_dir, today=today)
        assert info["longest_streak"] == 7
        assert info["current_streak"] == 2

    def test_only_today_is_one_day_streak(self, empty_data_dir: Path):
        today = date(2026, 4, 30)
        write_day(empty_data_dir / "journal", today)
        info = streak.compute_streak_info(empty_data_dir, today=today)
        assert info["current_streak"] == 1
        assert info["longest_streak"] == 1


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

class TestRenderShort:
    def test_active_streak(self):
        out = streak.render_short({
            "current_streak": 5, "longest_streak": 5, "total_entries": 20,
            "active_days": 5, "last_entry": "2026-04-30", "days_since_last": 0,
        })
        assert "🔥" in out
        assert "5-day streak" in out

    def test_no_entries_yet(self):
        out = streak.render_short({
            "current_streak": 0, "longest_streak": 0, "total_entries": 0,
            "active_days": 0, "last_entry": None, "days_since_last": None,
        })
        assert "No entries yet" in out

    def test_broken_yesterday(self):
        out = streak.render_short({
            "current_streak": 0, "longest_streak": 4, "total_entries": 4,
            "active_days": 4, "last_entry": "2026-04-29", "days_since_last": 1,
        })
        assert "yesterday" in out
        assert "Streak broken" in out

    def test_broken_n_days_ago(self):
        out = streak.render_short({
            "current_streak": 0, "longest_streak": 5, "total_entries": 7,
            "active_days": 5, "last_entry": "2026-04-15", "days_since_last": 15,
        })
        assert "15 days ago" in out


class TestRenderText:
    def test_active_streak_full_block(self):
        out = streak.render_text({
            "current_streak": 5, "longest_streak": 12, "total_entries": 80,
            "active_days": 30, "last_entry": "2026-04-30", "days_since_last": 0,
        })
        assert "Current streak: 5 days" in out
        assert "Longest streak: 12 days" in out
        assert "today" in out
        assert "Total entries:  80 across 30 days" in out

    def test_no_active_streak_still_shows_longest(self):
        out = streak.render_text({
            "current_streak": 0, "longest_streak": 4, "total_entries": 10,
            "active_days": 4, "last_entry": "2026-04-15", "days_since_last": 15,
        })
        assert "No active streak" in out
        assert "Longest streak: 4 days" in out
        assert "15 days ago" in out

    def test_no_entries(self):
        out = streak.render_text({
            "current_streak": 0, "longest_streak": 0, "total_entries": 0,
            "active_days": 0, "last_entry": None, "days_since_last": None,
        })
        assert "No entries yet" in out
        assert "Longest streak" not in out  # don't show 0 longest in cold-start


class TestRenderJsonAndQuiet:
    def test_json_round_trip(self):
        info = {
            "today": "2026-04-30", "current_streak": 5, "longest_streak": 5,
            "total_entries": 20, "active_days": 5, "last_entry": "2026-04-30",
            "days_since_last": 0,
        }
        payload = json.loads(streak.render_json(info))
        assert payload == info

    def test_quiet_just_int_zero(self):
        out = streak.render_quiet({"current_streak": 0})
        assert out.strip() == "0"

    def test_quiet_just_int_nonzero(self):
        out = streak.render_quiet({"current_streak": 7})
        assert out.strip() == "7"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_with_active_streak(tmp_path: Path) -> Path:
    """Set up a 3-day streak ending today (whatever today is), so the CLI
    runs against real `date.today()`. We can't override `today` from the
    CLI, so the fixture has to anchor on it."""
    today = date.today()
    journal = tmp_path / "data" / "journal"
    for offset in (0, 1, 2):
        write_day(journal, today - timedelta(days=offset))
    return tmp_path / "data"


class TestCli:
    def test_short_default(self, journal_with_active_streak: Path, capsys: pytest.CaptureFixture):
        rc = streak.main(["--data-dir", str(journal_with_active_streak)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "🔥" in out and "3-day" in out

    def test_json(self, journal_with_active_streak: Path, capsys: pytest.CaptureFixture):
        rc = streak.main(["--data-dir", str(journal_with_active_streak), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["current_streak"] == 3
        assert payload["last_entry"] == date.today().isoformat()

    def test_text(self, journal_with_active_streak: Path, capsys: pytest.CaptureFixture):
        rc = streak.main(["--data-dir", str(journal_with_active_streak), "--text"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Current streak: 3 days" in out
        assert "today" in out

    def test_quiet(self, journal_with_active_streak: Path, capsys: pytest.CaptureFixture):
        rc = streak.main(["--data-dir", str(journal_with_active_streak), "--quiet"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "3"

    def test_quiet_zero_when_no_entries(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        (tmp_path / "journal").mkdir()
        rc = streak.main(["--data-dir", str(tmp_path), "--quiet"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "0"

    def test_mode_flags_are_mutually_exclusive(self, journal_with_active_streak: Path):
        with pytest.raises(SystemExit):
            streak.main([
                "--data-dir", str(journal_with_active_streak),
                "--json", "--text",
            ])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
