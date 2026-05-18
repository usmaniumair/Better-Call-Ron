"""Read-only views over data/calls/*.json for the operator admin panel.

The on-disk call log is written by [src/call_log.py](call_log.py). This module
exposes derived/enriched views suitable for the History tab and the urgency
filter on active calls. No writes; no caching — calls are infrequent and the
files are small.
"""

import json
import logging
from pathlib import Path
from typing import Literal

_LOG = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent.parent / "data" / "calls"

Urgency = Literal["urgent", "shopper", "unclear"]
Status = Literal["transferred", "escalated", "dropped", "completed"]


def derive_urgency(call_log: dict) -> Urgency:
    """Infer urgency from Ron's tool sequence — no prompt change required.

    - `research_and_email` invoked at all → shopper flow.
    - `match_lawyers` invoked before any research → urgent flow.
    - Neither tool fired → unclear.
    """
    first_research_idx: int | None = None
    first_match_idx: int | None = None
    for i, ev in enumerate(call_log.get("events", [])):
        if ev.get("type") != "tool_result":
            continue
        name = ev.get("name", "")
        if name == "research_and_email" and first_research_idx is None:
            first_research_idx = i
        elif name == "match_lawyers" and first_match_idx is None:
            first_match_idx = i

    if first_research_idx is None and first_match_idx is None:
        return "unclear"
    if first_research_idx is None:
        return "urgent"
    if first_match_idx is None:
        return "shopper"
    return "urgent" if first_match_idx < first_research_idx else "shopper"


def derive_status(call_log: dict) -> Status:
    """Infer terminal status from the LAST non-error terminal tool call.

    `end_call` (hangup) → completed.
    `connect_to_lawyer` (transfer to lawyer) → transferred.
    `escalate_to_human` / `route_to_public_defender` → escalated.
    Nothing terminal succeeded → dropped (call ended without resolution).
    """
    for ev in reversed(call_log.get("events", [])):
        if ev.get("type") != "tool_result":
            continue
        name = ev.get("name", "")
        result = ev.get("result", {}) or {}
        if "error" in result:
            continue
        if name == "end_call":
            return "completed"
        if name == "connect_to_lawyer":
            return "transferred"
        if name in ("escalate_to_human", "route_to_public_defender"):
            return "escalated"
    return "dropped"


def _extract_turns(call_log: dict) -> list[dict]:
    """Flatten events into a clean speaker/text/ts sequence for the UI."""
    out: list[dict] = []
    for ev in call_log.get("events", []):
        et = ev.get("type")
        ts = ev.get("ts")
        if et == "opener":
            text = (ev.get("text") or "").strip()
            if text:
                out.append({"speaker": "agent", "text": text, "ts": ts})
        elif et == "user_transcript":
            text = (ev.get("raw") or "").strip()
            if text:
                out.append({"speaker": "caller", "text": text, "ts": ts})
        elif et == "assistant_response":
            text = (ev.get("text") or "").strip()
            if text:
                out.append({"speaker": "agent", "text": text, "ts": ts})
    return out


def _extract_tool_log(call_log: dict) -> list[dict]:
    """Return [{name, input, result, ts}] for each tool invocation."""
    return [
        {
            "name": ev.get("name"),
            "input": ev.get("input") or {},
            "result": ev.get("result") or {},
            "ts": ev.get("ts"),
        }
        for ev in call_log.get("events", [])
        if ev.get("type") == "tool_result"
    ]


def _summary(call_log: dict) -> dict:
    """Compact record used in /api/calls list responses."""
    turns = _extract_turns(call_log)
    return {
        "call_id": call_log.get("call_id"),
        "from_number": call_log.get("from_number") or "",
        "started_at": call_log.get("started_at"),
        "ended_at": call_log.get("ended_at"),
        "urgency": derive_urgency(call_log),
        "status": derive_status(call_log),
        "turn_count": len(turns),
    }


def _load_file(path: Path) -> dict | None:
    try:
        with path.open() as f:
            return json.load(f)
    except Exception as exc:
        _LOG.warning("call_history: failed to load %s: %s", path, exc)
        return None


def load_recent_calls(limit: int = 50) -> list[dict]:
    """Most-recent-first list of compact call summaries."""
    if not _DIR.exists():
        return []
    paths = sorted(
        (p for p in _DIR.glob("*.json") if not p.name.endswith(".tmp")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out: list[dict] = []
    for path in paths:
        data = _load_file(path)
        if data is None:
            continue
        out.append(_summary(data))
    return out


def load_call(call_id: str) -> dict | None:
    """Full record for one call: summary + turns + tool log."""
    if not _DIR.exists():
        return None
    matches = list(_DIR.glob(f"*{call_id}*.json"))
    matches = [p for p in matches if not p.name.endswith(".tmp")]
    if not matches:
        return None
    data = _load_file(matches[0])
    if data is None:
        return None
    return {
        **_summary(data),
        "turns": _extract_turns(data),
        "tool_log": _extract_tool_log(data),
    }
