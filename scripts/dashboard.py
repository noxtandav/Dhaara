#!/usr/bin/env python3
"""
Combined "everything in one place" Markdown dashboard for your Dhaara journal.

Weaves together every visualization in the toolset for a single date
range — perfect for an end-of-week review you can paste into a journal,
share with a friend, or save as a long-term archive.

Sections (in order):

    1. Streak status (current + longest)
    2. End-of-period snapshot ("today" relative to --to)
    3. Period summary (entries, days active, per-category counts)
    3a. (optional, --compare-prev) Week-over-week deltas
    4. Activity calendar (markdown table from activity_heatmap)
    5. Finance highlights (total, top categories, top expenses)
    6. Habits with longest-consecutive-day streaks
    7. Mood distribution + per-day timeline
    8. Notable moments (mood-tagged entries, capped at 5)

Reuses:
    streak.compute_streak_info
    today.build_report + render_markdown
    stats.compute_stats
    activity_heatmap.build_calendar + render_markdown
    mood_timeline.build_timeline + render_markdown (in part)
    weekly_summary.truncate + previous_period + compute_diff +
        render_diff_section

Examples
--------
  # Last 7 days, stdout
  python scripts/dashboard.py

  # Specific ISO week with week-over-week deltas
  python scripts/dashboard.py --from 2026-04-13 --to 2026-04-19 --compare-prev

  # Save to a file
  python scripts/dashboard.py --since 4w -o ~/PAI/DhaaraData/dashboards/last-month.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    Entry,
    collect_entries,
    parse_day_file,
    parse_since,
    resolve_data_dir,
)
from stats import compute_stats  # noqa: E402
from activity_heatmap import build_calendar, render_markdown as render_calendar_md  # noqa: E402
from mood_timeline import build_timeline  # noqa: E402
from streak import compute_streak_info  # noqa: E402
from today import build_report as build_today_report  # noqa: E402
from weekly_summary import (  # noqa: E402
    compute_diff,
    previous_period,
    render_diff_section,
    truncate,
)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def section_streak(data_dir: Path, today: date | None = None) -> list[str]:
    info = compute_streak_info(data_dir, today=today)
    lines = ["## Streak"]
    if info["current_streak"] > 0:
        lines.append(f"🔥 **Current streak**: {info['current_streak']} days")
    elif info["last_entry"] is None:
        lines.append("📓 No journal entries yet — start today!")
        lines.append("")
        return lines
    else:
        lines.append("💤 No active streak.")

    lines.append(f"- Longest streak: {info['longest_streak']} days")
    if info["last_entry"]:
        n = info["days_since_last"]
        if n == 0:
            note = "today"
        elif n == 1:
            note = "yesterday"
        else:
            note = f"{n} days ago"
        lines.append(f"- Last entry: {info['last_entry']} ({note})")
    lines.append("")
    return lines


def section_today(data_dir: Path, target: date) -> list[str]:
    day_file = data_dir / "journal" / f"{target.isoformat()}.md"
    entries = parse_day_file(day_file) if day_file.exists() else []
    report = build_today_report(entries, target)

    lines = [f"## Snapshot: {target.isoformat()} ({target.strftime('%A')})"]
    if report["total_entries"] == 0:
        lines.append("_Nothing recorded on this day._")
        lines.append("")
        return lines

    n = report["total_entries"]
    lines.append(f"**{n} entr{'y' if n == 1 else 'ies'}** today.")
    if report["finance_total"] > 0:
        lines.append(f"**Spending today**: ₹{report['finance_total']:,.0f}")
    if report["moods"]:
        lines.append(f"**Moods today**: {', '.join(report['moods'])}")
    lines.append("")
    return lines


def section_period_summary(stats: dict, span_days: int) -> list[str]:
    lines = ["## Period summary"]
    if stats["total_entries"] == 0:
        lines.append("_No entries in this period._")
        lines.append("")
        return lines

    days_active = stats["days_with_entries"]
    rate = (days_active / span_days * 100) if span_days else 0
    lines.append(
        f"**{stats['total_entries']} entries across {days_active} of {span_days} days "
        f"({rate:.0f}% active)**"
    )
    lines.append("")

    if stats["by_category"]:
        for cat, count in stats["by_category"].items():
            label = "entry" if count == 1 else "entries"
            lines.append(f"- **{cat}** — {count} {label}")
        lines.append("")
    return lines


def section_activity(entries: list[Entry], start: date, end: date) -> list[str]:
    cal = build_calendar(entries, start, end)
    if cal["total_entries"] == 0:
        return []  # period_summary already noted this; don't repeat
    body = render_calendar_md(cal)
    # Strip the leading "# Activity calendar: ..." header so the section
    # blends into the dashboard. Keep everything below it.
    pieces = body.split("\n", 2)
    body = pieces[2] if len(pieces) >= 3 else body
    return ["## Activity", body.rstrip(), ""]


def section_finance(stats: dict) -> list[str]:
    fin = stats["finance"]
    if fin["total"] <= 0:
        return []

    lines = [f"## Finance — ₹{fin['total']:,.0f} total"]
    top_subs = list(fin["by_subcategory"].items())[:5]
    if top_subs:
        lines.append("")
        lines.append("**Top categories**")
        for sub, amt in top_subs:
            lines.append(f"- {sub}: ₹{amt:,.0f}")
    if fin["top_expenses"]:
        lines.append("")
        lines.append("**Top expenses**")
        for exp in fin["top_expenses"][:5]:
            snippet = truncate(exp["text"], 80)
            lines.append(
                f"- ₹{exp['amount']:,.0f} — {snippet} _({exp['date']})_"
            )
    lines.append("")
    return lines


def section_habits(stats: dict) -> list[str]:
    habits = stats["habits"]
    if not habits["by_subcategory"]:
        return []
    lines = ["## Habits"]
    for sub, count in habits["by_subcategory"].items():
        streak = habits["streaks"].get(sub, 0)
        entry_word = "entry" if count == 1 else "entries"
        streak_word = "day" if streak == 1 else "days"
        lines.append(
            f"- **{sub}** — {count} {entry_word} (longest streak: {streak} {streak_word})"
        )
    lines.append("")
    return lines


def section_moods(entries: list[Entry], stats: dict, start: date, end: date) -> list[str]:
    if not stats["moods"]:
        return []
    lines = ["## Moods"]
    distribution = " · ".join(f"{m} ({c})" for m, c in stats["moods"].items())
    lines.append(f"**Distribution**: {distribution}")
    lines.append("")

    timeline = build_timeline(entries, start, end)
    day_lines: list[str] = []
    for d in timeline["days"]:
        day_moods = []
        for mood in timeline["moods"]:
            count = timeline["matrix"][mood].get(d, 0)
            if count == 0:
                continue
            day_moods.append(f"{mood} ×{count}" if count > 1 else mood)
        if day_moods:
            day_lines.append(f"- **{d}** — {', '.join(day_moods)}")
    if day_lines:
        lines.append("**Timeline**")
        lines.extend(day_lines)
        lines.append("")
    return lines


def section_notable(entries: list[Entry]) -> list[str]:
    notable = [e for e in entries if e.mood]
    notable.sort(key=lambda e: (e.date, e.time))
    if not notable:
        return []
    lines = ["## Notable moments"]
    for entry in notable[:5]:
        snippet = truncate(entry.text, 100)
        tag = f"{entry.category}/{entry.subcategory}" if entry.subcategory else entry.category
        lines.append(
            f"- _({entry.mood})_ \"{snippet}\" — `{entry.date}` `[{tag}]`"
        )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def section_compare_prev(
    journal_dir: Path,
    curr_stats: dict,
    start: date,
    end: date,
) -> list[str]:
    """Pull the same-length window before [start, end] and emit the diff."""
    prev_start, prev_end = previous_period(start, end)
    prev_entries = collect_entries(journal_dir, prev_start, prev_end, None)
    prev_stats = compute_stats(prev_entries)
    diff = compute_diff(curr_stats, prev_stats)
    return list(render_diff_section(diff))


def build_dashboard(
    data_dir: Path,
    start: date,
    end: date,
    *,
    now: datetime | None = None,
    compare_prev: bool = False,
) -> str:
    """Assemble all sections into one markdown document."""
    now = now or datetime.now()
    journal_dir = data_dir / "journal"
    entries = collect_entries(journal_dir, start, end, None)
    stats = compute_stats(entries)
    span_days = (end - start).days + 1

    lines: list[str] = []
    lines.append("# Dhaara Dashboard")
    lines.append(
        f"_{start.isoformat()} → {end.isoformat()} · "
        f"generated {now.strftime('%Y-%m-%d %H:%M')}_"
    )
    lines.append("")

    lines.extend(section_streak(data_dir, today=end))
    lines.extend(section_today(data_dir, end))
    lines.extend(section_period_summary(stats, span_days))
    if compare_prev:
        lines.extend(section_compare_prev(journal_dir, stats, start, end))
    lines.extend(section_activity(entries, start, end))
    lines.extend(section_finance(stats))
    lines.extend(section_habits(stats))
    lines.extend(section_moods(entries, stats, start, end))
    lines.extend(section_notable(entries))

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Combined Markdown dashboard for your Dhaara journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD.")
    parser.add_argument("--to", help="End date YYYY-MM-DD (defaults to today).")
    parser.add_argument(
        "--since",
        help="Relative shortcut: '7d', '4w', '6m', '1y'. Default = last 7 days.",
    )
    parser.add_argument(
        "--compare-prev",
        action="store_true",
        help=(
            "Add a 'Compared to the previous week' section with deltas. "
            "Pulls the same-length window immediately before the dashboard's "
            "date range."
        ),
    )
    parser.add_argument(
        "-o", "--output", default="-",
        help="Output file path, or '-' for stdout (default).",
    )
    args = parser.parse_args(argv)

    today = date.today()
    if args.from_:
        start = date.fromisoformat(args.from_)
    elif args.since:
        start = parse_since(args.since)
    else:
        start = today - timedelta(days=6)

    end: date = date.fromisoformat(args.to) if args.to else today

    if start > end:
        parser.error("start date must be on or before end date")

    data_dir = resolve_data_dir(args.data_dir)
    print(
        f"info: building dashboard for {start.isoformat()} → {end.isoformat()} "
        f"from {data_dir}",
        file=sys.stderr,
    )

    body = build_dashboard(data_dir, start, end, compare_prev=args.compare_prev)

    if args.output == "-":
        sys.stdout.write(body)
    else:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        print(f"info: wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
