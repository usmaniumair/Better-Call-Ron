import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from . import agentmail_client, agentphone_client, browseruse_client
from .config import require_env
from .matcher import match_lawyers as _match_lawyers
from .schemas import Lawyer, User


_LOG = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_USERS: list[User] = [User(**u) for u in json.loads((_DATA_DIR / "users.json").read_text())]
_LAWYERS: list[Lawyer] = [
    Lawyer(**lw) for lw in json.loads((_DATA_DIR / "lawyers.json").read_text())
]


def _user_by_id(user_id: str) -> Optional[User]:
    return next((u for u in _USERS if u.id == user_id), None)


def _lawyer_by_id(lawyer_id: str) -> Optional[Lawyer]:
    return next((lw for lw in _LAWYERS if lw.id == lawyer_id), None)


def lookup_user(
    phone_number: Optional[str] = None,
    name: Optional[str] = None,
    dob: Optional[str] = None,
) -> dict:
    if phone_number:
        for user in _USERS:
            if phone_number in user.phone_numbers:
                return {
                    "found": True,
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "preferred_language": user.preferred_language,
                    "home_jurisdiction": user.home_jurisdiction.model_dump(),
                    "match_method": "caller_id",
                }

    if name and dob:
        target = name.strip().lower()
        for user in _USERS:
            if user.name.lower() == target and user.date_of_birth == dob:
                return {
                    "found": True,
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "preferred_language": user.preferred_language,
                    "home_jurisdiction": user.home_jurisdiction.model_dump(),
                    "match_method": "name_dob",
                }

    return {"found": False}


def match_lawyers(
    user_id: str,
    jurisdiction_state: str,
    practice_area: str,
    urgency: str,
    jurisdiction_county: Optional[str] = None,
) -> dict:
    user = _user_by_id(user_id)
    if user is None:
        return {"error": "unknown_user", "user_id": user_id}
    result = _match_lawyers(
        _LAWYERS,
        user=user,
        jurisdiction_state=jurisdiction_state,
        jurisdiction_county=jurisdiction_county,
        practice_area=practice_area,
        urgency=urgency,
    )
    return result.model_dump()


def connect_to_lawyer(lawyer_id: str, caller_name: str, brief: str) -> dict:
    lawyer = _lawyer_by_id(lawyer_id)
    if lawyer is None:
        return {"error": "unknown_lawyer", "lawyer_id": lawyer_id}

    email_sent = False
    email_error: Optional[str] = None
    if lawyer.email:
        subject = f"New client lead from Better Call Ron: {caller_name}"
        body = (
            f"{brief}\n\n"
            f"Caller: {caller_name}\n"
            f"You are being cold-transferred now from Better Call Ron.\n"
        )
        try:
            agentmail_client.send_email(to=lawyer.email, subject=subject, text=body)
            email_sent = True
        except Exception as exc:  # NFR-6: email failure must not block transfer.
            email_error = f"{type(exc).__name__}: {exc}"
            _LOG.exception("send_email failed for lawyer %s", lawyer_id)
    else:
        email_error = "no_email_on_record"

    # Set the agent's transfer_number BEFORE returning the webhook response.
    # AgentPhone reads transferNumber from the agent record at bridge time —
    # NOT from the webhook response (per agentphone.ai docs). The response
    # must contain only {"text": ..., "action": "transfer"} for the bridge
    # to fire; including a `transferNumber` field is undocumented and may
    # cause the response to be silently rejected.
    transfer_to = lawyer.phone
    agentphone_client.set_transfer_number(transfer_to)

    result: dict = {
        "transfer": {"action": "transfer"},
        "transfer_number_set_to": transfer_to,
        "lawyer_name": lawyer.name,
        "email_sent": email_sent,
        "brief": brief,
        "caller_name": caller_name,
    }
    if email_error is not None:
        result["email_error"] = email_error
    return result


# Output-format rules appended to every BrowserUse task prompt. Keeps the
# returned text email-ready (no preamble, no meta-commentary) and UPL-safe
# (summarize, don't advise).
_RESEARCH_OUTPUT_RULES = (
    "OUTPUT FORMAT — STRICT:\n"
    "Your entire response MUST be only the plain-text email body, ready to send as-is.\n"
    "Do NOT include any of the following:\n"
    "- Preamble like 'Here is the email body:' or 'Final answer:'\n"
    "- Meta-commentary about your own work (e.g. 'compiled and saved', 'each source verified', "
    "  'final email body', file paths like /workspace/...)\n"
    "- Notes about which URLs you tried, redirected, or 404'd. Just use the working URL silently.\n"
    "- Markdown code fences or quotes around the body.\n"
    "- Salutations ('Hi caller,') or sign-offs ('— Ron') — the calling code adds those.\n"
    "Start your response with the first source name. End with the last bullet of the last source. "
    "Nothing else. Format each resource as:\n"
    "— Source name:\n"
    "  https://url-here\n"
    "  - bullet 1\n"
    "  - bullet 2\n"
    "  - bullet 3\n"
    "  (blank line between sources)\n"
    "Do NOT give legal advice or tell the reader what to do — just summarize what each source says."
)


_UPL_FOOTER = (
    "\n\nI'm Ron — I'm not a lawyer, and I can't tell you which of these applies "
    "to your specific situation. If after reading through these you still want "
    "to talk to an attorney, call back and I'll match you with one.\n\n"
    "— Ron, Better Call Ron"
)


# Jurisdiction-agnostic last-resort email used when BrowserUse can't run
# (no API key, error, timeout, empty result). Two universal US pointers
# only — not per-topic sample data.
_GENERIC_FALLBACK_BODY = (
    "I wasn't able to pull jurisdiction-specific resources for you this time, "
    "but here are two national starting points:\n"
    "\n"
    "— American Bar Association — Find Legal Help:\n"
    "  https://www.americanbar.org/groups/legal_services/flh-home/\n"
    "  - Directory of free and reduced-cost legal aid by state and topic.\n"
    "\n"
    "— USA.gov — Legal Aid:\n"
    "  https://www.usa.gov/legal-aid\n"
    "  - Federal portal that points to your state's official legal aid programs."
)


def _build_research_prompt(
    jurisdiction_state: str, practice_area: str, situation_summary: str
) -> str:
    """Compose a BrowserUse task prompt tailored to one caller's case."""
    area = practice_area.replace("_", " ")
    return (
        f"Research authoritative legal resources in {jurisdiction_state} for a "
        f"{area} matter. The caller's situation: {situation_summary}\n\n"
        f"Target official and vetted sources only:\n"
        f"- The {jurisdiction_state} Attorney General's relevant consumer/legal page\n"
        f"- {jurisdiction_state} court self-help portal pages on this topic\n"
        f"- The {jurisdiction_state} State Bar lawyer-referral service\n"
        f"- Vetted statewide legal aid (e.g. LawHelp{jurisdiction_state}, statewide aid orgs)\n"
        f"- Any directly-relevant {jurisdiction_state} statute or code section\n\n"
        f"Aim for 3-5 sources total. For each, return the working page URL and "
        f"2-3 plain-English bullets summarizing the key points relevant to the "
        f"caller's situation. Skip Wikipedia and commercial law-firm pages.\n\n"
        + _RESEARCH_OUTPUT_RULES
    )


def _send_generic_fallback(email: str, reason: str) -> None:
    """Send the jurisdiction-agnostic fallback email when BrowserUse can't deliver."""
    subject = "Legal resources from Better Call Ron"
    body = _GENERIC_FALLBACK_BODY + _UPL_FOOTER
    try:
        agentmail_client.send_email(to=email, subject=subject, text=body)
        _LOG.info("sent generic fallback to=%s reason=%s", email, reason)
    except Exception:
        _LOG.exception("generic fallback send failed to=%s", email)


async def _do_research_and_email(
    jurisdiction_state: str,
    practice_area: str,
    situation_summary: str,
    email: str,
) -> None:
    """Async worker: run browser-use for the caller's specific case, email the result.

    Tests call this directly (with browseruse_client.research monkeypatched).
    Production calls it via asyncio.create_task from research_and_email.
    """
    if not browseruse_client.is_configured():
        _send_generic_fallback(email, reason="no_api_key")
        return

    prompt = _build_research_prompt(jurisdiction_state, practice_area, situation_summary)
    try:
        output = await browseruse_client.research(prompt)
    except Exception:
        _LOG.exception(
            "browser-use research failed for state=%s area=%s; sending generic fallback",
            jurisdiction_state,
            practice_area,
        )
        _send_generic_fallback(email, reason="browser_use_error")
        return

    area = practice_area.replace("_", " ")
    subject = f"Your {area} resources from Better Call Ron"
    body = output + _UPL_FOOTER
    try:
        agentmail_client.send_email(to=email, subject=subject, text=body)
        _LOG.info(
            "sent browser-use research to=%s state=%s area=%s",
            email,
            jurisdiction_state,
            practice_area,
        )
    except Exception:
        _LOG.exception("send_email failed after research; trying generic fallback")
        _send_generic_fallback(email, reason="send_failed")


def research_and_email(
    jurisdiction_state: str,
    practice_area: str,
    situation_summary: str,
    email: str,
) -> dict:
    """Schedule async per-case research-and-email.

    Browser-use tasks take 15-60s, which would time out the webhook if run
    synchronously. Instead we schedule a background task and return immediately
    so Ron can tell the caller "researching now — will email shortly".

    If browser-use is unconfigured, errors, or times out, the background task
    falls back to a tiny jurisdiction-agnostic email so the caller never gets
    nothing.
    """
    if not email:
        return {"error": "no_email_provided"}

    try:
        asyncio.get_running_loop().create_task(
            _do_research_and_email(
                jurisdiction_state, practice_area, situation_summary, email
            )
        )
    except RuntimeError:
        # No running loop (e.g. invoked from a test without asyncio.run). Caller
        # should await _do_research_and_email directly in that context.
        _LOG.warning(
            "research_and_email called outside a running event loop — "
            "background task not scheduled. Call _do_research_and_email directly."
        )

    return {
        "status": "researching",
        "to": email,
        "jurisdiction_state": jurisdiction_state,
        "practice_area": practice_area,
        "eta_seconds": 60,
    }


def escalate_to_human(reason: str) -> dict:
    dispatcher = require_env("DISPATCHER_PHONE")
    agentphone_client.set_transfer_number(dispatcher)
    return {
        "transfer": {"action": "transfer"},
        "transfer_number_set_to": dispatcher,
        "reason": reason,
    }


def end_call(reason: str) -> dict:
    """Tell AgentPhone to hang up the call after Ron's closing line.

    The transfer dict is overloaded — server.py merges it into the webhook
    response, so `{"action": "hangup"}` becomes the top-level response. If
    AgentPhone's webhook contract doesn't recognize the hangup action, the
    call still ends via the inactivity timeout — this is best-effort.
    """
    return {
        "transfer": {"action": "hangup"},
        "reason": reason,
    }


def route_to_public_defender(reason: str) -> dict:
    """Route unknown callers (FR-9) to the static public-defender hotline."""
    pd = require_env("PUBLIC_DEFENDER_HOTLINE")
    agentphone_client.set_transfer_number(pd)
    return {
        "transfer": {"action": "transfer"},
        "transfer_number_set_to": pd,
        "reason": reason,
    }
