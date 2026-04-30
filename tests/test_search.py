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


# ---------------------------------------------------------------------------
# expand_with_context
# ---------------------------------------------------------------------------

class TestExpandWithContext:
    def test_no_matches_returns_empty(self):
        entries = [_entry("2026-04-15", "WORK", text="x")]
        assert search.expand_with_context(entries, [], n=2) == []

    def test_single_match_n0_returns_one_block_one_entry(self):
        entries = [
            _entry("2026-04-15", "WORK", text="x"),
            _entry("2026-04-15", "WORK", text="match here"),
            _entry("2026-04-15", "WORK", text="y"),
        ]
        match = search.Match(entry=entries[1], spans=[(0, 5)])
        blocks = search.expand_with_context(entries, [match], n=0)
        assert len(blocks) == 1
        assert len(blocks[0]) == 1
        assert blocks[0][0]["is_match"] is True

    def test_n1_pulls_one_before_and_after(self):
        entries = [
            _entry("2026-04-13", "WORK", text="before"),
            _entry("2026-04-14", "WORK", text="match"),
            _entry("2026-04-15", "WORK", text="after"),
            _entry("2026-04-16", "WORK", text="far"),
        ]
        match = search.Match(entry=entries[1], spans=[(0, 5)])
        blocks = search.expand_with_context(entries, [match], n=1)
        assert len(blocks) == 1
        assert [item["entry"].text for item in blocks[0]] == ["before", "match", "after"]
        assert [item["is_match"] for item in blocks[0]] == [False, True, False]

    def test_overlapping_windows_merge(self):
        entries = [_entry("2026-04-13", "WORK", text=str(i)) for i in range(5)]
        # Match at index 1 and index 3, n=1.
        # Windows: 0-2 and 2-4 → overlap at index 2 → single block 0..4.
        m1 = search.Match(entry=entries[1], spans=[(0, 1)])
        m2 = search.Match(entry=entries[3], spans=[(0, 1)])
        blocks = search.expand_with_context(entries, [m1, m2], n=1)
        assert len(blocks) == 1
        assert len(blocks[0]) == 5
        # is_match flags should be [False, True, False, True, False]
        flags = [item["is_match"] for item in blocks[0]]
        assert flags == [False, True, False, True, False]

    def test_non_overlapping_windows_split(self):
        entries = [_entry("2026-04-13", "WORK", text=str(i)) for i in range(10)]
        # Match at indices 1 and 7, n=1. Windows: 0-2 and 6-8 → distinct.
        m1 = search.Match(entry=entries[1], spans=[(0, 1)])
        m2 = search.Match(entry=entries[7], spans=[(0, 1)])
        blocks = search.expand_with_context(entries, [m1, m2], n=1)
        assert len(blocks) == 2
        assert [item["entry"].text for item in blocks[0]] == ["0", "1", "2"]
        assert [item["entry"].text for item in blocks[1]] == ["6", "7", "8"]

    def test_clamps_at_start_and_end(self):
        entries = [_entry("2026-04-13", "WORK", text=str(i)) for i in range(3)]
        # Match at index 0 with n=2: window asks for -2 to 2, but should clamp to 0..2.
        m = search.Match(entry=entries[0], spans=[(0, 1)])
        blocks = search.expand_with_context(entries, [m], n=2)
        assert len(blocks) == 1
        assert len(blocks[0]) == 3  # not 5 (no negative indices)

    def test_spans_preserved_only_on_match_entries(self):
        entries = [
            _entry("2026-04-13", "WORK", text="before"),
            _entry("2026-04-14", "WORK", text="match"),
            _entry("2026-04-15", "WORK", text="after"),
        ]
        match = search.Match(entry=entries[1], spans=[(0, 3)])
        blocks = search.expand_with_context(entries, [match], n=1)
        items = blocks[0]
        assert items[0]["spans"] == []  # context, not a match
        assert items[1]["spans"] == [(0, 3)]  # the match
        assert items[2]["spans"] == []


# ---------------------------------------------------------------------------
# render_text + render_json with blocks
# ---------------------------------------------------------------------------

class TestRenderWithBlocks:
    def _block(self, entries: list, match_indices: set):
        """Helper: build a block dict-list where match_indices are flagged."""
        return [
            {"entry": e, "spans": [(0, 3)] if i in match_indices else [], "is_match": i in match_indices}
            for i, e in enumerate(entries)
        ]

    def test_text_uses_match_marker(self):
        entries = [
            _entry("2026-04-13", "WORK", text="before"),
            _entry("2026-04-14", "WORK", text="match"),
        ]
        match = search.Match(entry=entries[1], spans=[(0, 5)])
        blocks = [self._block(entries, match_indices={1})]
        out = search.render_text([match], use_color=False, blocks=blocks)
        # Match line starts with "▸ ", context lines start with "  "
        lines = [line for line in out.splitlines() if line.startswith(("▸ ", "  "))]
        assert any(line.startswith("▸ ") for line in lines)
        assert any(line.startswith("  ") for line in lines)

    def test_text_inserts_separator_between_blocks(self):
        entries = [_entry("2026-04-13", "WORK", text=f"e{i}") for i in range(2)]
        m1 = search.Match(entry=entries[0], spans=[(0, 1)])
        m2 = search.Match(entry=entries[1], spans=[(0, 1)])
        blocks = [
            self._block([entries[0]], match_indices={0}),
            self._block([entries[1]], match_indices={0}),
        ]
        out = search.render_text([m1, m2], use_color=False, blocks=blocks)
        assert "--" in out

    def test_text_no_blocks_falls_back_to_default_format(self):
        # When blocks is None, format should match the iter-7 layout: no
        # ▸ marker, no -- separator.
        match = search.Match(
            entry=_entry("2026-04-15", "WORK", "coding", text="dhaara"),
            spans=[(0, 6)],
        )
        out = search.render_text([match], use_color=False, blocks=None)
        assert "▸" not in out
        assert "--" not in out

    def test_json_blocks_shape(self):
        entries = [
            _entry("2026-04-13", "WORK", text="before"),
            _entry("2026-04-14", "WORK", text="match"),
        ]
        match = search.Match(entry=entries[1], spans=[(0, 5)])
        blocks = [self._block(entries, match_indices={1})]
        payload = json.loads(search.render_json([match], blocks=blocks))
        # Outer is a list of blocks; each block is a list of records.
        assert isinstance(payload, list)
        assert isinstance(payload[0], list)
        records = payload[0]
        # Both records should carry is_match + match_spans + datetime_iso.
        for r in records:
            assert {"is_match", "match_spans", "datetime_iso"} <= r.keys()
        assert records[0]["is_match"] is False
        assert records[1]["is_match"] is True

    def test_json_blocks_none_falls_back_to_flat(self):
        match = search.Match(
            entry=_entry("2026-04-15", "WORK", "coding", text="x"),
            spans=[(0, 1)],
        )
        payload = json.loads(search.render_json([match], blocks=None))
        # Flat list of records (iteration 7 shape), not nested blocks.
        assert isinstance(payload, list)
        assert isinstance(payload[0], dict)


# ---------------------------------------------------------------------------
# CLI --context
# ---------------------------------------------------------------------------

class TestCliContext:
    @pytest.fixture
    def journal_dir(self, tmp_path: Path) -> Path:
        j = tmp_path / "data" / "journal"
        j.mkdir(parents=True)
        # Build five chronological entries across two days, one of which
        # mentions "needle".
        (j / "2026-04-13.md").write_text(
            "# 2026-04-13 Journal\n\n## [WORK]\n"
            "- [9:00 AM] [WORK/coding] entry one\n"
            "- [10:00 AM] [WORK/coding] entry two\n\n"
            "## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
        )
        (j / "2026-04-14.md").write_text(
            "# 2026-04-14 Journal\n\n## [WORK]\n"
            "- [9:00 AM] [WORK/coding] entry three\n"
            "- [10:00 AM] [WORK/coding] needle target\n"
            "- [11:00 AM] [WORK/coding] entry five\n\n"
            "## [PERSONAL]\n\n## [HABITS]\n\n## [FINANCE]\n"
        )
        return j

    def test_context_zero_unchanged(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "needle",
            "--data-dir", str(journal_dir.parent),
            "--color", "never",
            # no --context
        ])
        assert rc == 0
        out = capsys.readouterr().out
        # No marker, no separator
        assert "▸" not in out
        assert "--\n" not in out
        assert "needle target" in out

    def test_context_one_pulls_neighbors(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "needle",
            "--data-dir", str(journal_dir.parent),
            "--context", "1",
            "--color", "never",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        # Match marked with ▸; context entries are present
        assert "▸ " in out
        assert "entry three" in out  # one before
        assert "entry five" in out   # one after

    def test_context_negative_errors(self, journal_dir: Path):
        with pytest.raises(SystemExit):
            search.main([
                "needle",
                "--data-dir", str(journal_dir.parent),
                "--context", "-1",
            ])

    def test_context_json_emits_blocks(self, journal_dir: Path, capsys: pytest.CaptureFixture):
        rc = search.main([
            "needle",
            "--data-dir", str(journal_dir.parent),
            "--context", "1",
            "-f", "json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # Single block, 3 entries, exactly one is_match
        assert len(payload) == 1
        assert len(payload[0]) == 3
        match_count = sum(1 for r in payload[0] if r["is_match"])
        assert match_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
