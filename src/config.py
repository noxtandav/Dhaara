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
class SarvamConfig:
    api_key: str


@dataclass
class Config:
    telegram: TelegramConfig
    bedrock: BedrockConfig
    sarvam: SarvamConfig
    data_dir: Path
    timezone: str


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

    # Bedrock
    bd = raw.get("bedrock", {})
    if not bd.get("model_id"):
        raise ValueError("bedrock.model_id is required in config.yaml")

    # Sarvam
    sv = raw.get("sarvam", {})
    if not sv.get("api_key"):
        raise ValueError("sarvam.api_key is required in config.yaml")

    # Data dir
    data_dir_raw = raw.get("data_dir", "~/PAI/DhaaraData")
    data_dir = Path(os.path.expanduser(data_dir_raw))

    # Timezone (default: Asia/Kolkata)
    tz_name = raw.get("timezone", "Asia/Kolkata")

    return Config(
        telegram=TelegramConfig(
            bot_token=tg["bot_token"],
            authorized_user_id=int(tg["authorized_user_id"]),
        ),
        bedrock=BedrockConfig(
            model_id=bd["model_id"],
            region=bd.get("region", "us-east-1"),
            aws_profile=bd.get("aws_profile"),  # optional, None = default profile
        ),
        sarvam=SarvamConfig(api_key=sv["api_key"]),
        data_dir=data_dir,
        timezone=tz_name,
    )
