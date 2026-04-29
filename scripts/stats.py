#!/usr/bin/env python3
"""
Print stats over your Dhaara journal.

Reuses the parser from `export_journal.py` and rolls entries up into a
human-readable report (or JSON for piping into a dashboard). Lives next
to the export script so contributors learn one parser, not two.

What it shows
-------------
- Date coverage (entries, days with entries, active days share)
- Per-category entry counts
- FINANCE totals + per-subcategory breakdown + top expenses
- HABITS per-subcategory counts + longest consecutive-day streak
- Mood distribution (overall + per category if mixed)

Examples
--------
  # Default: all entries, text report
  python scripts/stats.py

  # Last 30 days
  python scripts/stats.py --since 30d

  # April 2026, JSON
  python scripts/stats.py --from 2026-04-01 --to 2026-04-30 -f json

  # Custom data dir
  python scripts/stats.py --data-dir ~/some/other/dir
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

# Reuse export_journal's parser. scripts/ is not a package, so add it to
# sys.path explicitly when stats.py is invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    VALID_CATEGORIES,
    Entry,
    collect_entries,
    parse_since,
    resolve_data_dir,
)

# Match a number like "₹1,500", "Rs. 295", "$25.50", or a bare "3750",
# optionally followed by a multiplier (k = thousand, lakh / lac =
# 100k, cr / crore = 10M). Currency marker is optional — every FINANCE
# entry is assumed to be money even if the user dropped the symbol.
_AMOUNT_RE = re.compile(
    r"(?:(?P<currency>₹|\$|Rs\.?)\s*)?"
    r"(?P<num>[0-9](?:[0-9,]*[0-9])?(?:\.[0-9]+)?)"
    r"\s*(?P<suffix>k|lakh|lac|cr|crore)?",
    re.IGNORECASE,
)

_MULTIPLIERS = {
    "": 1,
    "k": 1_000,
    "lakh": 100_000,
    "lac": 100_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
}


def extract_amount(text: str) -> float | None:
    """Return the largest plausible amount in `text`, or None.

    Heuristic:
      1. Prefer matches that carry a currency marker (₹/Rs/$).
      2. Otherwise, take the largest bare number with optional k/lakh suffix.
      3. Reject standalone numbers ≤ 9 — too noisy ("9 mins", "5 PM").
    """
    best_with_currency = 0.0
    best_bare = 0.0
    for match in _AMOUNT_RE.finditer(text):
        try:
            n = float(match.group("num").replace(",", ""))
        except ValueError:
            continue
        suffix = (match.group("suffix") or "").lower()
        amount = n * _MULTIPLIERS.get(suffix, 1)
        if match.group("currency"):
            best_with_currency = max(best_with_currency, amount)
        elif amount >= 10:
            best_bare = max(best_bare, amount)
    chosen = best_with_currency or best_bare
    return chosen or None


def longest_streak(entry_dates: set[date]) -> int:
    """Longest run of consecutive days that appear in `entry_dates`."""
    if not entry_dates:
        return 0
    sorted_dates = sorted(entry_dates)
    longest = run = 1
    for prev, curr in zip(sorted_dates, sorted_dates[1:]):
        if (curr - prev).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    return longest


def compute_stats(entries: list[Entry]) -> dict:
    """Roll a list of Entry records into a stats dict ready for text/JSON rendering."""
    if not entries:
        return {
            "total_entries": 0,
            "days_with_entries": 0,
            "first_date": None,
            "last_date": None,
            "by_category": {},
            "finance": {"total": 0.0, "by_subcategory": {}, "top_expenses": []},
            "habits": {"by_subcategory": {}, "streaks": {}},
            "moods": {},
        }

    by_category = Counter(e.category for e in entries)
    days_seen = {date.fromisoformat(e.date) for e in entries}
    sorted_days = sorted(days_seen)

    finance_total = 0.0
    finance_by_sub: dict[str, float] = defaultdict(float)
    finance_expenses: list[tuple[float, Entry]] = []
    for e in entries:
        if e.category != "FINANCE":
            continue
        amount = extract_amount(e.text)
        if amount is None:
            continue
        finance_total += amount
        finance_by_sub[e.subcategory or "(none)"] += amount
        finance_expenses.append((amount, e))
    finance_expenses.sort(key=lambda pair: pair[0], reverse=True)

    habit_subs: Counter[str] = Counter()
    habit_streak_dates: dict[str, set[date]] = defaultdict(set)
    for e in entries:
        if e.category != "HABITS":
            continue
        sub = e.subcategory or "(none)"
        habit_subs[sub] += 1
        habit_streak_dates[sub].add(date.fromisoformat(e.date))
    habit_streaks = {sub: longest_streak(d) for sub, d in habit_streak_dates.items()}

    moods = Counter(e.mood for e in entries if e.mood)

    return {
        "total_entries": len(entries),
        "days_with_entries": len(days_seen),
        "first_date": sorted_days[0].isoformat(),
        "last_date": sorted_days[-1].isoformat(),
        "by_category": dict(by_category.most_common()),
        "finance": {
            "total": round(finance_total, 2),
            "by_subcategory": {
                sub: round(amt, 2)
                for sub, amt in sorted(finance_by_sub.items(), key=lambda kv: -kv[1])
            },
            "top_expenses": [
                {
                    "amount": round(amt, 2),
                    "date": e.date,
                    "subcategory": e.subcategory,
                    "text": e.text,
                }
                for amt, e in finance_expenses[:5]
            ],
        },
        "habits": {
            "by_subcategory": dict(habit_subs.most_common()),
            "streaks": dict(sorted(habit_streaks.items(), key=lambda kv: -kv[1])),
        },
        "moods": dict(moods.most_common()),
    }


def render_text(stats: dict) -> str:
    if stats["total_entries"] == 0:
        return "No entries in this range."

    lines: list[str] = []
    lines.append(
        f"📓 {stats['total_entries']} entries across "
        f"{stats['days_with_entries']} day(s) "
        f"({stats['first_date']} → {stats['last_date']})"
    )
    lines.append("")

    lines.append("## Entries by category")
    for cat, count in stats["by_category"].items():
        lines.append(f"  {cat:<10} {count:>4}")
    lines.append("")

    fin = stats["finance"]
    if fin["total"] > 0:
        lines.append(f"## Finance — total ₹{fin['total']:,.2f}")
        for sub, amt in fin["by_subcategory"].items():
            lines.append(f"  {sub:<16} ₹{amt:>12,.2f}")
        if fin["top_expenses"]:
            lines.append("")
            lines.append("  Top expenses:")
            for exp in fin["top_expenses"]:
                tail = exp["text"]
                if len(tail) > 60:
                    tail = tail[:57] + "..."
                lines.append(
                    f"    ₹{exp['amount']:>10,.2f}  {exp['date']}  "
                    f"[{exp['subcategory']}]  {tail}"
                )
        lines.append("")

    habits = stats["habits"]
    if habits["by_subcategory"]:
        lines.append("## Habits")
        for sub, count in habits["by_subcategory"].items():
            streak = habits["streaks"].get(sub, 0)
            streak_note = f"(streak: {streak} day{'s' if streak != 1 else ''})"
            lines.append(f"  {sub:<16} {count:>4}  {streak_note}")
        lines.append("")

    if stats["moods"]:
        lines.append("## Moods")
        for mood, count in stats["moods"].items():
            lines.append(f"  {mood:<16} {count:>4}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print stats over your Dhaara journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        help="Path to Dhaara data dir (defaults to config.yaml's data_dir, then ~/PAI/DhaaraData).",
    )
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD (inclusive).")
    parser.add_argument("--to", help="End date YYYY-MM-DD (inclusive).")
    parser.add_argument(
        "--since",
        help="Shortcut for relative start: '7d', '4w', '6m', or YYYY-MM-DD. Overridden by --from.",
    )
    parser.add_argument(
        "--category",
        help=f"Limit stats to one category (one of {sorted(VALID_CATEGORIES)}).",
    )
    parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    if args.category and args.category.upper() not in VALID_CATEGORIES:
        parser.error(f"--category must be one of {sorted(VALID_CATEGORIES)}")

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

    print(f"info: {len(entries)} entries from {journal_dir}", file=sys.stderr)

    stats = compute_stats(entries)
    if args.format == "json":
        json.dump(stats, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
