# Codin'Chat - Interactive CLI assistant powered by GitHub Copilot
# Copyright (C) 2026  Christophe Clienti
# SPDX-License-Identifier: GPL-3.0-or-later

"""Remote configuration management for codin history backup."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from .term_output import Output


@dataclass
class Remote:
    name: str
    protocol: str  # "ssh" for now, extensible later
    host: str
    user: str
    path: str

    def display_str(self) -> str:
        if self.protocol == "ssh":
            return f"{self.name}  [{self.protocol}]  {self.user}@{self.host}:{self.path}"
        return f"{self.name}  [{self.protocol}]  {self.host}:{self.path}"


class RemoteManager:
    CONFIG_FILE = Path.home() / ".config" / "codin" / "remotes.json"

    def __init__(self):
        self._remotes: List[Remote] = []
        self._load()

    def _load(self):
        if not self.CONFIG_FILE.exists():
            return
        try:
            data = json.loads(self.CONFIG_FILE.read_text())
            self._remotes = [Remote(**r) for r in data.get("remotes", [])]
        except Exception as e:
            Output.warning(f"Could not load remotes config: {e}")

    def _save(self):
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"remotes": [asdict(r) for r in self._remotes]}
        self.CONFIG_FILE.write_text(json.dumps(data, indent=2))

    def add(self, name: str, protocol: str, host: str, user: str, path: str) -> Remote:
        """Add or replace a remote. New remotes are appended at the end."""
        self._remotes = [r for r in self._remotes if r.name != name]
        remote = Remote(name=name, protocol=protocol, host=host, user=user, path=path)
        self._remotes.append(remote)
        self._save()
        return remote

    def remove(self, name: str) -> bool:
        """Remove a remote by name. Returns True if found and removed."""
        before = len(self._remotes)
        self._remotes = [r for r in self._remotes if r.name != name]
        if len(self._remotes) == before:
            return False
        self._save()
        return True

    def get(self, name: Optional[str] = None) -> Optional[Remote]:
        """Get a remote by name, or the first remote (default) if name is None."""
        if not self._remotes:
            return None
        if name is None:
            return self._remotes[0]
        for r in self._remotes:
            if r.name == name:
                return r
        return None

    def list_remotes(self) -> List[Remote]:
        return list(self._remotes)

    @property
    def default(self) -> Optional[str]:
        """The default remote is always the first one."""
        return self._remotes[0].name if self._remotes else None

    def set_default(self, name: str) -> bool:
        """Make a remote the default by moving it to the first position."""
        idx = next((i for i, r in enumerate(self._remotes) if r.name == name), None)
        if idx is None:
            return False
        remote = self._remotes.pop(idx)
        self._remotes.insert(0, remote)
        self._save()
        return True
