import pytest

from src import tools
from src.tools import connect_to_lawyer, lookup_user, match_lawyers, route_to_public_defender


# Read u_002's current name + DOB from the seed so these tests don't break
# every time the demo persona is renamed.
_U_002 = next(u for u in tools._USERS if u.id == "u_002")


def test_lookup_user_by_caller_id():
    result = lookup_user(phone_number=_U_002.phone_numbers[0])
    assert result["found"] is True
    assert result["user_id"] == "u_002"
    assert result["match_method"] == "caller_id"


def test_lookup_user_by_name_and_dob_case_insensitive():
    result = lookup_user(name=_U_002.name.lower(), dob=_U_002.date_of_birth)
    assert result["found"] is True
    assert result["user_id"] == "u_002"
    assert result["match_method"] == "name_dob"


def test_lookup_user_unknown_returns_not_found():
    result = lookup_user(phone_number="+19999999999")
    assert result["found"] is False


def test_lookup_user_wrong_dob_returns_not_found():
    result = lookup_user(name=_U_002.name, dob="1900-01-01")
    assert result["found"] is False


def test_match_lawyers_tool_returns_serializable_dict():
    result = match_lawyers(
        user_id="u_001",
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="dui",
        urgency="urgent",
    )
    assert result["tier_used"] == "strict"
    assert len(result["lawyers"]) == 1
    assert result["lawyers"][0]["id"] == "l_001"


def test_connect_to_lawyer_returns_email_error_when_send_fails(monkeypatch):
    def boom(to: str, subject: str, text: str) -> str:
        raise RuntimeError("agentmail offline")

    monkeypatch.setattr(tools.agentmail_client, "send_email", boom)

    result = connect_to_lawyer(
        lawyer_id="l_001",
        caller_name="Umair Usmani",
        brief="Umair Usmani, DUI matter in Alameda, not yet arraigned. Retainer authorized.",
    )

    # Transfer must still be returned per NFR-6 even when email fails.
    assert result["transfer"]["action"] == "transfer"
    assert result["transfer"]["transferNumber"]  # whatever the lawyer's phone is
    assert result["email_sent"] is False
    assert "agentmail offline" in result["email_error"]
    # Lawyer name comes from the seed; just verify it's set rather than hardcoding.
    assert result["lawyer_name"]


def test_connect_to_lawyer_sends_email_to_lawyer_address(monkeypatch):
    captured: dict = {}

    def capture(to: str, subject: str, text: str) -> str:
        captured["to"] = to
        captured["subject"] = subject
        captured["text"] = text
        return "inbox_test"

    monkeypatch.setattr(tools.agentmail_client, "send_email", capture)

    result = connect_to_lawyer(
        lawyer_id="l_001",
        caller_name="Umair Usmani",
        brief="Umair Usmani, DUI matter in Alameda, not yet arraigned. Retainer authorized.",
    )

    assert result["email_sent"] is True
    assert "email_error" not in result
    # Lawyer l_001's email is the demo address in the seed.
    assert captured["to"] == "uausmani25@gmail.com"
    assert "Umair Usmani" in captured["subject"]
    assert "DUI matter in Alameda" in captured["text"]


def test_research_and_email_returns_researching_immediately():
    """The sync entry point schedules background work and returns immediately."""
    # No event loop running, no background task scheduled — but the contract
    # (return shape) is the same. Tool result tells Ron to say "researching".
    result = tools.research_and_email(topic="ca_tenant", email="caller@example.com")
    assert result["status"] == "researching"
    assert result["topic"] == "ca_tenant"
    assert result["to"] == "caller@example.com"


def test_research_and_email_returns_error_for_unknown_topic():
    result = tools.research_and_email(topic="zzz_nonexistent", email="x@example.com")
    assert result["error"] == "unknown_topic"
    assert result["topic"] == "zzz_nonexistent"
    assert "ca_tenant" in result["available"]


def test_research_and_email_returns_error_when_email_missing():
    result = tools.research_and_email(topic="ca_tenant", email="")
    assert result == {"error": "no_email_provided"}


def test_do_research_and_email_uses_browser_use_when_configured(monkeypatch):
    """When BROWSER_USE_API_KEY is set, async worker calls browser-use then emails."""
    import asyncio

    monkeypatch.setenv("BROWSER_USE_API_KEY", "test_key")

    captured_email: dict = {}
    captured_task: dict = {}

    async def fake_research(task: str) -> str:
        captured_task["task"] = task
        return "Found 3 official sources:\n— https://oag.ca.gov/...\n— https://courts.ca.gov/..."

    def capture(to: str, subject: str, text: str) -> str:
        captured_email["to"] = to
        captured_email["subject"] = subject
        captured_email["text"] = text
        return "inbox_test"

    monkeypatch.setattr(tools.browseruse_client, "research", fake_research)
    monkeypatch.setattr(tools.agentmail_client, "send_email", capture)

    asyncio.run(tools._do_research_and_email("ca_tenant", "caller@example.com"))

    # browser-use was called with the topic's research prompt
    assert "California Attorney General" in captured_task["task"]
    # The email body wraps the research output plus the UPL disclaimer
    assert "Found 3 official sources" in captured_email["text"]
    assert "not a lawyer" in captured_email["text"]
    assert captured_email["to"] == "caller@example.com"


def test_do_research_and_email_falls_back_to_curated_when_no_api_key(monkeypatch):
    """When BROWSER_USE_API_KEY is missing, the curated pack is sent instead."""
    import asyncio

    monkeypatch.delenv("BROWSER_USE_API_KEY", raising=False)

    captured: dict = {}

    def capture(to: str, subject: str, text: str) -> str:
        captured.update({"to": to, "subject": subject, "text": text})
        return "inbox_test"

    def boom(task: str):
        raise AssertionError("browser-use must not be called when API key is missing")

    monkeypatch.setattr(tools.browseruse_client, "research", boom)
    monkeypatch.setattr(tools.agentmail_client, "send_email", capture)

    asyncio.run(tools._do_research_and_email("ca_tenant", "caller@example.com"))

    # Curated pack was sent
    assert "oag.ca.gov" in captured["text"]
    assert "courts.ca.gov" in captured["text"]
    assert "not a lawyer" in captured["text"]


def test_do_research_and_email_falls_back_to_curated_on_browser_use_error(monkeypatch):
    """When browser-use raises, the curated pack is sent so the caller still gets something."""
    import asyncio

    monkeypatch.setenv("BROWSER_USE_API_KEY", "test_key")

    async def boom(task: str) -> str:
        raise RuntimeError("browser-use cloud offline")

    captured: dict = {}

    def capture(to: str, subject: str, text: str) -> str:
        captured.update({"to": to, "subject": subject, "text": text})
        return "inbox_test"

    monkeypatch.setattr(tools.browseruse_client, "research", boom)
    monkeypatch.setattr(tools.agentmail_client, "send_email", capture)

    asyncio.run(tools._do_research_and_email("ca_tenant", "caller@example.com"))

    # Fallback fired
    assert "oag.ca.gov" in captured["text"]


def test_end_call_returns_hangup_action():
    result = tools.end_call(reason="caller_done")
    assert result["transfer"] == {"action": "hangup"}
    assert result["reason"] == "caller_done"


def test_route_to_public_defender_returns_transfer_to_hotline(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEFENDER_HOTLINE", "+15555550911")
    result = route_to_public_defender(reason="unknown_caller")
    assert result["transfer"]["action"] == "transfer"
    assert result["transfer"]["transferNumber"] == "+15555550911"
    assert result["reason"] == "unknown_caller"


def test_route_to_public_defender_raises_without_env(monkeypatch):
    monkeypatch.delenv("PUBLIC_DEFENDER_HOTLINE", raising=False)
    with pytest.raises(RuntimeError):
        route_to_public_defender(reason="unknown_caller")
