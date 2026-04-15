"""
Load and validate Dhaara configuration from config.yaml.
"""
import os
from pathlib import Path
from dataclasses import dataclass

import yaml


@dataclass
class TelegramConfig:
    bot_token: str
    authorized_user_id: int


@dataclass
class BedrockConfig:
    model_id: str
    region: str
    aws_profile: str | None  # None = use default boto3 credential chain


@dataclass
class OpenRouterConfig:
    model: str
    api_key: str
    referer: str | None       # optional, sent as HTTP-Referer header
    app_title: str | None     # optional, sent as X-Title header


@dataclass
class SarvamConfig:
    api_key: str


@dataclass
class Config:
    telegram: TelegramConfig
    ai_provider: str  # "bedrock" or "openrouter"
    bedrock: BedrockConfig | None
    openrouter: OpenRouterConfig | None
    sarvam: SarvamConfig
    data_dir: Path
    telos_dir: Path
    timezone: str


_VALID_PROVIDERS = {"bedrock", "openrouter"}


def load_config(config_path: str | Path | None = None) -> Config:
    """
    Load config.yaml from the given path or from the project root.
    Raises ValueError if required fields are missing.
    """
    if config_path is None:
        # Default: config.yaml next to this project's root
        config_path = Path(__file__).parent.parent / "config.yaml"

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"config.yaml not found at {config_path}. "
            "Copy config.example.yaml to config.yaml and fill in your values."
        )

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Telegram
    tg = raw.get("telegram", {})
    if not tg.get("bot_token"):
        raise ValueError("telegram.bot_token is required in config.yaml")
    if not tg.get("authorized_user_id"):
        raise ValueError("telegram.authorized_user_id is required in config.yaml")

    # AI provider selection — default "bedrock" for backwards compatibility
    provider = (raw.get("ai", {}) or {}).get("provider", "bedrock")
    if provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"ai.provider must be one of {sorted(_VALID_PROVIDERS)}, got '{provider}'"
        )

    bedrock_cfg: BedrockConfig | None = None
    openrouter_cfg: OpenRouterConfig | None = None

    if provider == "bedrock":
        bd = raw.get("bedrock", {})
        if not bd.get("model_id"):
            raise ValueError("bedrock.model_id is required when ai.provider=bedrock")
        bedrock_cfg = BedrockConfig(
            model_id=bd["model_id"],
            region=bd.get("region", "us-east-1"),
            aws_profile=bd.get("aws_profile"),
        )
    else:  # openrouter
        orr = raw.get("openrouter", {})
        if not orr.get("model"):
            raise ValueError("openrouter.model is required when ai.provider=openrouter")
        if not orr.get("api_key"):
            raise ValueError("openrouter.api_key is required when ai.provider=openrouter")
        openrouter_cfg = OpenRouterConfig(
            model=orr["model"],
            api_key=orr["api_key"],
            referer=orr.get("referer"),
            app_title=orr.get("app_title"),
        )

    # Sarvam
    sv = raw.get("sarvam", {})
    if not sv.get("api_key"):
        raise ValueError("sarvam.api_key is required in config.yaml")

    # Data dir
    data_dir_raw = raw.get("data_dir", "~/PAI/DhaaraData")
    data_dir = Path(os.path.expanduser(data_dir_raw))

    # Telos dir — shared across all PAI agents, lives in the parent data root.
    # Can be overridden via config; defaults to <data_dir>/../_telos
    telos_dir_raw = raw.get("telos_dir")
    if telos_dir_raw:
        telos_dir = Path(os.path.expanduser(telos_dir_raw))
    else:
        telos_dir = data_dir.parent / "_telos"

    # Timezone (default: Asia/Kolkata)
    tz_name = raw.get("timezone", "Asia/Kolkata")

    return Config(
        telegram=TelegramConfig(
            bot_token=tg["bot_token"],
            authorized_user_id=int(tg["authorized_user_id"]),
        ),
        ai_provider=provider,
        bedrock=bedrock_cfg,
        openrouter=openrouter_cfg,
        sarvam=SarvamConfig(api_key=sv["api_key"]),
        data_dir=data_dir,
        telos_dir=telos_dir,
        timezone=tz_name,
    )
