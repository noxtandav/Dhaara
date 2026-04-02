"""
AWS Bedrock client wrapper.
Uses a named AWS profile if specified, otherwise falls back to boto3's
default credential chain (env vars, ~/.aws/credentials default profile, IAM role, etc.).

We use the Bedrock Converse API, which is a unified interface across all models.
AWS normalizes message format, system prompts, and tool use internally — you do NOT
need model-specific prompt templates (no <|system|> tokens, no [INST] tags, etc.).

IMPORTANT — Inference Profiles:
  Newer generation models on Bedrock are only available via cross-region inference
  profiles, NOT via bare model IDs. Using the bare model ID will give:
    "Invocation of model ID X with on-demand throughput isn't supported"

  The profile ID is just a prefixed version of the model ID:
    global.<model_id>   — routes across all commercial AWS regions
    us.<model_id>       — routes within US regions only
    eu.<model_id>       — routes within EU regions only

  Older models (Nova, some Anthropic) can still be called with the bare ID or us. prefix.
  See config.example.yaml for the correct IDs to use.

Dhaara requires: system prompts + tool use + multi-turn conversation.

Models that do NOT support tool use (will error at startup):
  amazon.titan-*, deepseek.*, meta.llama2-*, meta.llama3-2-1b-*, meta.llama3-2-3b-*,
  mistral.mistral-7b-*, mistral.mistral-small-2402-*, ai21.j2-*, cohere.command-text-*,
  cohere.command-light-*
"""
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Model ID substrings that are known to NOT support tool use.
# Raises ValueError at startup rather than failing mid-conversation.
_NO_TOOL_USE_PATTERNS = [
    "titan",
    "deepseek",
    "llama-2",
    "llama2",
    "llama3-2-1b",
    "llama3-2-3b",
    "mistral-7b",
    "mistral-small-2402",   # old Mistral Small; newer ministral-* models do support tools
    "jurassic",
    "j2-",
    "cohere.command-text",
    "cohere.command-light",
]

# Models that don't support system prompts
_NO_SYSTEM_PROMPT_PATTERNS = [
    "titan",
    "mistral-7b",
    "jurassic",
    "j2-",
]


def check_model_compatibility(model_id: str) -> None:
    """
    Raise ValueError at startup if the model doesn't support tool use (required by Dhaara).
    Warn if system prompt support is uncertain.
    Strips inference profile prefixes (global./us./eu.) before checking.
    """
    # Strip inference profile prefix before pattern matching
    model_lower = model_id.lower()
    for prefix in ("global.", "us.", "eu."):
        if model_lower.startswith(prefix):
            model_lower = model_lower[len(prefix):]
            break

    no_tools = any(p in model_lower for p in _NO_TOOL_USE_PATTERNS)
    no_system = any(p in model_lower for p in _NO_SYSTEM_PROMPT_PATTERNS)

    if no_tools:
        raise ValueError(
            f"Model '{model_id}' does not support tool use, which Dhaara requires.\n"
            "Recommended models: anthropic.claude-sonnet-4-6, "
            "amazon.nova-lite-v1:0, amazon.nova-pro-v1:0, "
            "anthropic.claude-haiku-4-5-20251001-v1:0\n"
            "Full list: https://docs.aws.amazon.com/bedrock/latest/userguide/"
            "conversation-inference-supported-models-features.html"
        )
    if no_system:
        logger.warning(
            f"Model '{model_id}' may not support system prompts. "
            "Dhaara uses a system prompt for its instructions — behaviour may be degraded."
        )


class BedrockClient:
    def __init__(self, model_id: str, region: str = "us-east-1", aws_profile: str | None = None):
        self.model_id = model_id
        check_model_compatibility(model_id)
        session = boto3.Session(profile_name=aws_profile, region_name=region)
        self._client = session.client("bedrock-runtime")

    def converse(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Call Bedrock Converse API.

        messages: list of {"role": "user"|"assistant", "content": [{"text": "..."}]}
        system_prompt: injected as system turn
        tools: Bedrock tool spec list
        Returns raw Bedrock response dict.
        """
        kwargs = {
            "modelId": self.model_id,
            "messages": messages,
            "system": [{"text": system_prompt}],
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}

        try:
            response = self._client.converse(**kwargs)
            return response
        except ClientError as e:
            code = e.response["Error"]["Code"]
            msg = e.response["Error"]["Message"]
            # Newer models require an inference profile ID (global./us. prefix),
            # not the bare model ID. Give the user a clear fix.
            if code == "ValidationException" and "inference profile" in msg.lower():
                raise RuntimeError(
                    f"Model '{self.model_id}' requires an inference profile ID.\n"
                    f"Change model_id in config.yaml to use the correct prefix, e.g.:\n"
                    f"  global.{self.model_id}  (routes across all AWS regions)\n"
                    f"  us.{self.model_id}       (routes within US regions only)\n"
                    f"See config.example.yaml for the full list of correct IDs."
                ) from e
            raise RuntimeError(f"Bedrock error [{code}]: {msg}") from e

    def extract_text(self, response: dict) -> str:
        """Extract plain text from a Bedrock converse response."""
        content = response.get("output", {}).get("message", {}).get("content", [])
        parts = [block["text"] for block in content if "text" in block]
        return "\n".join(parts)

    def extract_tool_uses(self, response: dict) -> list[dict]:
        """
        Extract tool use blocks from a Bedrock converse response.
        Returns list of {"toolUseId": str, "name": str, "input": dict}
        """
        content = response.get("output", {}).get("message", {}).get("content", [])
        return [block["toolUse"] for block in content if "toolUse" in block]

    def stop_reason(self, response: dict) -> str:
        """Return stop reason: 'end_turn', 'tool_use', etc."""
        return response.get("stopReason", "end_turn")
