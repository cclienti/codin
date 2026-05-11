# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for codin/commands.py module."""

import os
import tempfile
from unittest.mock import patch
from codin.commands import command_read_file, command_write_file, command_execute_shell


class TestCommandReadFile:
    """Tests for command_read_file function."""

    @patch("codin.commands.confirm_execution")
    def test_read_full_text_file(self, mock_confirm):
        """Test reading a full text file."""
        mock_confirm.return_value = True

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line 1\nline 2\nline 3\n")
            temp_file = f.name

        try:
            code = f"text\nfull\n{temp_file}"
            result = command_read_file(code)
            assert result == "line 1\nline 2\nline 3\n"
        finally:
            os.unlink(temp_file)

    @patch("codin.commands.confirm_execution")
    def test_read_head_lines(self, mock_confirm):
        """Test reading first N lines."""
        mock_confirm.return_value = True

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line 1\nline 2\nline 3\nline 4\n")
            temp_file = f.name

        try:
            code = f"text\nhead 2\n{temp_file}"
            result = command_read_file(code)
            assert result == "line 1\nline 2\n"
        finally:
            os.unlink(temp_file)

    @patch("codin.commands.confirm_execution")
    def test_read_tail_lines(self, mock_confirm):
        """Test reading last N lines."""
        mock_confirm.return_value = True

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line 1\nline 2\nline 3\nline 4\n")
            temp_file = f.name

        try:
            code = f"text\ntail 2\n{temp_file}"
            result = command_read_file(code)
            assert result == "line 3\nline 4\n"
        finally:
            os.unlink(temp_file)

    @patch("codin.commands.confirm_execution")
    def test_read_lines_range(self, mock_confirm):
        """Test reading specific line range."""
        mock_confirm.return_value = True

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line 1\nline 2\nline 3\nline 4\nline 5\n")
            temp_file = f.name

        try:
            code = f"text\nlines 2-4\n{temp_file}"
            result = command_read_file(code)
            assert result == "line 2\nline 3\nline 4\n"
        finally:
            os.unlink(temp_file)

    @patch("codin.commands.confirm_execution")
    def test_read_binary_file(self, mock_confirm):
        """Test reading a binary file."""
        mock_confirm.return_value = True

        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            temp_file = f.name

        try:
            code = f"bin\nfull\n{temp_file}"
            result = command_read_file(code)
            assert result == "AAECAw=="
        finally:
            os.unlink(temp_file)

    @patch("codin.commands.confirm_execution")
    def test_read_file_user_cancelled(self, mock_confirm):
        """Test when user cancels the operation."""
        mock_confirm.return_value = False

        code = "text\nfull\n/tmp/test.txt"
        result = command_read_file(code)
        assert result == "read_file error: user cancelled read_file"

    def test_read_file_invalid_block(self):
        """Test with invalid read_file block."""
        code = "text\nfull"  # Missing filename
        result = command_read_file(code)
        assert result == "read_file error: invalid read_file block"

    def test_read_file_invalid_mode(self):
        """Test with invalid mode."""
        code = "invalid_mode\nfull\n/tmp/test.txt"
        result = command_read_file(code)
        assert result == "read_file error: invalid mode"

    def test_read_file_invalid_head(self):
        """Test with invalid head specification."""
        code = "text\nhead abc\n/tmp/test.txt"
        result = command_read_file(code)
        assert result == "read_file error: invalid head N"

    def test_read_file_invalid_tail(self):
        """Test with invalid tail specification."""
        code = "text\ntail xyz\n/tmp/test.txt"
        result = command_read_file(code)
        assert result == "read_file error: invalid tail N"

    def test_read_file_invalid_lines(self):
        """Test with invalid lines specification."""
        code = "text\nlines 1,2\n/tmp/test.txt"
        result = command_read_file(code)
        assert result == "read_file error: invalid lines N-M"

    def test_read_file_unknown_part(self):
        """Test with unknown part specification."""
        code = "text\nunknown_part\n/tmp/test.txt"
        result = command_read_file(code)
        assert result == "read_file error: unknown part specification: unknown_part"

    @patch("codin.commands.confirm_execution")
    def test_read_file_not_found(self, mock_confirm):
        """Test reading a non-existent file."""
        mock_confirm.return_value = True

        code = "text\nfull\n/nonexistent/file.txt"
        result = command_read_file(code)
        assert result.startswith("read_file error:")


class TestCommandWriteFile:
    """Tests for command_write_file function."""

    @patch("codin.commands.confirm_execution")
    def test_write_file_success(self, mock_confirm):
        """Test writing a file successfully."""
        mock_confirm.return_value = True

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, "test.txt")
            code = f"write\n{temp_file}\nHello World\nLine 2"

            result = command_write_file(code)

            assert result == "write_file ok: written 18 bytes"
            with open(temp_file, "r") as f:
                content = f.read()
            assert content == "Hello World\nLine 2\n"

    @patch("codin.commands.confirm_execution")
    def test_write_file_user_cancelled(self, mock_confirm):
        """Test when user cancels the operation."""
        mock_confirm.return_value = False

        code = "write\n/tmp/test.txt\nContent"
        result = command_write_file(code)
        assert result == "write_file error: user cancelled write_file"

    @patch("codin.commands.confirm_execution")
    def test_write_file_permission_error(self, mock_confirm):
        """Test writing to a file without permissions."""
        mock_confirm.return_value = True

        code = "/root/test.txt\nContent"
        result = command_write_file(code)
        assert result.startswith("write_file error:")
        code = "write\n/root/test.txt\nContent"

    @patch("codin.commands.confirm_execution")
    def test_write_empty_file(self, mock_confirm):
        """Test writing an empty file."""
        mock_confirm.return_value = True

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, "empty.txt")
            code = f"write\n{temp_file}\n"

            result = command_write_file(code)

            assert result == "write_file ok: written 0 bytes"
            with open(temp_file, "r") as f:
                content = f.read()
            assert content == "\n"

    @patch("codin.commands.confirm_execution")
    def test_write_file_empty_file_2(self, mock_confirm):
        """Test with invalid write_file block."""
        mock_confirm.return_value = True

        code = "write\n/tmp/test.txt"  # Missing content
        result = command_write_file(code)

    @patch("codin.commands.confirm_execution")
    def test_append_file_success(self, mock_confirm):
        """Test appending to an existing file."""
        mock_confirm.return_value = True

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, "test.txt")
            # Create initial file
            with open(temp_file, "w") as f:
                f.write("Initial content\n")

            # Append to file
            code = f"append\n{temp_file}\nAppended content"
            result = command_write_file(code)

            assert result == "write_file ok: written 16 bytes"
            with open(temp_file, "r") as f:
                content = f.read()
            assert content == "Initial content\nAppended content\n"

    @patch("codin.commands.confirm_execution")
    def test_append_file_new_file(self, mock_confirm):
        """Test appending to a non-existent file (creates new file)."""
        mock_confirm.return_value = True

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, "newfile.txt")

            code = f"append\n{temp_file}\nNew content"
            result = command_write_file(code)

            assert result == "write_file ok: written 11 bytes"
            with open(temp_file, "r") as f:
                content = f.read()
            assert content == "New content\n"

    @patch("codin.commands.confirm_execution")
    def test_write_file_invalid_mode(self, mock_confirm):
        """Test with invalid mode."""
        mock_confirm.return_value = True

        code = "invalid_mode\n/tmp/test.txt\nContent"
        result = command_write_file(code)
        assert result == "write_file error: invalid mode: invalid_mode, must be 'write' or 'append'"


class TestCommandExecuteShell:
    """Tests for command_execute_shell function."""

    @patch("codin.commands.confirm_execution")
    def test_execute_shell_success(self, mock_confirm):
        """Test executing a successful shell command."""
        mock_confirm.return_value = True

        code = "echo 'Hello World'"
        result = command_execute_shell(code)

        assert "shell return code: 0" in result
        assert "Hello World" in result
        assert "The command succeeded." in result

    @patch("codin.commands.confirm_execution")
    def test_execute_shell_failure(self, mock_confirm):
        """Test executing a failing shell command."""
        mock_confirm.return_value = True

        code = "ls /nonexistent_directory"
        result = command_execute_shell(code)

        assert "shell return code:" in result
        assert "The command failed." in result

    @patch("codin.commands.confirm_execution")
    def test_execute_shell_user_cancelled(self, mock_confirm):
        """Test when user cancels the operation."""
        mock_confirm.return_value = False

        code = "echo 'test'"
        result = command_execute_shell(code)
        assert result == "shell error: user cancelled shell execution"

    @patch("codin.commands.confirm_execution")
    def test_execute_shell_with_stderr(self, mock_confirm):
        """Test command that produces stderr output."""
        mock_confirm.return_value = True

        code = "echo 'error' >&2"
        result = command_execute_shell(code)

        assert "STDERR:" in result
        assert "error" in result

    @patch("codin.commands.confirm_execution")
    @patch("codin.commands.subprocess.run")
    def test_execute_shell_timeout(self, mock_run, mock_confirm):
        """Test command timeout."""
        import subprocess

        mock_confirm.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 1000", timeout=300)

        code = "sleep 1000"
        result = command_execute_shell(code)

        assert "shell return code: -1" in result
        assert "timed out" in result

    @patch("codin.commands.confirm_execution")
    @patch("codin.commands.subprocess.run")
    def test_execute_shell_exception(self, mock_run, mock_confirm):
        """Test command that raises an exception."""
        mock_confirm.return_value = True
        mock_run.side_effect = Exception("Test exception")

        code = "some_command"
        result = command_execute_shell(code)

        assert "shell return code: -1" in result
        assert "Test exception" in result
