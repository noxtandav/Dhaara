#!/usr/bin/env python3
"""
GitHub-contribution-style activity heatmap for your Dhaara journal.

Tells you, at a glance:
  - Which days you journaled (and how much)
  - Your longest streak and current streak
  - Your most active day
  - Days you missed

Reuses `export_journal.parse_day_file` + `collect_entries`.

Three output formats:

    text      ANSI grid: rows = ISO weeks (Mon-Sun), cells use bar
              characters bucketed by entry count.
    markdown  Same grid as a markdown table — paste-able into a
              journal note or weekly review.
    json      Structured payload for piping into a notebook / dashboard.

Examples
--------
  # Default: last 12 weeks (~84 days)
  python scripts/activity_heatmap.py

  # Last year
  python scripts/activity_heatmap.py --since 1y

  # Specific range, markdown for embedding
  python scripts/activity_heatmap.py --from 2026-01-01 --to 2026-04-30 -f markdown
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    Entry,
    collect_entries,
    parse_since,
    resolve_data_dir,
)

# Five-tier bucketing à la GitHub's contribution graph.
#   0       no entries
#   1-2     light activity
#   3-5     moderate
#   6-9     active
#   10-14   busy
#   15+     very busy
_BUCKETS: list[tuple[int, str]] = [
    (0, "."),
    (2, "▁"),
    (5, "▃"),
    (9, "▅"),
    (14, "▆"),
]
_TOP_BAR = "▇"

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _bucket(count: int) -> str:
    if count <= 0:
        return "."
    for threshold, char in _BUCKETS:
        if 0 < count <= threshold:
            return char
    return _TOP_BAR


def _week_start(d: date) -> date:
    """Return the Monday of the ISO week that contains `d`."""
    return d - timedelta(days=d.weekday())


def build_calendar(entries: list[Entry], start: date, end: date) -> dict:
    """Aggregate entries by day and compute streak / consistency stats."""
    counts: Counter[date] = Counter()
    for e in entries:
        counts[date.fromisoformat(e.date)] += 1

    span_days = (end - start).days + 1
    days = [start + timedelta(days=i) for i in range(span_days)]

    # Streak math: walk the range chronologically, reset on zero days.
    longest = 0
    run = 0
    for d in days:
        if counts.get(d, 0) > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    # Current streak ends at `end`. Walk back as long as we have entries.
    current = 0
    cursor = end
    while cursor >= start and counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    active_days = sum(1 for d in days if counts.get(d, 0) > 0)
    total_entries = sum(counts.get(d, 0) for d in days)

    best_day = None
    best_count = 0
    for d in days:
        c = counts.get(d, 0)
        if c > best_count:
            best_count = c
            best_day = d

    # Group days by ISO week (Monday-anchored). This is what render_text
    # and render_markdown both consume.
    weeks: list[dict] = []
    if days:
        first_monday = _week_start(start)
        last_monday = _week_start(end)
        cur = first_monday
        while cur <= last_monday:
            row: dict = {"week_start": cur.isoformat(), "days": [], "total": 0}
            for offset in range(7):
                d = cur + timedelta(days=offset)
                in_range = start <= d <= end
                count = counts.get(d, 0) if in_range else 0
                row["days"].append({
                    "date": d.isoformat(),
                    "count": count,
                    "in_range": in_range,
                })
                row["total"] += count
            weeks.append(row)
            cur += timedelta(days=7)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "span_days": span_days,
        "active_days": active_days,
        "total_entries": total_entries,
        "longest_streak": longest,
        "current_streak": current,
        "best_day": (
            {"date": best_day.isoformat(), "count": best_count} if best_day and best_count else None
        ),
        "weeks": weeks,
    }


def _summary_line(cal: dict) -> str:
    pct = (cal["active_days"] / cal["span_days"] * 100) if cal["span_days"] else 0
    parts = [
        f"{cal['total_entries']} entries across {cal['active_days']}/{cal['span_days']} days "
        f"({pct:.0f}% active)"
    ]
    parts.append(f"longest streak {cal['longest_streak']} days")
    if cal["current_streak"]:
        parts.append(f"current streak {cal['current_streak']} days")
    if cal["best_day"]:
        b = cal["best_day"]
        parts.append(f"best day {b['date']} ({b['count']} entries)")
    return " · ".join(parts)


def render_text(cal: dict) -> str:
    if cal["total_entries"] == 0:
        return f"No entries between {cal['start']} and {cal['end']}.\n"

    lines: list[str] = []
    lines.append(f"Activity calendar: {cal['start']} → {cal['end']}")
    lines.append(_summary_line(cal))
    lines.append("")

    header_cells = "  ".join(name for name in WEEKDAY_NAMES)
    lines.append(f"Week of      {header_cells}   total")
    for week in cal["weeks"]:
        cells = []
        for day in week["days"]:
            char = _bucket(day["count"]) if day["in_range"] else " "
            cells.append(char.center(3))
        lines.append(f"{week['week_start']}   {' '.join(cells)}   {week['total']:>3}")

    lines.append("")
    lines.append(
        "Legend:  . = 0   ▁ 1-2   ▃ 3-5   ▅ 6-9   ▆ 10-14   ▇ 15+"
    )
    return "\n".join(lines) + "\n"


def render_markdown(cal: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Activity calendar: {cal['start']} → {cal['end']}")
    lines.append("")

    if cal["total_entries"] == 0:
        lines.append("_No entries in this period._")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"_{_summary_line(cal)}._")
    lines.append("")

    # Markdown table with one row per week.
    header = "| Week of | " + " | ".join(WEEKDAY_NAMES) + " | total |"
    sep = "|" + "|".join(["---"] * (len(WEEKDAY_NAMES) + 2)) + "|"
    lines.append(header)
    lines.append(sep)
    for week in cal["weeks"]:
        cells = []
        for day in week["days"]:
            cells.append(_bucket(day["count"]) if day["in_range"] else " ")
        lines.append(
            f"| {week['week_start']} | " + " | ".join(cells) + f" | {week['total']} |"
        )

    lines.append("")
    lines.append("**Legend:** `.` = 0  `▁` 1-2  `▃` 3-5  `▅` 6-9  `▆` 10-14  `▇` 15+")
    return "\n".join(lines) + "\n"


def render_json(cal: dict) -> str:
    return json.dumps(cal, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GitHub-contribution-style activity heatmap for your Dhaara journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD (inclusive).")
    parser.add_argument("--to", help="End date YYYY-MM-DD (inclusive). Defaults to today.")
    parser.add_argument(
        "--since",
        help="Relative shortcut: '7d', '4w', '6m', '1y' (overridden by --from). Default = 12 weeks back.",
    )
    parser.add_argument("-f", "--format", choices=["text", "markdown", "json"], default="text")
    args = parser.parse_args(argv)

    today = date.today()
    if args.from_:
        start = date.fromisoformat(args.from_)
    elif args.since:
        start = parse_since(args.since)
    else:
        # 12 weeks of context — wide enough to see streaks, narrow enough
        # to fit a normal terminal without horizontal scroll.
        start = today - timedelta(weeks=12) + timedelta(days=1)

    end: date = date.fromisoformat(args.to) if args.to else today

    if start > end:
        parser.error("start date must be on or before end date")

    data_dir = resolve_data_dir(args.data_dir)
    journal_dir = data_dir / "journal"
    entries = collect_entries(journal_dir, start, end, None)

    print(
        f"info: scanned {len(entries)} entries from {journal_dir} "
        f"({start.isoformat()} → {end.isoformat()})",
        file=sys.stderr,
    )

    calendar = build_calendar(entries, start, end)

    # `--color` was dropped: the grid uses bar characters that read fine on
    # any terminal. Honor NO_COLOR by simply not coloring (we never do).
    _ = os.getenv("NO_COLOR")

    if args.format == "json":
        sys.stdout.write(render_json(calendar))
    elif args.format == "markdown":
        sys.stdout.write(render_markdown(calendar))
    else:
        sys.stdout.write(render_text(calendar))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
