# Codin'Chat

An interactive CLI assistant powered by **GitHub Copilot** that can execute bash commands, read/write files, and reason about the results — all with user confirmation before any action.

## Features

- 💬 **Chat with GitHub Copilot** in your terminal
- 🔧 **Execute shell commands** — Copilot suggests, you confirm
- 📂 **Read files** (text or binary/base64)
- ✏️ **Write & append files** with preview
- 🔒 **Safety rules** — forbidden commands (sudo, rm, apt, pip…) are blocked
- 🗂️ **Session management** — save/load conversation history
- 🤖 **Multi-model support** — switch Copilot models on the fly
- ⚡ **Auto-compaction** — long conversations are summarized automatically
- 🖥️ **Rich terminal output** — colored, formatted, readable

## Installation

Requires [uv](https://github.com/astral-sh/uv) and a valid GitHub Copilot subscription.

```bash
git clone https://github.com/youruser/codin.git
cd codin
uv sync --dev
```

## Usage

```bash
uv run codin
```

Resume a previous session:

```bash
uv run codin --session path/to/session.jsonl
```

## Built-in Commands

| Command | Description |
|---|---|
| `help` | Show help |
| `clear` | Clear conversation history |
| `status` | Show token usage and session info |
| `compact` | Force compaction of conversation history |
| `list-models` | List enabled Copilot models |
| `list-all-models` | List all available models |
| `set-model <id>` | Switch to a different model |
| `get-model` | Show current model |
| `token` | Show Copilot token expiration |
| `system` | Show or replace the system prompt |
| `save-history [path]` | Save session to a file |
| `load-history <path>` | Load a session from a file |
| `quit` / `exit` | Exit (auto-saves session) |

## Shell Shortcuts

| Shortcut | Description |
|---|---|
| `!<cmd>` | Run a shell command locally (output not sent to Copilot) |
| `<<cmd>` | Run a shell command and pipe output to Copilot for analysis |

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Enter` (empty line) | Submit message |
| `Escape + Enter` | Submit message |
| `Enter` (non-empty line) | Insert newline (multi-line input) |
| `Tab` | Autocomplete commands / paths |
| `Ctrl-C` | Interrupt current request |
| `Ctrl-D` | Exit |

## How It Works

Copilot responds with structured command blocks:

- `<<<execute_command` — run a shell command
- `<<<read_file` — read a file (text or binary)
- `<<<write_file` — write or append to a file

Each command is shown to the user for confirmation before execution. Results are sent back to Copilot for analysis.

## Running Tests

```bash
uv run pytest tests/ -v
```

## License

GPL-3.0-or-later © 2026 Christophe Clienti
