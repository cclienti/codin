# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Anthropic LLM provider with prompt caching support.

Cache strategy (inspired by ECA):
  - System prompt blocks get cache_control to cache the static context.
  - The last user message gets cache_control to cache the growing conversation.

Pricing (claude-sonnet-4-5):
  Input:        $3.00 / MTok
  Output:       $15.00 / MTok
  Cache write:  $3.75 / MTok
  Cache read:   $0.30 / MTok  (10x cheaper than input)
"""

import json
import os
import requests

from pathlib import Path
from tabulate import tabulate
from typing import List, Optional

from ..term_output import Output, StreamingSpinner
from .base import BaseLLMClient, RequestInterrupted, ContextWindowExceeded


# ---------------------------------------------------------------------------
# Known Anthropic models with context windows
# ---------------------------------------------------------------------------

_ANTHROPIC_MODELS = {
    "claude-opus-4-5":   {"context": 200_000, "vendor": "Anthropic"},
    "claude-sonnet-4-5": {"context": 200_000, "vendor": "Anthropic"},
    "claude-haiku-3-5":  {"context": 200_000, "vendor": "Anthropic"},
    "claude-opus-4-0":   {"context": 200_000, "vendor": "Anthropic"},
    "claude-sonnet-4-0": {"context": 200_000, "vendor": "Anthropic"},
    "claude-haiku-3-0":  {"context": 200_000, "vendor": "Anthropic"},
}

_DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicClient(BaseLLMClient):
    """
    LLM client using Anthropic's API with prompt caching support.

    Caching follows ECA's strategy:
    - cache_control on system prompt blocks (static context, rarely changes)
    - cache_control on the last user message (captures growing conversation prefix)

    With 200K context window:
    - Cache writes:  $3.75/MTok (first request or cache miss)
    - Cache reads:   $0.30/MTok (subsequent requests — 10x cheaper than input)
    """

    CONFIG_PATH = Path.home() / ".config" / "codin"
    API_KEY_FILE = CONFIG_PATH / "anthropic.json"
    API_BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"
    # 1h TTL is only honored when hitting api.anthropic.com directly
    CACHE_TTL = "1h"

    def __init__(self, system_prompt: str, api_key: Optional[str] = None) -> None:
        super().__init__(system_prompt)
        self.model_id = _DEFAULT_MODEL
        self._api_key: Optional[str] = api_key
        if not self._api_key:
            self._load_api_key()
        self._load_model_from_disk()

    # ------------------------------------------------------------------
    # API key management
    # ------------------------------------------------------------------

    def _load_api_key(self) -> None:
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            self._api_key = env_key
            Output.success("Anthropic API key loaded from ANTHROPIC_API_KEY env var.")
            return

        if self.API_KEY_FILE.exists():
            try:
                data = json.loads(self.API_KEY_FILE.read_text())
                self._api_key = data.get("api_key")
                if self._api_key:
                    Output.success("Anthropic API key loaded from disk.")
                    return
            except Exception as e:
                Output.warning(f"Could not load Anthropic API key: {e}")

        Output.warning(
            "No Anthropic API key found. "
            "Set ANTHROPIC_API_KEY env var or use 'set-anthropic-key <key>'."
        )

    def save_api_key(self, api_key: str) -> None:
        self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        self.API_KEY_FILE.write_text(json.dumps({"api_key": api_key}, indent=2))
        self._api_key = api_key
        Output.success(f"Anthropic API key saved to {self.API_KEY_FILE}")

    # ------------------------------------------------------------------
    # Cache control helpers (ECA-inspired)
    # ------------------------------------------------------------------

    def _cache_control(self) -> dict:
        return {"type": "ephemeral", "ttl": self.CACHE_TTL}

    def _build_system_blocks(self) -> List[dict]:
        """System prompt as cacheable content blocks."""
        return [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": self._cache_control(),
            }
        ]

    def _add_cache_to_last_message(self, messages: List[dict]) -> List[dict]:
        """
        Add cache_control to the last user message.
        This caches the conversation prefix, making subsequent requests cheaper.
        """
        if not messages:
            return messages

        messages = list(messages)
        last = messages[-1]
        content = last.get("content", "")

        if isinstance(content, str):
            messages[-1] = {
                **last,
                "content": [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": self._cache_control(),
                    }
                ],
            }
        elif isinstance(content, list) and content:
            new_content = list(content)
            new_content[-1] = {**new_content[-1], "cache_control": self._cache_control()}
            messages[-1] = {**last, "content": new_content}

        return messages

    # ------------------------------------------------------------------
    # Message building (Anthropic format — system is separate)
    # ------------------------------------------------------------------

    def build_messages(self) -> List[dict]:
        """Return only non-system messages (system passed via _build_system_blocks)."""
        return [m for m in self._session.raw if m["role"] != "system"]

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def get_available_models(self, enabled: bool = False) -> None:
        headers = ["Vendor", "Model ID", "Context Window"]
        table_data = [
            [info["vendor"], model_id, f"{info['context']:,}"]
            for model_id, info in _ANTHROPIC_MODELS.items()
        ]
        print(tabulate(table_data, headers=headers, tablefmt="rounded_grid"))

    def get_enabled_model_ids(self) -> List[str]:
        return list(_ANTHROPIC_MODELS.keys())

    def _fetch_model_context_window(self, model_id: str) -> Optional[int]:
        info = _ANTHROPIC_MODELS.get(model_id)
        return info["context"] if info else None

    # ------------------------------------------------------------------
    # Core streaming
    # ------------------------------------------------------------------

    def _raw_stream(self, messages: List[dict]) -> Optional[str]:
        if not self._api_key:
            Output.error(
                "No Anthropic API key configured. "
                "Set ANTHROPIC_API_KEY or use 'set-anthropic-key <key>'."
            )
            return None

        # Anthropic: system is a top-level param, not part of messages
        conv_messages = [m for m in messages if m.get("role") != "system"]
        conv_messages = self._add_cache_to_last_message(conv_messages)

        payload = {
            "model": self.model_id,
            "system": self._build_system_blocks(),
            "messages": conv_messages,
            "max_tokens": 8096,
            "stream": True,
        }

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
            "anthropic-beta": "prompt-caching-2024-07-31",
        }

        response = None
        try:
            response = requests.post(
                f"{self.API_BASE_URL}/v1/messages",
                headers=headers,
                json=payload,
                stream=True,
                timeout=120,
            )

            if response.status_code == 401:
                Output.error("Anthropic API key is invalid or expired.")
                return None

            if response.status_code == 400:
                body = response.json()
                error_msg = body.get("error", {}).get("message", str(body))
                if "context" in error_msg.lower() or "token" in error_msg.lower():
                    Output.warning(f"HTTP 400 (context window exceeded?): {error_msg}")
                    raise ContextWindowExceeded()
                Output.error(f"HTTP 400: {error_msg}")
                return None

            if response.status_code == 529:
                Output.error("Anthropic API overloaded (529). Please retry later.")
                return None

            if response.status_code != 200:
                Output.error(f"Anthropic API error HTTP {response.status_code}: {response.text[:200]}")
                return None

            return self._parse_stream(response)

        except KeyboardInterrupt:
            if response is not None:
                response.close()
            raise RequestInterrupted()
        except requests.exceptions.RequestException as e:
            Output.error(f"Network error: {e}")
            return None
        except ContextWindowExceeded:
            raise
        except Exception as e:
            Output.error(f"Unexpected error: {e}")
            return None

    def _parse_stream(self, response: requests.Response) -> str:
        """Parse Anthropic SSE stream and return full response text."""
        full_response = ""
        spinner = StreamingSpinner()

        input_tokens = 0
        output_tokens = 0
        cache_creation_tokens = 0
        cache_read_tokens = 0

        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")

            if line.startswith("event: "):
                continue

            if not line.startswith("data: "):
                continue

            data_str = line[6:]
            if data_str == "[DONE]":
                break

            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            event_type = chunk.get("type", "")

            if event_type == "message_start":
                usage = chunk.get("message", {}).get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
                cache_read_tokens = usage.get("cache_read_input_tokens", 0)

            elif event_type == "content_block_delta":
                delta = chunk.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        spinner.update()
                        full_response += text

            elif event_type == "message_delta":
                usage = chunk.get("usage", {})
                output_tokens = usage.get("output_tokens", output_tokens)

            elif event_type == "message_stop":
                break

            elif event_type == "error":
                error = chunk.get("error", {})
                Output.error(f"Anthropic stream error: {error.get('message', chunk)}")
                break

        spinner.finish()

        # Log token usage with cache stats
        if input_tokens or output_tokens:
            parts = [f"in={input_tokens} out={output_tokens}"]
            if cache_creation_tokens:
                parts.append(f"cache_write={cache_creation_tokens}")
            if cache_read_tokens:
                pct = int(cache_read_tokens * 100 / input_tokens) if input_tokens else 0
                parts.append(f"cache_read={cache_read_tokens} ({pct}%)")
                saved = cache_read_tokens * (3.00 - 0.30) / 1_000_000
                if saved > 0.001:
                    parts.append(f"saved≈${saved:.4f}")
            Output.debug("tokens: " + "  ".join(parts))

        return full_response
