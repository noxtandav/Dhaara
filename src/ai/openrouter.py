"""
OpenRouter client wrapper.

OpenRouter exposes an OpenAI-compatible chat-completions API at
https://openrouter.ai/api/v1, giving access to Anthropic, OpenAI, Google,
Mistral, Meta, DeepSeek, Qwen, etc. through a single API key.

The rest of Dhaara (agent loop, prompts, tool specs) is written against the
Bedrock Converse shape. To avoid touching the agent, this client translates:
  - incoming Bedrock-shaped messages/tools  →  OpenAI chat-completions request
  - OpenAI response                         →  Bedrock-shaped response dict

So callers see the same `output.message.content` blocks, `stopReason`, and
`toolUse` shape they'd get from Bedrock.

Model IDs follow OpenRouter's `<vendor>/<model>` convention, e.g.
  anthropic/claude-sonnet-4.5
  openai/gpt-4o
  google/gemini-2.5-pro
  meta-llama/llama-3.3-70b-instruct
The chosen model must support function/tool calling — Dhaara requires it.
"""
import json
import logging

import httpx

from .provider import AIProvider

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient(AIProvider):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = _OPENROUTER_URL,
        referer: str | None = None,
        app_title: str | None = None,
        timeout: float = 120.0,
    ):
        self.model = model
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        # OpenRouter uses these optional headers for attribution / ranking.
        self._extra_headers: dict[str, str] = {}
        if referer:
            self._extra_headers["HTTP-Referer"] = referer
        if app_title:
            self._extra_headers["X-Title"] = app_title

    def converse(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        oai_messages = [{"role": "system", "content": system_prompt}]
        oai_messages.extend(_bedrock_messages_to_openai(messages))

        payload: dict = {
            "model": self.model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [_bedrock_tool_to_openai(t) for t in tools]
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        try:
            resp = httpx.post(
                self._base_url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text
            raise RuntimeError(
                f"OpenRouter HTTP {e.response.status_code}: {body}"
            ) from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"OpenRouter request failed: {e}") from e

        return _openai_response_to_bedrock(data)

    def extract_text(self, response: dict) -> str:
        content = response.get("output", {}).get("message", {}).get("content", [])
        return "\n".join(b["text"] for b in content if "text" in b)

    def extract_tool_uses(self, response: dict) -> list[dict]:
        content = response.get("output", {}).get("message", {}).get("content", [])
        return [b["toolUse"] for b in content if "toolUse" in b]

    def stop_reason(self, response: dict) -> str:
        return response.get("stopReason", "end_turn")


def _bedrock_tool_to_openai(tool: dict) -> dict:
    spec = tool["toolSpec"]
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "parameters": spec["inputSchema"]["json"],
        },
    }


def _bedrock_messages_to_openai(messages: list[dict]) -> list[dict]:
    """
    Flatten Bedrock content blocks into OpenAI chat messages.
    A single Bedrock 'user' turn may carry multiple toolResult blocks; OpenAI
    requires one 'tool' message per tool_call_id, so we fan them out.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        blocks = msg.get("content", [])

        if role == "assistant":
            text_parts = [b["text"] for b in blocks if "text" in b]
            tool_uses = [b["toolUse"] for b in blocks if "toolUse" in b]
            oai_msg: dict = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_uses:
                oai_msg["tool_calls"] = [
                    {
                        "id": tu["toolUseId"],
                        "type": "function",
                        "function": {
                            "name": tu["name"],
                            "arguments": json.dumps(tu.get("input", {})),
                        },
                    }
                    for tu in tool_uses
                ]
            out.append(oai_msg)
            continue

        # user turn: may contain text and/or toolResult blocks
        tool_results = [b["toolResult"] for b in blocks if "toolResult" in b]
        text_parts = [b["text"] for b in blocks if "text" in b]

        if tool_results:
            for tr in tool_results:
                result_text = "\n".join(
                    c["text"] for c in tr.get("content", []) if "text" in c
                )
                out.append({
                    "role": "tool",
                    "tool_call_id": tr["toolUseId"],
                    "content": result_text,
                })
            if text_parts:
                out.append({"role": "user", "content": "\n".join(text_parts)})
        else:
            out.append({"role": "user", "content": "\n".join(text_parts)})

    return out


def _openai_response_to_bedrock(data: dict) -> dict:
    """Wrap an OpenAI chat-completions response in Bedrock Converse shape."""
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {data}")

    choice = choices[0]
    msg = choice.get("message", {}) or {}
    finish = choice.get("finish_reason", "stop")

    content_blocks: list[dict] = []
    text = msg.get("content")
    if text:
        content_blocks.append({"text": text})

    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {}) or {}
        raw_args = fn.get("arguments", "") or "{}"
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            logger.warning("OpenRouter returned non-JSON tool args: %r", raw_args)
            parsed = {}
        content_blocks.append({
            "toolUse": {
                "toolUseId": tc.get("id", ""),
                "name": fn.get("name", ""),
                "input": parsed,
            },
        })

    stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"

    return {
        "output": {"message": {"content": content_blocks}},
        "stopReason": stop_reason,
    }
