"""Wake the local Codex session for an incoming message and capture its answer."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .config import Config


def prompt_for(message: dict) -> str:
    parts = [
        f"A2A message from {message.get('from_agent')} "
        f"(message {message.get('id')}, thread {message.get('thread_id') or message.get('session_id')}):",
        "",
        str(message.get("message") or ""),
    ]
    payload = message.get("payload") or {}
    if payload:
        parts += ["", "Payload (JSON):", json.dumps(payload, indent=2)]
    parts += [
        "",
        f"Your final message is sent back to {message.get('from_agent')} as the reply.",
    ]
    return "\n".join(parts)


def run(config: Config, prompt: str, session_id: str | None) -> tuple[str, str | None]:
    """Run Codex on the prompt. Returns (final message, Codex session id)."""
    with tempfile.TemporaryDirectory() as tmp:
        last = Path(tmp) / "last.txt"
        options = ["--json", "--skip-git-repo-check", "-o", str(last), *config.codex_args]
        if session_id:
            args = [config.codex_bin, "exec", "resume", *options, session_id, prompt]
        else:
            args = [config.codex_bin, "exec", *options, prompt]
        result = subprocess.run(
            args, cwd=config.workdir, capture_output=True, text=True, stdin=subprocess.DEVNULL
        )
        thread = session_id
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "thread.started" and event.get("thread_id"):
                thread = event["thread_id"]
        if result.returncode != 0:
            raise RuntimeError(f"codex exited {result.returncode}: {result.stderr[-400:]}")
        text = last.read_text().strip() if last.exists() else ""
        if not text:
            raise RuntimeError("codex produced no final message")
        return text, thread
