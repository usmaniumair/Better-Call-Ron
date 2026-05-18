import hashlib
import hmac
import logging
import os
from typing import Optional

from agentphone import AgentPhone

from . import config


_LOG = logging.getLogger(__name__)
_client: Optional[AgentPhone] = None


def _get_client() -> AgentPhone:
    global _client
    if _client is None:
        _client = AgentPhone(api_key=config.require_env("AGENTPHONE_API_KEY"))
    return _client


def send_sms(to: str, text: str) -> None:
    """Send SMS/iMessage from the agent. Pins to AGENTPHONE_MESSAGING_NUMBER_ID
    when set (e.g. the iMessage-capable line) so outbound routing is deterministic;
    otherwise AgentPhone picks one of the agent's attached numbers."""
    client = _get_client()
    kwargs: dict = {
        "agent_id": config.require_env("AGENTPHONE_AGENT_ID"),
        "to_number": to,
        "body": text,
    }
    number_id = os.environ.get("AGENTPHONE_MESSAGING_NUMBER_ID")
    if number_id:
        kwargs["number_id"] = number_id
    client.messages.send(**kwargs)


def set_transfer_number(to: str) -> None:
    """Set the agent's `transfer_number` so AgentPhone uses it for the next transfer.

    AgentPhone's transfer action reads `transfer_number` from the agent record,
    not from the per-call webhook response. Must be called BEFORE the transfer
    instruction is returned to AgentPhone. Best-effort: errors are logged but
    never raise — the webhook response is still returned in case the AgentPhone
    deployment respects the per-call override.
    """
    try:
        _get_client().agents.update(
            config.require_env("AGENTPHONE_AGENT_ID"),
            transfer_number=to,
        )
    except Exception as exc:
        _LOG.exception("set_transfer_number(%s) failed: %s", to, exc)


def transfer_instruction(to: str) -> dict:
    """Build the per-call transfer instruction returned in the webhook response.

    Pairs with `set_transfer_number(to)` — call that first to update the agent's
    transfer_number, then return this dict in the webhook response.
    """
    return {"action": "transfer", "transferNumber": to}


def verify_signature(body: bytes, signature: str, timestamp: Optional[str] = None) -> bool:
    # AgentPhone signs `{X-Webhook-Timestamp}.{raw body}` (Stripe-style). The
    # bundled SDK's verify_webhook only hashes the body and so always fails on
    # real inbound webhooks — we compute the HMAC ourselves.
    if not signature or not timestamp:
        return False
    secret = config.require_env("AGENTPHONE_WEBHOOK_SECRET")
    payload = f"{timestamp}.".encode() + body
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
