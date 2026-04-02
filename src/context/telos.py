"""
Read TELOS background files from data_dir/_telos/.
These are manually maintained markdown files the agent reads for context.
"""
from pathlib import Path

TELOS_EXAMPLE_WORK = """\
# Work TELOS

## Goals
- Build AI-powered tools that enhance personal productivity
- Deliver high-quality software that is maintainable and well-documented

## Current Projects
- Dhaara: AI journal agent (Phase 1 - recording)

## Obstacles
- Limited time due to other commitments

## Targets & Deadlines
- Dhaara Phase 1: Q2 2026

## Strengths
- Strong engineering background
- Clear vision for the PAI ecosystem
"""

TELOS_EXAMPLE_PERSONAL = """\
# Personal TELOS

## Goals
- Maintain physical and mental health
- Build consistent daily habits
- Grow personally and professionally

## Current Focus
- Exercise regularly
- Read more books
- Sleep consistently

## Obstacles
- Irregular schedule

## Targets & Deadlines
- Exercise: 5 days/week habit by end of month

## Strengths
- High motivation and self-awareness
"""


def init_telos_files(data_dir: Path) -> None:
    """Create example TELOS files if they don't exist."""
    telos_dir = data_dir / "_telos"
    telos_dir.mkdir(parents=True, exist_ok=True)

    work_file = telos_dir / "work.md"
    if not work_file.exists():
        work_file.write_text(TELOS_EXAMPLE_WORK)

    personal_file = telos_dir / "personal.md"
    if not personal_file.exists():
        personal_file.write_text(TELOS_EXAMPLE_PERSONAL)


def read_telos(data_dir: Path, background: str) -> str:
    """
    Read a TELOS background file.
    background: 'work' or 'personal' (case-insensitive)
    Returns file content or a message if not found.
    """
    name = background.lower().strip()
    path = data_dir / "_telos" / f"{name}.md"
    if path.exists():
        return path.read_text()
    return f"(No TELOS file found for '{background}'. Create {path} to add context.)"


def read_all_telos(data_dir: Path) -> str:
    """Read all TELOS files and concatenate for system prompt injection."""
    telos_dir = data_dir / "_telos"
    if not telos_dir.exists():
        return "(No TELOS backgrounds found.)"

    parts = []
    for md_file in sorted(telos_dir.glob("*.md")):
        content = md_file.read_text().strip()
        if content:
            parts.append(f"=== {md_file.stem.upper()} TELOS ===\n{content}")

    return "\n\n".join(parts) if parts else "(No TELOS backgrounds found.)"
