"""Tests for scripts/init.py."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import init as init_script  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(tmp_path: Path, *, data_dir: str, telos_dir: str | None = None) -> Path:
    """Write a minimal config.yaml pointing at the given paths."""
    body = textwrap.dedent(f"""\
        telegram:
          bot_token: "x"
          authorized_user_id: 1
        data_dir: "{data_dir}"
        timezone: "UTC"
        ai:
          provider: "openrouter"
        openrouter:
          model: "x/y"
          api_key: "k"
        sarvam:
          api_key: "k"
        """)
    if telos_dir is not None:
        body = body.replace(
            f'data_dir: "{data_dir}"',
            f'data_dir: "{data_dir}"\ntelos_dir: "{telos_dir}"',
        )
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body)
    return cfg


# ---------------------------------------------------------------------------
# resolve_paths
# ---------------------------------------------------------------------------

class TestResolvePaths:
    def test_explicit_telos_dir(self, tmp_path: Path):
        cfg = write_config(
            tmp_path,
            data_dir=str(tmp_path / "data"),
            telos_dir=str(tmp_path / "elsewhere" / "_telos"),
        )
        data_dir, telos_dir = init_script.resolve_paths(cfg)
        assert data_dir == (tmp_path / "data").resolve()
        assert telos_dir == (tmp_path / "elsewhere" / "_telos").resolve()

    def test_default_telos_is_sibling_underscore_telos(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        data_dir, telos_dir = init_script.resolve_paths(cfg)
        assert data_dir == (tmp_path / "data").resolve()
        assert telos_dir == (tmp_path / "_telos").resolve()

    def test_expanduser(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir="~/should-expand")
        data_dir, _ = init_script.resolve_paths(cfg)
        # Should resolve under the user's home, not include the literal ~.
        assert "~" not in str(data_dir)
        assert str(data_dir).startswith(str(Path.home()))

    def test_missing_data_dir_raises(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("timezone: UTC\n")
        with pytest.raises(ValueError, match="data_dir"):
            init_script.resolve_paths(cfg)

    def test_missing_config_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            init_script.resolve_paths(tmp_path / "nope.yaml")

    def test_non_mapping_top_level_raises(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("- a\n- b\n")
        with pytest.raises(ValueError, match="must be a mapping"):
            init_script.resolve_paths(cfg)


# ---------------------------------------------------------------------------
# run_init
# ---------------------------------------------------------------------------

class TestRunInit:
    def test_fresh_creates_everything(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        report = init_script.run_init(cfg)

        assert (tmp_path / "data").is_dir()
        assert (tmp_path / "data" / "journal").is_dir()
        assert (tmp_path / "_telos").is_dir()
        assert (tmp_path / "_telos" / "work.md").exists()
        assert (tmp_path / "_telos" / "personal.md").exists()

        assert report.created_count == 5
        assert report.existed_count == 0

    def test_idempotent_rerun(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        init_script.run_init(cfg)  # first run
        # Edit a TELOS file to make sure we don't overwrite the user's content.
        custom = "# my custom telos\n- ship dhaara phase 2\n"
        (tmp_path / "_telos" / "work.md").write_text(custom)

        report = init_script.run_init(cfg)
        assert report.created_count == 0
        assert report.existed_count == 5
        # Custom content preserved.
        assert (tmp_path / "_telos" / "work.md").read_text() == custom

    def test_dry_run_does_not_touch_disk(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        report = init_script.run_init(cfg, dry_run=True)

        assert not (tmp_path / "data").exists()
        assert not (tmp_path / "_telos").exists()
        # Every action should be flagged as would-create
        assert all(a.status == "would-create" for a in report.actions)
        assert report.dry_run is True

    def test_partial_existing_dirs(self, tmp_path: Path):
        # data_dir already exists from elsewhere; init.py shouldn't fail.
        (tmp_path / "data").mkdir()
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        report = init_script.run_init(cfg)
        # data_dir was already there → "exists"; the other 4 are new.
        kinds = [a.status for a in report.actions]
        assert kinds.count("exists") == 1
        assert kinds.count("created") == 4

    def test_seeds_match_canonical_examples(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        init_script.run_init(cfg)

        from src.context.telos import TELOS_EXAMPLE_PERSONAL, TELOS_EXAMPLE_WORK
        assert (tmp_path / "_telos" / "work.md").read_text() == TELOS_EXAMPLE_WORK
        assert (tmp_path / "_telos" / "personal.md").read_text() == TELOS_EXAMPLE_PERSONAL


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_dry_run_banner(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        report = init_script.run_init(cfg, dry_run=True)
        out = init_script.render_text(report)
        assert out.startswith("Dry run")
        assert "would be created" in out

    def test_first_run_summary(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        report = init_script.run_init(cfg)
        out = init_script.render_text(report)
        assert "Created 5 item(s)" in out
        assert "Edit your TELOS files" in out

    def test_already_initialized_summary(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        init_script.run_init(cfg)
        report = init_script.run_init(cfg)
        out = init_script.render_text(report)
        assert "Already initialized" in out


class TestRenderJson:
    def test_round_trip_with_counts(self, tmp_path: Path):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        report = init_script.run_init(cfg)
        payload = json.loads(init_script.render_json(report))
        assert payload["created_count"] == 5
        assert payload["existed_count"] == 0
        assert len(payload["actions"]) == 5
        assert payload["dry_run"] is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_first_run_default_text(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        rc = init_script.main(["--config", str(cfg)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Created 5 item(s)" in out

    def test_dry_run_does_not_create(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        rc = init_script.main(["--config", str(cfg), "--dry-run"])
        assert rc == 0
        assert not (tmp_path / "data").exists()
        assert "would be created" in capsys.readouterr().out

    def test_json_format(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        cfg = write_config(tmp_path, data_dir=str(tmp_path / "data"))
        rc = init_script.main(["--config", str(cfg), "-f", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["created_count"] == 5

    def test_missing_config_returns_2(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        rc = init_script.main(["--config", str(tmp_path / "nope.yaml")])
        assert rc == 2
        err = capsys.readouterr().err
        assert "config not found" in err

    def test_invalid_config_returns_2(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("- not: a mapping\n")
        rc = init_script.main(["--config", str(cfg)])
        assert rc == 2
        assert "invalid config" in capsys.readouterr().err

    def test_missing_data_dir_returns_2(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("timezone: UTC\n")
        rc = init_script.main(["--config", str(cfg)])
        assert rc == 2
        assert "invalid config" in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
