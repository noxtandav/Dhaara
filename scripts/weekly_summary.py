#!/usr/bin/env python3
"""
Generate a Markdown "week in review" digest from your Dhaara journal.

Reuses the parser from `export_journal.py` and the rollups from `stats.py`,
then renders a clean markdown report you can paste into a weekly journal,
share with a friend, or commit to a `weekly/` folder alongside your daily
files.

Examples
--------
  # Last 7 days, write to stdout
  python scripts/weekly_summary.py

  # Specific ISO week (Mon-Sun)
  python scripts/weekly_summary.py --week 2026-W17

  # Save to a file under your data dir
  python scripts/weekly_summary.py --week 2026-W17 -o ~/PAI/DhaaraData/weekly/2026-W17.md

  # Custom date range (overrides --week)
  python scripts/weekly_summary.py --from 2026-04-13 --to 2026-04-19

What's in the digest
--------------------
- Period header, total entries, days active
- Per-category entry counts
- Finance: total, top 3 subcategories, top 3 expenses
- Habits: entry counts + longest streak per subcategory
- Mood distribution (inline list)
- Notable moments: up to 5 entries that carry a mood (the user's
  emotionally-significant ones), sorted by date
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

# Reuse the parser + rollup logic. scripts/ is not a package, so add it to
# sys.path explicitly when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    Entry,
    collect_entries,
    resolve_data_dir,
)
from stats import compute_stats  # noqa: E402

ISO_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")


def parse_iso_week(value: str) -> tuple[date, date]:
    """Convert "YYYY-Www" to its (Monday, Sunday) date pair."""
    match = ISO_WEEK_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid ISO week format: {value!r}. Use 'YYYY-Www' (e.g. 2026-W17).")
    year, week = int(match.group(1)), int(match.group(2))
    if not 1 <= week <= 53:
        raise ValueError(f"Week number out of range: {week}")
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def default_range() -> tuple[date, date]:
    """Last 7 calendar days, ending today (inclusive)."""
    today = date.today()
    return today - timedelta(days=6), today


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "…"


def render_markdown(entries: list[Entry], start: date, end: date) -> str:
    span_days = (end - start).days + 1
    stats = compute_stats(entries)

    lines: list[str] = []
    title_range = f"{start.isoformat()} → {end.isoformat()}"
    lines.append(f"# Week of {title_range}")
    lines.append("")

    if not entries:
        lines.append("_No journal entries this week._")
        lines.append("")
        return "\n".join(lines)

    days_active = stats["days_with_entries"]
    rate = (days_active / span_days * 100) if span_days else 0
    lines.append(
        f"**{stats['total_entries']} entries across {days_active} of {span_days} days "
        f"({rate:.0f}% active)**"
    )
    lines.append("")

    # Activity by category
    if stats["by_category"]:
        lines.append("## Activity")
        for cat, count in stats["by_category"].items():
            label = "entry" if count == 1 else "entries"
            lines.append(f"- **{cat}** — {count} {label}")
        lines.append("")

    # Finance
    fin = stats["finance"]
    if fin["total"] > 0:
        lines.append(f"## Finance — ₹{fin['total']:,.0f} total")
        lines.append("")
        top_subs = list(fin["by_subcategory"].items())[:3]
        if top_subs:
            lines.append("**Top categories**")
            for sub, amt in top_subs:
                lines.append(f"- {sub}: ₹{amt:,.0f}")
            lines.append("")
        if fin["top_expenses"]:
            lines.append("**Top expenses**")
            for exp in fin["top_expenses"][:3]:
                snippet = truncate(exp["text"], 70)
                lines.append(
                    f"- ₹{exp['amount']:,.0f} — {snippet} _({exp['date']})_"
                )
            lines.append("")

    # Habits
    habits = stats["habits"]
    if habits["by_subcategory"]:
        lines.append("## Habits")
        for sub, count in habits["by_subcategory"].items():
            streak = habits["streaks"].get(sub, 0)
            entry_word = "entry" if count == 1 else "entries"
            streak_word = "day" if streak == 1 else "days"
            lines.append(
                f"- **{sub}** — {count} {entry_word} (longest streak: {streak} {streak_word})"
            )
        lines.append("")

    # Moods (inline list, most common first)
    if stats["moods"]:
        lines.append("## Moods this week")
        mood_items = [f"{mood} ({count})" for mood, count in stats["moods"].items()]
        lines.append("- " + " · ".join(mood_items))
        lines.append("")

    # Notable moments — entries with moods, max 5, sorted by date
    notable = [e for e in entries if e.mood]
    notable.sort(key=lambda e: (e.date, e.time))
    if notable:
        lines.append("## Notable moments")
        for entry in notable[:5]:
            snippet = truncate(entry.text, 100)
            lines.append(
                f"- _({entry.mood})_ \"{snippet}\" — `{entry.date}` "
                f"`[{entry.category}{('/' + entry.subcategory) if entry.subcategory else ''}]`"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a markdown weekly summary from your Dhaara journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        help="Path to Dhaara data dir (defaults to config.yaml's data_dir, then ~/PAI/DhaaraData).",
    )
    parser.add_argument(
        "--week",
        help="ISO week 'YYYY-Www' (e.g. 2026-W17). Overrides default last-7-days.",
    )
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD (overrides --week).")
    parser.add_argument("--to", help="End date YYYY-MM-DD (overrides --week).")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output file path, or '-' for stdout (default).",
    )
    args = parser.parse_args(argv)

    if args.from_ or args.to:
        if not (args.from_ and args.to):
            parser.error("--from and --to must be used together")
        start = date.fromisoformat(args.from_)
        end = date.fromisoformat(args.to)
    elif args.week:
        try:
            start, end = parse_iso_week(args.week)
        except ValueError as e:
            parser.error(str(e))
    else:
        start, end = default_range()

    if start > end:
        parser.error("start date must be on or before end date")

    data_dir = resolve_data_dir(args.data_dir)
    journal_dir = data_dir / "journal"
    entries = collect_entries(journal_dir, start, end, None)

    print(
        f"info: {len(entries)} entries from {journal_dir} "
        f"({start.isoformat()} → {end.isoformat()})",
        file=sys.stderr,
    )

    markdown = render_markdown(entries, start, end)

    if args.output == "-":
        sys.stdout.write(markdown)
    else:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"info: wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
