"""Tests for scripts/check_config.py."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import check_config  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CONFIG = textwrap.dedent("""\
    telegram:
      bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"
      authorized_user_id: 555111222

    data_dir: "{data_dir}"
    timezone: "Asia/Kolkata"

    ai:
      provider: "openrouter"

    openrouter:
      model: "anthropic/claude-sonnet-4.5"
      api_key: "sk-or-v1-abcdef0123456789abcdef0123456789"

    sarvam:
      api_key: "sk_test_realsarvamkey_abcdef"
    """)


@pytest.fixture
def good_config_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(VALID_CONFIG.format(data_dir=str(data_dir)))
    return cfg


def write_yaml(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body)
    return cfg


# ---------------------------------------------------------------------------
# Placeholder detector
# ---------------------------------------------------------------------------

class TestLooksLikePlaceholder:
    @pytest.mark.parametrize("value", [
        "YOUR_BOT_TOKEN",
        "YOUR_OPENROUTER_API_KEY",
        "your_telegram_id",
        "sk-or-v1-...",
        "example",
        "ChangeMe",
        "1234567890",
        "0",
        "",
        None,
    ])
    def test_flags_placeholders(self, value):
        if value is None:
            assert check_config.looks_like_placeholder(None) is False
        else:
            assert check_config.looks_like_placeholder(value), f"should flag {value!r}"

    @pytest.mark.parametrize("value", [
        "8123456789:AABBccDDeeFFgg",
        "sk-or-v1-realkeyhereabc123",
        "anthropic/claude-sonnet-4.5",
        555111222,
    ])
    def test_passes_real_values(self, value):
        assert not check_config.looks_like_placeholder(value)


# ---------------------------------------------------------------------------
# Top-level validate()
# ---------------------------------------------------------------------------

class TestValidate:
    def test_complete_config_passes(self, good_config_path: Path):
        report = check_config.validate(good_config_path)
        assert report.ok
        assert report.errors == []

    def test_missing_file(self, tmp_path: Path):
        report = check_config.validate(tmp_path / "nope.yaml")
        assert not report.ok
        assert any("not found" in i.message for i in report.errors)

    def test_unparseable_yaml(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "telegram: [unclosed bracket")
        report = check_config.validate(cfg)
        assert not report.ok
        assert any("YAML parse error" in i.message for i in report.errors)

    def test_empty_config(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "")
        report = check_config.validate(cfg)
        assert any("empty" in i.message for i in report.errors)

    def test_non_mapping_top_level(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "- a\n- b\n")
        report = check_config.validate(cfg)
        assert any("must be a mapping" in i.message for i in report.errors)


# ---------------------------------------------------------------------------
# Telegram block
# ---------------------------------------------------------------------------

class TestTelegram:
    def test_missing_bot_token(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace('bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"', 'bot_token: ""'))
        report = check_config.validate(cfg)
        assert any("bot_token is missing" in i.message for i in report.errors)

    def test_placeholder_bot_token(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace('bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"', 'bot_token: "YOUR_BOT_TOKEN"'))
        report = check_config.validate(cfg)
        assert any("placeholder" in i.message for i in report.errors)

    def test_oddly_shaped_bot_token_warns(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace('bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"', 'bot_token: "wrongshape"'))
        report = check_config.validate(cfg)
        assert any("typical" in i.message for i in report.warnings)
        # But still bootable — only a warning
        assert report.ok

    def test_user_id_placeholder(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace("authorized_user_id: 555111222", "authorized_user_id: 1234567890"))
        report = check_config.validate(cfg)
        assert any("authorized_user_id" in i.message and "placeholder" in i.message for i in report.errors)

    def test_user_id_not_int(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace("authorized_user_id: 555111222", 'authorized_user_id: "abc"'))
        report = check_config.validate(cfg)
        assert any("must be an integer" in i.message for i in report.errors)


# ---------------------------------------------------------------------------
# Storage block
# ---------------------------------------------------------------------------

class TestStorage:
    def test_missing_data_dir(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "data_dir: ''\ntimezone: 'UTC'\n")
        report = check_config.validate(cfg)
        assert any("data_dir is missing" in i.message for i in report.errors)

    def test_relative_data_dir_warns(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "data_dir: 'relative/path'\ntimezone: 'UTC'\n")
        report = check_config.validate(cfg)
        assert any("relative" in i.message for i in report.warnings)

    def test_nonexistent_data_dir_warns(self, tmp_path: Path):
        target = tmp_path / "nope"
        cfg = write_yaml(tmp_path, f"data_dir: '{target}'\ntimezone: 'UTC'\n")
        report = check_config.validate(cfg)
        assert any("does not exist yet" in i.message for i in report.warnings)

    def test_invalid_timezone(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, f"data_dir: '{tmp_path}'\ntimezone: 'Mars/Phobos'\n")
        report = check_config.validate(cfg)
        assert any("not a valid IANA zone" in i.message for i in report.errors)

    def test_missing_timezone(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, f"data_dir: '{tmp_path}'\n")
        report = check_config.validate(cfg)
        assert any("timezone is missing" in i.message for i in report.errors)


# ---------------------------------------------------------------------------
# AI provider routing
# ---------------------------------------------------------------------------

class TestAiProvider:
    def test_unknown_provider(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace('provider: "openrouter"', 'provider: "anthropic"'))
        report = check_config.validate(cfg)
        assert any("must be one of" in i.message for i in report.errors)

    def test_missing_provider(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace('  provider: "openrouter"', '  provider: ""'))
        report = check_config.validate(cfg)
        assert any("ai.provider is missing" in i.message for i in report.errors)

    def test_provider_block_missing(self, tmp_path: Path):
        # provider is openrouter but no openrouter: block
        body = textwrap.dedent(f"""\
            telegram:
              bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"
              authorized_user_id: 555111222
            data_dir: "{tmp_path}"
            timezone: "UTC"
            ai:
              provider: "openrouter"
            sarvam:
              api_key: "sk_test_realsarvamkey"
            """)
        cfg = write_yaml(tmp_path, body)
        report = check_config.validate(cfg)
        assert any("[openrouter] block is missing" in i.message for i in report.errors)


class TestOpenRouter:
    def test_placeholder_api_key(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace(
            'api_key: "sk-or-v1-abcdef0123456789abcdef0123456789"',
            'api_key: "YOUR_OPENROUTER_API_KEY"',
        ))
        report = check_config.validate(cfg)
        assert any("openrouter.api_key" in i.message and "placeholder" in i.message for i in report.errors)

    def test_wrong_prefix_warns(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace(
            'api_key: "sk-or-v1-abcdef0123456789abcdef0123456789"',
            'api_key: "anthropic-real-key-here"',
        ))
        report = check_config.validate(cfg)
        assert any("does not start with 'sk-or-'" in i.message for i in report.warnings)

    def test_model_without_slash_warns(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace(
            'model: "anthropic/claude-sonnet-4.5"',
            'model: "claude"',
        ))
        report = check_config.validate(cfg)
        assert any("vendor/model" in i.message for i in report.warnings)


class TestBedrock:
    def _bedrock_config(self, tmp_path: Path, **overrides) -> Path:
        defaults = {
            "model_id": "us.amazon.nova-pro-v1:0",
            "region": "us-east-1",
        }
        defaults.update(overrides)
        body = textwrap.dedent(f"""\
            telegram:
              bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"
              authorized_user_id: 555111222
            data_dir: "{tmp_path}"
            timezone: "UTC"
            ai:
              provider: "bedrock"
            bedrock:
              model_id: "{defaults['model_id']}"
              region: "{defaults['region']}"
            sarvam:
              api_key: "sk_test_realsarvamkey"
            """)
        return write_yaml(tmp_path, body)

    def test_complete_bedrock_passes(self, tmp_path: Path):
        cfg = self._bedrock_config(tmp_path)
        report = check_config.validate(cfg)
        assert report.ok

    def test_bad_region_warns(self, tmp_path: Path):
        cfg = self._bedrock_config(tmp_path, region="not-a-region")
        report = check_config.validate(cfg)
        assert any("does not match AWS region shape" in i.message for i in report.warnings)

    def test_missing_model_id(self, tmp_path: Path):
        cfg = self._bedrock_config(tmp_path, model_id="")
        report = check_config.validate(cfg)
        assert any("bedrock.model_id is missing" in i.message for i in report.errors)


# ---------------------------------------------------------------------------
# Sarvam
# ---------------------------------------------------------------------------

class TestSarvam:
    def test_missing_block(self, tmp_path: Path):
        body = textwrap.dedent(f"""\
            telegram:
              bot_token: "8123456789:AABBccDDeeFFggHHiijjKKllMMnnOOppQQ"
              authorized_user_id: 555111222
            data_dir: "{tmp_path}"
            timezone: "UTC"
            ai:
              provider: "openrouter"
            openrouter:
              model: "anthropic/claude-sonnet-4.5"
              api_key: "sk-or-v1-realkey"
            """)
        cfg = write_yaml(tmp_path, body)
        report = check_config.validate(cfg)
        assert any("sarvam block is missing" in i.message for i in report.errors)

    def test_placeholder_key(self, good_config_path: Path):
        cfg = good_config_path
        cfg.write_text(cfg.read_text().replace(
            'api_key: "sk_test_realsarvamkey_abcdef"',
            'api_key: "YOUR_SARVAM_API_KEY"',
        ))
        report = check_config.validate(cfg)
        assert any("sarvam.api_key" in i.message and "placeholder" in i.message for i in report.errors)


# ---------------------------------------------------------------------------
# Renderers + CLI
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_passing_message(self, good_config_path: Path):
        report = check_config.validate(good_config_path)
        out = check_config.render_text(report)
        assert "All checks passed" in out

    def test_failing_message(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "telegram: {}\n")
        report = check_config.validate(cfg)
        out = check_config.render_text(report)
        assert "error(s)" in out
        assert "Fix errors" in out


class TestRenderJson:
    def test_shape(self, good_config_path: Path):
        report = check_config.validate(good_config_path)
        payload = json.loads(check_config.render_json(report))
        assert payload["ok"] is True
        assert payload["errors"] == []

    def test_failing_shape(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "telegram: {}\n")
        report = check_config.validate(cfg)
        payload = json.loads(check_config.render_json(report))
        assert payload["ok"] is False
        assert all({"severity", "section", "message"} <= e.keys() for e in payload["errors"])


class TestCli:
    def test_exit_zero_on_pass(self, good_config_path: Path, capsys: pytest.CaptureFixture):
        rc = check_config.main(["--config", str(good_config_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "All checks passed" in out

    def test_exit_one_on_fail(self, tmp_path: Path):
        cfg = write_yaml(tmp_path, "telegram: {}\n")
        rc = check_config.main(["--config", str(cfg)])
        assert rc == 1

    def test_json_format(self, good_config_path: Path, capsys: pytest.CaptureFixture):
        rc = check_config.main(["--config", str(good_config_path), "-f", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
