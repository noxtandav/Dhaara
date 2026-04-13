"""
Format journal entries into the one-file-per-day markdown format.

Each entry is a self-contained line with inline metadata tags for RAG retrieval:
  - [TIME] [CATEGORY/subcategory] Text *(mood: emotion)*

File format:
  # YYYY-MM-DD Journal

  ## [WORK]
  - [10:32 AM] [WORK/meetings] Had standup with team
  - [2:15 PM] [WORK/coding] Finished the API refactor

  ## [PERSONAL]
  - [9:00 AM] [PERSONAL/family] Had breakfast with family *(mood: happy)*

  ## [HABITS]
  - [7:00 AM] [HABITS/exercise] Gym: 45 mins

  ## [FINANCE]
  - [1:30 PM] [FINANCE/food] Spent ₹150 on lunch
  - [6:00 PM] [FINANCE/groceries] Bought vegetables ₹300

Categories are fixed: WORK, PERSONAL, HABITS, FINANCE
Subcategories are free-form, chosen by the AI based on context.
"""
from datetime import datetime

CATEGORIES = ["WORK", "PERSONAL", "HABITS", "FINANCE"]


def format_entry(
    text: str,
    timestamp: datetime,
    category: str,
    subcategory: str | None = None,
    mood: str | None = None,
) -> str:
    """
    Format a single bullet entry with inline category/subcategory tags.
    Each entry is a self-contained chunk suitable for RAG retrieval.
    """
    time_str = timestamp.strftime("%-I:%M %p")
    tag = f"{category}/{subcategory}" if subcategory else category
    entry = f"- [{time_str}] [{tag}] {text}"
    if mood:
        entry += f"  *(mood: {mood})*"
    return entry


def format_day_header(date: datetime) -> str:
    """Return the markdown header for a new daily file."""
    date_str = date.strftime("%Y-%m-%d")
    sections = "\n\n".join(f"## [{cat}]" for cat in CATEGORIES)
    return f"# {date_str} Journal\n\n{sections}\n"
