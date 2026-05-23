# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""
GitHub Copilot LLM provider.
"""

import json
import requests
import time

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tabulate import tabulate
from typing import List, Optional

from ..term_output import Style, Output, StreamingSpinner
from .base import BaseLLMClient, RequestInterrupted, ContextWindowExceeded


class CopilotClient(BaseLLMClient):
    """LLM client using GitHub Copilot as backend."""

    CONFIG_PATH = Path.home() / ".config" / "codin"
    TOKEN_FILE = CONFIG_PATH / "hosts.json"
    COPILOT_TOKEN_FILE = CONFIG_PATH / "copilot_token.json"

    DEFAULT_MODEL = "gpt-4.1"

    def __init__(self, system_prompt: str) -> None:
        super().__init__(system_prompt)
        self.copilot_token: Optional[str] = None
        self.copilot_token_expires_at: Optional[datetime] = None
        self._token_refresh_in_progress: bool = False
        self.model_id = self.DEFAULT_MODEL
        self._load_model_from_disk()
        self._load_copilot_token_from_disk()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_copilot_token_from_disk(self) -> None:
        if not self.COPILOT_TOKEN_FILE.exists():
            return
        try:
            data = json.loads(self.COPILOT_TOKEN_FILE.read_text())
            self.copilot_token = data.get("token")
            expires_at_str = data.get("expires_at")
            if expires_at_str:
                self.copilot_token_expires_at = datetime.fromisoformat(expires_at_str)
                if self.copilot_token_expires_at.tzinfo is None:
                    self.copilot_token_expires_at = self.copilot_token_expires_at.replace(
                        tzinfo=timezone.utc
                    )
            Output.success(
                f"Loaded cached Copilot token "
                f"(expires: {self.copilot_token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
            )
        except Exception as e:
            Output.warning(f"Could not load cached Copilot token: {e}")
            self.copilot_token = None
            self.copilot_token_expires_at = None

    def _save_copilot_token_to_disk(self) -> None:
        if not self.copilot_token or not self.copilot_token_expires_at:
            return
        try:
            self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
            data = {
                "token": self.copilot_token,
                "expires_at": self.copilot_token_expires_at.isoformat(),
            }
            self.COPILOT_TOKEN_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            Output.warning(f"Could not save Copilot token to disk: {e}")

    def _clear_invalid_tokens(self) -> None:
        self.copilot_token = None
        self.copilot_token_expires_at = None
        if self.TOKEN_FILE.exists():
            self.TOKEN_FILE.unlink()
            Output.warning("Removed invalid GitHub token")
        if self.COPILOT_TOKEN_FILE.exists():
            self.COPILOT_TOKEN_FILE.unlink()
            Output.warning("Removed invalid Copilot token")

    def authenticate_via_device_flow(self) -> bool:
        Output.section("Starting GitHub authentication...")
        try:
            response = requests.post(
                "https://github.com/login/device/code",
                data={"client_id": "Iv1.b507a08c87ecfe98", "scope": "read:user"},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if response.status_code != 200:
                Output.error(f"Authentication request failed: {response.text}")
                return False

            device_data = response.json()
            user_code = device_data["user_code"]
            verification_uri = device_data["verification_uri"]
            device_code = device_data["device_code"]

            Output.banner("GitHub Authentication Required")
            Output.warning(f"Please visit: {Style.BRIGHT}{verification_uri}")
            Output.warning(f"Enter code: {Style.BRIGHT}{user_code}")
            Output.separator()
            Output.status("Waiting for authorization...")

            while True:
                time.sleep(5)
                response = requests.post(
                    "https://github.com/login/oauth/access_token",
                    data={
                        "client_id": "Iv1.b507a08c87ecfe98",
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                result = response.json()
                if "access_token" in result:
                    self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
                    token_data = {
                        "github.com": {
                            "oauth_token": result["access_token"],
                            "user": "user",
                        }
                    }
                    self.TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
                    Output.success("Authentication successful!")
                    self.copilot_token = None
                    self.copilot_token_expires_at = None
                    return True

                error = result.get("error")
                if error == "authorization_pending":
                    continue
                else:
                    Output.error(f"Authentication error: {error}")
                    return False
        except requests.exceptions.RequestException as e:
            Output.error(f"Network error during authentication: {e}")
            return False

    def get_auth_token(self) -> Optional[str]:
        if not self.TOKEN_FILE.exists():
            if not self.authenticate_via_device_flow():
                return None
        try:
            data = json.loads(self.TOKEN_FILE.read_text())
            return data.get("github.com", {}).get("oauth_token")
        except Exception as e:
            Output.error(f"Error reading token: {e}")
            return None

    def get_copilot_token(self, force_refresh: bool = False) -> Optional[str]:
        now = datetime.now(timezone.utc)
        if self._token_refresh_in_progress:
            Output.warning("Token refresh already in progress, waiting...")
            return None

        if not force_refresh and self.copilot_token and self.copilot_token_expires_at:
            if now < self.copilot_token_expires_at - timedelta(minutes=5):
                return self.copilot_token
            else:
                Output.status("Copilot token expired or expiring soon, refreshing...")

        self._token_refresh_in_progress = True
        token = self.get_auth_token()
        if not token:
            self._token_refresh_in_progress = False
            return None

        try:
            response = requests.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/json",
                    "User-Agent": "GitHubCopilot/1.0",
                },
                timeout=10,
            )
            if response.status_code in [401, 403]:
                Output.warning(
                    f"GitHub token expired or invalid (HTTP {response.status_code}), "
                    f"re-authenticating..."
                )
                self._clear_invalid_tokens()
                if self.authenticate_via_device_flow():
                    self._token_refresh_in_progress = False
                    return self.get_copilot_token(force_refresh=True)
                self._token_refresh_in_progress = False
                return None

            if response.status_code == 200:
                data = response.json()
                self.copilot_token = data.get("token")
                expires_at = data.get("expires_at", 0)
                if isinstance(expires_at, (int, float)):
                    self.copilot_token_expires_at = datetime.fromtimestamp(
                        expires_at, tz=timezone.utc
                    )
                else:
                    self.copilot_token_expires_at = now + timedelta(hours=1)

                self._save_copilot_token_to_disk()
                Output.success(
                    f"Copilot token refreshed "
                    f"(expires at {self.copilot_token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
                )
                self._token_refresh_in_progress = False
                return self.copilot_token

            Output.error(f"Error getting Copilot token: HTTP {response.status_code}")
            self._token_refresh_in_progress = False
            return None
        except requests.exceptions.RequestException as e:
            Output.error(f"Network error getting Copilot token: {e}")
            self._token_refresh_in_progress = False
            return None

    def show_token_info(self) -> None:
        if self.copilot_token_expires_at:
            Output.info(
                f"Copilot token expires at: "
                f"{self.copilot_token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        else:
            Output.warning("No Copilot token cached.")

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _copilot_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": "GitHubCopilot/1.0",
            "Editor-Version": "Neovim/0.9.0",
            "Editor-Plugin-Version": "copilot.vim/1.16.0",
            "Copilot-Integration-Id": "vscode-chat",
            "Accept": "application/json",
        }

    def get_available_models(self, enabled: bool = False) -> None:
        token = self.get_copilot_token()
        if not token:
            Output.error("Failed to get Copilot token")
            return
        response = requests.get(
            "https://api.githubcopilot.com/models",
            headers=self._copilot_headers(token),
        )
        if response.status_code == 200:
            self._display_models(response.json(), enabled)
        else:
            Output.error(f"HTTP/{response.status_code}, {response.text}")

    def get_enabled_model_ids(self) -> List[str]:
        token = self.get_copilot_token()
        if not token:
            return []
        try:
            response = requests.get(
                "https://api.githubcopilot.com/models",
                headers=self._copilot_headers(token),
            )
            if response.status_code == 200:
                data = response.json()
                models_list = data.get("models", data.get("data", []))
                return [
                    m.get("id")
                    for m in models_list
                    if m.get("policy", {}).get("state") == "enabled" and m.get("id")
                ]
        except Exception:
            pass
        return []

    def _fetch_model_context_window(self, model_id: str) -> Optional[int]:
        token = self.get_copilot_token()
        if not token:
            return None
        try:
            response = requests.get(
                "https://api.githubcopilot.com/models",
                headers=self._copilot_headers(token),
                timeout=10,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            models_list = data.get("models", data.get("data", []))
            for m in models_list:
                if m.get("id") == model_id:
                    limits = m.get("capabilities", {}).get("limits", {})
                    ctx = limits.get("max_context_window_tokens")
                    return int(ctx) if ctx else None
        except Exception:
            pass
        return None

    @staticmethod
    def _display_models(response_data: dict, enabled_only: bool = False) -> None:
        if isinstance(response_data, dict):
            models_list = response_data.get("models", response_data.get("data", []))
        else:
            models_list = response_data

        table_data = []
        headers = ["Vendor", "Model ID", "Context Window", "State", "Vision"]

        for model in models_list:
            state = model.get("policy", {}).get("state", "N/A")
            if enabled_only and state != "enabled":
                continue
            caps = model.get("capabilities", {})
            limits = caps.get("limits", {})
            table_data.append([
                model.get("vendor", "N/A"),
                model.get("id", "N/A"),
                limits.get("max_context_window_tokens", "N/A"),
                state,
                "Yes" if caps.get("supports", {}).get("vision") else "No",
            ])

        if not table_data:
            print("No models found.")
            return

        table_data.sort(key=lambda row: (row[0], row[1]))
        print(tabulate(table_data, headers=headers, tablefmt="rounded_grid"))

    # ------------------------------------------------------------------
    # Core streaming
    # ------------------------------------------------------------------

    def _raw_stream(self, messages: List[dict]) -> Optional[str]:
        copilot_token = self.get_copilot_token()
        if not copilot_token:
            return None

        headers = {
            "Authorization": f"Bearer {copilot_token}",
            "Content-Type": "application/json",
            "User-Agent": "GitHubCopilot/1.0",
            "Editor-Version": "Neovim/0.9.0",
            "Editor-Plugin-Version": "copilot.vim/1.16.0",
            "Copilot-Integration-Id": "vscode-chat",
        }

        payload = {
            "messages": messages,
            "model": self.model_id,
            "temperature": 0.1,
            "top_p": 1,
            "stream": True,
        }

        response = None
        try:
            response = requests.post(
                "https://api.githubcopilot.com/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60,
            )

            if response.status_code == 401:
                Output.warning("Copilot token expired, refreshing...")
                self.copilot_token = self.get_copilot_token(force_refresh=True)
                if self.copilot_token:
                    return self._raw_stream(messages)
                return None

            if response.status_code == 400:
                Output.warning("HTTP 400: context window likely exceeded, will attempt compaction...")
                raise ContextWindowExceeded()

            response.raise_for_status()

            full_response = ""
            spinner = StreamingSpinner()
            usage: dict = {}

            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            spinner.update()
                            full_response += content
                        if "usage" in chunk and chunk["usage"]:
                            usage = chunk["usage"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

            spinner.finish()

            if usage:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
                parts = [f"in={prompt_tokens} out={completion_tokens}"]
                if cached:
                    pct = int(cached * 100 / prompt_tokens) if prompt_tokens else 0
                    parts.append(f"cached={cached} ({pct}%)")
                Output.debug("tokens: " + "  ".join(parts))

            return full_response

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
