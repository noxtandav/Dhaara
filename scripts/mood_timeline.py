#!/usr/bin/env python3
"""
Plot a per-day mood timeline from your Dhaara journal.

The agent already tags each entry with an optional mood. This script
adds the missing time dimension: when did "anxious" appear? Was it a
one-day spike or a sustained pattern? Was last month genuinely darker
than this one, or is it just recall bias?

Three output formats:

    text     ANSI heatmap with bar-char intensity (default; ideal for terminals)
    markdown Per-day bullet list of moods that appeared each day
    json     Structured payload for piping into a notebook / dashboard

Reuses `export_journal.parse_day_file` + `collect_entries`.

Examples
--------
  # Last 30 days, ANSI heatmap
  python scripts/mood_timeline.py

  # Specific range, markdown for a journal note
  python scripts/mood_timeline.py --from 2026-04-01 --to 2026-04-30 -f markdown

  # All-time JSON for a notebook
  python scripts/mood_timeline.py --since 1y -f json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    Entry,
    collect_entries,
    parse_since,
    resolve_data_dir,
)

# Bar characters used in the heatmap. The cell stays empty (".") for zero
# occurrences. Counts above the highest bar saturate at the last symbol.
_BARS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]


def build_timeline(entries: list[Entry], start: date, end: date) -> dict:
    """Aggregate moods by day. Returns a dict shaped for both renderers."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    # mood -> { date_iso -> count }
    by_mood: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mood_totals: Counter[str] = Counter()

    for e in entries:
        if not e.mood:
            continue
        by_mood[e.mood][e.date] += 1
        mood_totals[e.mood] += 1

    # Sort moods by overall frequency (most common first), then alphabetic.
    sorted_moods = [m for m, _ in sorted(
        mood_totals.items(), key=lambda kv: (-kv[1], kv[0])
    )]

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": [d.isoformat() for d in days],
        "moods": sorted_moods,
        "totals": dict(mood_totals),
        "matrix": {m: dict(by_mood[m]) for m in sorted_moods},
    }


def _bar(count: int) -> str:
    """Map a positive integer to a bar character; saturates at the top."""
    if count <= 0:
        return "."
    return _BARS[min(count - 1, len(_BARS) - 1)]


def render_text(timeline: dict, use_color: bool = False) -> str:
    if not timeline["moods"]:
        return f"No mood-bearing entries between {timeline['start']} and {timeline['end']}.\n"

    days: list[str] = timeline["days"]
    moods: list[str] = timeline["moods"]

    # Pick a date label width that fits even the longest range without
    # blowing up the line length.
    label_fmt = "%m-%d" if len(days) > 7 else "%Y-%m-%d"
    headers = [date.fromisoformat(d).strftime(label_fmt) for d in days]
    header_width = len(headers[0])

    label_width = max(len(m) for m in moods)
    label_width = max(label_width, len("Mood"))

    lines: list[str] = []
    span = f"{timeline['start']} → {timeline['end']}"
    total_entries = sum(timeline["totals"].values())
    lines.append(
        f"Mood timeline: {span}  ({len(days)} days, "
        f"{len(moods)} mood{'s' if len(moods) != 1 else ''}, "
        f"{total_entries} mood-tagged entries)"
    )
    lines.append("")

    # Header row
    header_cells = " ".join(h.rjust(header_width) for h in headers)
    lines.append(f"{'Mood'.ljust(label_width)}  {header_cells}    total")

    # Body rows
    bold_on = "\033[1m" if use_color else ""
    bold_off = "\033[0m" if use_color else ""
    for mood in moods:
        cells = []
        per_day = timeline["matrix"][mood]
        for d in days:
            count = per_day.get(d, 0)
            cell = _bar(count)
            cells.append(cell.center(header_width))
        total = timeline["totals"][mood]
        lines.append(
            f"{bold_on}{mood.ljust(label_width)}{bold_off}  "
            f"{' '.join(cells)}  ({total})"
        )

    lines.append("")
    lines.append(f"Legend: . = none   {' '.join(f'{b}={i + 1}' for i, b in enumerate(_BARS[:3]))}   {_BARS[-1]} = 8+")
    return "\n".join(lines) + "\n"


def render_markdown(timeline: dict) -> str:
    days: list[str] = timeline["days"]
    moods: list[str] = timeline["moods"]

    lines: list[str] = []
    span = f"{timeline['start']} → {timeline['end']}"
    lines.append(f"# Mood timeline: {span}")
    lines.append("")

    total_entries = sum(timeline["totals"].values())
    if total_entries == 0:
        lines.append("_No mood-bearing entries in this period._")
        lines.append("")
        return "\n".join(lines)

    lines.append(
        f"_{total_entries} mood-tagged entries across "
        f"{len(moods)} mood{'s' if len(moods) != 1 else ''}._"
    )
    lines.append("")

    # Per-day bullet list. Skips days with no moods so the report stays tight.
    for d in days:
        day_entries: list[str] = []
        for mood in moods:
            count = timeline["matrix"][mood].get(d, 0)
            if count == 0:
                continue
            day_entries.append(f"{mood} ×{count}" if count > 1 else mood)
        if day_entries:
            lines.append(f"- **{d}** — {', '.join(day_entries)}")

    lines.append("")
    lines.append("## Totals")
    for mood in moods:
        lines.append(f"- {mood}: {timeline['totals'][mood]}")

    return "\n".join(lines) + "\n"


def render_json(timeline: dict) -> str:
    return json.dumps(timeline, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plot a per-day mood timeline from your Dhaara journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD (inclusive).")
    parser.add_argument("--to", help="End date YYYY-MM-DD (inclusive). Defaults to today.")
    parser.add_argument(
        "--since",
        help="Relative shortcut: '7d', '4w', '6m', '1y', or YYYY-MM-DD (overridden by --from).",
    )
    parser.add_argument("-f", "--format", choices=["text", "markdown", "json"], default="text")
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Bold mood labels in text output (default: auto = TTY only).",
    )
    args = parser.parse_args(argv)

    # Date range: --from overrides --since; default is last 30 days.
    today = date.today()
    if args.from_:
        start = date.fromisoformat(args.from_)
    elif args.since:
        start = parse_since(args.since)
    else:
        start = today - timedelta(days=29)

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

    timeline = build_timeline(entries, start, end)

    use_color = (args.color == "always") or (
        args.color == "auto" and sys.stdout.isatty() and os.getenv("NO_COLOR") is None
    )

    if args.format == "json":
        sys.stdout.write(render_json(timeline))
    elif args.format == "markdown":
        sys.stdout.write(render_markdown(timeline))
    else:
        sys.stdout.write(render_text(timeline, use_color=use_color))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
