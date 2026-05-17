"""One-shot AgentPhone configuration for Better Call Ron.

Updates the agent's begin_message, points its webhook at the given URL,
captures the returned signing secret, and writes that secret into .env
in place (without echoing it).

Usage:
    python -m scripts.setup_agent https://abc123.ngrok-free.app
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agentphone import AgentPhone
from dotenv import load_dotenv

load_dotenv()


RON_OPENER = "Hey, this is Ron. How can I help you?"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _update_env_secret(secret: str) -> None:
    lines = ENV_FILE.read_text().splitlines(keepends=True)
    new_lines = []
    replaced = False
    for line in lines:
        if line.startswith("AGENTPHONE_WEBHOOK_SECRET="):
            new_lines.append(f"AGENTPHONE_WEBHOOK_SECRET={secret}\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"AGENTPHONE_WEBHOOK_SECRET={secret}\n")
    ENV_FILE.write_text("".join(new_lines))


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.setup_agent <ngrok-https-url>", file=sys.stderr)
        sys.exit(1)
    ngrok_url = sys.argv[1].rstrip("/")
    if not ngrok_url.startswith("https://"):
        print(f"Refusing non-HTTPS url: {ngrok_url}", file=sys.stderr)
        sys.exit(1)
    webhook_url = f"{ngrok_url}/webhook"

    agent_id = os.environ["AGENTPHONE_AGENT_ID"]
    ap = AgentPhone(api_key=os.environ["AGENTPHONE_API_KEY"])

    print(f"Updating agent {agent_id} ...")
    ap.agents.update(
        agent_id,
        begin_message=RON_OPENER,
        system_prompt="",  # webhook mode owns the brain; clear demo prompt
    )
    print(f"  begin_message: {RON_OPENER!r}")
    print("  system_prompt: cleared (webhook owns behavior)")

    print(f"\nSetting webhook -> {webhook_url} ...")
    wh = ap.agents.set_webhook(agent_id, url=webhook_url)
    print(f"  url: {wh.url}")
    print(f"  context_limit: {getattr(wh, 'context_limit', '<n/a>')}")
    print(f"  timeout: {getattr(wh, 'timeout', '<n/a>')}")

    secret = getattr(wh, "secret", None)
    if not secret:
        print("WARNING: set_webhook did not return a secret in the response object.")
        print(f"   raw repr: {wh!r}")
        sys.exit(2)

    _update_env_secret(secret)
    print(f"\nWrote new AGENTPHONE_WEBHOOK_SECRET to {ENV_FILE} (value not echoed).")
    print("Restart any running server so it picks up the new secret.")


if __name__ == "__main__":
    main()
