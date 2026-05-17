"""AgentMail client. Sends a brief to the matched lawyer on connect.

Inbox lifecycle:
- If AGENTMAIL_INBOX_ID is set, we use that inbox directly.
- Otherwise we lazily create an inbox on first send and cache the id in-process.
  The id is logged at INFO so you can paste it into .env to reuse across
  restarts (otherwise every server restart spawns a new inbox).
"""

import logging
import os
from typing import Optional

from agentmail import AgentMail

from . import config


_LOG = logging.getLogger(__name__)

_client: Optional[AgentMail] = None
_inbox_id: Optional[str] = None


def _get_client() -> AgentMail:
    global _client
    if _client is None:
        _client = AgentMail(api_key=config.require_env("AGENTMAIL_API_KEY"))
    return _client


def _get_inbox_id() -> str:
    """Return the inbox id to send from. Cached for the process lifetime."""
    global _inbox_id
    if _inbox_id is not None:
        return _inbox_id

    env_id = os.environ.get("AGENTMAIL_INBOX_ID", "").strip()
    if env_id:
        _inbox_id = env_id
        return _inbox_id

    inbox = _get_client().inboxes.create()
    _inbox_id = inbox.inbox_id
    _LOG.info(
        "Created AgentMail inbox %s — paste into .env as AGENTMAIL_INBOX_ID to reuse across restarts",
        _inbox_id,
    )
    return _inbox_id


def send_email(to: str, subject: str, text: str) -> str:
    """Send an email to `to`. Returns the inbox id used (for logging/debugging)."""
    inbox_id = _get_inbox_id()
    _get_client().inboxes.messages.send(
        inbox_id,
        to=to,
        subject=subject,
        text=text,
    )
    return inbox_id
