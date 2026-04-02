"""
Sandboxed journal file store.
All reads/writes are confined to data_dir. Path traversal is rejected.
"""
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from .formatter import format_entry, format_day_header
from .silos import silo_exists, get_silo_names


class JournalStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()

    def _safe_path(self, *parts: str) -> Path:
        """
        Resolve a path inside data_dir. Raise ValueError if it escapes.
        """
        candidate = (self.data_dir / Path(*parts)).resolve()
        if not str(candidate).startswith(str(self.data_dir)):
            raise ValueError(f"Path traversal rejected: {parts}")
        return candidate

    def _day_file(self, silo: str, date: datetime) -> Path:
        date_str = date.strftime("%Y-%m-%d")
        return self._safe_path(silo, f"{date_str}.md")

    def read_day(self, silo: str, date: datetime) -> str | None:
        """Return content of silo's daily file, or None if it doesn't exist."""
        path = self._day_file(silo, date)
        if not path.exists():
            return None
        return path.read_text()

    def append_entry(
        self,
        silo: str,
        text: str,
        timestamp: datetime,
        mood: str | None = None,
        tags: list[str] | None = None,
        finance_items: list[dict] | None = None,
    ) -> Path:
        """
        Append a formatted entry to the silo's daily file.
        Creates the file (with day header) if it doesn't exist.
        Returns the path of the file written.
        """
        if not silo_exists(self.data_dir, silo):
            raise ValueError(f"Silo '{silo}' does not exist. Create it first.")

        path = self._day_file(silo, timestamp)
        lock_path = path.with_suffix(".lock")

        entry_md = format_entry(
            text=text,
            timestamp=timestamp,
            mood=mood,
            tags=tags,
            finance_items=finance_items,
        )

        with FileLock(str(lock_path)):
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(format_day_header(timestamp) + "\n" + entry_md)
            else:
                with open(path, "a") as f:
                    f.write("\n" + entry_md)

        return path

    def list_silos_summary(self) -> str:
        """Return a plain-text summary of available silos for the agent."""
        names = get_silo_names(self.data_dir)
        return ", ".join(names) if names else "(no silos)"
