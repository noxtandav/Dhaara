#!/usr/bin/env python3
"""
First-run setup for a Dhaara data directory.

Reads `config.yaml` (or `--config <path>`), resolves `data_dir` and the
shared TELOS directory, then creates the directory layout and seeds the
two example TELOS files. Idempotent — re-running tells you what was
already there and creates only what was missing.

Pairs with `check_config.py`:
  - `check_config.py` lints your config.yaml.
  - `init.py` realizes the file system that config points at.

Examples
--------
  # Default: read ./config.yaml and create everything
  python scripts/init.py

  # Show what would happen without touching disk
  python scripts/init.py --dry-run

  # Use a specific config file
  python scripts/init.py --config /etc/dhaara/config.yaml

  # JSON output for scripting
  python scripts/init.py -f json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# scripts/ → repo root → src/ is importable. Reuse the canonical TELOS
# example seeds rather than duplicating the strings here.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import yaml  # type: ignore
except ImportError:
    print(
        "error: PyYAML is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    raise SystemExit(2)

from src.context.telos import (  # noqa: E402
    TELOS_EXAMPLE_PERSONAL,
    TELOS_EXAMPLE_WORK,
)


@dataclass
class Action:
    target: str          # absolute path
    kind: str            # "dir" | "file"
    status: str          # "created" | "exists" | "would-create"


@dataclass
class InitReport:
    config_path: str
    data_dir: str
    telos_dir: str
    dry_run: bool
    actions: list[Action] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return sum(1 for a in self.actions if a.status in ("created", "would-create"))

    @property
    def existed_count(self) -> int:
        return sum(1 for a in self.actions if a.status == "exists")


def resolve_paths(config_path: Path) -> tuple[Path, Path]:
    """Return (data_dir, telos_dir) absolute paths from config.yaml.

    Falls back to telos_dir = <data_dir>/../_telos when the config doesn't
    set telos_dir explicitly. This matches the convention documented in
    src/config.py and the README.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"top-level config must be a mapping, got {type(raw).__name__}")

    data_dir_str = raw.get("data_dir")
    if not data_dir_str:
        raise ValueError("config is missing 'data_dir'")
    data_dir = Path(str(data_dir_str)).expanduser().resolve()

    telos_str = raw.get("telos_dir")
    if telos_str:
        telos_dir = Path(str(telos_str)).expanduser().resolve()
    else:
        telos_dir = (data_dir.parent / "_telos").resolve()

    return data_dir, telos_dir


def _ensure_dir(path: Path, dry_run: bool) -> Action:
    if path.is_dir():
        return Action(target=str(path), kind="dir", status="exists")
    if dry_run:
        return Action(target=str(path), kind="dir", status="would-create")
    path.mkdir(parents=True, exist_ok=True)
    return Action(target=str(path), kind="dir", status="created")


def _ensure_file(path: Path, content: str, dry_run: bool) -> Action:
    if path.exists():
        return Action(target=str(path), kind="file", status="exists")
    if dry_run:
        return Action(target=str(path), kind="file", status="would-create")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return Action(target=str(path), kind="file", status="created")


def run_init(config_path: Path, dry_run: bool = False) -> InitReport:
    """Plan + execute (unless dry_run) the first-run setup."""
    data_dir, telos_dir = resolve_paths(config_path)

    report = InitReport(
        config_path=str(config_path),
        data_dir=str(data_dir),
        telos_dir=str(telos_dir),
        dry_run=dry_run,
    )

    report.actions.append(_ensure_dir(data_dir, dry_run))
    report.actions.append(_ensure_dir(data_dir / "journal", dry_run))
    report.actions.append(_ensure_dir(telos_dir, dry_run))
    report.actions.append(
        _ensure_file(telos_dir / "work.md", TELOS_EXAMPLE_WORK, dry_run)
    )
    report.actions.append(
        _ensure_file(telos_dir / "personal.md", TELOS_EXAMPLE_PERSONAL, dry_run)
    )

    return report


def render_text(report: InitReport) -> str:
    icons = {"created": "✓", "exists": "·", "would-create": "+"}
    lines: list[str] = []
    if report.dry_run:
        lines.append("Dry run — no files written.")
        lines.append("")
    lines.append(f"data_dir:  {report.data_dir}")
    lines.append(f"telos_dir: {report.telos_dir}")
    lines.append("")
    for action in report.actions:
        icon = icons.get(action.status, "?")
        lines.append(f"  {icon} [{action.kind:<4}] {action.status:<13} {action.target}")
    lines.append("")

    if report.dry_run:
        n = report.created_count
        lines.append(
            f"{n} item(s) would be created. {report.existed_count} already in place."
        )
    else:
        n = report.created_count
        if n == 0:
            lines.append(f"Already initialized. {report.existed_count} item(s) verified.")
        else:
            lines.append(
                f"Created {n} item(s). {report.existed_count} already in place. "
                "Edit your TELOS files to give the agent context, then run dhaara."
            )
    return "\n".join(lines) + "\n"


def render_json(report: InitReport) -> str:
    payload = asdict(report)
    payload["created_count"] = report.created_count
    payload["existed_count"] = report.existed_count
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="First-run setup for a Dhaara data directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    default_config = REPO_ROOT / "config.yaml"
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help=f"Path to config.yaml (default: {default_config}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing anything.",
    )
    parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        report = run_init(args.config, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (ValueError, yaml.YAMLError) as e:
        print(f"error: invalid config: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        sys.stdout.write(render_json(report))
    else:
        sys.stdout.write(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
