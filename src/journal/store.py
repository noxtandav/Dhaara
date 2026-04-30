"""
Sandboxed journal file store.
One file per day: journal/YYYY-MM-DD.md
All entries for a day live in one file, organized by ## [CATEGORY] sections.
All reads/writes are confined to data_dir.
"""
from datetime import datetime, timedelta
from pathlib import Path
import re

from filelock import FileLock

from .formatter import format_entry, format_day_header, CATEGORIES


class JournalStore:
    VALID_CATEGORIES = CATEGORIES

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.journal_dir = self.data_dir / "journal"
        self.journal_dir.mkdir(exist_ok=True)

    def _safe_path(self, *parts: str) -> Path:
        """Resolve a path inside data_dir. Raise ValueError if it escapes."""
        candidate = (self.data_dir / Path(*parts)).resolve()
        if not str(candidate).startswith(str(self.data_dir)):
            raise ValueError(f"Path traversal rejected: {parts}")
        return candidate

    def _day_file(self, date: datetime) -> Path:
        date_str = date.strftime("%Y-%m-%d")
        return self.journal_dir / f"{date_str}.md"

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def read_day(self, date: datetime) -> str | None:
        """Return content of the day's file, or None if it doesn't exist."""
        path = self._day_file(date)
        if not path.exists():
            return None
        return path.read_text()

    def append_entry(
        self,
        category: str,
        text: str,
        timestamp: datetime,
        subcategory: str | None = None,
        mood: str | None = None,
    ) -> Path:
        """
        Append a bullet entry to the correct ## [CATEGORY] section in the day's file.
        Creates the file with all category headers if it doesn't exist.
        """
        category = category.upper()
        if category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {self.VALID_CATEGORIES}"
            )

        path = self._day_file(timestamp)
        lock_path = path.with_suffix(".lock")
        entry_md = format_entry(
            text=text, timestamp=timestamp, category=category,
            subcategory=subcategory, mood=mood,
        )

        with FileLock(str(lock_path)):
            if not path.exists():
                path.write_text(format_day_header(timestamp) + "\n")

            content = path.read_text()

            # Find the ## [CATEGORY] section and insert bullet before the next ## or at end
            new_content = self._insert_into_section(content, category, entry_md)
            path.write_text(new_content)

        return path

    def _insert_into_section(self, content: str, category: str, entry: str) -> str:
        """
        Insert `entry` as a new bullet under ## [CATEGORY].
        The entry is inserted at the end of the section (before the next ## or end of file).
        Maintains a blank line between the last entry and the next section header.
        """
        section_header = f"## [{category}]"
        pos = content.find(section_header)
        if pos == -1:
            raise ValueError(f"Section '{section_header}' not found in file")

        # Find end of this section (start of next ## or end of file)
        rest = content[pos + len(section_header):]
        next_match = re.search(r"\n## \[", rest)

        if next_match:
            # Insert before the next section header, preserving a blank line
            end_pos = pos + len(section_header) + next_match.start()
            # Strip trailing whitespace in the section, then add entry + blank line
            before = content[:end_pos].rstrip()
            after = content[end_pos:]  # starts with \n## [
            return before + "\n" + entry + "\n" + after
        else:
            # Last section: append at end of file
            before = content.rstrip()
            return before + "\n" + entry + "\n"

    def read_journal_range(self, end_date: datetime, days: int) -> dict:
        """
        Read journal entries across a date range.

        Returns a dict with:
          - "content": concatenated markdown of all days with entries
          - "days_with_entries": number of days that had journal files
          - "days_requested": total days in the range
        """
        parts: list[str] = []
        days_with_entries = 0

        for offset in range(days):
            day = end_date - timedelta(days=offset)
            content = self.read_day(day)
            if content:
                days_with_entries += 1
                parts.append(content)

        # Reverse so entries are chronological (oldest first)
        parts.reverse()

        return {
            "content": "\n\n---\n\n".join(parts) if parts else "(No entries found.)",
            "days_with_entries": days_with_entries,
            "days_requested": days,
        }

    # -------------------------------------------------------------------------
    # Entry management (list / edit / delete by line number)
    # -------------------------------------------------------------------------

    def list_entries(self, date: datetime) -> str:
        """Return all bullet entries with their 1-based line numbers."""
        path = self._day_file(date)
        if not path.exists():
            return "No entries yet today."
        lines = path.read_text().splitlines()
        entries = []
        for i, line in enumerate(lines, start=1):
            if line.strip().startswith("- "):
                entries.append(f"L{i}: {line.strip()}")
        if not entries:
            return "No entries yet today."
        return "\n".join(entries)

    # Pattern to match: - [TIME] [CATEGORY/subcategory] content *(mood: ...)*
    _ENTRY_PATTERN = re.compile(
        r"^- \[(?P<time>[^\]]+)\] \[(?P<tag>[^\]]+)\] (?P<content>.+?)(?:\s+\*\(mood: (?P<mood>[^)]+)\)\*)?$"
    )

    def edit_entry(self, date: datetime, line_number: int, new_text: str) -> str:
        """Replace only the content of the entry at the given line, preserving time and category tags."""
        path = self._day_file(date)
        if not path.exists():
            return "No journal file for today."

        lock_path = path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            lines = path.read_text().splitlines()
            idx = line_number - 1  # 0-based

            if idx < 0 or idx >= len(lines):
                return f"Line {line_number} does not exist (file has {len(lines)} lines)."
            if not lines[idx].strip().startswith("- "):
                return f"Line {line_number} is not a bullet entry: '{lines[idx].strip()}'"

            # Preserve existing time and category/subcategory tags
            match = self._ENTRY_PATTERN.match(lines[idx].strip())
            if match:
                time_str = match.group("time")
                tag = match.group("tag")
                old_mood = match.group("mood")
                # Rebuild with preserved prefix, new content, keep old mood if present
                entry = f"- [{time_str}] [{tag}] {new_text}"
                if old_mood:
                    entry += f"  *(mood: {old_mood})*"
                lines[idx] = entry
            else:
                # Fallback: old-format entry without tags, just replace content
                lines[idx] = f"- {new_text}"

            path.write_text("\n".join(lines) + "\n")
        return f"Updated line {line_number}."

    def delete_entry(self, date: datetime, line_number: int) -> str:
        """Delete the entry at the given 1-based line number."""
        path = self._day_file(date)
        if not path.exists():
            return "No journal file for today."

        lock_path = path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            lines = path.read_text().splitlines()
            idx = line_number - 1

            if idx < 0 or idx >= len(lines):
                return f"Line {line_number} does not exist (file has {len(lines)} lines)."
            if not lines[idx].strip().startswith("- "):
                return f"Line {line_number} is not a bullet entry: '{lines[idx].strip()}'"

            removed = lines.pop(idx)
            path.write_text("\n".join(lines) + "\n")
        return f"Deleted: {removed.strip()}"
