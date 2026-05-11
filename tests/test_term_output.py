# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for codin/term_output.py - Output formatting utilities."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from codin.term_output import Output, Style


class TestOutputBasicMessages:
    """Test basic message output methods."""

    def test_error(self, capsys):
        """Test error message output."""
        Output.error("Test error")
        captured = capsys.readouterr()
        assert "x Test error" in captured.out
        assert captured.out.strip().endswith(Style.RESET_ALL)

    def test_success(self, capsys):
        """Test success message output."""
        Output.success("Test success")
        captured = capsys.readouterr()
        assert "✓ Test success" in captured.out

    def test_warning(self, capsys):
        """Test warning message output."""
        Output.warning("Test warning")
        captured = capsys.readouterr()
        assert "⚠ Test warning" in captured.out

    def test_info(self, capsys):
        """Test info message output."""
        Output.info("Test info")
        captured = capsys.readouterr()
        assert "▪ Test info" in captured.out

    def test_status(self, capsys):
        """Test status message output."""
        Output.status("Test status")
        captured = capsys.readouterr()
        assert "▸ Test status" in captured.out

    def test_debug(self, capsys):
        """Test debug message output."""
        Output.debug("Test debug")
        captured = capsys.readouterr()
        assert "[debug] Test debug" in captured.out

    def test_message_with_custom_style(self, capsys):
        """Test message with custom style."""
        Output.error("Test", style=Style.BRIGHT)
        captured = capsys.readouterr()
        assert Style.BRIGHT in captured.out

    def test_message_without_newline(self, capsys):
        """Test message output without trailing newline."""
        Output.info("Test", end="")
        captured = capsys.readouterr()
        assert not captured.out.endswith("\n")


class TestOutputFormatting:
    """Test formatting methods."""

    def test_separator_constants(self):
        """Test separator style constants."""
        assert len(Output.SEP_LIGHT) == 70
        assert len(Output.SEP_MEDIUM) == 70
        assert len(Output.SEP_HEAVY) == 70

    def test_separator(self, capsys):
        """Test separator output."""
        Output.separator()
        captured = capsys.readouterr()
        assert Output.SEP_MEDIUM in captured.out

    def test_section(self, capsys):
        """Test section title output."""
        Output.section("Test Section")
        captured = capsys.readouterr()
        assert "Test Section" in captured.out

    def test_banner(self, capsys):
        """Test banner output."""
        Output.banner("Test Banner")
        captured = capsys.readouterr()
        assert "Test Banner" in captured.out
        assert "═" in captured.out

    def test_header_without_content(self, capsys):
        """Test header without content."""
        Output.header("Test Header")
        captured = capsys.readouterr()
        assert "Test Header" in captured.out

    def test_header_with_content(self, capsys):
        """Test header with content."""
        Output.header("Test Header", "Line 1\nLine 2")
        captured = capsys.readouterr()
        assert "Test Header" in captured.out
        assert "Line 1" in captured.out
        assert "Line 2" in captured.out


class TestOutputCodeBlocks:
    """Test code and command block output methods."""

    def test_command_block(self, capsys):
        """Test command block output."""
        Output.command_block("Test Command", "echo hello")
        captured = capsys.readouterr()
        assert "Test Command:" in captured.out
        assert "echo hello" in captured.out

    def test_command_block_multiline(self, capsys):
        """Test command block with multiline command."""
        command = "line1\nline2\nline3"
        Output.command_block("Test", command)
        captured = capsys.readouterr()
        assert "line1" in captured.out
        assert "line2" in captured.out

    def test_code_block_with_numbers(self, capsys):
        """Test code block with line numbers."""
        lines = ["line1", "line2", "line3"]
        Output.code_block(lines)
        captured = capsys.readouterr()
        assert "1 |" in captured.out
        assert "line1" in captured.out

    def test_code_block_without_numbers(self, capsys):
        """Test code block without line numbers."""
        lines = ["line1", "line2"]
        Output.code_block(lines, show_numbers=False)
        captured = capsys.readouterr()
        assert "|" not in captured.out
        assert "line1" in captured.out

    def test_code_block_max_lines(self, capsys):
        """Test code block with max_lines truncation."""
        lines = [f"line{i}" for i in range(1, 26)]
        Output.code_block(lines, max_lines=10)
        captured = capsys.readouterr()
        assert "line1" in captured.out
        assert "line10" in captured.out
        assert "line11" not in captured.out
        assert "more lines" in captured.out

    def test_file_preview(self, capsys):
        """Test file preview output."""
        content = "line1\nline2\nline3"
        Output.file_preview("test.txt", content)
        captured = capsys.readouterr()
        assert "Current content" in captured.out
        assert "3 lines" in captured.out


class TestOutputExecutionResults:
    """Test execution result display methods."""

    def test_execution_result_success(self, capsys):
        """Test execution result with success."""
        Output.execution_result(0, stdout="output")
        captured = capsys.readouterr()
        assert "Return code: 0" in captured.out
        assert "success" in captured.out
        assert "output" in captured.out

    def test_execution_result_failure(self, capsys):
        """Test execution result with failure."""
        Output.execution_result(1, stderr="error")
        captured = capsys.readouterr()
        assert "Return code: 1" in captured.out
        assert "failed" in captured.out
        assert "error" in captured.out

    def test_execution_result_multiline_output(self, capsys):
        """Test execution result with multiline output."""
        stdout = "line1\nline2\nline3"
        stderr = "err1\nerr2"
        Output.execution_result(1, stdout=stdout, stderr=stderr)
        captured = capsys.readouterr()
        assert "line1" in captured.out
        assert "err1" in captured.out


class TestOutputFileOperations:
    """Test file operation display methods."""

    def test_file_operation_basic(self, capsys):
        """Test basic file operation output."""
        Output.file_operation("Created", "test.txt")
        captured = capsys.readouterr()
        assert "Created: test.txt" in captured.out

    def test_file_operation_with_details(self, capsys):
        """Test file operation with details."""
        Output.file_operation("Modified", "test.txt", "100 bytes")
        captured = capsys.readouterr()
        assert "Modified: test.txt" in captured.out
        assert "100 bytes" in captured.out


class TestOutputLists:
    """Test list output methods."""

    def test_numbered_list(self, capsys):
        """Test numbered list output."""
        items = ["item1", "item2", "item3"]
        Output.numbered_list(items)
        captured = capsys.readouterr()
        assert " 1." in captured.out
        assert "item1" in captured.out

    def test_numbered_list_long_items(self, capsys):
        """Test numbered list with long items truncation."""
        long_item = "a" * 100
        Output.numbered_list([long_item], max_preview=50)
        captured = capsys.readouterr()
        assert "..." in captured.out


class TestOutputTokenInfo:
    """Test token information display."""

    def test_token_info_far_future(self, capsys):
        """Test token info with far future expiration."""
        expires = datetime.now(timezone.utc) + timedelta(hours=5)
        Output.token_info(expires)
        captured = capsys.readouterr()
        assert "Token expires:" in captured.out
        assert "h remaining" in captured.out


class TestOutputHelp:
    """Test help output methods."""

    def test_help_command(self, capsys):
        """Test help command output."""
        Output.help_command("test_cmd", "Test description")
        captured = capsys.readouterr()
        assert "test_cmd" in captured.out
        assert "Test description" in captured.out

    def test_help_section(self, capsys):
        """Test help section output."""
        Output.help_section("Test Section")
        captured = capsys.readouterr()
        assert "Test Section:" in captured.out


class TestOutputPrompts:
    """Test prompt methods."""

    @patch("builtins.input", return_value="test input")
    def test_prompt(self, mock_input):
        """Test basic prompt."""
        result = Output.prompt("Enter something")
        assert result == "test input"

    @patch("builtins.input", return_value="  test  ")
    def test_prompt_strips_whitespace(self, mock_input):
        """Test that prompt strips whitespace."""
        result = Output.prompt("Enter something")
        assert result == "test"

    def test_confirmation_prompt_basic(self, capsys):
        """Test basic confirmation prompt."""
        Output.confirmation_prompt("Test purpose")
        captured = capsys.readouterr()
        assert "Command Detected" in captured.out
        assert "Test purpose" in captured.out

    def test_confirmation_prompt_with_command(self, capsys):
        """Test confirmation prompt with command."""
        Output.confirmation_prompt("Test", command="echo hello")
        captured = capsys.readouterr()
        assert "Command:" in captured.out
        assert "echo hello" in captured.out

    def test_confirmation_prompt_with_warning(self, capsys):
        """Test confirmation prompt with warning."""
        Output.confirmation_prompt("Test", warning="Warning message")
        captured = capsys.readouterr()
        assert "Warning message" in captured.out
