# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""
GitHub Copilot Agent Client
"""

import json
import re
import uuid
import requests

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tabulate import tabulate
from typing import Callable, List, Optional, Tuple

from .term_output import Style, Fore, Output, render_markdown, StreamingSpinner


class RequestInterrupted(Exception):
    """Exception raised when a request is interrupted by CTRL-C."""

    pass


class ContextWindowExceeded(Exception):
    """Exception raised when the API returns 400 due to context window overflow."""

    pass


# ---------------------------------------------------------------------------
# Conversation state management (inspired by claude-code session/compact)
# ---------------------------------------------------------------------------

# Rough token estimator: ~4 chars per token (GPT-style).
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class ConversationMessage:
    """A single message in the conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str
    token_estimate: int = field(init=False)

    def __post_init__(self) -> None:
        self.token_estimate = _estimate_tokens(self.content)

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


# Summary prompt injected as a synthetic system message after compaction.
_COMPACT_SUMMARY_PROMPT = """\
You are a helpful assistant. Below is a summary of the earlier part of this
conversation, followed by the most recent messages. Use the summary as context
but treat the recent messages as the primary source of truth.

[CONVERSATION SUMMARY]
{summary}
[END SUMMARY]"""

_COMPACTION_REQUEST = """\
Please produce a concise but complete summary of the conversation so far.
Include:
- The user's overall goal and any sub-tasks
- Every shell command that was executed and its outcome (success/failure, key output)
- Every file that was read or written, and the key content or changes
- Any important decisions, errors encountered, and how they were resolved
- The current state of the work (what is done, what is pending)

Be factual and terse. Output only the summary text, no preamble."""


class ConversationSession:
    """
    Manages conversation history with automatic compaction when the token
    budget is exceeded — similar to how claude-code handles long sessions.

    Strategy
    --------
    * We keep a target soft limit (`token_budget`). When the total token
      estimate exceeds it we compact: the tail of `tail_messages` recent
      messages is preserved verbatim; everything before that is summarised
      by calling the model and stored as a single synthetic system message.
    * The summary is prepended so that context is never fully lost.
    * Each compaction reduces the history to:
        [summary_system_msg] + last `tail_messages` messages
    """

    def __init__(
        self,
        token_budget: int = 80_000,
        tail_messages: int = 20,
    ) -> None:
        self._messages: List[ConversationMessage] = []
        self.token_budget = token_budget
        self.tail_messages = tail_messages
        self._compaction_summary: Optional[str] = None  # most recent compact summary

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def add(self, role: str, content: str) -> None:
        """Append a message."""
        self._messages.append(ConversationMessage(role=role, content=content))

    @property
    def total_tokens(self) -> int:
        return sum(m.token_estimate for m in self._messages)

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def needs_compaction(self) -> bool:
        return self.total_tokens > self.token_budget

    def compact(self, summarizer: Callable[[List[dict]], Optional[str]]) -> bool:
        """
        Summarise the older portion of the conversation.

        `summarizer` receives a list of {"role", "content"} dicts (the
        messages to summarise) and must return a summary string, or None
        on failure.

        Returns True if compaction was performed, False otherwise.
        """
        if len(self._messages) <= self.tail_messages:
            return False  # nothing to compact

        to_summarise = self._messages[: -self.tail_messages]
        tail = self._messages[-self.tail_messages :]

        # Build a minimal context for the summariser.
        ctx: List[dict] = []
        if self._compaction_summary:
            # Include the previous summary so we accumulate knowledge.
            ctx.append(
                {
                    "role": "system",
                    "content": _COMPACT_SUMMARY_PROMPT.format(summary=self._compaction_summary),
                }
            )
        ctx.extend(m.to_dict() for m in to_summarise)
        ctx.append({"role": "user", "content": _COMPACTION_REQUEST})

        Output.status("Compacting conversation history (session too long)...")
        summary = summarizer(ctx)
        if not summary:
            Output.warning("Compaction failed — falling back to hard trim.")
            # Fallback: just keep the tail, losing the older context.
            self._messages = list(tail)
            return True

        self._compaction_summary = summary
        Output.success(f"Compacted {len(to_summarise)} messages into a summary ({_estimate_tokens(summary)} tokens).")

        # Rebuild: one synthetic system message + the recent tail.
        summary_msg = ConversationMessage(
            role="system",
            content=_COMPACT_SUMMARY_PROMPT.format(summary=summary),
        )
        self._messages = [summary_msg] + list(tail)
        return True

    def to_api_messages(self, system_prompt: str) -> List[dict]:
        """
        Build the messages list to send to the API.
        The primary system prompt always comes first.
        """
        result: List[dict] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend(m.to_dict() for m in self._messages)
        return result

    def clear(self) -> None:
        self._messages.clear()
        self._compaction_summary = None

    # For backward-compat with code that accessed conversation_history directly.
    @property
    def raw(self) -> List[dict]:
        return [m.to_dict() for m in self._messages]

    def save_history(self, path: Path, session_uuid: str = "") -> None:
        """Serialise the session to a JSONL file (one JSON object per line)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            meta = {"_meta": True, "compaction_summary": self._compaction_summary, "session_uuid": session_uuid}
            fh.write(json.dumps(meta) + "\n")
            for msg in self._messages:
                fh.write(json.dumps(msg.to_dict()) + "\n")

    def load_history(self, path: Path) -> str:
        """Deserialise a session from a JSONL file produced by save_history.

        Returns the session_uuid stored in the file, or "" if not present."""
        self.clear()
        loaded_uuid: str = ""
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("_meta"):
                    self._compaction_summary = obj.get("compaction_summary")
                    loaded_uuid = obj.get("session_uuid", "")
                else:
                    self._messages.append(ConversationMessage(role=obj["role"], content=obj["content"]))

        return loaded_uuid


# ---------------------------------------------------------------------------
# Copilot API client
# ---------------------------------------------------------------------------


class CopilotAgentClient:
    """Client using GitHub Copilot with command execution capabilities."""

    CONFIG_PATH = Path.home() / ".config" / "codin"
    TOKEN_FILE = CONFIG_PATH / "hosts.json"
    COPILOT_TOKEN_FILE = CONFIG_PATH / "copilot_token.json"
    MODEL_FILE = CONFIG_PATH / "model.json"

    def __init__(self, system_prompt: str):
        self.system_prompt: str = system_prompt
        self.session_uuid: str = str(uuid.uuid4())
        self._session = ConversationSession(token_budget=80_000, tail_messages=20)
        self.last_commands: List[str] = []
        self.copilot_token: Optional[str] = None
        self.copilot_token_expires_at: Optional[datetime] = None
        self._load_copilot_token_from_disk()
        self._token_refresh_in_progress: bool = False
        self.model_id: str = "gpt-4.1"
        self._load_model_from_disk()

    # ------------------------------------------------------------------
    # Backward-compatible property so cli.py can still read
    # client.conversation_history if needed.
    # ------------------------------------------------------------------
    @property
    def conversation_history(self) -> List[dict]:
        return self._session.raw

    def _load_model_from_disk(self) -> None:
        """Load last used model from disk."""
        if not self.MODEL_FILE.exists():
            return
        try:
            data = json.loads(self.MODEL_FILE.read_text())
            self.model_id = data.get("model_id", self.model_id)
        except Exception:
            pass

    def _save_model_to_disk(self, model_id: str) -> None:
        """Persist the selected model to disk."""
        self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        self.MODEL_FILE.write_text(json.dumps({"model_id": model_id}, indent=2))

    def _load_copilot_token_from_disk(self) -> None:
        """Load cached Copilot token from disk."""
        if not self.COPILOT_TOKEN_FILE.exists():
            return
        try:
            data = json.loads(self.COPILOT_TOKEN_FILE.read_text())
            self.copilot_token = data.get("token")
            expires_at_str = data.get("expires_at")
            if expires_at_str:
                self.copilot_token_expires_at = datetime.fromisoformat(expires_at_str)
                if self.copilot_token_expires_at.tzinfo is None:
                    self.copilot_token_expires_at = self.copilot_token_expires_at.replace(tzinfo=timezone.utc)
            Output.success(
                f"Loaded cached Copilot token (expires: {self.copilot_token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
            )
        except Exception as e:
            Output.warning(f"Could not load cached Copilot token: {e}")
            self.copilot_token = None
            self.copilot_token_expires_at = None

    def _save_copilot_token_to_disk(self) -> None:
        """Save Copilot token to disk for persistence."""
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
        """Clear invalid tokens from disk and memory."""
        self.copilot_token = None
        self.copilot_token_expires_at = None
        if self.TOKEN_FILE.exists():
            self.TOKEN_FILE.unlink()
            Output.warning("Removed invalid GitHub token")
        if self.COPILOT_TOKEN_FILE.exists():
            self.COPILOT_TOKEN_FILE.unlink()
            Output.warning("Removed invalid Copilot token")

    def authenticate_via_device_flow(self) -> bool:
        """Authenticate using GitHub device flow."""
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
            Output.info(f"You may need to login first: {Style.BRIGHT}https://github.com/enterprises/cfm-emu/sso")
            Output.warning(f"Enter code: {Style.BRIGHT}{user_code}")
            Output.separator()
            Output.status("Waiting for authorization...")

            import time

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
        """Get authentication token from config."""
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
        """Get or refresh Copilot token with full error handling."""
        now = datetime.now(timezone.utc)
        if self._token_refresh_in_progress:
            Output.warning("Token refresh already in progress, waiting...")
            return None

        # Check cached token
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
                Output.warning(f"GitHub token expired or invalid (HTTP {response.status_code}), Re-authenticating...")
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
                    self.copilot_token_expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                else:
                    self.copilot_token_expires_at = now + timedelta(hours=1)

                self._save_copilot_token_to_disk()
                Output.success(
                    f"Copilot token refreshed (expires at {self.copilot_token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
                )
                self._token_refresh_in_progress = False
                return self.copilot_token

            Output.error(f"Error getting Copilot token: HTTP {response.status_code}")
            Output.debug(f"Response: {response.text[:200]}")
            self._token_refresh_in_progress = False
            return None
        except requests.exceptions.RequestException as e:
            Output.error(f"Network error getting Copilot token: {e}")
            self._token_refresh_in_progress = False
            return None

    def build_messages(self) -> List[dict]:
        """Build messages list with system prompt."""
        return self._session.to_api_messages(self.system_prompt)

    @staticmethod
    def display_models_info(response_data: dict, enabled_only=False) -> None:
        """
        Displays important model capabilities in a tabular format.
        Handles the dictionary wrapper returned by the Copilot API.
        """
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

            m_id = model.get("id", "N/A")
            vendor = model.get("vendor", "N/A")

            caps = model.get("capabilities", {})
            limits = caps.get("limits", {})

            context = limits.get("max_context_window_tokens", "N/A")
            vision = "Yes" if caps.get("supports", {}).get("vision") else "No"

            table_data.append([vendor, m_id, context, state, vision])

        if not table_data:
            print("No models found or no models match the filter.")
            return

        table_data.sort(key=lambda row: (row[0], row[1]))
        print(tabulate(table_data, headers=headers, tablefmt="rounded_grid"))

    def get_available_models(self, enabled=False):
        token = self.get_copilot_token()
        if not token:
            Output.error("Failed to get Copilot token")
            return
        url = "https://api.githubcopilot.com/models"
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "GitHubCopilot/1.0",
            "Editor-Version": "Neovim/0.9.0",
            "Editor-Plugin-Version": "copilot.vim/1.16.0",
            "Copilot-Integration-Id": "vscode-chat",
            "Accept": "application/json",
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            CopilotAgentClient.display_models_info(response.json(), enabled)
        else:
            Output.error(f"HTTP/{response.status_code}, {response.text}")

    def get_enabled_model_ids(self) -> list[str]:
        """Return a list of enabled model IDs (for completion)."""
        token = self.get_copilot_token()
        if not token:
            return []
        url = "https://api.githubcopilot.com/models"
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "GitHubCopilot/1.0",
            "Editor-Version": "Neovim/0.9.0",
            "Editor-Plugin-Version": "copilot.vim/1.16.0",
            "Copilot-Integration-Id": "vscode-chat",
            "Accept": "application/json",
        }
        try:
            response = requests.get(url, headers=headers)
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
        """Return max_context_window_tokens for *model_id*, or None on failure."""
        token = self.get_copilot_token()
        if not token:
            return None
        url = "https://api.githubcopilot.com/models"
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "GitHubCopilot/1.0",
            "Editor-Version": "Neovim/0.9.0",
            "Editor-Plugin-Version": "copilot.vim/1.16.0",
            "Copilot-Integration-Id": "vscode-chat",
            "Accept": "application/json",
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
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

    def set_model(self, model_id: str) -> None:
        self.model_id = model_id
        self._save_model_to_disk(model_id)
        ctx = self._fetch_model_context_window(model_id)
        if ctx:
            budget = int(ctx * 0.80)
            self._session.token_budget = budget
            Output.info(f"Model '{model_id}': context window {ctx:,} tokens → token budget set to {budget:,}")
        else:
            Output.warning(
                f"Could not fetch context window for '{model_id}', keeping current budget ({self._session.token_budget:,})"
            )

    def get_model(self) -> str:
        return self.model_id

    # ------------------------------------------------------------------
    # Core streaming call — used both for normal messages and compaction.
    # ------------------------------------------------------------------

    def _raw_stream(self, messages: List[dict]) -> Optional[str]:
        """
        POST `messages` to the Copilot chat completions endpoint and return
        the full streamed response text, or None on error.

        Raises RequestInterrupted on CTRL-C.
        """
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
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

            spinner.finish()
            return full_response

        except KeyboardInterrupt:
            if response is not None:
                response.close()
            raise RequestInterrupted()

        except requests.exceptions.RequestException as e:
            Output.error(f"Network error: {e}")
            return None
        except Exception as e:
            Output.error(f"Unexpected error: {e}")
            return None

    def _make_summarizer(self) -> Callable[[List[dict]], Optional[str]]:
        """
        Return a callable that feeds a list of messages to the model and
        returns its plain-text reply (the compaction summary).
        """

        def summarizer(ctx: List[dict]) -> Optional[str]:
            return self._raw_stream(ctx)

        return summarizer

    def send_message(self, message: str, show_response: bool = True) -> Optional[str]:
        """
        Send a user message, compacting the session first if needed.

        Raises:
            RequestInterrupted: If the user interrupts the request with CTRL-C.
        """
        # Compact before adding the new message so the summary can include
        # the full prior history.
        if self._session.needs_compaction():
            self._session.compact(self._make_summarizer())

        self._session.add("user", message)
        messages = self.build_messages()

        try:
            full_response = self._raw_stream(messages)
        except RequestInterrupted:
            # Remove the user message we just added since we didn't complete.
            # The session stores ConversationMessage objects; pop the last one.
            if self._session._messages and self._session._messages[-1].role == "user":
                self._session._messages.pop()
            raise
        except ContextWindowExceeded:
            # 400 from the API — force compaction and retry once.
            Output.warning("Forcing compaction due to context window overflow, then retrying...")
            # Roll back the user message before compacting.
            if self._session._messages and self._session._messages[-1].role == "user":
                self._session._messages.pop()
            compacted = self._session.compact(self._make_summarizer())
            if not compacted:
                Output.error("Compaction failed, cannot retry.")
                return None
            # Re-add user message and retry.
            self._session.add("user", message)
            messages = self.build_messages()
            try:
                full_response = self._raw_stream(messages)
            except (RequestInterrupted, ContextWindowExceeded):
                if self._session._messages and self._session._messages[-1].role == "user":
                    self._session._messages.pop()
                Output.error("Request failed even after compaction.")
                return None

        if full_response is None:
            # Network / auth error — roll back the user message.
            if self._session._messages and self._session._messages[-1].role == "user":
                self._session._messages.pop()
            return None

        if show_response and full_response:
            render_markdown(full_response)

        self._session.add("assistant", full_response)
        self._autosave()
        return full_response

    def extract_code_blocks(self, text: str) -> List[Tuple[str, str]]:
        """Extract code blocks using <<<lang and >>> delimiters with nesting support."""
        # Strip ANSI color codes first to ensure clean parsing.
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        text = ansi_escape.sub("", text)

        results = []
        lines = text.splitlines()

        stack_level = 0
        current_lang = ""
        current_block_content = []
        valid_langs = ("execute_command", "read_file", "write_file")

        for line in lines:
            stripped_line = line.strip()

            if stripped_line.startswith("<<<"):
                if stack_level == 0:
                    current_lang = stripped_line[3:].lower().strip()
                else:
                    current_block_content.append(line)
                stack_level += 1
                continue

            if stripped_line == ">>>":
                stack_level -= 1
                if stack_level == 0:
                    if current_lang in valid_langs:
                        results.append((current_lang, "\n".join(current_block_content).strip()))
                    current_block_content = []
                    current_lang = ""
                else:
                    current_block_content.append(line)
                continue

            if stack_level > 0:
                current_block_content.append(line)

        return results

    def clear_history(self):
        """Clear conversation history."""
        self._session.clear()
        self.last_commands = []

    def force_compact(self) -> bool:
        """Force an immediate compaction of the conversation history, regardless of token budget."""
        if len(self._session._messages) <= self._session.tail_messages:
            Output.warning(f"Not enough messages to compact (need more than {self._session.tail_messages}).")
            return False
        return self._session.compact(self._make_summarizer())

    _DEFAULT_HISTORY_DIR = Path.home() / ".cache" / "codin" / "history"

    def _autosave(self) -> None:
        """Automatically save the session to a fixed file named after session_uuid."""
        self._DEFAULT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path = self._DEFAULT_HISTORY_DIR / f"{self.session_uuid}.jsonl"
        self._session.save_history(path)

    def save_history(self, path: Path | None = None) -> Path:
        """Save the current session to *path* (default: ~/.config/codin/sessions/<timestamp>.jsonl)."""
        if path is None:
            import datetime

            self._DEFAULT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self._DEFAULT_HISTORY_DIR / f"session_{ts}.jsonl"
        self._session.save_history(path)
        Output.success(f"Session saved to {path}")
        return path

    def load_history(self, path: Path) -> None:
        """Load a session from *path*, replacing current history."""
        loaded_uuid = self._session.load_history(path)
        if loaded_uuid:
            self.session_uuid = loaded_uuid
        else:
            stem = path.stem
            try:
                import uuid as _uuid

                self.session_uuid = str(_uuid.UUID(stem))
            except ValueError:
                pass
        self.last_commands = []
        n = len(self._session.raw)
        Output.success(f"Loaded {n} messages from {path}")

    def show_system_prompt(self):
        """Display the current system prompt."""
        Output.header("System Prompt", self.system_prompt)

    def set_system_prompt(self, prompt: str):
        """Set a new system prompt."""
        self.system_prompt = prompt
        Output.success("System prompt updated")
