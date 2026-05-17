"""Browser Use Cloud client wrapper. Thin shim around browser_use_sdk."""

import logging
import os
from typing import Optional

from browser_use_sdk.v3 import AsyncBrowserUse


_LOG = logging.getLogger(__name__)

_client: Optional[AsyncBrowserUse] = None


def _get_client() -> AsyncBrowserUse:
    """Return a cached AsyncBrowserUse client. Reads BROWSER_USE_API_KEY from env."""
    global _client
    if _client is None:
        # SDK reads BROWSER_USE_API_KEY from env automatically.
        _client = AsyncBrowserUse()
    return _client


def is_configured() -> bool:
    """True iff BROWSER_USE_API_KEY is set in env."""
    return bool(os.environ.get("BROWSER_USE_API_KEY", "").strip())


async def research(task: str) -> str:
    """Run a single browsing task in the cloud, return the agent's output text.

    Raises on any failure. Callers should handle exceptions and fall back to
    a curated response so the caller is never left empty-handed.
    """
    client = _get_client()
    result = await client.run(task)
    output = getattr(result, "output", None)
    if not output:
        raise RuntimeError("browser_use returned empty output")
    return str(output)
