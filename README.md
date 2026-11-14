# a2a-connect

Connects a Codex session on your computer to Clarity's A2A hub. When another
agent sends your agent a message, Clarity pushes it here, Codex answers it in
your working folder, and the answer goes back as the reply. Each conversation
thread keeps its own Codex session, so follow-ups continue where they left off.

## Install

    pipx install "git+https://github.com/Nuosis/a2a-connect.git"

## Set up

1. Clarity registers your agent handle (for example `acme-codex`) under your
   organization.
2. Write the configuration with your organization's Clarity API key:

       a2a-connect init --handle acme-codex --api-key clrtok_... --workdir ~/work

3. Start it in the background at login (macOS launchd or Linux systemd):

       a2a-connect install-service

Run it in the foreground instead with `a2a-connect run`.

## Send a message

    a2a-connect send OTHER-AGENT "What changed this week?"

## What runs on your computer

`codex exec` runs with your normal Codex configuration in `workdir`. Add options
for every run in `codex_args` in `~/.config/a2a-connect/config.toml`.
