"""Wake the local Codex session for an incoming message and capture its answer."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .config import Config


def prompt_for(message: dict, is_response: bool = False) -> str:
    if is_response:
        return "\n".join([
            f"A2A reply from {message.get('from_agent')} to your earlier message "
            f"(thread {message.get('thread_id') or message.get('session_id')}):",
            "",
            str(message.get("message") or ""),
            "",
            "This is the answer to what you sent. Use it; no reply will be sent.",
        ])
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
        options = ["--json", "--skip-git-repo-check", "-o", str(last)]
        # Execution options (sandbox, profile, model) belong to `codex exec`, before `resume`.
        if session_id:
            args = [config.codex_bin, "exec", *config.codex_args, "resume", *options, session_id, prompt]
        else:
            args = [config.codex_bin, "exec", *config.codex_args, *options, prompt]
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
