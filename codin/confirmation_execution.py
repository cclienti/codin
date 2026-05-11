# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

import os
_STARTUP_PWD = os.getcwd()

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "codin")
TRUSTED_DIRS_FILE = os.path.join(_CACHE_DIR, "trusted_dirs")


def load_trusted_dirs():
    if not os.path.exists(TRUSTED_DIRS_FILE):
        return set()
    with open(TRUSTED_DIRS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def is_trusted_dir(path):
    abs_dir = os.path.abspath(os.path.dirname(os.path.expanduser(path)))
    if abs_dir == _STARTUP_PWD or abs_dir.startswith(_STARTUP_PWD + os.sep):
        return True
    trusted_dirs = load_trusted_dirs()
    return any(abs_dir == td or abs_dir.startswith(td + os.sep) for td in trusted_dirs)


def add_trusted_dir(path):
    abs_dir = os.path.abspath(os.path.dirname(os.path.expanduser(path)))
    os.makedirs(os.path.dirname(TRUSTED_DIRS_FILE), exist_ok=True)
    trusted_dirs = load_trusted_dirs()
    if abs_dir not in trusted_dirs:
        with open(TRUSTED_DIRS_FILE, "a") as f:
            f.write(abs_dir + "\n")


"""
Confirmation execution module for codin.
Provides comprehensive user confirmation for command execution with detailed prompts.
"""

import os
import shlex
import re
from typing import Optional, Tuple

from .term_output import Fore, Output


class CommandAnalyzer:
    """Analyzes commands to detect potential risks and extract metadata."""

    # Destructive command patterns
    DESTRUCTIVE_PATTERNS = [
        (r"\brm\s+", "File removal command"),
        (r"\brm\s+-rf?\s+", "Recursive file removal"),
        (r"\bfind\s+.*-delete", "Find with delete operation"),
        (r"\bdd\s+", "Direct disk write (dd)"),
        (r">\s*/dev/", "Write to device file"),
    ]

    # File operation patterns
    FILE_OPERATION_PATTERNS = [
        (r"\bmv\s+", "File move/rename"),
        (r"\bcp\s+", "File copy"),
        (r"\bchmod\s+", "Change file permissions"),
        (r"\bchown\s+", "Change file ownership"),
        (r"\btouch\s+", "Create/update file timestamp"),
    ]

    # Privileged operation patterns
    PRIVILEGED_PATTERNS = [
        (r"\bsudo\s+", "Elevated privileges (sudo)"),
        (r"\bsu\s+", "Switch user (su)"),
    ]

    # Network operation patterns
    NETWORK_PATTERNS = [
        (r"\bcurl\s+", "Network request (curl)"),
        (r"\bwget\s+", "Network download (wget)"),
        (r"\bssh\s+", "SSH connection"),
        (r"\bscp\s+", "Secure copy"),
        (r"\brsync\s+", "Remote sync"),
    ]

    # System modification patterns
    SYSTEM_PATTERNS = [
        (r"\bapt\s+", "Package manager (apt)"),
        (r"\byum\s+", "Package manager (yum)"),
        (r"\bdnf\s+", "Package manager (dnf)"),
        (r"\bpip\s+install", "Python package installation"),
        (r"\bnpm\s+install", "Node package installation"),
        (r"\bsystemctl\s+", "System service management"),
    ]

    @staticmethod
    def analyze_command(command: str) -> Tuple[str, list, str]:
        """
        Analyze a command and return (risk_level, warnings, description).

        Returns:
            risk_level: 'critical', 'high', 'medium', 'low'
            warnings: List of warning messages
            description: Brief description of what the command does
        """
        warnings = []
        risk_level = "low"

        # Check for destructive operations
        for pattern, desc in CommandAnalyzer.DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                warnings.append(f"⚠ {desc}")
                risk_level = "critical"

        # Check for privileged operations (forbidden)
        for pattern, desc in CommandAnalyzer.PRIVILEGED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                warnings.append(f"🚫 {desc} - FORBIDDEN")
                risk_level = "critical"

        # Check for system modifications (forbidden)
        for pattern, desc in CommandAnalyzer.SYSTEM_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                warnings.append(f"🚫 {desc} - FORBIDDEN")
                risk_level = "critical"

        # Check for file operations
        if risk_level != "critical":
            for pattern, desc in CommandAnalyzer.FILE_OPERATION_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    warnings.append(f"📝 {desc}")
                    if risk_level == "low":
                        risk_level = "medium"

        # Check for network operations
        if risk_level == "low":
            for pattern, desc in CommandAnalyzer.NETWORK_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    warnings.append(f"🌐 {desc}")
                    risk_level = "medium"

        # Generate description
        description = CommandAnalyzer._generate_description(command)

        return risk_level, warnings, description

    @staticmethod
    def _generate_description(command: str) -> str:
        """Generate a brief description of the command."""
        command_clean = command.strip().split("\n")[0][:100]

        # Extract first command word
        first_word = command_clean.split()[0] if command_clean.split() else ""

        common_commands = {
            "ls": "List directory contents",
            "cd": "Change directory",
            "pwd": "Print working directory",
            "cat": "Display file contents",
            "echo": "Print text",
            "grep": "Search text patterns",
            "find": "Search for files",
            "sed": "Stream editor",
            "awk": "Text processing",
            "git": "Version control operation",
            "make": "Build automation",
            "python": "Execute Python script",
            "bash": "Execute bash script",
            "sh": "Execute shell script",
        }

        return common_commands.get(first_word, f"Execute: {first_word}")

    @staticmethod
    def extract_file_paths(command: str) -> list:
        """Extract potential file paths from command."""
        # Use shlex to properly parse quoted strings
        try:
            words = shlex.split(command)
        except ValueError:
            # Fallback to simple split if shlex fails
            words = command.split()

        # Also detect quoted strings in original command
        quoted_words = []
        in_quote = False
        quote_char = None
        current_word = []
        for char in command:
            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
                current_word = []
            elif char == quote_char and in_quote:
                in_quote = False
                if current_word:
                    quoted_words.append("".join(current_word))
                current_word = []
            elif in_quote:
                current_word.append(char)

        # Combine both word lists
        all_words = set(words + quoted_words)

        paths = []
        for word in all_words:
            # Check if it looks like a path or was quoted
            if "/" in word or word.startswith(".") or word.startswith("~") or word in quoted_words:
                # Check if file exists
                expanded = os.path.expanduser(word)
                if os.path.exists(expanded):
                    paths.append((word, os.path.abspath(expanded)))
                else:
                    paths.append((word, None))
        return paths


def confirm_execution(
    purpose: str,
    command: Optional[str] = None,
    operation_type: str = "command",
    additional_info: Optional[dict] = None,
    new_content: Optional[str] = None,
) -> bool:
    """
    Ask user to confirm command execution with simpler display.

    Args:
        purpose: Brief description of what this operation will do
        command: The actual command to execute (if applicable)
        operation_type: Type of operation ('command', 'file_read', 'file_write', 'file_append')
        additional_info: Dictionary with additional context (e.g., filepath, content_size)
        new_content: For file_write/file_append, the new content to be written (used for diff display)

    Returns:
        True if user confirms, False otherwise
    """
    additional_info = additional_info or {}

    # Trusted directory logic for file reads
    if operation_type == "file_read":
        filepath = additional_info.get("filepath", "")
        if filepath:
            if is_trusted_dir(filepath):
                return True  # Auto-approve trusted directory
            # Prompt user for action
            Output.confirmation_prompt(purpose, command, None, additional_info)
            while True:
                try:
                    response = Output.prompt("Execute? (y/n/a):", Fore.MAGENTA).lower()
                    if response in ["y", "yes"]:
                        return True
                    elif response in ["n", "no"]:
                        return False
                    elif response in ["a", "always"]:
                        add_trusted_dir(filepath)
                        Output.info(
                            f"Directory '{os.path.abspath(os.path.dirname(os.path.expanduser(filepath)))}' added to trusted list."
                        )
                        return True
                    else:
                        Output.warning("Please enter 'y', 'n', or 'a'")
                except (KeyboardInterrupt, EOFError):
                    print()
                    Output.warning("Operation cancelled by user")
                    return False

    # Detect warnings for commands
    warning = None
    if command:
        risk_level, warnings, _ = CommandAnalyzer.analyze_command(command)
        if warnings:
            warning = "\n".join(warnings)
        # Check for forbidden operations
        if risk_level == "critical" and any("FORBIDDEN" in w for w in warnings):
            Output.error("This command contains FORBIDDEN operations and will be rejected.")
            return False

    # Check for file overwrites and show diff if applicable
    show_diff = False
    old_content = ""
    if operation_type in ("file_write", "file_append"):
        filepath = additional_info.get("filepath", "")
        if filepath:
            expanded_path = os.path.expanduser(filepath)
            if os.path.exists(expanded_path):
                file_size = os.path.getsize(expanded_path)
                overwrite_warning = f"File exists and will be OVERWRITTEN (current size: {file_size:,} bytes)"
                if warning:
                    warning = f"{warning}\n{overwrite_warning}"
                else:
                    warning = overwrite_warning

                # Read old content for diff display if new_content is provided
                if new_content is not None:
                    try:
                        with open(expanded_path, "r", encoding="utf-8", errors="replace") as f:
                            old_content = f.read()
                        show_diff = True
                    except Exception:
                        # If we can't read the file, skip diff display
                        pass

    Output.confirmation_prompt(purpose, command, warning, additional_info)

    # Show diff if we have both old and new content
    if show_diff and new_content is not None:
        filepath = additional_info.get("filepath", "")
        # For append operations, show what the final content will look like
        if operation_type == "file_append":
            final_content = old_content + new_content + "\n"
            Output.file_diff(old_content, final_content, filepath)
        else:
            Output.file_diff(old_content, new_content + "\n", filepath)

    # Get user confirmation
    while True:
        try:
            response = Output.prompt("Execute? (y/n):", Fore.MAGENTA).lower()
            if response in ["y", "yes"]:
                return True
            elif response in ["n", "no"]:
                return False
            else:
                Output.warning("Please enter 'y' or 'n'")
        except (KeyboardInterrupt, EOFError):
            print()
            Output.warning("Operation cancelled by user")
            return False
