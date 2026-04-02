"""
Silo discovery, creation, and validation.
Silos are directories under data_dir, each registered in _config/silos.yaml.
"""
from pathlib import Path

import yaml

DEFAULT_SILOS = [
    {"name": "Work", "description": "Professional tasks, projects, work-related activities and reflections"},
    {"name": "Personal", "description": "Personal life events, relationships, reflections, health"},
    {"name": "Habits", "description": "Habit tracking - exercise, reading, sleep, routines"},
    {"name": "Finance", "description": "Expenses, income, financial transactions and notes"},
]


def _config_path(data_dir: Path) -> Path:
    return data_dir / "_config" / "silos.yaml"


def init_data_dir(data_dir: Path) -> None:
    """
    Create the data directory structure if it doesn't exist.
    Creates _config/, _telos/, and default silo folders.
    """
    (data_dir / "_config").mkdir(parents=True, exist_ok=True)
    (data_dir / "_telos").mkdir(parents=True, exist_ok=True)

    cfg = _config_path(data_dir)
    if not cfg.exists():
        with open(cfg, "w") as f:
            yaml.dump({"silos": DEFAULT_SILOS}, f, default_flow_style=False)

    # Create default silo directories
    for silo in DEFAULT_SILOS:
        (data_dir / silo["name"]).mkdir(exist_ok=True)


def list_silos(data_dir: Path) -> list[dict]:
    """Return list of silo dicts: [{name, description}, ...]"""
    cfg = _config_path(data_dir)
    if not cfg.exists():
        return []
    with open(cfg) as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("silos", [])


def get_silo_names(data_dir: Path) -> list[str]:
    return [s["name"] for s in list_silos(data_dir)]


def silo_exists(data_dir: Path, name: str) -> bool:
    return name.lower() in [s["name"].lower() for s in list_silos(data_dir)]


def create_silo(data_dir: Path, name: str, description: str) -> None:
    """
    Create a new silo: make the directory and register it in silos.yaml.
    Raises ValueError if silo already exists.
    """
    if silo_exists(data_dir, name):
        raise ValueError(f"Silo '{name}' already exists.")

    # Sanitize name: only allow alphanumeric, spaces, hyphens, underscores
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_name:
        raise ValueError(f"Invalid silo name: '{name}'")

    (data_dir / safe_name).mkdir(exist_ok=True)

    silos = list_silos(data_dir)
    silos.append({"name": safe_name, "description": description})

    cfg = _config_path(data_dir)
    with open(cfg, "w") as f:
        yaml.dump({"silos": silos}, f, default_flow_style=False)
