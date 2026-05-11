# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone
from typing import List
import difflib
import re

try:
    from colorama import Back, Fore, Style, init

    init(autoreset=True)
except ImportError:
    print("Warning: colorama not installed. Run: pip install colorama")

    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""

    class Back:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""

    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""


try:
    from rich.console import Console
    from rich.markdown import Markdown

    RICH_AVAILABLE = True
    _console = Console()
except ImportError:
    RICH_AVAILABLE = False
    _console = None


# ==============================================================================
# MARKDOWN RENDERING
# ==============================================================================


def render_markdown(text: str) -> None:
    """
    Render markdown text using rich, with special handling:
    - Command blocks (<<<tag ... >>>) are silently stripped (shown later in confirmation prompts)
    - Empty markdown code blocks are filtered out

    If rich is not available, prints plain text.
    """
    if not RICH_AVAILABLE or not text.strip():
        if text.strip():
            print(text)
        return

    # Pattern to match command blocks: <<<tag ... >>>
    command_block_pattern = re.compile(r"(<<<\w+\n.*?>>>)", re.DOTALL)

    # Pattern to match empty or whitespace-only code blocks
    empty_code_block_pattern = re.compile(r"```\w*\s*```", re.DOTALL)

    # Remove empty code blocks first
    text = empty_code_block_pattern.sub("", text)

    # Split text by command blocks
    parts = command_block_pattern.split(text)

    for part in parts:
        if not part.strip():
            continue

        if part.startswith("<<<") and part.rstrip().endswith(">>>"):
            # Command blocks are silently skipped here;
            # they will be shown in the confirmation prompt instead.
            pass
        else:
            # Regular markdown content - render with rich
            # Also filter out any remaining empty code blocks within this part
            part = empty_code_block_pattern.sub("", part)
            if part.strip():
                md = Markdown(part)
                _console.print(md)


# ==============================================================================
# DIFF DISPLAY
# ==============================================================================


def display_unified_diff(
    old_content: str,
    new_content: str,
    old_label: str = "current",
    new_label: str = "new",
    context_lines: int = 3,
    max_lines: int = 50,
) -> None:
    """
    Display a unified diff between old and new content with colored output.

    Args:
        old_content: The original file content
        new_content: The new content to be written
        old_label: Label for the old content (shown in diff header)
        new_label: Label for the new content (shown in diff header)
        context_lines: Number of context lines around changes
        max_lines: Maximum number of diff lines to display
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Generate unified diff
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=new_label,
            n=context_lines,
        )
    )

    if not diff:
        print(f"{Fore.YELLOW}No changes detected.{Style.RESET_ALL}")
        return

    reset = Style.RESET_ALL
    displayed = 0

    for line in diff:
        if displayed >= max_lines:
            remaining = len(diff) - displayed
            print(f"{Fore.YELLOW}  ... ({remaining} more diff lines){reset}")
            break

        # Remove trailing newline for cleaner display
        line_display = line.rstrip("\n\r")

        if line.startswith("---"):
            # Old file header
            print(f"{Fore.RED}{Style.BRIGHT}{line_display}{reset}")
        elif line.startswith("+++"):
            # New file header
            print(f"{Fore.GREEN}{Style.BRIGHT}{line_display}{reset}")
        elif line.startswith("@@"):
            # Hunk header
            print(f"{Fore.CYAN}{line_display}{reset}")
        elif line.startswith("-"):
            # Removed line
            print(f"{Fore.RED}{line_display}{reset}")
        elif line.startswith("+"):
            # Added line
            print(f"{Fore.GREEN}{line_display}{reset}")
        else:
            # Context line
            print(f"{Style.DIM}{line_display}{reset}")

        displayed += 1


# ==============================================================================
# OUTPUT / DISPLAY UTILITIES
# ==============================================================================


class Output:
    """Centralized output utility with consistent formatting and colors."""

    # Separator styles
    SEP_LIGHT = "─" * 70
    SEP_MEDIUM = "━" * 70
    SEP_HEAVY = "═" * 70

    @staticmethod
    def error(msg: str, style: str = None, end: str = "\n", flush: bool = False) -> None:
        """Print error message in red."""
        style = style or ""
        print(f"{style}{Fore.RED}x {msg}{Style.RESET_ALL}", end=end, flush=flush)

    @staticmethod
    def success(msg: str, style: str = None, end: str = "\n", flush: bool = False) -> None:
        """Print success message in green."""
        style = style or ""
        print(f"{style}{Fore.GREEN}✓ {msg}{Style.RESET_ALL}", end=end, flush=flush)

    @staticmethod
    def warning(msg: str, style: str = None, end: str = "\n", flush: bool = False) -> None:
        """Print warning message in yellow."""
        style = style or ""
        print(f"{style}{Fore.YELLOW}⚠ {msg}{Style.RESET_ALL}", end=end, flush=flush)

    @staticmethod
    def info(msg: str, style: str = None, end: str = "\n", flush: bool = False) -> None:
        """Print info message in cyan."""
        style = style or ""
        print(f"{style}{Fore.CYAN}▪ {msg}{Style.RESET_ALL}", end=end, flush=flush)

    @staticmethod
    def status(msg: str, style: str = None, end: str = "\n", flush: bool = False) -> None:
        """Print status message."""
        style = style or ""
        print(f"{style}{Fore.MAGENTA}▸ {msg}{Style.RESET_ALL}", end=end, flush=flush)

    @staticmethod
    def debug(msg: str) -> None:
        """Print debug message in dim."""
        print(f"{Style.DIM}[debug] {msg}{Style.RESET_ALL}")

    @staticmethod
    def header(title: str, content: str = None, style: str = None) -> None:
        """Print a formatted header with optional multi-line content."""
        sep = style or Output.SEP_MEDIUM
        color = f"{Fore.CYAN}{Style.BRIGHT}"
        reset = Style.RESET_ALL

        print(f"\n{color}-- {title} {sep[len(title) + 4 :]}{reset}")
        if content:
            # Handle multi-line content safely
            for line in content.splitlines():
                print(line)
            print(f"{color}{sep}{reset}")

    @staticmethod
    def separator(color: str = Fore.CYAN, style: str = None) -> None:
        """Print a separator line."""
        sep = style or Output.SEP_MEDIUM
        print(f"{color}{sep}{Style.RESET_ALL}")

    @staticmethod
    def section(title: str) -> None:
        """Print a section title."""
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{title}{Style.RESET_ALL}")

    @staticmethod
    def banner(text: str) -> None:
        """Print a prominent banner with consistent coloring on all lines."""
        border = "═" * (len(text))
        color = f"{Fore.YELLOW}{Style.BRIGHT}"
        reset = Style.RESET_ALL

        print(f"\n{color}{border}{reset}")
        print(f"{color}{text}{reset}")
        print(f"{color}{border}{reset}\n")

    @staticmethod
    def command_block(title: str, command: str, color: str = Fore.GREEN) -> None:
        """Display a formatted command block, ensuring all lines are colored."""
        print(f"\n{Fore.CYAN}{title}:{Style.RESET_ALL}")
        for line in command.splitlines():
            print(f"{color}{line}{Style.RESET_ALL}")

    @staticmethod
    def code_block(
        lines: List[str],
        max_lines: int = 20,
        show_numbers: bool = True,
        start_line: int = 1,
    ) -> None:
        """Display code with optional line numbers and consistent coloring."""
        displayed = lines[:max_lines]
        for i, line in enumerate(displayed, start_line):
            if show_numbers:
                # Color the number and the line separately for safety
                print(f"{Fore.WHITE}{i:4d} | {line}{Style.RESET_ALL}")
            else:
                print(f"{Fore.WHITE}{line}{Style.RESET_ALL}")

        if len(lines) > max_lines:
            remaining = len(lines) - max_lines
            print(f"{Fore.YELLOW}  -- ({remaining} more lines){Style.RESET_ALL}")

    @staticmethod
    def file_preview(filepath: str, content: str, max_lines: int = 20) -> None:
        """Display file content preview."""
        lines = content.split("\n")
        Output.info(f"Current content ({len(content)} bytes, {len(lines)} lines):")
        Output.code_block(lines, max_lines)

    @staticmethod
    def file_diff(old_content: str, new_content: str, filepath: str = None, max_lines: int = 50) -> None:
        """Display a diff between old and new file content."""
        old_label = f"a/{filepath}" if filepath else "current"
        new_label = f"b/{filepath}" if filepath else "new"

        Output.section("Changes to be applied")
        display_unified_diff(old_content, new_content, old_label, new_label, max_lines=max_lines)

    @staticmethod
    def execution_result(returncode: int, stdout: str = None, stderr: str = None) -> None:
        """Display command execution results with line-by-line color safety."""
        Output.section("Execution Results")
        if returncode == 0:
            print(f"{Fore.GREEN}+ Return code: {returncode} (success){Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}x Return code: {returncode} (failed){Style.RESET_ALL}")

        if stdout and stdout.strip():
            print(f"\n{Fore.CYAN}STDOUT:{Style.RESET_ALL}")
            for line in stdout.splitlines():
                print(f"{Fore.WHITE}{line}{Style.RESET_ALL}")

        if stderr and stderr.strip():
            print(f"\n{Fore.RED}STDERR:{Style.RESET_ALL}")
            for line in stderr.splitlines():
                print(f"{Fore.RED}{line}{Style.RESET_ALL}")
        Output.separator()

    @staticmethod
    def file_operation(operation: str, filename: str, details: str = None) -> None:
        """Display file operation information."""
        msg = f"{operation}: {filename}"
        if details:
            msg += f" {Style.DIM}({details}){Style.RESET_ALL}"
        Output.info(msg)

    @staticmethod
    def numbered_list(items: List[str], max_preview: int = 80) -> None:
        """Print a numbered list with preview."""
        for i, item in enumerate(items, 1):
            preview = item[:max_preview] + ("..." if len(item) > max_preview else "")
            print(f"{Fore.YELLOW}{i:2d}.{Style.RESET_ALL} {Fore.GREEN}{preview}{Style.RESET_ALL}")

    @staticmethod
    def token_info(expires_at: datetime) -> None:
        """Display token expiration information."""
        timestamp = expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        now = datetime.now(timezone.utc)
        remaining = expires_at - now
        hours = remaining.total_seconds() / 3600
        color = Fore.GREEN if hours > 1 else Fore.YELLOW if hours > 0.5 else Fore.RED
        print(f"{color}Token expires: {timestamp} ({hours:.1f}h remaining){Style.RESET_ALL}")

    @staticmethod
    def help_command(name: str, description: str, indent: int = 2) -> None:
        """Print a help entry for a command."""
        spaces = " " * indent
        print(f"{spaces}{Fore.YELLOW}{name:<20}{Style.RESET_ALL} {description}")

    @staticmethod
    def help_section(title: str) -> None:
        """Print a help section title."""
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{title}:{Style.RESET_ALL}")

    @staticmethod
    def prompt(text: str, color: str = Fore.MAGENTA) -> str:
        """Display a prompt and return user input."""
        # Note: input() handles the trailing reset better if it's inside the string
        return input(f"{color}{Style.BRIGHT}{text}{Style.RESET_ALL} ").strip()

    @staticmethod
    def confirmation_prompt(
        purpose: str, command: str = None, warning: str = None, additional_info: dict = None
    ) -> None:
        """Display command confirmation prompt with details and multi-line safety."""
        sep_color = f"{Fore.YELLOW}{Style.BRIGHT}"
        reset = Style.RESET_ALL

        print(f"\n{sep_color}━━ Command Detected {Output.SEP_MEDIUM[20:]}{reset}")
        print(f"{Fore.CYAN}Purpose:{reset} {purpose}")

        if command:
            print(f"{Fore.CYAN}Command:{reset}")
            # Ensure every line of the command is green
            for line in command.splitlines():
                print(f"{Fore.GREEN}{line}{reset}")

        if warning:
            for line in warning.splitlines():
                print(f"\n{Fore.RED}{line}{reset}")

        if additional_info:
            for key, value in additional_info.items():
                label = key.replace("_", " ").title()
                print(f"{Fore.CYAN}{label}:{reset} {value}")

        print(f"{sep_color}{Output.SEP_MEDIUM}{reset}")


# ==============================================================================
# STREAMING SPINNER ANIMATION
# ==============================================================================


class StreamingSpinner:
    """
    Terminal animation displayed while streaming tokens from the AI model.
    Shows a spinning animation with token count to indicate progress.
    """

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._frame_index = 0
        self._token_count = 0
        self._last_line_len = 0

    def update(self) -> None:
        """Call on each received token to advance the animation."""
        self._token_count += 1
        frame = self.FRAMES[self._frame_index % len(self.FRAMES)]
        self._frame_index += 1

        text = f"\r{Fore.CYAN}{frame} Receiving response... {Style.DIM}({self._token_count} chunks){Style.RESET_ALL}"
        # Pad with spaces to clear any leftover characters from previous longer lines
        padding = max(0, self._last_line_len - len(text)) * " "
        print(f"{text}{padding}", end="", flush=True)
        self._last_line_len = len(text)

    def finish(self) -> None:
        """Clear the spinner line when streaming is complete."""
        # Overwrite the spinner line with spaces and return cursor
        clear = "\r" + " " * (self._last_line_len + 10) + "\r"
        print(clear, end="", flush=True)
