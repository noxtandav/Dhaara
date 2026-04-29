#!/usr/bin/env python3
"""
Search your Dhaara journal — substring or regex, filtered by date,
category, and mood.

Foundation for the Phase 2 RAG roadmap item ("what did I write about
dhaara last month?"). Plain markdown is `grep`-able already, but this
tool understands the entry structure: it filters by parsed metadata
(category, subcategory, mood, date range) and shows results in a
clean per-entry format with ANSI highlighting on a TTY.

Reuses `export_journal.parse_day_file` + `collect_entries`.

Examples
--------
  # Find every entry mentioning "dhaara" in the last 30 days
  python scripts/search.py dhaara --since 30d

  # Case-sensitive regex over WORK entries only
  python scripts/search.py "API\\b" --regex --match-case --category WORK

  # All "anxious" moments in April
  python scripts/search.py --mood anxious --from 2026-04-01 --to 2026-04-30

  # JSON for piping into a script
  python scripts/search.py "claude" -f json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    VALID_CATEGORIES,
    Entry,
    collect_entries,
    parse_since,
    resolve_data_dir,
)

ANSI_BOLD_RED = "\033[1;31m"
ANSI_RESET = "\033[0m"


@dataclass
class Match:
    entry: Entry
    spans: list[tuple[int, int]]  # (start, end) in entry.text


def build_pattern(query: str | None, regex: bool, ignore_case: bool) -> re.Pattern[str] | None:
    """Compile a regex from `query`. Returns None if no query was given."""
    if not query:
        return None
    flags = re.IGNORECASE if ignore_case else 0
    if regex:
        try:
            return re.compile(query, flags)
        except re.error as e:
            raise ValueError(f"invalid regex {query!r}: {e}") from e
    return re.compile(re.escape(query), flags)


def find_matches(
    entries: list[Entry],
    pattern: re.Pattern[str] | None,
    mood: str | None,
) -> list[Match]:
    """Filter and return entries that match the query and mood filter.

    If `pattern` is None, every entry passes the text test (so a
    standalone --mood query returns every mood-bearing entry).
    """
    results: list[Match] = []
    mood_norm = mood.lower() if mood else None
    for e in entries:
        if mood_norm and e.mood.lower() != mood_norm:
            continue
        if pattern is None:
            results.append(Match(entry=e, spans=[]))
            continue
        spans = [(m.start(), m.end()) for m in pattern.finditer(e.text)]
        if spans:
            results.append(Match(entry=e, spans=spans))
    return results


def highlight(text: str, spans: list[tuple[int, int]], use_color: bool) -> str:
    """Wrap each (start, end) span with ANSI bold red if use_color is on."""
    if not spans or not use_color:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        pieces.append(ANSI_BOLD_RED + text[start:end] + ANSI_RESET)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def render_text(matches: list[Match], use_color: bool) -> str:
    if not matches:
        return "No matches.\n"
    lines: list[str] = []
    for match in matches:
        e = match.entry
        tag = f"{e.category}/{e.subcategory}" if e.subcategory else e.category
        body = highlight(e.text, match.spans, use_color)
        mood_suffix = f"  ({e.mood})" if e.mood else ""
        lines.append(f"{e.date} {e.time:>8}  [{tag}]  {body}{mood_suffix}")
    lines.append("")
    lines.append(f"{len(matches)} match(es).")
    return "\n".join(lines) + "\n"


def render_json(matches: list[Match]) -> str:
    payload = []
    for match in matches:
        record = asdict(match.entry)
        record["datetime_iso"] = match.entry.datetime_iso
        record["match_spans"] = [[s, e] for s, e in match.spans]
        payload.append(record)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search your Dhaara journal entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Text or regex to search for. Omit if you only want metadata filters (e.g. --mood).",
    )
    parser.add_argument("--regex", action="store_true", help="Treat query as a regex (default: literal).")
    parser.add_argument(
        "--match-case",
        action="store_true",
        help="Case-sensitive match (default: case-insensitive).",
    )
    parser.add_argument(
        "--category",
        help=f"Limit to one category ({sorted(VALID_CATEGORIES)}).",
    )
    parser.add_argument("--mood", help="Limit to entries with exactly this mood (case-insensitive).")
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD (inclusive).")
    parser.add_argument("--to", help="End date YYYY-MM-DD (inclusive).")
    parser.add_argument("--since", help="Relative shortcut: '7d', '4w', '6m', or YYYY-MM-DD.")
    parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Highlight matches in the text output (default: auto = TTY only).",
    )
    args = parser.parse_args(argv)

    if not args.query and not args.mood:
        parser.error("provide a query, --mood, or both")

    if args.category and args.category.upper() not in VALID_CATEGORIES:
        parser.error(f"--category must be one of {sorted(VALID_CATEGORIES)}")

    try:
        pattern = build_pattern(args.query, args.regex, ignore_case=not args.match_case)
    except ValueError as e:
        parser.error(str(e))

    start: date | None = None
    if args.from_:
        start = date.fromisoformat(args.from_)
    elif args.since:
        start = parse_since(args.since)

    end: date | None = date.fromisoformat(args.to) if args.to else None

    if start and end and start > end:
        parser.error("--from must be on or before --to")

    data_dir = resolve_data_dir(args.data_dir)
    journal_dir = data_dir / "journal"
    entries = collect_entries(journal_dir, start, end, args.category)

    matches = find_matches(entries, pattern, args.mood)

    print(
        f"info: scanned {len(entries)} entries from {journal_dir}",
        file=sys.stderr,
    )

    use_color = (args.color == "always") or (
        args.color == "auto" and sys.stdout.isatty() and os.getenv("NO_COLOR") is None
    )

    if args.format == "json":
        sys.stdout.write(render_json(matches))
    else:
        sys.stdout.write(render_text(matches, use_color))

    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
