#!/usr/bin/env python3
"""
Lint a Dhaara config.yaml without booting the bot.

Catches the things that bite first-time users:
  - Missing required keys for the chosen AI provider
  - Placeholder values left in from `config.example.yaml`
  - Non-IANA timezones
  - Suspicious-looking Telegram / OpenRouter / Sarvam credentials
  - Unparseable YAML

Exit code is 0 on success and 1 on any error (warnings don't fail).

Examples
--------
  # Default: check ./config.yaml
  python scripts/check_config.py

  # Specific path
  python scripts/check_config.py --config /etc/dhaara/config.yaml

  # JSON output for CI / scripts
  python scripts/check_config.py -f json

This script does NOT make network calls; it's a static validator. A future
`--check-apis` flag could add live connectivity checks against Bedrock,
OpenRouter, and Sarvam — for now keep first-run feedback fast and offline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    print(
        "error: PyYAML is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    raise SystemExit(2)

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    print("error: zoneinfo (Python 3.9+) is required.", file=sys.stderr)
    raise SystemExit(2)


VALID_PROVIDERS = {"bedrock", "openrouter"}

# Patterns that suggest the user copied config.example.yaml and forgot to fill in.
PLACEHOLDER_PATTERNS = [
    re.compile(r"^YOUR[_ ]"),
    re.compile(r"\.\.\.$"),  # trailing ellipsis like "sk-or-v1-..."
    re.compile(r"^example", re.IGNORECASE),
    re.compile(r"^changeme$", re.IGNORECASE),
]

PLACEHOLDER_LITERALS = {
    "1234567890",
    "123456789",
    "your_telegram_id",
    "YOUR_TELEGRAM_ID",
    "0",
}


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    section: str
    message: str


@dataclass
class Report:
    config_path: str
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: str, section: str, message: str) -> None:
        self.issues.append(Issue(severity, section, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def looks_like_placeholder(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return True
    if text in PLACEHOLDER_LITERALS:
        return True
    return any(p.search(text) for p in PLACEHOLDER_PATTERNS)


def check_telegram(cfg: dict, report: Report) -> None:
    section = "telegram"
    tg = cfg.get("telegram")
    if not isinstance(tg, dict):
        report.add("error", section, "missing or not a mapping")
        return

    token = tg.get("bot_token")
    if not token:
        report.add("error", section, "bot_token is missing or empty")
    elif looks_like_placeholder(token):
        report.add("error", section, f"bot_token looks like a placeholder: {token!r}")
    elif not re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", str(token)):
        report.add(
            "warning",
            section,
            "bot_token doesn't match the typical '<digits>:<token>' shape",
        )

    user_id = tg.get("authorized_user_id")
    if user_id is None:
        report.add("error", section, "authorized_user_id is missing")
    elif not isinstance(user_id, int):
        report.add("error", section, f"authorized_user_id must be an integer, got {type(user_id).__name__}")
    elif looks_like_placeholder(user_id):
        report.add(
            "error",
            section,
            f"authorized_user_id looks like a placeholder ({user_id}); set your real Telegram user ID",
        )


def check_storage(cfg: dict, report: Report) -> None:
    section = "storage"
    data_dir = cfg.get("data_dir")
    if not data_dir:
        report.add("error", section, "data_dir is missing or empty")
    else:
        path = Path(str(data_dir)).expanduser()
        if not path.is_absolute():
            report.add(
                "warning",
                section,
                f"data_dir {data_dir!r} is relative; resolving against cwd may surprise you",
            )
        if not path.exists():
            report.add(
                "warning",
                section,
                f"data_dir {path} does not exist yet — will be created on first run",
            )

    tz = cfg.get("timezone")
    if not tz:
        report.add("error", section, "timezone is missing")
    else:
        try:
            ZoneInfo(str(tz))
        except (ZoneInfoNotFoundError, ValueError):
            report.add("error", section, f"timezone {tz!r} is not a valid IANA zone (try 'Asia/Kolkata')")


def check_ai_provider(cfg: dict, report: Report) -> None:
    section = "ai"
    ai = cfg.get("ai")
    if not isinstance(ai, dict):
        report.add("error", section, "ai is missing or not a mapping")
        return
    provider = ai.get("provider")
    if not provider:
        report.add("error", section, "ai.provider is missing")
        return
    if provider not in VALID_PROVIDERS:
        report.add(
            "error",
            section,
            f"ai.provider must be one of {sorted(VALID_PROVIDERS)}, got {provider!r}",
        )
        return

    if provider == "openrouter":
        check_openrouter(cfg, report)
    elif provider == "bedrock":
        check_bedrock(cfg, report)


def check_openrouter(cfg: dict, report: Report) -> None:
    section = "openrouter"
    block = cfg.get("openrouter")
    if not isinstance(block, dict):
        report.add("error", section, "ai.provider is openrouter but [openrouter] block is missing")
        return
    model = block.get("model")
    api_key = block.get("api_key")

    if not model:
        report.add("error", section, "openrouter.model is missing")
    elif "/" not in str(model):
        report.add(
            "warning",
            section,
            f"openrouter.model {model!r} doesn't look like a 'vendor/model' id",
        )

    if not api_key:
        report.add("error", section, "openrouter.api_key is missing")
    elif looks_like_placeholder(api_key):
        report.add("error", section, f"openrouter.api_key looks like a placeholder: {api_key!r}")
    elif not str(api_key).startswith("sk-or-"):
        report.add(
            "warning",
            section,
            "openrouter.api_key does not start with 'sk-or-' — double-check it's an OpenRouter key",
        )


def check_bedrock(cfg: dict, report: Report) -> None:
    section = "bedrock"
    block = cfg.get("bedrock")
    if not isinstance(block, dict):
        report.add("error", section, "ai.provider is bedrock but [bedrock] block is missing")
        return
    model_id = block.get("model_id")
    region = block.get("region")

    if not model_id:
        report.add("error", section, "bedrock.model_id is missing")
    elif looks_like_placeholder(model_id):
        report.add("error", section, f"bedrock.model_id looks like a placeholder: {model_id!r}")

    if not region:
        report.add("error", section, "bedrock.region is missing")
    elif not re.match(r"^[a-z]{2}-[a-z]+-\d$", str(region)):
        report.add(
            "warning",
            section,
            f"bedrock.region {region!r} does not match AWS region shape (e.g. 'us-east-1')",
        )


def check_sarvam(cfg: dict, report: Report) -> None:
    section = "sarvam"
    block = cfg.get("sarvam")
    if not isinstance(block, dict):
        report.add("error", section, "sarvam block is missing (required for voice + multilingual)")
        return
    api_key = block.get("api_key")
    if not api_key:
        report.add("error", section, "sarvam.api_key is missing")
    elif looks_like_placeholder(api_key):
        report.add("error", section, f"sarvam.api_key looks like a placeholder: {api_key!r}")


def validate(config_path: Path) -> Report:
    report = Report(config_path=str(config_path))

    if not config_path.exists():
        report.add("error", "file", f"config not found: {config_path}")
        return report

    try:
        raw = config_path.read_text()
    except OSError as e:
        report.add("error", "file", f"cannot read {config_path}: {e}")
        return report

    try:
        cfg = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        report.add("error", "file", f"YAML parse error: {e}")
        return report

    if cfg is None:
        report.add("error", "file", "config is empty")
        return report
    if not isinstance(cfg, dict):
        report.add("error", "file", f"top-level config must be a mapping, got {type(cfg).__name__}")
        return report

    check_telegram(cfg, report)
    check_storage(cfg, report)
    check_ai_provider(cfg, report)
    check_sarvam(cfg, report)

    return report


def render_text(report: Report) -> str:
    icons = {"error": "✗", "warning": "⚠", "info": "·"}
    lines = [f"Checking config: {report.config_path}", ""]

    if not report.issues:
        lines.append("✓ All checks passed.")
        return "\n".join(lines) + "\n"

    by_section: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_section.setdefault(issue.section, []).append(issue)

    for section in sorted(by_section):
        lines.append(f"[{section}]")
        for issue in by_section[section]:
            lines.append(f"  {icons[issue.severity]} {issue.message}")
        lines.append("")

    n_err, n_warn = len(report.errors), len(report.warnings)
    summary = f"{n_err} error(s), {n_warn} warning(s)."
    if report.ok:
        summary += " Config is bootable."
    else:
        summary += " Fix errors before running dhaara."
    lines.append(summary)
    return "\n".join(lines) + "\n"


def render_json(report: Report) -> str:
    return json.dumps(
        {
            "config_path": report.config_path,
            "ok": report.ok,
            "errors": [asdict(i) for i in report.errors],
            "warnings": [asdict(i) for i in report.warnings],
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a Dhaara config.yaml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    default_config = Path(__file__).resolve().parent.parent / "config.yaml"
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help=f"Path to config.yaml (default: {default_config}).",
    )
    parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = validate(args.config)
    output = render_json(report) if args.format == "json" else render_text(report)
    sys.stdout.write(output)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
