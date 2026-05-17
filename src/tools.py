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

    # DEMO MODE: route every connect to DISPATCHER_PHONE (founder's phone)
    # instead of the lawyer's number. Lets you demonstrate a working transfer
    # without depending on each seed lawyer's phone being reachable. The email
    # still goes to the lawyer's email address per the seed.
    transfer_to = require_env("DISPATCHER_PHONE")
    agentphone_client.set_transfer_number(transfer_to)

    result: dict = {
        "transfer": {"action": "transfer", "transferNumber": transfer_to},
        "lawyer_name": lawyer.name,
        "email_sent": email_sent,
        "brief": brief,
        "caller_name": caller_name,
    }
    if email_error is not None:
        result["email_error"] = email_error
    return result


# Browser Use research-task prompts, per topic. These are the natural-language
# instructions sent to browser-use cloud to do live research. Each one must:
#   - target authoritative sources only (.gov, courts, official AG pages, vetted legal aid)
#   - return the URL + a short summary so the caller can read further
#   - NEVER ask the agent to interpret what the caller should do (UPL safety)
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


_RESEARCH_TASKS = {
    "ca_tenant": (
        "Visit the California Attorney General page on landlord-tenant issues "
        "(https://oag.ca.gov/consumers/general/landlord-tenant-issues), the California "
        "Courts Self-Help Center for landlord-tenant matters "
        "(https://www.courts.ca.gov/selfhelp-landtenant.htm), and the official page on "
        "California Civil Code §1950.5 (security deposit return rules — 21-day window, "
        "itemized statement). For each, extract the page URL and 2-3 plain-English bullet "
        "points covering the key rules a tenant should know. Also find one URL for free "
        "legal aid in California (e.g. LawHelpCA).\n\n" + _RESEARCH_OUTPUT_RULES
    ),
    "il_tenant": (
        "Visit the Illinois Attorney General page on landlord-tenant rights, the Illinois "
        "Legal Aid Online landlord-tenant section (https://www.illinoislegalaid.org/), and "
        "any official page covering the Illinois Security Deposit Return Act (765 ILCS 710) "
        "and Security Deposit Interest Act (765 ILCS 715) — deposit return timing (typically "
        "30-45 days) and itemization rules. For Cook County / Chicago specifically, also "
        "find the Chicago Residential Landlord and Tenant Ordinance (RLTO) page. For each "
        "source, extract the page URL and 2-3 plain-English bullet points covering the key "
        "rules a tenant should know.\n\n" + _RESEARCH_OUTPUT_RULES
    ),
}


# Curated, authoritative resource packs per topic. Used as a FALLBACK when
# browser-use is unconfigured, times out, or errors — so the caller always
# gets a usable email. Sources are .gov, official court self-help portals,
# and vetted legal aid only, so Ron is providing resources (UPL-safe).
_RESOURCE_PACKS = {
    "ca_tenant": {
        "subject": "California tenant resources from Better Call Ron",
        "body": (
            "Here are official resources for your California housing matter. These come "
            "from the California Attorney General, the courts, and vetted legal aid "
            "organizations.\n"
            "\n"
            "— California Attorney General — Tenants' Rights overview:\n"
            "  https://oag.ca.gov/consumers/general/landlord-tenant-issues\n"
            "\n"
            "— California Courts — Landlord/Tenant Self-Help Center:\n"
            "  https://www.courts.ca.gov/selfhelp-landtenant.htm\n"
            "\n"
            "— Tenant Protection Act of 2019 (rent caps, just-cause eviction):\n"
            "  https://landlordtenant.dre.ca.gov/tenant/protection_act.html\n"
            "\n"
            "— Security deposit rules (CA Civil Code §1950.5 — landlord must return\n"
            "  itemized deposit within 21 days):\n"
            "  https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1950.5.&lawCode=CIV\n"
            "\n"
            "— Free legal help by county (LawHelpCA):\n"
            "  https://www.lawhelpca.org/\n"
            "\n"
            "I'm Ron — I'm not a lawyer, and I can't tell you which of these applies "
            "to your specific situation. If after reading through these you still want "
            "to talk to an attorney, call back and I'll match you with one.\n"
            "\n"
            "— Ron, Better Call Ron"
        ),
    },
    "il_tenant": {
        "subject": "Illinois tenant resources from Better Call Ron",
        "body": (
            "Here are official resources for your Illinois housing matter. These come "
            "from Illinois Legal Aid Online, the Illinois Attorney General, and the "
            "Chicago RLTO where applicable.\n"
            "\n"
            "— Illinois Legal Aid Online — Housing section:\n"
            "  https://www.illinoislegalaid.org/legal-information/housing\n"
            "\n"
            "— Illinois Attorney General — Tenants' Rights handbook:\n"
            "  https://www.illinoisattorneygeneral.gov/Page-Attachments/Tenants_Rights_Handbook.pdf\n"
            "\n"
            "— Illinois Security Deposit Return Act (765 ILCS 710 — return timing\n"
            "  and itemized deductions):\n"
            "  https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=2208\n"
            "\n"
            "— Chicago Residential Landlord and Tenant Ordinance (RLTO — applies\n"
            "  to most rentals in Chicago / Cook County):\n"
            "  https://www.chicago.gov/city/en/depts/doh/provdrs/landlords/svcs/rlto.html\n"
            "\n"
            "I'm Ron — I'm not a lawyer, and I can't tell you which of these applies "
            "to your specific situation. If after reading through these you still want "
            "to talk to an attorney, call back and I'll match you with one.\n"
            "\n"
            "— Ron, Better Call Ron"
        ),
    },
}


_UPL_FOOTER = (
    "\n\nI'm Ron — I'm not a lawyer, and I can't tell you which of these applies "
    "to your specific situation. If after reading through these you still want "
    "to talk to an attorney, call back and I'll match you with one.\n\n"
    "— Ron, Better Call Ron"
)


def _send_curated_fallback(topic: str, email: str, reason: str) -> None:
    """Send the static curated pack for `topic`. Used when browser-use is unavailable."""
    pack = _RESOURCE_PACKS.get(topic)
    if not pack:
        _LOG.warning("no curated fallback for topic=%s (reason=%s)", topic, reason)
        return
    try:
        agentmail_client.send_email(to=email, subject=pack["subject"], text=pack["body"])
        _LOG.info("sent curated fallback to=%s topic=%s reason=%s", email, topic, reason)
    except Exception:
        _LOG.exception("curated fallback send failed to=%s topic=%s", email, topic)


async def _do_research_and_email(topic: str, email: str) -> None:
    """Async worker: run browser-use, email the result, fall back on any failure.

    Tests call this directly (with browseruse_client.research monkeypatched).
    Production calls it via asyncio.create_task from research_and_email.
    """
    task_prompt = _RESEARCH_TASKS.get(topic)
    if not task_prompt or not browseruse_client.is_configured():
        _send_curated_fallback(topic, email, reason="no_task_or_no_api_key")
        return

    try:
        output = await browseruse_client.research(task_prompt)
    except Exception:
        _LOG.exception("browser-use research failed for topic=%s; sending curated fallback", topic)
        _send_curated_fallback(topic, email, reason="browser_use_error")
        return

    subject = f"Your {topic.replace('_', ' ')} research from Better Call Ron"
    body = output + _UPL_FOOTER
    try:
        agentmail_client.send_email(to=email, subject=subject, text=body)
        _LOG.info("sent browser-use research to=%s topic=%s", email, topic)
    except Exception:
        _LOG.exception("send_email failed after research; trying curated fallback")
        _send_curated_fallback(topic, email, reason="send_failed")


def research_and_email(topic: str, email: str) -> dict:
    """Schedule async research-and-email for an informational topic.

    Browser-use tasks take 15-60s, which would time out the webhook if run
    synchronously. Instead we schedule a background task and return immediately
    so Ron can tell the caller "researching now — will email shortly".

    If browser-use is unconfigured, errors, or times out, the background task
    falls back to a curated static resource pack so the caller never gets
    nothing.
    """
    if not email:
        return {"error": "no_email_provided"}
    if topic not in _RESEARCH_TASKS and topic not in _RESOURCE_PACKS:
        return {
            "error": "unknown_topic",
            "topic": topic,
            "available": sorted(set(_RESEARCH_TASKS) | set(_RESOURCE_PACKS)),
        }

    try:
        asyncio.get_running_loop().create_task(_do_research_and_email(topic, email))
    except RuntimeError:
        # No running loop (e.g. invoked from a test without asyncio.run). Caller
        # should await _do_research_and_email directly in that context.
        _LOG.warning(
            "research_and_email called outside a running event loop — "
            "background task not scheduled. Call _do_research_and_email directly."
        )

    return {"status": "researching", "topic": topic, "to": email, "eta_seconds": 60}


def escalate_to_human(reason: str) -> dict:
    dispatcher = require_env("DISPATCHER_PHONE")
    agentphone_client.set_transfer_number(dispatcher)
    return {
        "transfer": {"action": "transfer", "transferNumber": dispatcher},
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
        "transfer": {"action": "transfer", "transferNumber": pd},
        "reason": reason,
    }
