#!/usr/bin/env python3
"""
Export Dhaara journal entries to CSV or JSON.

Reads every `journal/YYYY-MM-DD.md` file under the data dir, parses each
bullet into a structured record (date, time, category, subcategory, text,
mood), and writes the result to stdout or a file. Useful for analysing your
journal in pandas / Sheets / Excel without going through the bot.

Examples
--------
  # Export everything to CSV (stdout)
  python scripts/export_journal.py

  # Last 30 days, finance only, to a file
  python scripts/export_journal.py --since 30d --category FINANCE -o finance.csv

  # JSON, all of April 2026
  python scripts/export_journal.py --from 2026-04-01 --to 2026-04-30 -f json

  # Use a custom data dir (otherwise read from config.yaml, then fall back
  # to ~/PAI/DhaaraData)
  python scripts/export_journal.py --data-dir ~/some/other/dir

The script is intentionally standalone — it does not import the `src`
package, so contributors can run it without setting up the full dev
environment. It does need PyYAML if you rely on config.yaml lookup.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

VALID_CATEGORIES = {"WORK", "PERSONAL", "HABITS", "FINANCE"}

DAY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")

ENTRY_RE = re.compile(
    r"^- \[(?P<time>[^\]]+)\] \[(?P<tag>[^\]]+)\] (?P<text>.+?)"
    r"(?:\s+\*\(mood: (?P<mood>[^)]+)\)\*)?$"
)

SECTION_RE = re.compile(r"^## \[(?P<category>[A-Z]+)\]\s*$")


@dataclass
class Entry:
    date: str
    time: str
    category: str
    subcategory: str
    text: str
    mood: str

    @property
    def datetime_iso(self) -> str:
        """Best-effort ISO datetime by combining date and parsed 12-hour time.

        Falls back to just the date if the time can't be parsed."""
        for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
            try:
                t = datetime.strptime(self.time.strip(), fmt).time()
                return datetime.combine(date.fromisoformat(self.date), t).isoformat()
            except ValueError:
                continue
        return self.date


def parse_day_file(path: Path) -> list[Entry]:
    """Parse a single YYYY-MM-DD.md file into Entry records."""
    match = DAY_FILE_RE.match(path.name)
    if not match:
        return []
    day = match.group(1)

    current_section = ""
    entries: list[Entry] = []

    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        section_match = SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group("category")
            continue
        if not line.lstrip().startswith("- "):
            continue
        entry_match = ENTRY_RE.match(line.lstrip())
        if not entry_match:
            continue
        tag = entry_match.group("tag")
        if "/" in tag:
            category, subcategory = tag.split("/", 1)
        else:
            category, subcategory = tag, ""
        # Section header takes precedence if present and tag is missing/odd
        category = (category or current_section).upper()
        entries.append(
            Entry(
                date=day,
                time=entry_match.group("time").strip(),
                category=category,
                subcategory=subcategory.strip(),
                text=entry_match.group("text").strip(),
                mood=(entry_match.group("mood") or "").strip(),
            )
        )
    return entries


def parse_since(value: str) -> date:
    """Parse a relative ('30d', '4w', '6m') or absolute (YYYY-MM-DD) date."""
    value = value.strip()
    rel = re.fullmatch(r"(\d+)([dwm])", value)
    if rel:
        n, unit = int(rel.group(1)), rel.group(2)
        days = {"d": 1, "w": 7, "m": 30}[unit] * n
        return date.today() - timedelta(days=days)
    return date.fromisoformat(value)


def resolve_data_dir(explicit: str | None) -> Path:
    """Pick the data dir: CLI flag > config.yaml > ~/PAI/DhaaraData."""
    if explicit:
        return Path(explicit).expanduser().resolve()

    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml  # type: ignore
        except ImportError:
            print(
                "warn: config.yaml found but PyYAML not installed; "
                "falling back to ~/PAI/DhaaraData. Install with: pip install pyyaml",
                file=sys.stderr,
            )
        else:
            cfg = yaml.safe_load(config_path.read_text()) or {}
            if cfg.get("data_dir"):
                return Path(cfg["data_dir"]).expanduser().resolve()

    return (Path.home() / "PAI" / "DhaaraData").resolve()


def collect_entries(
    journal_dir: Path,
    start: date | None,
    end: date | None,
    category: str | None,
) -> list[Entry]:
    if not journal_dir.is_dir():
        raise SystemExit(f"error: journal dir not found: {journal_dir}")

    entries: list[Entry] = []
    for path in sorted(journal_dir.glob("*.md")):
        match = DAY_FILE_RE.match(path.name)
        if not match:
            continue
        day = date.fromisoformat(match.group(1))
        if start and day < start:
            continue
        if end and day > end:
            continue
        entries.extend(parse_day_file(path))

    if category:
        cat = category.upper()
        entries = [e for e in entries if e.category == cat]

    return entries


def write_csv(entries: list[Entry], stream) -> None:
    writer = csv.writer(stream)
    writer.writerow(["date", "time", "datetime_iso", "category", "subcategory", "text", "mood"])
    for e in entries:
        writer.writerow([e.date, e.time, e.datetime_iso, e.category, e.subcategory, e.text, e.mood])


def write_json(entries: list[Entry], stream) -> None:
    payload = [{**asdict(e), "datetime_iso": e.datetime_iso} for e in entries]
    json.dump(payload, stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export Dhaara journal entries to CSV or JSON.",
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
        help=f"Filter to one category (one of {sorted(VALID_CATEGORIES)}).",
    )
    parser.add_argument("-f", "--format", choices=["csv", "json"], default="csv")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output file path, or '-' for stdout (default).",
    )
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

    writer = write_csv if args.format == "csv" else write_json
    if args.output == "-":
        writer(entries, sys.stdout)
    else:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer(entries, fh)
        print(f"info: wrote {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
