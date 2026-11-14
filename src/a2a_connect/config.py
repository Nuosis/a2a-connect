"""Connector configuration and local state."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("A2A_CONNECT_CONFIG", "~/.config/a2a-connect/config.toml")).expanduser()
STATE_DIR = Path(os.environ.get("A2A_CONNECT_STATE", "~/.local/state/a2a-connect")).expanduser()

TEMPLATE = """# a2a-connect configuration
# Clarity A2A hub
api_base = "https://api.claritycustomsoftware.com"
# Registered agent handle this connector receives messages for
handle = "{handle}"
# Your organization's Clarity API key (clrtok_...). Either set it here or give a
# command that prints it, e.g. api_key_command = ["security", "find-generic-password", "-s", "a2a-connect", "-w"]
api_key = "{api_key}"
# Folder Codex runs in when a message arrives
workdir = "{workdir}"
# Codex executable and any extra options passed to `codex exec`
codex_bin = "codex"
codex_args = []
"""


@dataclass
class Config:
    api_base: str
    handle: str
    api_key: str
    workdir: Path
    codex_bin: str = "codex"
    codex_args: list[str] = field(default_factory=list)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "User-Agent": "a2a-connect/0.1"}


def load_config(path: Path = CONFIG_PATH) -> Config:
    data = tomllib.loads(path.read_text())
    key = str(data.get("api_key") or "").strip()
    if not key and data.get("api_key_command"):
        key = subprocess.check_output(list(data["api_key_command"])).decode().strip()
    if not key.startswith("clrtok_"):
        raise SystemExit(f"{path}: api_key must be a Clarity API key (clrtok_...)")
    return Config(
        api_base=str(data.get("api_base", "https://api.claritycustomsoftware.com")).rstrip("/"),
        handle=str(data["handle"]).strip(),
        api_key=key,
        workdir=Path(str(data.get("workdir", "~"))).expanduser(),
        codex_bin=str(data.get("codex_bin", "codex")),
        codex_args=[str(a) for a in data.get("codex_args", [])],
    )


class State:
    """Which messages were handled and which Codex session owns each thread."""

    def __init__(self, directory: Path = STATE_DIR) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "state.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"threads": {}, "done": []}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2))
        tmp.replace(self.path)

    def is_done(self, message_id: str) -> bool:
        return message_id in self.data["done"]

    def mark_done(self, message_id: str) -> None:
        self.data["done"] = (self.data["done"] + [message_id])[-2000:]
        self.save()

    def session_for(self, thread: str) -> str | None:
        return self.data["threads"].get(thread)

    def remember(self, thread: str, session_id: str) -> None:
        self.data["threads"][thread] = session_id
        self.save()
