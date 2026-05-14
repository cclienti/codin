# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import base64
import subprocess
from typing import Tuple
from .term_output import Output
from .confirmation_execution import confirm_execution


def _expand_filename(filename: str) -> str:
    """Expand environment variables and user home in filename."""
    return os.path.expandvars(os.path.expanduser(filename))


def command_read_file(code: str) -> str:
    """Process read_file command block and return file content or error."""

    def cmd_error(msg):
        return f"read_file error: {msg}"

    lines = code.splitlines()
    if len(lines) < 3:
        Output.warning("Invalid read_file block, skipping")
        return cmd_error("invalid read_file block")

    mode = lines[0].strip()
    part = lines[1].strip()
    filename = lines[2].strip()

    if mode == "bin":
        mode = "rb"
    elif mode == "text":
        mode = "r"
    else:
        return cmd_error("invalid mode")

    # Parse part specification
    if part == "full":
        part_type = "full"
        start_line = None
        stop_line = None
    elif part.startswith("head "):
        part_type = "head"
        try:
            start_line = int(part[5:].strip())
            stop_line = None
        except ValueError:
            return cmd_error("invalid head N")
    elif part.startswith("tail "):
        part_type = "tail"
        try:
            start_line = int(part[5:].strip())
            stop_line = None
        except ValueError:
            return cmd_error("invalid tail N")
    elif part.startswith("lines "):
        part_type = "lines"
        try:
            range_part = part[6:].strip()
            start_str, stop_str = range_part.split("-")
            start_line = int(start_str)
            stop_line = int(stop_str)
        except ValueError:
            return cmd_error("invalid lines N-M")
    else:
        return cmd_error(f"unknown part specification: {part}")

    if not confirm_execution(
        purpose=f"Read file: {filename}",
        command=None,
        operation_type="file_read",
        additional_info={
            "filepath": filename,
            "mode": mode,
            "part": part,
        },
    ):
        return cmd_error("user cancelled read_file")

    try:
        with open(_expand_filename(filename), mode) as f:
            if part_type == "full":
                content = f.read()
            else:
                all_lines = f.readlines()
                if part_type == "head":
                    content = "".join(all_lines[:start_line])
                elif part_type == "tail":
                    content = "".join(all_lines[-start_line:])
                elif part_type == "lines":
                    content = "".join(all_lines[start_line - 1 : stop_line])

        if mode == "rb":
            content = base64.b64encode(content).decode("ascii")
        Output.file_operation("Read", filename, f"{len(content)} bytes")
        return content
    except Exception as e:
        Output.error(f"Failed to read file {filename}: {e}")
        return cmd_error(str(e))


def command_write_file(code: str) -> str:
    """Process write_file command block and write file content."""

    def cmd_error(msg):
        return f"write_file error: {msg}"

    lines = code.splitlines()
    if len(lines) < 2:
        Output.warning("Invalid write_file block, skipping")
        return cmd_error("invalid write_file block")

    mode = lines[0].strip()
    filename = lines[1].strip()

    # Validate mode
    if mode == "write":
        file_mode = "w"
        operation = "Write"
        operation_type = "file_write"
    elif mode == "append":
        file_mode = "a"
        operation = "Append"
        operation_type = "file_append"
    else:
        return cmd_error(f"invalid mode: {mode}, must be 'write' or 'append'")

    if len(lines) == 2:
        file_content = ""
    else:
        file_content = "\n".join(lines[2:])

    if not confirm_execution(
        purpose=f"{operation} file: {filename}",
        command=None,
        operation_type=operation_type,
        additional_info={
            "filepath": filename,
            "mode": mode,
            "content_size": len(file_content),
        },
        new_content=file_content,
    ):
        return cmd_error("user cancelled write_file")

    try:
        dir_path = os.path.dirname(_expand_filename(filename))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(_expand_filename(filename), file_mode) as f:
            f.write(file_content)
            f.write("\n")
        Output.file_operation(operation + " ok", filename, f"{len(file_content)} bytes")
        return f"write_file ok: written {len(file_content)} bytes"
    except Exception as e:
        Output.error(f"Failed to write file {filename}: {e}")
        return cmd_error(str(e))


def command_execute_shell(code: str) -> str:
    """Process shell command block and return output or error."""

    def cmd_error(msg):
        return f"shell error: {msg}"

    def execute_command(command: str) -> Tuple[int, str, str]:
        """Execute a bash command and return (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out after 300 seconds"
        except Exception as e:
            return -1, "", str(e)

    if not confirm_execution(
        purpose="Execute shell command",
        command=code,
        operation_type="command",
    ):
        return cmd_error("user cancelled shell execution")

    Output.status("Executing command...")
    returncode, stdout, stderr = execute_command(code)

    Output.execution_result(returncode, stdout, stderr)

    feedback = f"shell: command:\n{code}\n\nshell return code: {returncode}\n"
    if stdout:
        feedback += f"STDOUT:\n{stdout}\n"
    if stderr:
        feedback += f"STDERR:\n{stderr}\n"

    if returncode != 0:
        feedback += "\nThe command failed. Please analyze the error and suggest a fix."
    else:
        feedback += "\nThe command succeeded."

    return feedback


def execute_user_command(code: str, capture_output=None, text=None) -> Tuple[int, str, str]:
    """Execute a user command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(code, shell=True, capture_output=capture_output, text=text, timeout=300)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out after 300 seconds"
    except Exception as e:
        return -1, "", str(e)
