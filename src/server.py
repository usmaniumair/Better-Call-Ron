import asyncio
import itertools
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import agentphone_client, call_log, tools
from .claude_loop import run_turn
from .transcript_bus import bus


_LOG = logging.getLogger(__name__)

app = FastAPI(title="Better Call Ron")

# Per-call message history. Mutations are serialized by CALL_LOCKS so concurrent
# webhooks for the same call_id can't interleave tool_use / tool_result pairs.
CALL_STATE: dict[str, list[dict]] = {}
CALL_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Cached per-call context: maps call_id -> (system_prompt_addendum, raw_history_list, identity_dict_or_None).
# Computed once on first webhook for the call (call_start or first user transcript),
# reused on every subsequent turn. Identity is resolved via tools.lookup_user against
# the caller's phone number so Ron can greet by name from his first utterance and skip
# the redundant lookup_user tool call later.
CALL_HISTORY: dict[str, tuple[str | None, list[dict], dict | None]] = {}

# AgentPhone STT fires multiple webhooks per utterance as the transcript refines
# ("Yeah." -> "Yeah. I'm..." -> "Yeah. I'm still on the line."). Each new webhook
# bumps the per-call sequence number; older in-flight webhooks check after their
# debounce wait whether they are still the latest and return {} if superseded.
_DEBOUNCE_SECONDS = float(os.environ.get("RON_DEBOUNCE_SECONDS", "0.4"))
_SEQ_COUNTER = itertools.count(1)
LATEST_SEQ: dict[str, int] = {}

_PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"

# Ron's hardcoded opener (PRD FR-10). Returned without invoking Claude when
# we receive a call-start event or an empty first transcript.
RON_OPENER = "Hey, this is Ron. How can I help you?"

# AgentPhone webhook event names we know about. The SDK only documents
# `agent.message` (see agentphone/webhook.py), but call-lifecycle events have
# appeared in the wild as `agent.call_started` / `agent.call_ended` etc. We
# treat any non-`agent.message` event with a recognizable "start" name as a
# trigger for the opener, and everything else as a no-op.
_CALL_START_EVENTS = {"agent.call_started", "call.started", "agent.call.started"}
_CALL_END_EVENTS = {"agent.call_ended", "call.ended", "agent.call.ended"}


def _extract_call_id(data: dict, event: dict) -> str:
    # AgentPhone uses `conversationId` for persistent turn keying; some payloads
    # may use `callId` for voice calls. Fall back to from-number if neither.
    return (
        data.get("callId")
        or data.get("conversationId")
        or event.get("agentId", "")
        + "_"
        + (data.get("from") or "")
        or data.get("from")
        or "unknown"
    )


def _extract_transcript(data: dict) -> str:
    # AgentPhone WebhookEventData uses `message`; legacy payloads may use
    # `transcript`. Empty/missing means a non-utterance event (e.g. call start).
    return (data.get("message") or data.get("transcript") or "").strip()


def _extract_from_number(data: dict) -> str:
    return data.get("from") or data.get("fromNumber") or ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_identity_block(identity: dict) -> str:
    """Render a pre-resolved caller identity as a system-prompt addendum."""
    return (
        "# Caller identity — already resolved from caller ID\n"
        "We've matched this caller's phone number to a registered user. Use these "
        "fields DIRECTLY instead of calling `lookup_user` — that call is redundant.\n"
        f"- user_id: {identity.get('user_id')}\n"
        f"- name: {identity.get('name')}\n"
        f"- email: {identity.get('email')}\n"
        f"- preferred_language: {identity.get('preferred_language')}\n"
        f"- home_jurisdiction (residence — NOT the matter's jurisdiction): "
        f"{identity.get('home_jurisdiction')}\n"
        "\n"
        "**CRITICAL — home_jurisdiction is the caller's home address, NOT where "
        "their legal matter is happening.** People get arrested while traveling. "
        "Their landlord might be in a different state. NEVER pass home_jurisdiction "
        "to `match_lawyers` or `research_and_email` as the matter's state without "
        "first confirming with the caller (URGENT: ask 'Where are you being held?'; "
        "NON-URGENT: ask 'What state is this in?'). The only thing you may skip is "
        "the `lookup_user` tool call itself — you still ask the same triage questions."
    )


def _get_or_compute_history(
    call_id: str, from_number: str
) -> tuple[str | None, list[dict], dict | None]:
    """Resolve caller identity + prior-call history for `from_number`, cache + return.

    Returns (system_prompt_addendum, raw_history_list, identity_dict_or_None).
    The addendum bundles both blocks (identity + history) when present. Identity
    is resolved synchronously via tools.lookup_user against the phone number, so
    Ron can greet by name from his very first utterance.
    """
    if call_id in CALL_HISTORY:
        return CALL_HISTORY[call_id]

    history = call_log.lookup_history(from_number, exclude_call_id=call_id, limit=3)

    identity: dict | None = None
    if from_number:
        lookup_result = tools.lookup_user(phone_number=from_number)
        if lookup_result.get("found"):
            identity = lookup_result

    blocks: list[str] = []
    if identity:
        blocks.append(_format_identity_block(identity))
    history_block = call_log.format_history_for_prompt(history)
    if history_block:
        blocks.append(history_block)
    extra = "\n\n".join(blocks) if blocks else None

    CALL_HISTORY[call_id] = (extra, history, identity)
    return extra, history, identity


def _pretty_practice_area(pa: str) -> str:
    """Format a controlled-vocab practice_area for spoken output."""
    pa = (pa or "").replace("_", " ").strip()
    if pa == "dui":
        return "DUI"
    return pa


def _customized_opener(history: list[dict], identity: dict | None) -> str:
    """Return a personalized opener if we know the caller, else the canonical one.

    Priority: prior topic > first name from history > first name from identity > generic.
    """
    if history:
        most_recent = history[0]
        name = most_recent.get("caller_name") or ""
        first_name = name.split()[0] if name else None
        last_match = most_recent.get("last_match") or {}
        topic = _pretty_practice_area(last_match.get("practice_area"))
        if first_name and topic:
            return f"Hey {first_name}, calling back about the {topic}?"
        if first_name:
            return f"Hey {first_name}, glad you called back. What's up?"

    if identity:
        name = identity.get("name") or ""
        first_name = name.split()[0] if name else None
        if first_name:
            return f"Hey {first_name}, this is Ron. What's going on?"

    return RON_OPENER


async def _emit_opener(call_id: str, from_number: str = "") -> dict:
    """Seed CALL_STATE for a new call and return the (possibly personalized) opener."""
    msgs = CALL_STATE.setdefault(call_id, [])
    if not msgs:
        _, history, identity = _get_or_compute_history(call_id, from_number)
        opener_text = _customized_opener(history, identity)
        # Record the opener as an assistant turn so the next user transcript
        # lands with proper conversational context.
        msgs.append({"role": "assistant", "content": opener_text})
        call_log.record(
            call_id,
            "opener",
            text=opener_text,
            prior_call_count=len(history),
            _from_number=from_number,
        )
        await bus.publish(
            call_id,
            {"callId": call_id, "ts": _now_iso(), "speaker": "agent", "text": opener_text},
        )
        return {"text": opener_text}
    return {"text": msgs[0]["content"]}


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    raw = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")
    if not agentphone_client.verify_signature(raw, signature, timestamp):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = json.loads(raw)
    event_name = event.get("event", "")
    data = event.get("data", {}) or {}
    call_id = _extract_call_id(data, event)
    from_number = _extract_from_number(data)

    # Call-lifecycle events bypass debounce: respond immediately.
    if event_name in _CALL_START_EVENTS:
        call_log.record(call_id, "lifecycle", event=event_name, _from_number=from_number)
        async with CALL_LOCKS[call_id]:
            return await _emit_opener(call_id, from_number=from_number)
    if event_name in _CALL_END_EVENTS:
        call_log.record(call_id, "lifecycle", event=event_name, data=data)
        async with CALL_LOCKS[call_id]:
            CALL_STATE.pop(call_id, None)
            LATEST_SEQ.pop(call_id, None)
            CALL_HISTORY.pop(call_id, None)
            return {}

    if event_name != "agent.message":
        _LOG.info("Ignoring unrecognized webhook event: %s", event_name)
        call_log.record(call_id, "unknown_event", event=event_name, data=data)
        return {}

    transcript = _extract_transcript(data)

    # Empty-transcript message on a fresh call is call-start-equivalent.
    if not transcript:
        async with CALL_LOCKS[call_id]:
            if call_id not in CALL_STATE:
                return await _emit_opener(call_id, from_number=from_number)
            call_log.record(call_id, "empty_transcript_ignored")
            return {}

    # Debounce interim transcripts. Each new webhook for this call bumps the
    # latest seq; older in-flight webhooks check after waiting and return {}
    # if a newer one arrived. This collapses STT refinement spam ("Yeah." ->
    # "Yeah. I'm still on the line.") into one Claude call on the final form.
    my_seq = next(_SEQ_COUNTER)
    LATEST_SEQ[call_id] = my_seq
    await asyncio.sleep(_DEBOUNCE_SECONDS)
    if LATEST_SEQ.get(call_id) != my_seq:
        return {}

    async with CALL_LOCKS[call_id]:
        # Re-check under lock: a newer webhook might have arrived while we
        # were waiting to acquire it.
        if LATEST_SEQ.get(call_id) != my_seq:
            return {}

        msgs = CALL_STATE.setdefault(call_id, [])

        # Only the very first user turn needs the caller-phone prefix so the
        # model can look the user up.
        seen_user_turn = any(m.get("role") == "user" for m in msgs)
        if not seen_user_turn:
            user_content = f"[caller_phone={from_number}] {transcript}"
        else:
            user_content = transcript
        msgs.append({"role": "user", "content": user_content})

        call_log.record(
            call_id,
            "user_transcript",
            raw=transcript,
            prefixed=user_content if not seen_user_turn else None,
            _from_number=from_number,
        )

        await bus.publish(
            call_id,
            {"callId": call_id, "ts": _now_iso(), "speaker": "caller", "text": transcript},
        )

        system_extra, _, _ = _get_or_compute_history(call_id, from_number)
        try:
            text, transfer = await run_turn(
                msgs,
                call_id=call_id,
                system_extra=system_extra,
            )
        except Exception as exc:
            call_log.record(call_id, "run_turn_error", error=repr(exc))
            raise
        msgs.append({"role": "assistant", "content": text})

        call_log.record(
            call_id,
            "assistant_response",
            text=text,
            text_empty=not bool(text.strip()),
            transfer=transfer,
        )

        await bus.publish(
            call_id,
            {"callId": call_id, "ts": _now_iso(), "speaker": "agent", "text": text},
        )

        response: dict = {"text": text}
        if transfer:
            response.update(transfer)
        return response


@app.websocket("/transcript/{call_id}")
async def transcript_ws(ws: WebSocket, call_id: str) -> None:
    await ws.accept()
    try:
        async for msg in bus.subscribe(call_id):
            await ws.send_json(msg)
    except WebSocketDisconnect:
        # Browser tab refreshed / closed / navigated away. Normal — exit cleanly
        # so the next async-for iteration's GeneratorExit triggers bus cleanup.
        return


@app.get("/transcript.html")
def transcript_page() -> FileResponse:
    return FileResponse(_PUBLIC_DIR / "transcript.html")
