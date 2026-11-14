"""Talk to Clarity's A2A hub: the message stream, status updates and replies."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from .config import Config


def stream(config: Config) -> Iterator[tuple[str, dict]]:
    """Yield (event, data) from the agent's Server-Sent Events stream."""
    url = f"{config.api_base}/agent/agent_messages/stream"
    timeout = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0)  # server pings every 15 s
    with httpx.stream("GET", url, params={"to_agent": config.handle}, headers=config.headers, timeout=timeout) as response:
        if response.status_code != 200:
            raise RuntimeError(f"stream refused: {response.status_code} {response.read()[:300]!r}")
        event, data = "message", []
        for line in response.iter_lines():
            if line == "":
                if data:
                    try:
                        yield event, json.loads("\n".join(data))
                    except ValueError:
                        pass
                event, data = "message", []
            elif line.startswith(":"):
                continue
            elif line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())


def _post(config: Config, path: str, body: dict) -> dict:
    response = httpx.post(f"{config.api_base}{path}", json=body, headers=config.headers, timeout=30.0)
    response.raise_for_status()
    data = response.json()
    return data.get("data", data) if isinstance(data, dict) else data


def set_status(config: Config, message_id: str, status: str, error: str | None = None) -> None:
    body = {"id": message_id, "status": status, "delivery_status": status}
    if error:
        body["last_error"] = error[:500]
    _post(config, "/agent/agent_messages/id/status", body)


def reply(config: Config, message_id: str, text: str) -> dict:
    return _post(
        config,
        "/agent/agent_messages/reply",
        {
            "id": message_id,
            "from_agent": config.handle,
            "message": text,
            "idempotency_key": f"a2a-connect:{message_id}",
        },
    )


def send(config: Config, to_agent: str, text: str, session_id: str | None = None) -> dict:
    import uuid

    body = {
        "session_id": session_id or f"a2a-connect:{uuid.uuid4()}",
        "from_agent": config.handle,
        "to_agent": to_agent,
        "message": text,
    }
    return _post(config, "/agent/agent_messages", body)
