"""
Sandboxed journal file store.
One file per day: journal/YYYY-MM-DD.md
All entries for a day live in one file, organized by ## [CATEGORY] sections.
All reads/writes are confined to data_dir.
"""
from datetime import datetime
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
        entry_md = format_entry(text=text, timestamp=timestamp, category=category, mood=mood)

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
        """
        # Pattern: find the section header
        section_header = f"## [{category}]"
        next_section_pattern = re.compile(r"\n## \[")
        pos = content.find(section_header)
        if pos == -1:
            raise ValueError(f"Section '{section_header}' not found in file")

        # Find end of this section (start of next ## or end of file)
        rest = content[pos + len(section_header):]
        next_match = next_section_pattern.search(rest)
        if next_match:
            end_pos = pos + len(section_header) + next_match.start()
        else:
            end_pos = pos + len(content)

        # Insert the entry at the end of the section
        new_content = content[:end_pos] + "\n" + entry + content[end_pos:]
        return new_content
