"""
Format journal entries into markdown.
"""
from datetime import datetime

def format_entry(
    text: str,
    timestamp: datetime,
    mood: str | None = None,
    tags: list[str] | None = None,
    finance_items: list[dict] | None = None,
) -> str:
    """
    Format a single journal entry as a markdown section.

    finance_items: list of {"item": str, "amount": float|int, "category": str}
    """
    time_str = timestamp.strftime("%-I:%M %p")  # e.g. "10:32 AM"
    lines = [f"### {time_str}", text, ""]

    if finance_items:
        lines.append("| Item | Amount | Category |")
        lines.append("|---|---|---|")
        total = 0
        for fi in finance_items:
            lines.append(f"| {fi['item']} | {fi['amount']} | {fi['category']} |")
            total += fi.get("amount", 0)
        lines.append("")
        lines.append(f"**Daily Total:** {total}")
        lines.append("")

    if mood:
        lines.append(f"**Mood:** {mood}")
    if tags:
        tag_str = " ".join(f"#{t.lstrip('#')}" for t in tags)
        lines.append(f"**Tags:** {tag_str}")

    # Ensure trailing newline
    lines.append("")
    return "\n".join(lines)


def format_day_header(date: datetime) -> str:
    """Return the markdown header for a new daily file."""
    date_str = date.strftime("%Y-%m-%d")
    return f"# {date_str}\n\n## Entries\n"
