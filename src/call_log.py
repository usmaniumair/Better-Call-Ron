"""Per-call JSON log writer for post-mortem debugging.

Writes one file per call_id to data/calls/. Each event is appended to the
file's `events` list. Concurrency is already handled by server.py's per-call
asyncio.Lock, and each call writes its own file, so no extra locking is needed.

This module is best-effort: any failure here is swallowed and logged so the
call path is never broken by a logging error.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent.parent / "data" / "calls"
_UNSAFE = re.compile(r"[^A-Za-z0-9_+\-.]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(call_id: str) -> Path:
    safe = _UNSAFE.sub("_", call_id) or "unknown"
    return _DIR / f"{safe}.json"


def _load_or_init(call_id: str, from_number: str) -> dict:
    path = _path(call_id)
    if path.exists():
        try:
            with path.open() as f:
                return json.load(f)
        except Exception:
            # Corrupt file — back it up and start fresh rather than lose this call.
            path.rename(path.with_suffix(".json.corrupt"))
    return {
        "call_id": call_id,
        "from_number": from_number,
        "started_at": _now(),
        "ended_at": None,
        "events": [],
    }


def record(call_id: str, event_type: str, **fields: Any) -> None:
    """Append an event to the call's log file. Never raises."""
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        from_number = fields.pop("_from_number", "")
        data = _load_or_init(call_id, from_number=from_number)
        if from_number and not data.get("from_number"):
            data["from_number"] = from_number

        event = {"ts": _now(), "type": event_type, **fields}
        data["events"].append(event)

        if event_type == "lifecycle" and str(fields.get("event", "")).endswith("ended"):
            data["ended_at"] = event["ts"]

        path = _path(call_id)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.replace(path)
    except Exception as exc:
        _LOG.warning("call_log.record(%s, %s) failed: %s", call_id, event_type, exc)


# ─── Repeat-caller memory ──────────────────────────────────────────────────

def _summarize(data: dict) -> dict:
    """Extract a compact summary of one prior call for prompt injection."""
    caller_name = None
    opening = None
    last_match = None
    connected = False
    for ev in data.get("events", []):
        et = ev.get("type")
        if et == "tool_result" and ev.get("name") == "lookup_user":
            r = ev.get("result", {}) or {}
            if r.get("found") and not caller_name:
                caller_name = r.get("name")
        elif et == "user_transcript" and opening is None:
            opening = ev.get("raw")
        elif et == "tool_result" and ev.get("name") == "match_lawyers":
            r = ev.get("result", {}) or {}
            lawyers = r.get("lawyers") or []
            if lawyers:
                lw = lawyers[0]
                juris = (lw.get("jurisdictions") or [{}])[0]
                counties = juris.get("counties") or []
                # Prefer the practice_area the caller was actually classified
                # under (from the tool input) over the lawyer record's first
                # listed area — the input reflects the caller's real ask.
                input_pa = (ev.get("input") or {}).get("practice_area")
                last_match = {
                    "lawyer_name": lw.get("name"),
                    "practice_area": input_pa or (lw.get("practice_areas") or ["?"])[0],
                    "county": counties[0] if counties else "?",
                }
        elif et == "tool_result" and ev.get("name") == "connect_to_lawyer":
            r = ev.get("result", {}) or {}
            if "error" not in r:
                connected = True
    return {
        "call_id": data.get("call_id"),
        "started_at": data.get("started_at"),
        "caller_name": caller_name,
        "opening_transcript": (opening or "").strip(),
        "last_match": last_match,
        "connected": connected,
    }


def lookup_history(
    from_number: str,
    exclude_call_id: str | None = None,
    limit: int = 3,
) -> list[dict]:
    """Return up to `limit` prior call summaries for this phone, newest first."""
    if not from_number:
        return []
    try:
        if not _DIR.exists():
            return []
        paths = sorted(_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []

    summaries: list[dict] = []
    for path in paths:
        try:
            with path.open() as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("call_id") == exclude_call_id:
            continue
        if data.get("from_number") != from_number:
            continue
        summaries.append(_summarize(data))
        if len(summaries) >= limit:
            break
    return summaries


def format_history_for_prompt(history: list[dict]) -> str:
    """Render prior-call summaries as a system-prompt addendum block."""
    if not history:
        return ""
    lines = [
        "# Caller history — this number has called before",
        f"This caller has {len(history)} prior call(s) in our system, newest first:",
        "",
    ]
    for i, h in enumerate(history, 1):
        bits = [f"{i}. {h.get('started_at', '?')}"]
        if h.get("caller_name"):
            bits.append(f"caller={h['caller_name']}")
        if h.get("opening_transcript"):
            opening = h["opening_transcript"]
            if len(opening) > 120:
                opening = opening[:117] + "..."
            bits.append(f'said: "{opening}"')
        if h.get("last_match"):
            m = h["last_match"]
            bits.append(f"matched {m['lawyer_name']} ({m['practice_area']}, {m['county']})")
        bits.append("CONNECTED" if h.get("connected") else "did NOT connect")
        lines.append(" — ".join(bits))
    lines += [
        "",
        "Acknowledge the prior context naturally in your opener AND during the call. Examples:",
        '  - "Hey {first_name}, calling back about the {topic}?"',
        '  - "Same situation as last time, or something new?"',
        "Do NOT re-ask info you already have (caller's name, prior practice area). Skip lookup_user "
        "for known callers if their name is in this block — go straight to triage.",
    ]
    return "\n".join(lines)
