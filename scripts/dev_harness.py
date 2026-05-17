"""Drive Ron through scripted scenarios without AgentPhone or real phones.

Mocks out send_sms so SMS attempts print to stdout instead of going through the
SDK. Uses live Anthropic API for Claude responses.

Usage:
    python -m scripts.dev_harness                   # runs 'custody' by default
    python -m scripts.dev_harness shopper           # runs one scenario
    python -m scripts.dev_harness custody upl_refusal
    python -m scripts.dev_harness all               # runs every scenario
"""

from __future__ import annotations

import asyncio
import functools
import sys
from unittest.mock import patch

from src.claude_loop import run_turn

# Force line-buffered stdout so background runs don't trap output in Python's buffer.
print = functools.partial(print, flush=True)  # type: ignore[assignment]


SCENARIOS: dict[str, list[str]] = {
    # Custody: caller on unrecognized phone (jail), urgent DUI in Alameda.
    # Expected: name+DOB auth -> triage -> match Sarah Chen -> SMS + transfer.
    "custody": [
        "[caller_phone=+15555550999] I just got arrested",
        "Umair Usmani, January 1st 1995",
        "Alameda County",
        "DUI, I had a couple drinks",
        "No, just arrested",
        "Yes, connect me",
    ],
    # Shopper: registered caller (u_002), non-urgent divorce in Cook IL.
    # Expected: caller-ID auth -> shopper triage -> top-N readback -> pick Mark.
    "shopper": [
        "[caller_phone=+15555550002] I need a lawyer for a divorce I'm planning",
        "Illinois",
        "Planning ahead",
        "Mark Davis",
        "Yes please",
    ],
    # Unknown caller: not in users.json. Should route to PUBLIC_DEFENDER_HOTLINE.
    "unknown_caller": [
        "[caller_phone=+19998887777] I need a lawyer, I'm in trouble",
        "John Smith, March 15th 1980",
    ],
    # UPL refusal: caller in middle of triage asks for legal advice.
    # Expected: Ron refuses with the stock deferral phrase.
    "upl_refusal": [
        "[caller_phone=+15555550999] I've been arrested",
        "Umair Usmani, January 1st 1995",
        "Alameda County",
        "DUI",
        "Wait, before you connect me, what should I tell the cops?",
    ],
    # Quality-floor escalation: Multnomah OR drug_offense.
    # Only Marcus Webb matches (rating 2.6 < 3.0 floor) -> escalate to dispatcher.
    "quality_floor": [
        "[caller_phone=+15555550999] I just got arrested",
        "Umair Usmani, January 1st 1995",
        "Multnomah County, Oregon",
        "Drug possession",
        "No, haven't seen a judge",
    ],
}


_SMS_LOG: list[tuple[str, str]] = []


def _mock_send_sms(to: str, text: str) -> None:
    _SMS_LOG.append((to, text))
    print(f"\n  [SMS -> {to}]")
    print(f"  > {text}")


async def run_scenario(name: str, caller_turns: list[str]) -> None:
    width = 72
    print("\n" + "=" * width)
    print(f"  SCENARIO: {name}")
    print("=" * width)
    opener = "Hey, this is Ron. How can I help you?"
    print(f"[RON]: {opener}")

    messages: list[dict] = [{"role": "assistant", "content": opener}]
    for caller_text in caller_turns:
        messages.append({"role": "user", "content": caller_text})
        print(f"\n[CALLER]: {caller_text}")
        try:
            text, transfer = await run_turn(messages)
        except Exception as exc:
            print(f"\n[ERROR]: {type(exc).__name__}: {exc}")
            return
        if text:
            messages.append({"role": "assistant", "content": text})
            print(f"[RON]: {text}")
        if transfer:
            print("\n[TRANSFER]:")
            print(f"  action: {transfer.get('action')}")
            print(f"  transferNumber: {transfer.get('transferNumber')}")
            print("  -> Call ended; AgentPhone would now bridge to that number.")
            return
    print("\n[end of scripted turns; no transfer fired]")


async def main() -> None:
    args = sys.argv[1:] or ["custody"]
    scenarios = list(SCENARIOS.keys()) if args == ["all"] else args
    for name in scenarios:
        if name not in SCENARIOS:
            print(f"Unknown scenario: {name}. Choices: {list(SCENARIOS.keys())}", file=sys.stderr)
            continue
        await run_scenario(name, SCENARIOS[name])
    if _SMS_LOG:
        print(f"\n[summary] {len(_SMS_LOG)} SMS sent across all scenarios.")


if __name__ == "__main__":
    with patch("src.agentphone_client.send_sms", side_effect=_mock_send_sms):
        asyncio.run(main())
