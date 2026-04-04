"""
Format journal entries into the one-file-per-day markdown format.

File format:
  # YYYY-MM-DD Journal

  ## [WORK]
  - entry text

  ## [PERSONAL]
  - entry text

  ## [HABITS]
  - entry text

  ## [FINANCE]
  - entry text

Categories are fixed: WORK, PERSONAL, HABITS, FINANCE
"""
from datetime import datetime

CATEGORIES = ["WORK", "PERSONAL", "HABITS", "FINANCE"]


def format_entry(
    text: str,
    timestamp: datetime,
    category: str,
    mood: str | None = None,
) -> str:
    """
    Format a single bullet entry for a specific category section.
    """
    time_str = timestamp.strftime("%-I:%M %p")
    entry = f"- [{time_str}] {text}"
    if mood:
        entry += f"  *(mood: {mood})*"
    return entry


def format_day_header(date: datetime) -> str:
    """Return the markdown header for a new daily file."""
    date_str = date.strftime("%Y-%m-%d")
    sections = "\n\n".join(f"## [{cat}]" for cat in CATEGORIES)
    return f"# {date_str} Journal\n\n{sections}\n"
