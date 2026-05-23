# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Base LLM client - abstract interface for all LLM providers.
"""

import json
import re
import uuid

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..term_output import Output


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RequestInterrupted(Exception):
    """Raised when a request is interrupted by CTRL-C."""
    pass


class ContextWindowExceeded(Exception):
    """Raised when the API returns 400 due to context window overflow."""
    pass


# ---------------------------------------------------------------------------
# Conversation session
# ---------------------------------------------------------------------------

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


class ConversationSession:
    """
    Manages conversation history with automatic compaction when the token
    budget is exceeded.
    """

    def __init__(self, token_budget: int = 80_000, tail_messages: int = 20) -> None:
        self._messages: List[ConversationMessage] = []
        self.token_budget = token_budget
        self.tail_messages = tail_messages
        self._compaction_summary: Optional[str] = None

    def add(self, role: str, content: str) -> None:
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
        if len(self._messages) <= self.tail_messages:
            return False

        to_summarise = self._messages[: -self.tail_messages]
        tail = self._messages[-self.tail_messages :]

        ctx: List[dict] = []
        if self._compaction_summary:
            ctx.append({
                "role": "system",
                "content": _COMPACT_SUMMARY_PROMPT.format(summary=self._compaction_summary),
            })
        ctx.extend(m.to_dict() for m in to_summarise)
        ctx.append({"role": "user", "content": _COMPACTION_REQUEST})

        Output.status("Compacting conversation history (session too long)...")
        summary = summarizer(ctx)
        if not summary:
            Output.warning("Compaction failed — falling back to hard trim.")
            self._messages = list(tail)
            return True

        self._compaction_summary = summary
        Output.success(
            f"Compacted {len(to_summarise)} messages into a summary "
            f"({_estimate_tokens(summary)} tokens)."
        )

        summary_msg = ConversationMessage(
            role="system",
            content=_COMPACT_SUMMARY_PROMPT.format(summary=summary),
        )
        self._messages = [summary_msg] + list(tail)
        return True

    def to_api_messages(self, system_prompt: str) -> List[dict]:
        result: List[dict] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend(m.to_dict() for m in self._messages)
        return result

    def clear(self) -> None:
        self._messages.clear()
        self._compaction_summary = None

    @property
    def raw(self) -> List[dict]:
        return [m.to_dict() for m in self._messages]

    def save_history(self, path: Path, session_uuid: str = "") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            meta = {
                "_meta": True,
                "compaction_summary": self._compaction_summary,
                "session_uuid": session_uuid,
            }
            fh.write(json.dumps(meta) + "\n")
            for msg in self._messages:
                fh.write(json.dumps(msg.to_dict()) + "\n")

    def load_history(self, path: Path) -> str:
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
                    self._messages.append(
                        ConversationMessage(role=obj["role"], content=obj["content"])
                    )
        return loaded_uuid


# ---------------------------------------------------------------------------
# Abstract base client
# ---------------------------------------------------------------------------

class BaseLLMClient(ABC):
    """
    Abstract base class for all LLM provider clients.

    Subclasses must implement:
      - _raw_stream(messages)        → stream a completion, return full text
      - get_available_models()       → display available models
      - get_enabled_model_ids()      → return list of enabled model IDs
      - _fetch_model_context_window() → return context window size for a model
    """

    _DEFAULT_HISTORY_DIR = Path.home() / ".cache" / "codin" / "history"

    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.session_uuid = str(uuid.uuid4())
        self._session = ConversationSession(token_budget=80_000, tail_messages=20)
        self.last_commands: List[str] = []
        self.model_id: str = ""

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by each provider
    # ------------------------------------------------------------------

    @abstractmethod
    def _raw_stream(self, messages: List[dict]) -> Optional[str]:
        """
        Send `messages` to the provider and return the full response text,
        or None on error. Must raise RequestInterrupted on CTRL-C and
        ContextWindowExceeded on context overflow.
        """
        ...

    @abstractmethod
    def get_available_models(self, enabled: bool = False) -> None:
        """Display available models in a human-readable table."""
        ...

    @abstractmethod
    def get_enabled_model_ids(self) -> List[str]:
        """Return list of enabled/available model IDs (for tab completion)."""
        ...

    @abstractmethod
    def _fetch_model_context_window(self, model_id: str) -> Optional[int]:
        """Return max context window tokens for model_id, or None."""
        ...

    # ------------------------------------------------------------------
    # Model management (shared)
    # ------------------------------------------------------------------

    def set_model(self, model_id: str) -> None:
        self.model_id = model_id
        self._save_model_to_disk(model_id)
        ctx = self._fetch_model_context_window(model_id)
        if ctx:
            budget = int(ctx * 0.80)
            self._session.token_budget = budget
            Output.info(
                f"Model '{model_id}': context window {ctx:,} tokens "
                f"→ token budget set to {budget:,}"
            )
        else:
            Output.warning(
                f"Could not fetch context window for '{model_id}', "
                f"keeping current budget ({self._session.token_budget:,})"
            )

    def get_model(self) -> str:
        return self.model_id

    # ------------------------------------------------------------------
    # Model persistence (shared, override if needed)
    # ------------------------------------------------------------------

    @property
    def _model_file(self) -> Path:
        return Path.home() / ".config" / "codin" / "model.json"

    def _load_model_from_disk(self) -> None:
        if not self._model_file.exists():
            return
        try:
            data = json.loads(self._model_file.read_text())
            self.model_id = data.get("model_id", self.model_id)
        except Exception:
            pass

    def _save_model_to_disk(self, model_id: str) -> None:
        self._model_file.parent.mkdir(parents=True, exist_ok=True)
        self._model_file.write_text(json.dumps({"model_id": model_id}, indent=2))

    # ------------------------------------------------------------------
    # Conversation management (shared)
    # ------------------------------------------------------------------

    @property
    def conversation_history(self) -> List[dict]:
        return self._session.raw

    def build_messages(self) -> List[dict]:
        return self._session.to_api_messages(self.system_prompt)

    def _make_summarizer(self) -> Callable[[List[dict]], Optional[str]]:
        def summarizer(ctx: List[dict]) -> Optional[str]:
            return self._raw_stream(ctx)
        return summarizer

    def send_message(self, message: str, show_response: bool = True) -> Optional[str]:
        """
        Send a user message, compacting the session first if needed.
        Raises RequestInterrupted if the user hits CTRL-C.
        """
        if self._session.needs_compaction():
            self._session.compact(self._make_summarizer())

        self._session.add("user", message)
        messages = self.build_messages()

        try:
            full_response = self._raw_stream(messages)
        except RequestInterrupted:
            if self._session._messages and self._session._messages[-1].role == "user":
                self._session._messages.pop()
            raise
        except ContextWindowExceeded:
            Output.warning("Forcing compaction due to context window overflow, then retrying...")
            if self._session._messages and self._session._messages[-1].role == "user":
                self._session._messages.pop()
            compacted = self._session.compact(self._make_summarizer())
            if not compacted:
                Output.error("Compaction failed, cannot retry.")
                return None
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
            if self._session._messages and self._session._messages[-1].role == "user":
                self._session._messages.pop()
            return None

        if show_response and full_response:
            from ..term_output import render_markdown
            render_markdown(full_response)

        self._session.add("assistant", full_response)
        self._autosave()
        return full_response

    def clear_history(self) -> None:
        self._session.clear()
        self.last_commands = []

    def force_compact(self) -> bool:
        if len(self._session._messages) <= self._session.tail_messages:
            Output.warning(
                f"Not enough messages to compact "
                f"(need more than {self._session.tail_messages})."
            )
            return False
        return self._session.compact(self._make_summarizer())

    def show_system_prompt(self) -> None:
        Output.header("System Prompt", self.system_prompt)

    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt
        Output.success("System prompt updated")

    # ------------------------------------------------------------------
    # History persistence (shared)
    # ------------------------------------------------------------------

    def _autosave(self) -> None:
        self._DEFAULT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path = self._DEFAULT_HISTORY_DIR / f"{self.session_uuid}.jsonl"
        self._session.save_history(path)

    def save_history(self, path: Optional[Path] = None) -> Path:
        if path is None:
            import datetime
            self._DEFAULT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self._DEFAULT_HISTORY_DIR / f"session_{ts}.jsonl"
        self._session.save_history(path, self.session_uuid)
        Output.success(f"Session saved to {path}")
        return path

    def load_history(self, path: Path) -> None:
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

    # ------------------------------------------------------------------
    # Command block parsing (shared — format is provider-agnostic)
    # ------------------------------------------------------------------

    def extract_code_blocks(self, text: str) -> List[Tuple[str, str]]:
        """Extract <<<tag ... >>> command blocks from a response."""
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
