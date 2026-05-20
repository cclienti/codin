# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""Remote operations (SSH/rsync) for codin history backup."""

import subprocess
from pathlib import Path
from typing import List

from .remote import Remote
from .term_output import Output


def _ssh_target(remote: Remote) -> str:
    return f"{remote.user}@{remote.host}"


def remote_save(remote: Remote, local_path: Path) -> bool:
    """Upload a local .jsonl session file to the remote using rsync."""
    if remote.protocol != "ssh":
        Output.error(f"Unsupported protocol: {remote.protocol}")
        return False
    dest = f"{_ssh_target(remote)}:{remote.path}/"
    cmd = ["rsync", "-az", "--mkpath", str(local_path), dest]
    Output.status(f"Saving {local_path.name} to {remote.name} ({remote.user}@{remote.host}:{remote.path}) ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        Output.success(f"Saved {local_path.name} to remote '{remote.name}'")
        return True
    Output.error(f"rsync failed (rc={result.returncode}): {result.stderr.strip()}")
    return False


def remote_list(remote: Remote) -> List[str]:
    """List .jsonl session files available on the remote."""
    if remote.protocol != "ssh":
        Output.error(f"Unsupported protocol: {remote.protocol}")
        return []
    cmd = ["ssh", _ssh_target(remote), f"ls {remote.path}/*.jsonl 2>/dev/null || true"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if not result.stdout.strip():
        return []
    return [Path(f).name for f in result.stdout.strip().splitlines() if f.strip()]


def remote_delete(remote: Remote, filename: str) -> bool:
    """Delete a session file on the remote."""
    if remote.protocol != "ssh":
        Output.error(f"Unsupported protocol: {remote.protocol}")
        return False
    remote_file = f"{remote.path}/{filename}"
    cmd = ["ssh", _ssh_target(remote), f"rm -f -- {remote_file}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        Output.success(f"Deleted '{filename}' from remote '{remote.name}'")
        return True
    Output.error(f"Delete failed (rc={result.returncode}): {result.stderr.strip()}")
    return False


def remote_load(remote: Remote, filename: str, local_dest: Path) -> bool:
    """Download a session file from the remote to local_dest."""
    if remote.protocol != "ssh":
        Output.error(f"Unsupported protocol: {remote.protocol}")
        return False
    src = f"{_ssh_target(remote)}:{remote.path}/{filename}"
    cmd = ["rsync", "-az", src, str(local_dest)]
    Output.status(f"Loading '{filename}' from remote '{remote.name}' ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        Output.success(f"Downloaded to {local_dest}")
        return True
    Output.error(f"rsync failed (rc={result.returncode}): {result.stderr.strip()}")
    return False
