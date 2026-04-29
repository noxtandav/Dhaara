"""Tests for scripts/search.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import search  # noqa: E402
from export_journal import Entry  # noqa: E402


# ---------------------------------------------------------------------------
# build_pattern
# ---------------------------------------------------------------------------

class TestBuildPattern:
    def test_none_query_returns_none(self):
        assert search.build_pattern(None, regex=False, ignore_case=True) is None
        assert search.build_pattern("", regex=False, ignore_case=True) is None

    def test_literal_substring_default(self):
        pat = search.build_pattern("API.refactor", regex=False, ignore_case=True)
        # The dot must be treated literally since regex=False.
        assert pat.search("Refactored API.refactor module")
        assert not pat.search("Refactored APIxrefactor module")

    def test_regex_treated_as_pattern(self):
        pat = search.build_pattern(r"API\b", regex=True, ignore_case=True)
        assert pat.search("Worked on API today")
        assert not pat.search("APItitan")

    def test_ignore_case_default(self):
        pat = search.build_pattern("dhaara", regex=False, ignore_case=True)
        assert pat.search("Dhaara is great")

    def test_match_case(self):
        pat = search.build_pattern("dhaara", regex=False, ignore_case=False)
        assert not pat.search("Dhaara is great")
        assert pat.search("just dhaara")

    def test_invalid_regex_raises(self):
        with pytest.raises(ValueError):
            search.build_pattern("(unclosed", regex=True, ignore_case=False)


# ---------------------------------------------------------------------------
# find_matches
# ---------------------------------------------------------------------------

def _entry(d: str, cat: str, sub: str = "", text: str = "x", mood: str = "", time: str = "9:00 AM") -> Entry:
    return Entry(date=d, time=time, category=cat, subcategory=sub, text=text, mood=mood)


class TestFindMatches:
    def test_pattern_only(self):
        entries = [
            _entry("2026-04-15", "WORK", text="Worked on dhaara"),
            _entry("2026-04-15", "WORK", text="Standup meeting"),
            _entry("2026-04-15", "WORK", text="More dhaara work"),
        ]
        pat = search.build_pattern("dhaara", regex=False, ignore_case=True)
        matches = search.find_matches(entries, pat, mood=None)
        assert len(matches) == 2
        assert all(m.spans for m in matches)

    def test_no_query_returns_all_when_no_mood(self):
        entries = [_entry("2026-04-15", "WORK"), _entry("2026-04-16", "WORK")]
        matches = search.find_matches(entries, pattern=None, mood=None)
        assert len(matches) == 2
        assert all(m.spans == [] for m in matches)

    def test_mood_filter_alone(self):
        entries = [
            _entry("2026-04-15", "WORK", mood="happy"),
            _entry("2026-04-15", "WORK", mood="sad"),
            _entry("2026-04-15", "WORK"),  # no mood
            _entry("2026-04-15", "WORK", mood="HAPPY"),  # different case
        ]
        matches = search.find_matches(entries, pattern=None, mood="happy")
        assert len(matches) == 2  # case-insensitive match

    def test_pattern_and_mood_combined(self):
        entries = [
            _entry("2026-04-15", "WORK", text="dhaara work", mood="focused"),
            _entry("2026-04-16", "WORK", text="dhaara work", mood="tired"),
            _entry("2026-04-17", "WORK", text="other work", mood="focused"),
        ]
        pat = search.build_pattern("dhaara", regex=False, ignore_case=True)
        matches = search.find_matches(entries, pat, mood="focused")
        assert len(matches) == 1
        assert matches[0].entry.date == "2026-04-15"

    def test_multiple_spans_in_one_entry(self):
        entries = [_entry("2026-04-15", "WORK", text="dhaara, dhaara, and more dhaara")]
        pat = search.build_pattern("dhaara", regex=False, ignore_case=True)
        matches = search.find_matches(entries, pat, mood=None)
        assert len(matches[0].spans) == 3


# ---------------------------------------------------------------------------
# highlight
# ---------------------------------------------------------------------------

class TestHighlight:
    def test_no_color_returns_text(self):
        out = search.highlight("hello world", [(0, 5)], use_color=False)
        assert out == "hello world"

    def test_no_spans_returns_text(self):
        out = search.highlight("hello", [], use_color=True)
        assert out == "hello"

    def test_wraps_each_span_with_ansi(self):
        out = search.highlight("foo bar foo", [(0, 3), (8, 11)], use_color=True)
        assert out.count(search.ANSI_BOLD_RED) == 2
        assert out.count(search.ANSI_RESET) == 2
        assert "foo" in out

    def test_spans_in_order_only(self):
        # Implementation assumes non-overlapping ascending spans.
        out = search.highlight("abcdef", [(0, 2), (4, 6)], use_color=True)
        assert out.startswith(search.ANSI_BOLD_RED + "ab" + search.ANSI_RESET)
        assert out.endswith(search.ANSI_BOLD_RED + "ef" + search.ANSI_RESET)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_empty_returns_no_matches(self):
        out = search.render_text([], use_color=False)
        assert "No matches" in out

    def test_includes_metadata_line(self):
        match = search.Match(
            entry=_entry("2026-04-15", "WORK", "coding", "Refactored", mood="focused", time="2:15 PM"),
            spans=[(0, 10)],
        )
        out = search.render_text([match], use_color=False)
        assert "2026-04-15" in out
        assert "2:15 PM" in out
        assert "[WORK/coding]" in out
        assert "(focused)" in out
        assert "1 match(es)" in out

    def test_no_subcategory_no_slash(self):
        match = search.Match(
            entry=_entry("2026-04-15", "WORK", text="x"),
            spans=[],
        )
        out = search.render_text([match], use_color=False)
        assert "[WORK]" in out
        assert "[WORK/]" not in out


class TestRenderJson:
    def test_records_include_match_spans_and_iso(self):
        match = search.Match(
            entry=_entry("2026-04-15", "WORK", "coding", "Hello world"),
            spans=[(0, 5)],
        )
        payload = json.loads(search.render_json([match]))
        assert payload[0]["text"] == "Hello world"
        assert payload[0]["match_spans"] == [[0, 5]]
        assert payload[0]["datetime_iso"].startswith("2026-04-15T")

    def test_empty_list(self):
        assert json.loads(search.render_json([])) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    j = tmp_path / "data" / "journal"
    j.mkdir(parents=True)
    (j / "2026-04-13.md").write_text(
        "# 2026-04-13 Journal\n\n"
        "## [WORK]\n- [10:00 AM] [WORK/coding] Worked on dhaara today  *(mood: focused)*\n\n"
        "## [PERSONAL]\n- [9:00 AM] [PERSONAL/family] Lunch with mom\n\n"
        "## [HABITS]\n\n## [FINANCE]\n"
    )
    (j / "2026-04-15.md").write_text(
        "# 2026-04-15 Journal\n\n"
        "## [WORK]\n- [9:00 AM] [WORK/meetings] Standup  *(mood: tired)*\n\n"
        "## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
        "- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch\n"
    )
    return j


class TestCli:
    def test_substring_match(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "dhaara",
            "--data-dir", str(journal_dir.parent),
            "--color", "never",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Worked on dhaara today" in out
        assert "1 match(es)" in out

    def test_no_results_returns_one(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "nonexistent-token-xyz",
            "--data-dir", str(journal_dir.parent),
            "--color", "never",
        ])
        assert rc == 1
        out = capsys.readouterr().out
        assert "No matches" in out

    def test_mood_only(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "--mood", "tired",
            "--data-dir", str(journal_dir.parent),
            "--color", "never",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Standup" in out
        assert "Worked on dhaara" not in out

    def test_category_filter(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "lunch",
            "--data-dir", str(journal_dir.parent),
            "--category", "FINANCE",
            "--color", "never",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Spent ₹150 on lunch" in out
        assert "Lunch with mom" not in out  # PERSONAL filtered out

    def test_regex_match(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            r"^Stand",
            "--regex",
            "--data-dir", str(journal_dir.parent),
            "--color", "never",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Standup" in out

    def test_match_case(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "Dhaara",  # capital D
            "--match-case",
            "--data-dir", str(journal_dir.parent),
            "--color", "never",
        ])
        # Real entry is lowercase "dhaara" — case-sensitive search misses.
        assert rc == 1
        assert "No matches" in capsys.readouterr().out

    def test_json_output(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "dhaara",
            "--data-dir", str(journal_dir.parent),
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        assert payload[0]["match_spans"]

    def test_color_always_emits_ansi(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "dhaara",
            "--data-dir", str(journal_dir.parent),
            "--color", "always",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert search.ANSI_BOLD_RED in out
        assert search.ANSI_RESET in out

    def test_requires_query_or_mood(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            search.main(["--data-dir", str(journal_dir.parent)])

    def test_invalid_regex_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            search.main([
                "(unclosed",
                "--regex",
                "--data-dir", str(journal_dir.parent),
            ])

    def test_invalid_category_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            search.main([
                "x",
                "--data-dir", str(journal_dir.parent),
                "--category", "BOGUS",
            ])

    def test_inverted_range_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            search.main([
                "x",
                "--data-dir", str(journal_dir.parent),
                "--from", "2026-04-20",
                "--to", "2026-04-10",
            ])

    def test_date_range_filter(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "dhaara",
            "--data-dir", str(journal_dir.parent),
            "--from", "2026-04-15",
            "--to", "2026-04-30",
            "--color", "never",
        ])
        # The "dhaara" entry is on 2026-04-13, outside the range.
        assert rc == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
