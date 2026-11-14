"""a2a-connect command line: init, run, send, install-service."""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import codex, hub
from .config import CONFIG_PATH, STATE_DIR, TEMPLATE, Config, State, load_config

log = logging.getLogger("a2a-connect")


def handle_message(config: Config, state: State, message: dict) -> None:
    message_id = str(message["id"])
    if state.is_done(message_id) or message.get("status") != "pending":
        return
    thread = str(message.get("thread_id") or message.get("session_id") or message_id)
    is_response = message.get("kind") == "response" or message.get("message_type") == "reply"
    log.info(
        "%s %s from %s (thread %s)",
        "reply" if is_response else "message", message_id, message.get("from_agent"), thread,
    )
    # The message stays pending until it is answered, so a restart picks it up again.
    try:
        text, session_id = codex.run(
            config, codex.prompt_for(message, is_response), state.session_for(thread)
        )
        if session_id:
            state.remember(thread, session_id)
        if not is_response:  # a reply is information for Codex, never answered again
            hub.reply(config, message_id, text)
            log.info("replied to %s", message_id)
        hub.set_status(config, message_id, "completed")
    except Exception as exc:  # report the failure on the message; keep serving
        log.exception("message %s failed", message_id)
        hub.set_status(config, message_id, "failed", str(exc))
    state.mark_done(message_id)


def run(config: Config) -> None:
    state = State()
    delay = 2.0
    while True:
        try:
            for event, data in hub.stream(config):
                delay = 2.0
                if event == "ready":
                    log.info("connected as %s (%s pending)", config.handle, data.get("pending"))
                elif event == "message":
                    handle_message(config, state, data)
            log.warning("stream closed; reconnecting")
        except KeyboardInterrupt:
            return
        except Exception as exc:
            log.warning("stream error: %s; retrying in %.0f s", exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)


def init(args: argparse.Namespace) -> None:
    if CONFIG_PATH.exists() and not args.force:
        raise SystemExit(f"{CONFIG_PATH} exists (use --force to replace it)")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        TEMPLATE.format(handle=args.handle, api_key=args.api_key or "", workdir=args.workdir)
    )
    CONFIG_PATH.chmod(0o600)
    print(f"wrote {CONFIG_PATH}")


def install_service(_args: argparse.Namespace) -> None:
    exe = shutil.which("a2a-connect") or sys.argv[0]
    path_env = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = STATE_DIR / "connector.log"
    env = {"PATH": path_env, "A2A_CONNECT_CONFIG": str(CONFIG_PATH), "A2A_CONNECT_STATE": str(STATE_DIR)}
    if platform.system() == "Darwin":
        plist = Path("~/Library/LaunchAgents/com.clarity.a2a-connect.plist").expanduser()
        plist.parent.mkdir(parents=True, exist_ok=True)
        env_xml = "".join(f"<key>{k}</key><string>{v}</string>" for k, v in env.items())
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.clarity.a2a-connect</string>
  <key>ProgramArguments</key><array><string>{exe}</string><string>run</string></array>
  <key>EnvironmentVariables</key><dict>{env_xml}</dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>{log_file}</string>
  <key>StandardErrorPath</key><string>{log_file}</string>
</dict></plist>
""")
        uid = os.getuid()
        subprocess.call(["launchctl", "bootout", f"gui/{uid}", str(plist)], stderr=subprocess.DEVNULL)
        subprocess.check_call(["launchctl", "bootstrap", f"gui/{uid}", str(plist)])
        print(f"installed and started {plist}; log {log_file}")
    else:
        unit = Path("~/.config/systemd/user/a2a-connect.service").expanduser()
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(f"""[Unit]
Description=Clarity A2A connector for Codex

[Service]
ExecStart={exe} run
{chr(10).join(f'Environment="{k}={v}"' for k, v in env.items())}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
""")
        subprocess.check_call(["systemctl", "--user", "daemon-reload"])
        subprocess.check_call(["systemctl", "--user", "enable", "--now", "a2a-connect.service"])
        print(f"installed and started {unit}; logs: journalctl --user -u a2a-connect")


def main() -> None:
    parser = argparse.ArgumentParser(prog="a2a-connect")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="write the configuration file")
    p.add_argument("--handle", required=True, help="registered agent handle, e.g. acme-codex")
    p.add_argument("--api-key", help="your organization's Clarity API key (clrtok_...)")
    p.add_argument("--workdir", default="~", help="folder Codex runs in")
    p.add_argument("--force", action="store_true")
    sub.add_parser("run", help="connect and answer messages until stopped")
    p = sub.add_parser("send", help="send a message to another agent")
    p.add_argument("to_agent")
    p.add_argument("message")
    sub.add_parser("install-service", help="run the connector in the background at login")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "init":
        init(args)
    elif args.command == "run":
        run(load_config())
    elif args.command == "send":
        print(hub.send(load_config(), args.to_agent, args.message))
    elif args.command == "install-service":
        install_service(args)


if __name__ == "__main__":
    main()
