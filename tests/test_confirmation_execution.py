# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Unit tests for codin/confirmation_execution.py module.
Tests CommandAnalyzer and confirm_execution functionality.
"""

from unittest.mock import patch
from codin.confirmation_execution import CommandAnalyzer, confirm_execution


class TestCommandAnalyzer:
    """Test suite for CommandAnalyzer class."""

    def test_analyze_destructive_rm_command(self):
        """Test detection of rm command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("rm file.txt")

        assert risk_level == "critical"
        assert any("File removal command" in w for w in warnings)
        assert len(warnings) >= 1

    def test_analyze_destructive_rm_rf_command(self):
        """Test detection of rm -rf command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("rm -rf /tmp/test")

        assert risk_level == "critical"
        assert any("Recursive file removal" in w for w in warnings)

    def test_analyze_find_delete_command(self):
        """Test detection of find with -delete."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("find . -name '*.tmp' -delete")

        assert risk_level == "critical"
        assert any("Find with delete operation" in w for w in warnings)

    def test_analyze_dd_command(self):
        """Test detection of dd command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("dd if=/dev/zero of=/dev/sda")

        assert risk_level == "critical"
        assert any("Direct disk write" in w for w in warnings)

    def test_analyze_device_write_command(self):
        """Test detection of write to device file."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("echo test > /dev/null")

        assert risk_level == "critical"
        assert any("Write to device file" in w for w in warnings)

    def test_analyze_file_operation_mv(self):
        """Test detection of mv command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("mv old.txt new.txt")

        assert risk_level == "medium"
        assert any("File move/rename" in w for w in warnings)

    def test_analyze_file_operation_cp(self):
        """Test detection of cp command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("cp source.txt dest.txt")

        assert risk_level == "medium"
        assert any("File copy" in w for w in warnings)

    def test_analyze_file_operation_chmod(self):
        """Test detection of chmod command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("chmod 755 script.sh")

        assert risk_level == "medium"
        assert any("Change file permissions" in w for w in warnings)

    def test_analyze_file_operation_chown(self):
        """Test detection of chown command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("chown user:group file.txt")

        assert risk_level == "medium"
        assert any("Change file ownership" in w for w in warnings)

    def test_analyze_file_operation_touch(self):
        """Test detection of touch command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("touch newfile.txt")

        assert risk_level == "medium"
        assert any("Create/update file timestamp" in w for w in warnings)

    def test_analyze_privileged_sudo(self):
        """Test detection of sudo (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("sudo apt update")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "sudo" in w for w in warnings)

    def test_analyze_privileged_su(self):
        """Test detection of su (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("su - root")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "su" in w for w in warnings)

    def test_analyze_network_curl(self):
        """Test detection of curl command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("curl https://example.com")

        assert risk_level == "medium"
        assert any("Network request (curl)" in w for w in warnings)

    def test_analyze_network_wget(self):
        """Test detection of wget command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("wget https://example.com/file.zip")

        assert risk_level == "medium"
        assert any("Network download (wget)" in w for w in warnings)

    def test_analyze_network_ssh(self):
        """Test detection of ssh command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("ssh user@example.com")

        assert risk_level == "medium"
        assert any("SSH connection" in w for w in warnings)

    def test_analyze_network_scp(self):
        """Test detection of scp command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("scp file.txt user@host:/path")

        assert risk_level == "medium"
        assert any("Secure copy" in w for w in warnings)

    def test_analyze_network_rsync(self):
        """Test detection of rsync command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("rsync -av src/ dest/")

        assert risk_level == "medium"
        assert any("Remote sync" in w for w in warnings)

    def test_analyze_system_apt(self):
        """Test detection of apt (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("apt install package")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "apt" in w for w in warnings)

    def test_analyze_system_yum(self):
        """Test detection of yum (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("yum install package")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "yum" in w for w in warnings)

    def test_analyze_system_dnf(self):
        """Test detection of dnf (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("dnf install package")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "dnf" in w for w in warnings)

    def test_analyze_system_pip_install(self):
        """Test detection of pip install (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("pip install requests")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "Python package" in w for w in warnings)

    def test_analyze_system_npm_install(self):
        """Test detection of npm install (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("npm install express")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "Node package" in w for w in warnings)

    def test_analyze_system_systemctl(self):
        """Test detection of systemctl (forbidden)."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("systemctl restart nginx")

        assert risk_level == "critical"
        assert any("FORBIDDEN" in w and "System service" in w for w in warnings)

    def test_analyze_safe_ls_command(self):
        """Test analysis of safe ls command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("ls -la")

        assert risk_level == "low"
        assert len(warnings) == 0
        assert "List directory contents" in description

    def test_analyze_safe_pwd_command(self):
        """Test analysis of safe pwd command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("pwd")

        assert risk_level == "low"
        assert len(warnings) == 0
        assert "Print working directory" in description

    def test_analyze_safe_cat_command(self):
        """Test analysis of safe cat command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("cat file.txt")

        assert risk_level == "low"
        assert len(warnings) == 0
        assert "Display file contents" in description

    def test_analyze_safe_echo_command(self):
        """Test analysis of safe echo command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("echo 'Hello World'")

        assert risk_level == "low"
        assert len(warnings) == 0
        assert "Print text" in description

    def test_analyze_safe_grep_command(self):
        """Test analysis of safe grep command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("grep pattern file.txt")

        assert risk_level == "low"
        assert len(warnings) == 0
        assert "Search text patterns" in description

    def test_analyze_safe_git_command(self):
        """Test analysis of safe git command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("git status")

        assert risk_level == "low"
        assert len(warnings) == 0
        assert "Version control operation" in description

    def test_analyze_case_insensitive(self):
        """Test that pattern matching is case-insensitive."""
        risk_level1, warnings1, _ = CommandAnalyzer.analyze_command("RM file.txt")
        risk_level2, warnings2, _ = CommandAnalyzer.analyze_command("rm file.txt")

        assert risk_level1 == risk_level2 == "critical"
        assert len(warnings1) == len(warnings2)

    def test_analyze_multiline_command(self):
        """Test analysis of multiline command."""
        command = "ls -la\nrm file.txt"
        risk_level, warnings, description = CommandAnalyzer.analyze_command(command)

        # Should still detect rm in the command
        assert risk_level == "critical"
        assert any("File removal command" in w for w in warnings)

    def test_generate_description_unknown_command(self):
        """Test description generation for unknown command."""
        risk_level, warnings, description = CommandAnalyzer.analyze_command("unknowncmd arg1 arg2")

        assert "unknowncmd" in description

    def test_extract_file_paths_absolute_path(self):
        """Test extraction of absolute file paths."""
        command = "cat /etc/hosts"
        paths = CommandAnalyzer.extract_file_paths(command)

        # /etc/hosts should be found if it exists
        assert any("/etc/hosts" in path[0] for path in paths)

    def test_extract_file_paths_relative_path(self):
        """Test extraction of relative file paths."""
        command = "cat ./test.txt"
        paths = CommandAnalyzer.extract_file_paths(command)

        assert any("./test.txt" in path[0] for path in paths)

    def test_extract_file_paths_tilde_expansion(self):
        """Test extraction of paths with tilde."""
        command = "cat ~/test.txt"
        paths = CommandAnalyzer.extract_file_paths(command)

        assert any("~/test.txt" in path[0] for path in paths)

    def test_extract_file_paths_quoted(self):
        """Test extraction of quoted file paths."""
        command = "cat 'file with spaces.txt'"
        paths = CommandAnalyzer.extract_file_paths(command)

        # Should extract without quotes
        assert len(paths) > 0

    def test_extract_file_paths_nonexistent(self):
        """Test extraction of non-existent file paths."""
        command = "cat /this/path/does/not/exist.txt"
        paths = CommandAnalyzer.extract_file_paths(command)

        # Should still extract the path
        assert any("/this/path/does/not/exist.txt" in path[0] for path in paths)
        # But absolute path should be None for non-existent
        for path, abspath in paths:
            if "/this/path/does/not/exist.txt" in path:
                assert abspath is None

    @patch("os.path.exists")
    def test_extract_file_paths_existing_file(self, mock_exists):
        """Test extraction with existing file."""
        mock_exists.return_value = True
        command = "cat /tmp/test.txt"
        paths = CommandAnalyzer.extract_file_paths(command)

        assert len(paths) > 0
        # Should have absolute path for existing file
        for path, abspath in paths:
            if "/tmp/test.txt" in path:
                assert abspath is not None


class TestConfirmExecution:
    """Test suite for confirm_execution function."""

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_user_accepts(self, mock_confirm_prompt, mock_prompt):
        """Test user accepting the execution."""
        mock_prompt.return_value = "y"

        result = confirm_execution("Test operation", "ls -la")

        assert result is True
        mock_confirm_prompt.assert_called_once()
        mock_prompt.assert_called_once()

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_user_accepts_yes(self, mock_confirm_prompt, mock_prompt):
        """Test user accepting with 'yes'."""
        mock_prompt.return_value = "yes"

        result = confirm_execution("Test operation", "ls -la")

        assert result is True

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_user_rejects(self, mock_confirm_prompt, mock_prompt):
        """Test user rejecting the execution."""
        mock_prompt.return_value = "n"

        result = confirm_execution("Test operation", "ls -la")

        assert result is False

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_user_rejects_no(self, mock_confirm_prompt, mock_prompt):
        """Test user rejecting with 'no'."""
        mock_prompt.return_value = "no"

        result = confirm_execution("Test operation", "ls -la")

        assert result is False

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    @patch("codin.confirmation_execution.Output.warning")
    def test_confirm_execution_invalid_then_valid(self, mock_warning, mock_confirm_prompt, mock_prompt):
        """Test invalid input followed by valid input."""
        mock_prompt.side_effect = ["invalid", "maybe", "y"]

        result = confirm_execution("Test operation", "ls -la")

        assert result is True
        assert mock_warning.call_count == 2  # Called for each invalid input

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_keyboard_interrupt(self, mock_confirm_prompt, mock_prompt):
        """Test handling of KeyboardInterrupt."""
        mock_prompt.side_effect = KeyboardInterrupt()

        result = confirm_execution("Test operation", "ls -la")

        assert result is False

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_eof_error(self, mock_confirm_prompt, mock_prompt):
        """Test handling of EOFError."""
        mock_prompt.side_effect = EOFError()

        result = confirm_execution("Test operation", "ls -la")

        assert result is False

    @patch("codin.confirmation_execution.Output.error")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_forbidden_sudo(self, mock_confirm_prompt, mock_error):
        """Test that sudo commands are rejected without prompting."""
        result = confirm_execution("Test operation", "sudo apt update")

        assert result is False
        mock_error.assert_called_once()
        assert "FORBIDDEN" in mock_error.call_args[0][0]

    @patch("codin.confirmation_execution.Output.error")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_forbidden_apt(self, mock_confirm_prompt, mock_error):
        """Test that apt commands are rejected without prompting."""
        result = confirm_execution("Test operation", "apt install package")

        assert result is False
        mock_error.assert_called_once()

    @patch("codin.confirmation_execution.Output.error")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_forbidden_pip_install(self, mock_confirm_prompt, mock_error):
        """Test that pip install commands are rejected without prompting."""
        result = confirm_execution("Test operation", "pip install requests")

        assert result is False
        mock_error.assert_called_once()

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_with_warnings(self, mock_confirm_prompt, mock_prompt):
        """Test execution with warnings displayed."""
        mock_prompt.return_value = "y"

        result = confirm_execution("Test operation", "rm file.txt")

        assert result is True
        # Should have been called with warning parameter
        call_args = mock_confirm_prompt.call_args
        assert call_args[0][2] is not None  # Warning should be present

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_file_read_operation(self, mock_confirm_prompt, mock_prompt):
        """Test file read operation type."""
        mock_prompt.return_value = "y"

        result = confirm_execution(
            "Read file", operation_type="file_read", additional_info={"filepath": "/tmp/test.txt"}
        )

        assert result is True
        mock_confirm_prompt.assert_called_once()

    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_file_write_overwrite(self, mock_confirm_prompt, mock_prompt, mock_getsize, mock_exists):
        """Test file write operation with overwrite warning."""
        mock_prompt.return_value = "y"
        mock_exists.return_value = True
        mock_getsize.return_value = 1024

        result = confirm_execution(
            "Write file", operation_type="file_write", additional_info={"filepath": "/tmp/test.txt"}
        )

        assert result is True
        # Should have overwrite warning
        call_args = mock_confirm_prompt.call_args
        assert call_args[0][2] is not None
        assert "OVERWRITTEN" in call_args[0][2]
        assert "1,024 bytes" in call_args[0][2]

    @patch("os.path.exists")
    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_file_write_new_file(self, mock_confirm_prompt, mock_prompt, mock_exists):
        """Test file write operation for new file."""
        mock_prompt.return_value = "y"
        mock_exists.return_value = False

        result = confirm_execution(
            "Write file", operation_type="file_write", additional_info={"filepath": "/tmp/newfile.txt"}
        )

        assert result is True
        # Should not have overwrite warning
        call_args = mock_confirm_prompt.call_args
        warning = call_args[0][2]
        if warning:
            assert "OVERWRITTEN" not in warning

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_no_command(self, mock_confirm_prompt, mock_prompt):
        """Test confirm_execution without a command."""
        mock_prompt.return_value = "y"

        result = confirm_execution("Generic operation")

        assert result is True
        mock_confirm_prompt.assert_called_once()

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_with_additional_info(self, mock_confirm_prompt, mock_prompt):
        """Test confirm_execution with additional_info dict."""
        mock_prompt.return_value = "y"

        result = confirm_execution("Test operation", "ls -la", additional_info={"custom_key": "custom_value"})

        assert result is True

    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_destructive_command_with_file_overwrite(
        self, mock_confirm_prompt, mock_prompt, mock_getsize, mock_exists
    ):
        """Test destructive command combined with file overwrite warning."""
        mock_prompt.return_value = "y"
        mock_exists.return_value = True
        mock_getsize.return_value = 2048

        result = confirm_execution(
            "Dangerous operation",
            "rm -rf /tmp/test",
            operation_type="file_write",
            additional_info={"filepath": "/tmp/output.txt"},
        )

        assert result is True
        # Should have both warnings
        call_args = mock_confirm_prompt.call_args
        warning = call_args[0][2]
        assert warning is not None
        assert "Recursive file removal" in warning
        assert "OVERWRITTEN" in warning

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_case_insensitive_response(self, mock_confirm_prompt, mock_prompt):
        """Test that user responses are case-insensitive."""
        mock_prompt.return_value = "Y"

        result = confirm_execution("Test operation", "ls -la")

        assert result is True

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_no_case_insensitive(self, mock_confirm_prompt, mock_prompt):
        """Test that 'N' is accepted as rejection."""
        mock_prompt.return_value = "N"

        result = confirm_execution("Test operation", "ls -la")

        assert result is False

    @patch("os.path.expanduser")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_tilde_expansion_in_filepath(
        self, mock_confirm_prompt, mock_prompt, mock_getsize, mock_exists, mock_expanduser
    ):
        """Test that tilde is expanded in file paths."""
        mock_prompt.return_value = "y"
        mock_expanduser.return_value = "/home/user/test.txt"
        mock_exists.return_value = True
        mock_getsize.return_value = 512

        result = confirm_execution(
            "Write file", operation_type="file_write", additional_info={"filepath": "~/test.txt"}
        )

        assert result is True
        mock_expanduser.assert_called_once_with("~/test.txt")

    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_file_append_overwrite(self, mock_confirm_prompt, mock_prompt, mock_getsize, mock_exists):
        """Test file append operation with overwrite warning."""
        mock_prompt.return_value = "y"
        mock_exists.return_value = True
        mock_getsize.return_value = 2048

        result = confirm_execution(
            "Append to file", operation_type="file_append", additional_info={"filepath": "/tmp/test.txt"}
        )

        assert result is True
        # Should have overwrite warning (even for append)
        call_args = mock_confirm_prompt.call_args
        assert call_args[0][2] is not None
        assert "OVERWRITTEN" in call_args[0][2]
        assert "2,048 bytes" in call_args[0][2]

    @patch("os.path.exists")
    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_file_append_new_file(self, mock_confirm_prompt, mock_prompt, mock_exists):
        """Test file append operation for new file."""
        mock_prompt.return_value = "y"
        mock_exists.return_value = False

        result = confirm_execution(
            "Append to file", operation_type="file_append", additional_info={"filepath": "/tmp/newfile.txt"}
        )

        assert result is True
        # Should not have overwrite warning
        call_args = mock_confirm_prompt.call_args
        warning = call_args[0][2]
        if warning:
            assert "OVERWRITTEN" not in warning

    @patch("codin.confirmation_execution.Output.prompt")
    @patch("codin.confirmation_execution.Output.confirmation_prompt")
    def test_confirm_execution_file_append_with_destructive_command(self, mock_confirm_prompt, mock_prompt):
        """Test file append with destructive pattern in command."""
        mock_prompt.return_value = "y"

        result = confirm_execution(
            "Append to file",
            command="rm -rf /tmp/something",
            operation_type="file_append",
            additional_info={"filepath": "/tmp/test.txt"},
        )

        assert result is True
        # Should have warning about destructive command
        call_args = mock_confirm_prompt.call_args
        assert call_args[0][2] is not None
        assert "removal" in call_args[0][2].lower()
