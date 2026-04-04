"""
Silo discovery, creation, and validation.
Silos are directories under data_dir, each registered in _config/silos.yaml.
"""
from pathlib import Path

import yaml

DEFAULT_SILOS = [
    {"name": "Work", "description": "Professional tasks, projects, work-related activities and reflections — things you'd discuss in a work 1:1"},
    {"name": "Personal", "description": "Everything else — meals, health, emotions, money, sleep, habits, friendships, hobbies, leisure, travel, family"},
]


def _config_path(data_dir: Path) -> Path:
    return data_dir / "_config" / "silos.yaml"


def init_data_dir(data_dir: Path) -> None:
    """
    Create the data directory structure if it doesn't exist.
    Creates _config/, _telos/, and journal/ directories.
    """
    (data_dir / "_config").mkdir(parents=True, exist_ok=True)
    (data_dir / "_telos").mkdir(parents=True, exist_ok=True)
    (data_dir / "journal").mkdir(parents=True, exist_ok=True)

    cfg = _config_path(data_dir)
    if not cfg.exists():
        with open(cfg, "w") as f:
            yaml.dump({"silos": DEFAULT_SILOS}, f, default_flow_style=False)
