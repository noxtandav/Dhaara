#!/usr/bin/env python3
"""
Show what you've journaled today (or any specific day) at a glance.

Fills the gap between `streak.py` (moment-to-moment nudge) and
`weekly_summary.py` (last 7 days). When you sit down at lunchtime
wondering "wait, what did I record this morning?", this is the
answer in one screenful.

Output formats
--------------

    text     (default) Sectioned per-category breakdown with finance
             subtotal, mood inline per entry, and a "moods today"
             line at the bottom.
    markdown Same layout in clean Markdown for embedding in a daily
             review note.
    json     Structured payload: {date, dow, entries[], by_category,
             total_finance, moods}.

Examples
--------
  # What have I journaled today?
  python scripts/today.py

  # Yesterday's recap
  python scripts/today.py --date 2026-04-29

  # Markdown for a daily note
  python scripts/today.py -f markdown

Reuses `export_journal.parse_day_file` and `extract_amount` from
`stats.py` (so finance subtotals match the rollups elsewhere).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    Entry,
    collect_entries,
    parse_day_file,
    resolve_data_dir,
)
from stats import extract_amount  # noqa: E402

CATEGORY_ORDER = ["WORK", "PERSONAL", "HABITS", "FINANCE"]


def _parse_time(time_str: str) -> int:
    """Convert "10:32 AM" / "2:15 PM" to minutes-since-midnight for sorting."""
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            t = datetime.strptime(time_str.strip(), fmt).time()
            return t.hour * 60 + t.minute
        except ValueError:
            continue
    return 0  # unparseable times sort first


def find_last_entry_on_or_before(data_dir: Path, target: date) -> Entry | None:
    """Most recent entry whose date <= `target`. None if none.

    Used for the "last entry was N days ago" hint we surface when the
    target day itself has no entries — turns the empty-day report from
    a dead end into a nudge.
    """
    journal_dir = data_dir / "journal"
    if not journal_dir.is_dir():
        return None
    try:
        all_entries = collect_entries(journal_dir, None, target, None)
    except SystemExit:
        return None
    if not all_entries:
        return None
    # collect_entries returns entries in date order but doesn't sort by
    # time within a day; pin the ordering with (date, parsed_time).
    all_entries.sort(key=lambda e: (e.date, _parse_time(e.time)))
    return all_entries[-1]


def _format_gap(target: date, entry_date: str) -> str:
    """Return 'today' / 'yesterday' / 'N days ago' for the gap from
    `entry_date` to `target`."""
    delta = (target - date.fromisoformat(entry_date)).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "yesterday"
    return f"{delta} days ago"


def build_report(
    entries: list[Entry],
    target: date,
    *,
    last_entry: Entry | None = None,
) -> dict:
    """Group entries by category and compute the per-section subtotals.

    `last_entry` is only consulted when the target day itself has no
    entries — in that case it powers the "last entry was N days ago"
    nudge in the empty-day message. When None or when target has its
    own entries, the report ignores it.
    """
    # Keep the canonical 4-section ordering, but only surface sections
    # that actually have entries for the day.
    by_category: "OrderedDict[str, list[Entry]]" = OrderedDict()
    for cat in CATEGORY_ORDER:
        rows = [e for e in entries if e.category == cat]
        rows.sort(key=lambda e: _parse_time(e.time))
        if rows:
            by_category[cat] = rows
    # Anything outside the canonical 4 (rare but possible) goes after.
    for e in entries:
        if e.category not in CATEGORY_ORDER:
            by_category.setdefault(e.category, []).append(e)

    finance_total = 0.0
    for e in by_category.get("FINANCE", []):
        amount = extract_amount(e.text)
        if amount is not None:
            finance_total += amount

    moods: list[str] = []
    for e in entries:
        if e.mood and e.mood not in moods:
            moods.append(e.mood)

    last_info: dict | None = None
    if not entries and last_entry is not None:
        last_info = {
            "date": last_entry.date,
            "time": last_entry.time,
            "category": last_entry.category,
            "subcategory": last_entry.subcategory,
            "gap": _format_gap(target, last_entry.date),
        }

    return {
        "date": target.isoformat(),
        "dow": target.strftime("%A"),
        "total_entries": len(entries),
        "by_category": {cat: [asdict(e) for e in rows] for cat, rows in by_category.items()},
        "finance_total": round(finance_total, 2),
        "moods": moods,
        "last_entry": last_info,
    }


def _format_entry_line(entry: Entry) -> str:
    """One-line entry: time, subcategory tag, text, optional mood."""
    sub = f"[{entry.subcategory}]" if entry.subcategory else "       "
    line = f"  {entry.time:>8}  {sub:<12}  {entry.text}"
    if entry.mood:
        line += f"  *({entry.mood})*"
    return line


def render_text(report: dict, entries: list[Entry]) -> str:
    if report["total_entries"] == 0:
        head = f"📓 {report['date']} ({report['dow']}) — Nothing recorded yet."
        last = report.get("last_entry")
        if last:
            head += f" Last entry: {last['gap']} ({last['date']} {last['time']})."
        else:
            head += " No journal entries yet anywhere."
        return head + "\n"

    lines: list[str] = []
    n = report["total_entries"]
    lines.append(
        f"📓 {report['date']} ({report['dow']}) · "
        f"{n} entr{'y' if n == 1 else 'ies'}"
    )
    lines.append("")

    by_cat: dict[str, list[Entry]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)
    for rows in by_cat.values():
        rows.sort(key=lambda e: _parse_time(e.time))

    for cat in CATEGORY_ORDER + [c for c in by_cat if c not in CATEGORY_ORDER]:
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        header = f"{cat} ({len(rows)})"
        if cat == "FINANCE" and report["finance_total"] > 0:
            header += f" — ₹{report['finance_total']:,.0f} today"
        lines.append(header)
        for entry in rows:
            lines.append(_format_entry_line(entry))
        lines.append("")

    if report["moods"]:
        lines.append(f"Moods today: {', '.join(report['moods'])}")
    else:
        lines.append("(no moods tagged)")

    return "\n".join(lines) + "\n"


def render_markdown(report: dict, entries: list[Entry]) -> str:
    lines: list[str] = []
    lines.append(f"# {report['date']} ({report['dow']})")
    lines.append("")

    if report["total_entries"] == 0:
        lines.append("_Nothing recorded yet._")
        last = report.get("last_entry")
        if last:
            lines.append(
                f"_Last entry: {last['gap']} "
                f"(`{last['date']}` at {last['time']})._"
            )
        else:
            lines.append("_No journal entries yet anywhere._")
        lines.append("")
        return "\n".join(lines)

    n = report["total_entries"]
    lines.append(f"_{n} entr{'y' if n == 1 else 'ies'}._")
    lines.append("")

    by_cat: dict[str, list[Entry]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)
    for rows in by_cat.values():
        rows.sort(key=lambda e: _parse_time(e.time))

    for cat in CATEGORY_ORDER + [c for c in by_cat if c not in CATEGORY_ORDER]:
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        header = f"## {cat} ({len(rows)})"
        if cat == "FINANCE" and report["finance_total"] > 0:
            header += f" — ₹{report['finance_total']:,.0f}"
        lines.append(header)
        for entry in rows:
            sub = f"`{entry.subcategory}`" if entry.subcategory else ""
            mood = f" *({entry.mood})*" if entry.mood else ""
            piece = f"- **{entry.time}** {sub} {entry.text}{mood}".strip()
            # Tidy double spaces from the empty-subcategory case
            lines.append(piece.replace("  ", " "))
        lines.append("")

    if report["moods"]:
        lines.append(f"**Moods today**: {', '.join(report['moods'])}")
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show what you've journaled today (or any specific day).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    parser.add_argument(
        "--date",
        help="Target date YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument("-f", "--format", choices=["text", "markdown", "json"], default="text")
    args = parser.parse_args(argv)

    target = date.fromisoformat(args.date) if args.date else date.today()

    data_dir = resolve_data_dir(args.data_dir)
    day_file = data_dir / "journal" / f"{target.isoformat()}.md"
    entries = parse_day_file(day_file) if day_file.exists() else []

    print(
        f"info: {len(entries)} entries from {day_file}",
        file=sys.stderr,
    )

    # Only do the wider scan when we'd actually use the result — keeps the
    # active-day path as fast as it was in iteration 12.
    last_entry = (
        find_last_entry_on_or_before(data_dir, target) if not entries else None
    )

    report = build_report(entries, target, last_entry=last_entry)

    if args.format == "json":
        sys.stdout.write(render_json(report))
    elif args.format == "markdown":
        sys.stdout.write(render_markdown(report, entries))
    else:
        sys.stdout.write(render_text(report, entries))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
