"""Tests for src/journal/formatter.py."""
from datetime import datetime

import pytest

from src.journal.formatter import CATEGORIES, format_day_header, format_entry


class TestFormatEntry:
    def test_basic_entry(self):
        ts = datetime(2026, 4, 15, 10, 32)
        result = format_entry("Standup with team", ts, "WORK")
        assert result == "- [10:32 AM] [WORK] Standup with team"

    def test_with_subcategory(self):
        ts = datetime(2026, 4, 15, 14, 15)
        result = format_entry("Refactored API", ts, "WORK", subcategory="coding")
        assert result == "- [2:15 PM] [WORK/coding] Refactored API"

    def test_with_mood(self):
        ts = datetime(2026, 4, 15, 23, 0)
        result = format_entry("Couldn't sleep", ts, "PERSONAL", mood="anxious")
        assert result == "- [11:00 PM] [PERSONAL] Couldn't sleep  *(mood: anxious)*"

    def test_with_subcategory_and_mood(self):
        ts = datetime(2026, 4, 15, 9, 0)
        result = format_entry(
            "Breakfast with family", ts, "PERSONAL", subcategory="family", mood="happy"
        )
        assert result == "- [9:00 AM] [PERSONAL/family] Breakfast with family  *(mood: happy)*"

    def test_midnight_uses_12_am(self):
        ts = datetime(2026, 4, 15, 0, 7)
        result = format_entry("Late expense", ts, "FINANCE", subcategory="food")
        assert result.startswith("- [12:07 AM]")

    def test_noon_uses_12_pm(self):
        ts = datetime(2026, 4, 15, 12, 4)
        result = format_entry("Lunch", ts, "FINANCE", subcategory="food")
        assert result.startswith("- [12:04 PM]")

    def test_unicode_text_preserved(self):
        ts = datetime(2026, 4, 15, 13, 30)
        result = format_entry("Spent ₹150 on lunch — दोपहर", ts, "FINANCE", subcategory="food")
        assert "₹150" in result
        assert "दोपहर" in result

    def test_empty_subcategory_treated_as_none(self):
        ts = datetime(2026, 4, 15, 10, 0)
        # subcategory=None → no slash
        result = format_entry("note", ts, "WORK", subcategory=None)
        assert "[WORK]" in result
        assert "/" not in result.split("] ")[1]

    def test_empty_mood_omits_mood_suffix(self):
        ts = datetime(2026, 4, 15, 10, 0)
        result = format_entry("note", ts, "WORK", mood=None)
        assert "*(mood:" not in result


class TestFormatDayHeader:
    def test_includes_date(self):
        result = format_day_header(datetime(2026, 4, 15))
        assert result.startswith("# 2026-04-15 Journal")

    def test_includes_all_four_sections_in_order(self):
        result = format_day_header(datetime(2026, 4, 15))
        # Sections must appear in WORK → PERSONAL → HABITS → FINANCE order
        # because the agent depends on them existing when appending.
        positions = [result.find(f"## [{c}]") for c in CATEGORIES]
        assert all(p >= 0 for p in positions), f"missing section in: {result}"
        assert positions == sorted(positions), "sections out of order"

    def test_trailing_newline(self):
        result = format_day_header(datetime(2026, 4, 15))
        assert result.endswith("\n")


class TestCategories:
    def test_categories_are_fixed_set(self):
        assert CATEGORIES == ["WORK", "PERSONAL", "HABITS", "FINANCE"]

    def test_categories_are_uppercase(self):
        assert all(c.isupper() for c in CATEGORIES)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
