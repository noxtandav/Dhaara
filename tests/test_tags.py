"""Tests for scripts/tags.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import tags  # noqa: E402
from export_journal import Entry  # noqa: E402


def _entry(date: str, cat: str, sub: str = "", mood: str = "", text: str = "x") -> Entry:
    return Entry(
        date=date, time="9:00 AM", category=cat, subcategory=sub,
        text=text, mood=mood,
    )


# ---------------------------------------------------------------------------
# build_inventory
# ---------------------------------------------------------------------------

class TestBuildInventory:
    def test_empty_input(self):
        inv = tags.build_inventory([])
        assert inv["total_entries"] == 0
        assert inv["days_with_entries"] == 0
        assert inv["first_date"] is None
        assert inv["last_date"] is None
        assert inv["by_category"] == {}
        assert inv["moods"] == []

    def test_period_summary_dates(self):
        entries = [
            _entry("2026-04-13", "WORK"),
            _entry("2026-04-15", "WORK"),
            _entry("2026-04-15", "WORK"),  # same day, doesn't double-count
        ]
        inv = tags.build_inventory(entries)
        assert inv["total_entries"] == 3
        assert inv["days_with_entries"] == 2
        assert inv["first_date"] == "2026-04-13"
        assert inv["last_date"] == "2026-04-15"

    def test_subcategory_count_and_last_date(self):
        entries = [
            _entry("2026-04-13", "WORK", sub="coding"),
            _entry("2026-04-15", "WORK", sub="coding"),
            _entry("2026-04-14", "WORK", sub="coding"),
            _entry("2026-04-13", "WORK", sub="meetings"),
        ]
        inv = tags.build_inventory(entries)
        coding = next(r for r in inv["by_category"]["WORK"]["subcategories"] if r.name == "coding")
        meetings = next(r for r in inv["by_category"]["WORK"]["subcategories"] if r.name == "meetings")
        assert coding.count == 3
        assert coding.last_date == "2026-04-15"  # latest
        assert meetings.count == 1
        assert meetings.last_date == "2026-04-13"

    def test_subcategory_sort_count_desc_then_alpha(self):
        entries = [
            _entry("2026-04-13", "WORK", sub="zebra"),
            _entry("2026-04-13", "WORK", sub="alpha"),
            _entry("2026-04-13", "WORK", sub="alpha"),
            _entry("2026-04-13", "WORK", sub="beta"),
            _entry("2026-04-13", "WORK", sub="beta"),
        ]
        inv = tags.build_inventory(entries)
        names = [r.name for r in inv["by_category"]["WORK"]["subcategories"]]
        # Counts: alpha=2, beta=2, zebra=1. Tie → alphabetical.
        assert names == ["alpha", "beta", "zebra"]

    def test_empty_subcategory_falls_back_to_none(self):
        entries = [_entry("2026-04-13", "WORK", sub="")]
        inv = tags.build_inventory(entries)
        rows = inv["by_category"]["WORK"]["subcategories"]
        assert rows[0].name == "(none)"

    def test_categories_can_share_subcategory_names(self):
        # `food` legitimately appears under FINANCE (cost), HABITS (what
        # I ate), and PERSONAL (a meal experience) — they should be
        # tracked independently per category.
        entries = [
            _entry("2026-04-13", "FINANCE", sub="food"),
            _entry("2026-04-13", "FINANCE", sub="food"),
            _entry("2026-04-13", "HABITS", sub="food"),
            _entry("2026-04-14", "PERSONAL", sub="food"),
        ]
        inv = tags.build_inventory(entries)
        finance_food = next(r for r in inv["by_category"]["FINANCE"]["subcategories"] if r.name == "food")
        habits_food = next(r for r in inv["by_category"]["HABITS"]["subcategories"] if r.name == "food")
        personal_food = next(r for r in inv["by_category"]["PERSONAL"]["subcategories"] if r.name == "food")
        assert finance_food.count == 2
        assert habits_food.count == 1
        assert personal_food.count == 1

    def test_category_totals(self):
        entries = [
            _entry("2026-04-13", "FINANCE", sub="food"),
            _entry("2026-04-13", "FINANCE", sub="food"),
            _entry("2026-04-13", "FINANCE", sub="transport"),
            _entry("2026-04-13", "WORK", sub="coding"),
        ]
        inv = tags.build_inventory(entries)
        assert inv["by_category"]["FINANCE"]["total_entries"] == 3
        assert inv["by_category"]["WORK"]["total_entries"] == 1

    def test_mood_aggregation(self):
        entries = [
            _entry("2026-04-13", "WORK", mood="happy"),
            _entry("2026-04-15", "WORK", mood="happy"),
            _entry("2026-04-14", "PERSONAL", mood="anxious"),
            _entry("2026-04-13", "WORK"),  # no mood, ignored
        ]
        inv = tags.build_inventory(entries)
        moods = {r.name: r for r in inv["moods"]}
        assert moods["happy"].count == 2
        assert moods["happy"].last_date == "2026-04-15"
        assert moods["anxious"].count == 1
        assert "" not in moods  # empty mood not tracked

    def test_mood_sort_count_desc_then_alpha(self):
        entries = [
            _entry("2026-04-13", "WORK", mood="zoo"),
            _entry("2026-04-13", "WORK", mood="apple"),
            _entry("2026-04-13", "WORK", mood="apple"),
            _entry("2026-04-13", "WORK", mood="banana"),
            _entry("2026-04-13", "WORK", mood="banana"),
        ]
        inv = tags.build_inventory(entries)
        names = [r.name for r in inv["moods"]]
        assert names == ["apple", "banana", "zoo"]

    def test_unknown_categories_pass_through(self):
        # CATEGORY_ORDER lists WORK/PERSONAL/HABITS/FINANCE; anything else
        # should still be aggregated, just sorted after the canonical four
        # in the renderer.
        entries = [_entry("2026-04-13", "REFLECT", sub="meta")]
        inv = tags.build_inventory(entries)
        assert "REFLECT" in inv["by_category"]


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_empty_message(self):
        out = tags.render_text(tags.build_inventory([]))
        assert "No entries" in out

    def test_includes_header(self):
        entries = [_entry("2026-04-13", "WORK", sub="coding")]
        out = tags.render_text(tags.build_inventory(entries))
        assert "Tag inventory" in out
        assert "1 entries across 1 day(s)" in out
        assert "(2026-04-13 → 2026-04-13)" in out

    def test_canonical_category_order(self):
        # Build entries mixed up, expect WORK→PERSONAL→HABITS→FINANCE order.
        entries = [
            _entry("2026-04-13", "FINANCE", sub="food"),
            _entry("2026-04-13", "WORK", sub="coding"),
            _entry("2026-04-13", "PERSONAL", sub="family"),
            _entry("2026-04-13", "HABITS", sub="exercise"),
        ]
        out = tags.render_text(tags.build_inventory(entries))
        positions = [
            out.find("WORK ("),
            out.find("PERSONAL ("),
            out.find("HABITS ("),
            out.find("FINANCE ("),
        ]
        assert all(p >= 0 for p in positions)
        assert positions == sorted(positions)

    def test_singular_vs_plural_subcategory_count(self):
        e_one = [_entry("2026-04-13", "WORK", sub="coding")]
        e_many = [
            _entry("2026-04-13", "WORK", sub="coding"),
            _entry("2026-04-13", "WORK", sub="meetings"),
        ]
        assert "1 subcategory" in tags.render_text(tags.build_inventory(e_one))
        assert "2 subcategories" in tags.render_text(tags.build_inventory(e_many))

    def test_singular_vs_plural_entry_count(self):
        e_one = [_entry("2026-04-13", "WORK", sub="coding")]
        e_many = [
            _entry("2026-04-13", "WORK", sub="coding"),
            _entry("2026-04-13", "WORK", sub="coding"),
        ]
        out_one = tags.render_text(tags.build_inventory(e_one))
        out_many = tags.render_text(tags.build_inventory(e_many))
        # In single-line form: "  coding    1 entry  (last: ...)"
        assert "1 entry " in out_one
        assert "2 entries" in out_many

    def test_no_moods_message(self):
        entries = [_entry("2026-04-13", "WORK", sub="coding")]
        out = tags.render_text(tags.build_inventory(entries))
        assert "## Moods" in out
        assert "(no moods tagged in this range)" in out

    def test_mood_section_with_data(self):
        entries = [
            _entry("2026-04-13", "WORK", mood="focused"),
            _entry("2026-04-13", "WORK", mood="focused"),
            _entry("2026-04-13", "WORK", mood="happy"),
        ]
        out = tags.render_text(tags.build_inventory(entries))
        assert "## Moods (2 distinct)" in out
        assert "focused" in out
        assert "happy" in out


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------

class TestRenderJson:
    def test_round_trip_shape(self):
        entries = [
            _entry("2026-04-13", "WORK", sub="coding", mood="focused"),
            _entry("2026-04-15", "FINANCE", sub="food", mood="happy"),
        ]
        payload = json.loads(tags.render_json(tags.build_inventory(entries)))
        assert payload["total_entries"] == 2
        assert payload["days_with_entries"] == 2
        assert payload["first_date"] == "2026-04-13"
        assert payload["last_date"] == "2026-04-15"
        # subcategories serialized as plain dicts.
        coding = payload["by_category"]["WORK"]["subcategories"][0]
        assert coding == {
            "name": "coding", "count": 1, "last_date": "2026-04-13",
        }
        # moods preserved.
        mood_names = [m["name"] for m in payload["moods"]]
        assert set(mood_names) == {"focused", "happy"}

    def test_empty_round_trip(self):
        payload = json.loads(tags.render_json(tags.build_inventory([])))
        assert payload["total_entries"] == 0
        assert payload["by_category"] == {}
        assert payload["moods"] == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n## [WORK]\n"
        "- [10:00 AM] [WORK/coding] one\n"
        "- [11:00 AM] [WORK/meetings] two\n\n"
        "## [PERSONAL]\n- [9:00 AM] [PERSONAL/family] mom  *(mood: happy)*\n\n"
        "## [HABITS]\n## [FINANCE]\n"
    )
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n## [WORK]\n"
        "- [10:00 AM] [WORK/coding] three  *(mood: focused)*\n\n"
        "## [PERSONAL]\n## [HABITS]\n## [FINANCE]\n"
        "- [1:30 PM] [FINANCE/food] lunch\n"
    )
    return j


class TestCli:
    def test_text_default(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = tags.main(["--data-dir", str(journal_dir.parent)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Tag inventory" in out
        assert "WORK" in out
        assert "coding" in out
        assert "## Moods" in out

    def test_json_format(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = tags.main(["--data-dir", str(journal_dir.parent), "-f", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # Apr 13: 3 entries (WORK x2 + PERSONAL x1); Apr 15: 2 entries
        # (WORK x1 + FINANCE x1). Total: 5.
        assert payload["total_entries"] == 5
        assert payload["by_category"]["WORK"]["total_entries"] == 3

    def test_since_filter(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        # Range starts 2026-04-15 → only the Apr 15 entries should land.
        rc = tags.main([
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-15",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total_entries"] == 2  # Apr 15 has 2 entries
        # WORK/coding still appears (Apr 15), but WORK/meetings (Apr 13) shouldn't.
        work_subs = [r["name"] for r in payload["by_category"]["WORK"]["subcategories"]]
        assert "coding" in work_subs
        assert "meetings" not in work_subs

    def test_inverted_range_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            tags.main([
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
