#!/usr/bin/env python3
"""
Print your Dhaara journaling streak — designed to be glanced at.

Drop this into your shell prompt, status bar, or starship config and
you'll see your streak every time you open a terminal. That nudge is
the whole point: a habit you can see is a habit you keep.

Output modes
------------

    short    (default) "🔥 5-day streak" or "💤 Streak broken — last entry 3 days ago"
    text     Multi-line summary: current streak, longest streak, last entry, totals
    json     Structured payload for piping into a status-bar plugin
    quiet    Just the integer (current streak); 0 when broken — for arithmetic

Examples
--------
  # Default short message
  python scripts/streak.py

  # Status-bar friendly: just the number
  python scripts/streak.py --quiet

  # Full report
  python scripts/streak.py --text

Reuses `build_calendar` from `activity_heatmap.py` so the streak math
matches what `python scripts/activity_heatmap.py` shows.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import collect_entries, resolve_data_dir  # noqa: E402
from activity_heatmap import build_calendar  # noqa: E402


def compute_streak_info(data_dir: Path, today: date | None = None) -> dict:
    """Pull a wide window of entries and roll them up into streak stats.

    `today` is overridable for testing; defaults to `date.today()`.
    Window is fixed at 1 year back from today — wide enough to capture
    any plausible streak, narrow enough to keep the file scan cheap.
    """
    today = today or date.today()
    start = today - timedelta(days=365)
    journal_dir = data_dir / "journal"
    entries = collect_entries(journal_dir, start, today, None)
    cal = build_calendar(entries, start, today)

    # Days since last entry: walk back from today until we hit a non-empty day.
    last_entry_date: date | None = None
    for week in reversed(cal["weeks"]):
        for day in reversed(week["days"]):
            if not day["in_range"]:
                continue
            if day["count"] > 0:
                last_entry_date = date.fromisoformat(day["date"])
                break
        if last_entry_date:
            break

    days_since_last = (today - last_entry_date).days if last_entry_date else None

    return {
        "today": today.isoformat(),
        "current_streak": cal["current_streak"],
        "longest_streak": cal["longest_streak"],
        "total_entries": cal["total_entries"],
        "active_days": cal["active_days"],
        "last_entry": last_entry_date.isoformat() if last_entry_date else None,
        "days_since_last": days_since_last,
    }


def render_short(info: dict) -> str:
    if info["current_streak"] > 0:
        days = info["current_streak"]
        return f"🔥 {days}-day streak\n"
    if info["last_entry"] is None:
        return "📓 No entries yet — start today!\n"
    n = info["days_since_last"]
    if n == 1:
        when = "yesterday"
    else:
        when = f"{n} days ago"
    return f"💤 Streak broken — last entry {when}\n"


def render_text(info: dict) -> str:
    lines: list[str] = []
    if info["current_streak"] > 0:
        lines.append(f"🔥 Current streak: {info['current_streak']} days")
    elif info["last_entry"] is None:
        lines.append("📓 No entries yet — start today!")
        lines.append("")
        return "\n".join(lines) + "\n"
    else:
        lines.append("💤 No active streak")

    lines.append(f"   Longest streak: {info['longest_streak']} days")

    last = info["last_entry"]
    if last:
        n = info["days_since_last"]
        if n == 0:
            note = "today"
        elif n == 1:
            note = "yesterday"
        else:
            note = f"{n} days ago"
        lines.append(f"   Last entry:     {last} ({note})")

    lines.append(f"   Total entries:  {info['total_entries']} across {info['active_days']} days")
    lines.append("")
    return "\n".join(lines)


def render_json(info: dict) -> str:
    return json.dumps(info, indent=2, ensure_ascii=False) + "\n"


def render_quiet(info: dict) -> str:
    """Just the integer — designed for shell prompts and arithmetic."""
    return f"{info['current_streak']}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print your Dhaara journaling streak.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="Multi-line summary.")
    mode.add_argument("--json", action="store_true", help="JSON payload.")
    mode.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the current-streak integer (0 if broken). Ideal for shell prompts.",
    )
    args = parser.parse_args(argv)

    data_dir = resolve_data_dir(args.data_dir)
    info = compute_streak_info(data_dir)

    if args.json:
        sys.stdout.write(render_json(info))
    elif args.text:
        sys.stdout.write(render_text(info))
    elif args.quiet:
        sys.stdout.write(render_quiet(info))
    else:
        sys.stdout.write(render_short(info))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
