import json
import logging
from typing import Optional

from anthropic import AsyncAnthropic

from . import call_log, config, tools
from .prompts import SYSTEM_PROMPT


_LOG = logging.getLogger(__name__)

_client: Optional[AsyncAnthropic] = None
MAX_ITERATIONS = 8


TOOL_DEFS = [
    {
        "name": "lookup_user",
        "description": (
            "Look up a registered user by caller-ID phone number (preferred) "
            "or by full name + date of birth (fallback). Returns user_id and "
            "home jurisdiction when found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone_number": {
                    "type": "string",
                    "description": "Caller's phone in E.164 format (e.g. +14155551234).",
                },
                "name": {
                    "type": "string",
                    "description": "Full legal name. Required if phone_number is missing or unmatched.",
                },
                "dob": {
                    "type": "string",
                    "description": "Date of birth as YYYY-MM-DD. Required with name.",
                },
            },
        },
    },
    {
        "name": "match_lawyers",
        "description": (
            "Find the best-match lawyer(s) for the caller. Returns lawyers list "
            "plus tier_used and relaxed_constraints metadata that you MUST narrate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "user_id from lookup_user."},
                "jurisdiction_state": {
                    "type": "string",
                    "description": "Two-letter US state code (e.g. CA, IL, NY).",
                },
                "jurisdiction_county": {
                    "type": "string",
                    "description": (
                        "County name (no 'County' suffix). Optional — OMIT this field "
                        "entirely if unknown. Do NOT pass the literal string 'null'."
                    ),
                },
                "practice_area": {
                    "type": "string",
                    "description": (
                        "Controlled vocab: criminal_defense, dui, drug_offense, assault, "
                        "domestic_violence, family, divorce, custody, immigration, "
                        "immigration_detention, asylum, civil, business, estate, employment, "
                        "personal_injury, landlord_tenant."
                    ),
                },
                "urgency": {
                    "type": "string",
                    "enum": ["urgent", "non_urgent"],
                },
            },
            "required": ["user_id", "jurisdiction_state", "practice_area", "urgency"],
        },
    },
    {
        "name": "connect_to_lawyer",
        "description": (
            "SMS-brief the matched lawyer and return the cold-transfer instruction. "
            "Call only after the caller has confirmed they want to be connected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lawyer_id": {"type": "string", "description": "lawyer_id from match_lawyers."},
                "caller_name": {"type": "string", "description": "Caller's full name."},
                "brief": {
                    "type": "string",
                    "description": (
                        "One-sentence SMS for the lawyer. Format: "
                        "'{name}, {practice_area} matter in {county}, "
                        "{court status if urgent}. Retainer authorized.'"
                    ),
                },
            },
            "required": ["lawyer_id", "caller_name", "brief"],
        },
    },
    {
        "name": "research_and_email",
        "description": (
            "Kick off dynamic web research for the caller's specific legal "
            "situation and email them a pack of authoritative resources. Use "
            "for any non-urgent caller after you've identified state + practice "
            "area + a one-sentence summary of what's going on. The email arrives "
            "in 15-60 seconds; this returns immediately with {status: 'researching'}. "
            "After calling this, tell the caller you're emailing them resources "
            "and ask if they also want to be matched with a lawyer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction_state": {
                    "type": "string",
                    "description": "Two-letter US state code (e.g. CA, IL, NY).",
                },
                "practice_area": {
                    "type": "string",
                    "description": (
                        "Controlled vocab (same as match_lawyers): criminal_defense, "
                        "dui, drug_offense, assault, domestic_violence, family, "
                        "divorce, custody, immigration, immigration_detention, "
                        "asylum, civil, business, estate, employment, "
                        "personal_injury, landlord_tenant."
                    ),
                },
                "situation_summary": {
                    "type": "string",
                    "description": (
                        "One or two short sentences describing what's going on, "
                        "in the caller's own framing. Used to focus the research."
                    ),
                },
                "email": {
                    "type": "string",
                    "description": (
                        "Caller's email address. Use the `email` field from the "
                        "# Caller identity block or from lookup_user. If neither "
                        "has an email, ask the caller before invoking this tool."
                    ),
                },
            },
            "required": [
                "jurisdiction_state",
                "practice_area",
                "situation_summary",
                "email",
            ],
        },
    },
    {
        "name": "end_call",
        "description": (
            "Hang up the call. Use this paired with your final spoken line when the "
            "caller has confirmed they don't need anything else (e.g. they said 'no', "
            "'I'm good', 'thanks', 'bye'). Call this in the SAME turn as your closing "
            "speech so the line actually drops — otherwise AgentPhone keeps the call "
            "open and STT will fire repeat webhooks for the caller's continued speech."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Short code: caller_done (after self-serve research), "
                        "caller_satisfied (general goodbye), inactive."
                    ),
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Cold-transfer to the human dispatcher. Use when the matcher returns "
            "tier_used='escalate' (below quality floor or no match in network), the "
            "caller explicitly asks for a human, or any tool returns an error. Do NOT "
            "use this for unknown-caller fallback — use route_to_public_defender instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Short reason code: caller_requested, "
                        "below_quality_floor, no_match_in_network, tool_error."
                    ),
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "route_to_public_defender",
        "description": (
            "Cold-transfer to the static public-defender hotline. Use ONLY when "
            "lookup_user returns found=false after both caller-ID and name+DOB "
            "lookups — i.e. the caller has no registered account (PRD FR-9)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short reason, e.g. unknown_caller.",
                },
            },
            "required": ["reason"],
        },
    },
]


TOOL_IMPLS = {
    "lookup_user": tools.lookup_user,
    "match_lawyers": tools.match_lawyers,
    "connect_to_lawyer": tools.connect_to_lawyer,
    "research_and_email": tools.research_and_email,
    "end_call": tools.end_call,
    "escalate_to_human": tools.escalate_to_human,
    "route_to_public_defender": tools.route_to_public_defender,
}


# Cache breakpoint on the final tool entry caches the entire tools array as one block.
# Combined with the system-prompt cache below, this is ~8k tokens that stop being sent
# cold on every turn of a call — the practical fix for the dead-air problem.
_CACHED_TOOL_DEFS = [dict(t) for t in TOOL_DEFS]
_CACHED_TOOL_DEFS[-1] = {**_CACHED_TOOL_DEFS[-1], "cache_control": {"type": "ephemeral"}}


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=config.require_env("ANTHROPIC_API_KEY"))
    return _client


def _invoke_tool(name: str, raw_input: dict) -> dict:
    """Run a tool by name; never raise — surface errors back to the model."""
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        _LOG.warning("Claude requested unknown tool: %s", name)
        return {"error": "unknown_tool", "tool_name": name}
    try:
        return impl(**raw_input)
    except Exception as exc:  # NFR-6: tool failures degrade to escalation, not 500.
        _LOG.exception("Tool %s raised", name)
        return {"error": str(exc), "tool_name": name}


async def run_turn(
    messages: list[dict],
    call_id: str | None = None,
    system_extra: str | None = None,
) -> tuple[str, dict | None]:
    """Run Claude until end_turn or iteration cap.

    Mutates `messages` with assistant + tool_result turns.
    Returns (combined_text, pending_transfer_or_None).

    `system_extra`, if provided, is appended to SYSTEM_PROMPT for this turn —
    used to inject per-call context (e.g. repeat-caller history).

    `pending_transfer` is only honored when the loop exits naturally via
    `end_turn`; if MAX_ITERATIONS trips, we return None for the transfer so a
    stale instruction never fires.
    """
    client = _get_client()
    pending_transfer: dict | None = None
    text_chunks: list[str] = []
    iterations = 0

    system = SYSTEM_PROMPT + ("\n\n" + system_extra if system_extra else "")

    while iterations < MAX_ITERATIONS:
        iterations += 1
        resp = await client.messages.create(
            model=config.CLAUDE_MODEL,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=_CACHED_TOOL_DEFS,
            messages=messages,
            max_tokens=512,
        )

        iter_text: list[str] = []
        iter_tools: list[dict] = []
        for block in resp.content:
            if block.type == "text" and block.text:
                text_chunks.append(block.text)
                iter_text.append(block.text)
            elif block.type == "tool_use":
                iter_tools.append({"name": block.name, "input": dict(block.input)})

        if call_id:
            call_log.record(
                call_id,
                "claude_iteration",
                iteration=iterations,
                stop_reason=resp.stop_reason,
                input_messages=len(messages),
                text=iter_text,
                tool_calls=iter_tools,
                usage={
                    "input_tokens": getattr(resp.usage, "input_tokens", None),
                    "output_tokens": getattr(resp.usage, "output_tokens", None),
                    "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", None),
                    "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", None),
                },
            )

        # Defend against the rare case where the model returns
        # stop_reason="tool_use" but emits no actual tool_use blocks (just
        # text). Without this guard we'd append {"role": "user", "content": []}
        # and the next API call fails with 400 "user messages must have
        # non-empty content", stalling the call until AgentPhone times it out.
        if resp.stop_reason == "tool_use" and not iter_tools:
            combined = " ".join(t.strip() for t in text_chunks if t.strip())
            return combined, pending_transfer

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                result = _invoke_tool(block.name, dict(block.input))
                if call_id:
                    call_log.record(
                        call_id,
                        "tool_result",
                        name=block.name,
                        input=dict(block.input),
                        result=result,
                    )
                if isinstance(result, dict) and "transfer" in result:
                    pending_transfer = result["transfer"]
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            continue

        # Natural end_turn (or end_turn-equivalent stop_reason): commit transfer.
        combined = " ".join(t.strip() for t in text_chunks if t.strip())
        return combined, pending_transfer

    # Iteration cap hit. Never fire a stale transfer.
    fallback = " ".join(t.strip() for t in text_chunks if t.strip())
    if not fallback:
        fallback = "One sec — let me get a dispatcher."
    if call_id:
        call_log.record(
            call_id,
            "iteration_cap_hit",
            iterations=iterations,
            fallback_text=fallback,
            discarded_transfer=pending_transfer,
        )
    return fallback, None
