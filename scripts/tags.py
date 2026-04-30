#!/usr/bin/env python3
"""
Inventory the subcategories and moods you've used across your journal.

The agent invents free-form subcategory tags as you go (`coding`, `food`,
`subscriptions`, `family`...) — over time you build up your own
classification system without ever planning one. This script surfaces
that system: per-category subcategory counts with last-seen dates, plus
mood frequencies. Useful for spotting:

  - subcategories you used once and never again (rename or merge?)
  - subcategories that explode (split into smaller buckets?)
  - moods you tag a lot vs. moods you've stopped using
  - cross-category overlaps (e.g. `food` shows up under FINANCE,
    HABITS, *and* PERSONAL — is that intentional?)

Reuses `export_journal.parse_day_file` + `collect_entries`.

Examples
--------
  # Inventory the whole journal
  python scripts/tags.py

  # Just the last 90 days — what's my recent taxonomy?
  python scripts/tags.py --since 90d

  # JSON for piping into a notebook / wrangler
  python scripts/tags.py -f json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_journal import (  # noqa: E402
    Entry,
    collect_entries,
    parse_since,
    resolve_data_dir,
)

CATEGORY_ORDER = ["WORK", "PERSONAL", "HABITS", "FINANCE"]


@dataclass
class TagRow:
    name: str
    count: int
    last_date: str

    def to_json(self) -> dict:
        return asdict(self)


def build_inventory(entries: list[Entry]) -> dict:
    """Aggregate entries into a per-category subcategory inventory + a
    mood inventory.

    Returns:
        {
            "total_entries": N,
            "days_with_entries": N,
            "first_date": "YYYY-MM-DD" or None,
            "last_date":  "YYYY-MM-DD" or None,
            "by_category": {
                "WORK": {
                    "total_entries": N,
                    "subcategories": [TagRow, ...],   # sorted by count desc
                },
                ...
            },
            "moods": [TagRow, ...],                   # sorted by count desc
        }
    """
    if not entries:
        return {
            "total_entries": 0,
            "days_with_entries": 0,
            "first_date": None,
            "last_date": None,
            "by_category": {},
            "moods": [],
        }

    # Days touched (just for the period summary line).
    days_seen = {e.date for e in entries}
    sorted_days = sorted(days_seen)

    # by_category[CAT] -> dict[subcategory_name -> {count, last_date}]
    by_cat: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"count": 0, "last_date": ""}
    ))
    cat_totals: Counter[str] = Counter()

    for e in entries:
        sub = e.subcategory or "(none)"
        slot = by_cat[e.category][sub]
        slot["count"] += 1
        if e.date > slot["last_date"]:
            slot["last_date"] = e.date
        cat_totals[e.category] += 1

    # Moods.
    mood_data: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_date": ""})
    for e in entries:
        if not e.mood:
            continue
        slot = mood_data[e.mood]
        slot["count"] += 1
        if e.date > slot["last_date"]:
            slot["last_date"] = e.date

    by_category_out = {}
    for cat in cat_totals:
        rows = [
            TagRow(name=name, count=info["count"], last_date=info["last_date"])
            for name, info in by_cat[cat].items()
        ]
        rows.sort(key=lambda r: (-r.count, r.name))
        by_category_out[cat] = {
            "total_entries": cat_totals[cat],
            "subcategories": rows,
        }

    mood_rows = [
        TagRow(name=name, count=info["count"], last_date=info["last_date"])
        for name, info in mood_data.items()
    ]
    mood_rows.sort(key=lambda r: (-r.count, r.name))

    return {
        "total_entries": len(entries),
        "days_with_entries": len(days_seen),
        "first_date": sorted_days[0],
        "last_date": sorted_days[-1],
        "by_category": by_category_out,
        "moods": mood_rows,
    }


def render_text(inv: dict) -> str:
    if inv["total_entries"] == 0:
        return "No entries in this range.\n"

    lines: list[str] = []
    lines.append(
        f"Tag inventory · {inv['total_entries']} entries across "
        f"{inv['days_with_entries']} day(s) "
        f"({inv['first_date']} → {inv['last_date']})"
    )
    lines.append("")

    lines.append("## Categories")
    lines.append("")

    # Walk CATEGORY_ORDER first, then any others (rare but possible).
    seen = set()
    cat_order = [c for c in CATEGORY_ORDER if c in inv["by_category"]]
    cat_order += sorted(c for c in inv["by_category"] if c not in CATEGORY_ORDER)

    for cat in cat_order:
        seen.add(cat)
        block = inv["by_category"][cat]
        rows: list[TagRow] = block["subcategories"]
        n_subs = len(rows)
        lines.append(
            f"{cat} ({n_subs} subcategor{'y' if n_subs == 1 else 'ies'}, "
            f"{block['total_entries']} entries)"
        )
        # Right-pad subcategory names so counts line up.
        name_w = max((len(r.name) for r in rows), default=0)
        for r in rows:
            label = "entry" if r.count == 1 else "entries"
            lines.append(
                f"  {r.name.ljust(name_w)}  {r.count:>3} {label}  "
                f"(last: {r.last_date})"
            )
        lines.append("")

    n_moods = len(inv["moods"])
    if n_moods:
        lines.append(f"## Moods ({n_moods} distinct)")
        lines.append("")
        name_w = max(len(r.name) for r in inv["moods"])
        for r in inv["moods"]:
            label = "entry" if r.count == 1 else "entries"
            lines.append(
                f"  {r.name.ljust(name_w)}  {r.count:>3} {label}  "
                f"(last: {r.last_date})"
            )
    else:
        lines.append("## Moods")
        lines.append("")
        lines.append("  (no moods tagged in this range)")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json(inv: dict) -> str:
    payload = {
        "total_entries": inv["total_entries"],
        "days_with_entries": inv["days_with_entries"],
        "first_date": inv["first_date"],
        "last_date": inv["last_date"],
        "by_category": {
            cat: {
                "total_entries": block["total_entries"],
                "subcategories": [r.to_json() for r in block["subcategories"]],
            }
            for cat, block in inv["by_category"].items()
        },
        "moods": [r.to_json() for r in inv["moods"]],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory subcategories and moods you've used across your journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", help="Path to Dhaara data dir.")
    parser.add_argument("--from", dest="from_", help="Start date YYYY-MM-DD.")
    parser.add_argument("--to", help="End date YYYY-MM-DD.")
    parser.add_argument(
        "--since",
        help="Relative shortcut: '7d', '4w', '6m', '1y' (overridden by --from). "
             "Defaults to all-time.",
    )
    parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    start: date | None = None
    if args.from_:
        start = date.fromisoformat(args.from_)
    elif args.since:
        start = parse_since(args.since)

    end: date | None = date.fromisoformat(args.to) if args.to else None

    if start and end and start > end:
        parser.error("start date must be on or before end date")

    data_dir = resolve_data_dir(args.data_dir)
    journal_dir = data_dir / "journal"
    entries = collect_entries(journal_dir, start, end, None)

    print(
        f"info: scanned {len(entries)} entries from {journal_dir}",
        file=sys.stderr,
    )

    inv = build_inventory(entries)

    if args.format == "json":
        sys.stdout.write(render_json(inv))
    else:
        sys.stdout.write(render_text(inv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
