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
    # AgentPhone reads the destination number from the agent record (set via
    # agentphone_client.set_transfer_number), so the response only carries
    # {"action": "transfer"}. The number actually set is exposed for logging.
    assert result["transfer"] == {"action": "transfer"}
    assert result["transfer_number_set_to"]  # whatever the lawyer's phone is
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
    result = tools.research_and_email(
        jurisdiction_state="CA",
        practice_area="landlord_tenant",
        situation_summary="My landlord is withholding my security deposit.",
        email="caller@example.com",
    )
    assert result["status"] == "researching"
    assert result["to"] == "caller@example.com"
    assert result["jurisdiction_state"] == "CA"
    assert result["practice_area"] == "landlord_tenant"


def test_research_and_email_returns_error_when_email_missing():
    result = tools.research_and_email(
        jurisdiction_state="CA",
        practice_area="landlord_tenant",
        situation_summary="Deposit withheld.",
        email="",
    )
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

    asyncio.run(
        tools._do_research_and_email(
            jurisdiction_state="CA",
            practice_area="landlord_tenant",
            situation_summary="Landlord won't return deposit after 60 days.",
            email="caller@example.com",
        )
    )

    # browser-use was called with a per-case prompt built from the inputs.
    task = captured_task["task"]
    assert "CA" in task
    assert "landlord tenant" in task  # underscores stripped for prose
    assert "Landlord won't return deposit" in task
    # The email body wraps the research output plus the UPL disclaimer.
    assert "Found 3 official sources" in captured_email["text"]
    assert "not a lawyer" in captured_email["text"]
    assert captured_email["to"] == "caller@example.com"
    # Subject reflects the practice area in human-readable form.
    assert "landlord tenant" in captured_email["subject"]


def test_do_research_and_email_falls_back_to_generic_when_no_api_key(monkeypatch):
    """When BROWSER_USE_API_KEY is missing, the generic-US fallback email is sent."""
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

    asyncio.run(
        tools._do_research_and_email(
            jurisdiction_state="CA",
            practice_area="landlord_tenant",
            situation_summary="Deposit withheld.",
            email="caller@example.com",
        )
    )

    # Generic-US fallback sent — universal pointers, jurisdiction-agnostic.
    assert "americanbar.org" in captured["text"]
    assert "usa.gov/legal-aid" in captured["text"]
    assert "not a lawyer" in captured["text"]


def test_do_research_and_email_falls_back_to_generic_on_browser_use_error(monkeypatch):
    """When browser-use raises, the generic-US fallback is sent so the caller still gets something."""
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

    asyncio.run(
        tools._do_research_and_email(
            jurisdiction_state="IL",
            practice_area="divorce",
            situation_summary="Considering filing for divorce.",
            email="caller@example.com",
        )
    )

    # Fallback fired with the universal pointers.
    assert "americanbar.org" in captured["text"]
    assert "usa.gov/legal-aid" in captured["text"]


def test_notify_emergency_contact_sends_sms_to_each_contact(monkeypatch):
    captured: list[dict] = []

    def capture(to: str, text: str) -> None:
        captured.append({"to": to, "text": text})

    monkeypatch.setattr(tools.agentphone_client, "send_sms", capture)

    # u_001 has one emergency contact in the seed.
    result = tools.notify_emergency_contact(
        user_id="u_001",
        message="Hi, this is Ron from Better Call Ron. Umair was just connected with an attorney.",
    )

    assert "error" not in result
    assert len(result["notified"]) == len(captured) >= 1
    # Each notified entry exposes name + relationship for narration.
    for entry in result["notified"]:
        assert entry["name"]
        assert entry["relationship"]


def test_notify_emergency_contact_returns_error_when_no_contacts(monkeypatch):
    # u_002 has emergency_contacts: [] in the seed.
    def boom(to: str, text: str) -> None:
        raise AssertionError("send_sms must not be called when no contacts on file")

    monkeypatch.setattr(tools.agentphone_client, "send_sms", boom)

    result = tools.notify_emergency_contact(user_id="u_002", message="anything")
    assert result == {"error": "no_emergency_contact_on_file", "user_id": "u_002"}


def test_notify_emergency_contact_returns_error_for_unknown_user(monkeypatch):
    def boom(to: str, text: str) -> None:
        raise AssertionError("send_sms must not be called for unknown user")

    monkeypatch.setattr(tools.agentphone_client, "send_sms", boom)

    result = tools.notify_emergency_contact(user_id="u_zzz", message="anything")
    assert result == {"error": "unknown_user", "user_id": "u_zzz"}


def test_notify_emergency_contact_captures_sms_failure(monkeypatch):
    def boom(to: str, text: str) -> None:
        raise RuntimeError("agentphone SMS offline")

    monkeypatch.setattr(tools.agentphone_client, "send_sms", boom)

    result = tools.notify_emergency_contact(user_id="u_001", message="test")
    # Failure does not raise — it surfaces in the `failed` list so the model
    # can decide what (if anything) to tell the caller.
    assert result["notified"] == []
    assert len(result["failed"]) >= 1
    assert "agentphone SMS offline" in result["failed"][0]["error"]


def test_lookup_user_result_includes_emergency_contacts():
    # u_001 has a contact; this should surface in the lookup result so the
    # # Caller identity block (and the model directly) can see whether to use
    # notify_emergency_contact.
    result = lookup_user(phone_number=_U_002.phone_numbers[0])  # u_002 has none
    assert result["emergency_contacts"] == []

    result = lookup_user(phone_number="+12152982128")  # u_001
    assert isinstance(result["emergency_contacts"], list)
    assert len(result["emergency_contacts"]) >= 1
    assert {"name", "relationship", "phone"} <= set(result["emergency_contacts"][0].keys())


def test_end_call_returns_hangup_action():
    result = tools.end_call(reason="caller_done")
    assert result["transfer"] == {"action": "hangup"}
    assert result["reason"] == "caller_done"


def test_route_to_public_defender_returns_transfer_to_hotline(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEFENDER_HOTLINE", "+15555550911")
    result = route_to_public_defender(reason="unknown_caller")
    assert result["transfer"] == {"action": "transfer"}
    # Number is set on the agent record via set_transfer_number; surfaced
    # in the tool result for logging.
    assert result["transfer_number_set_to"] == "+15555550911"
    assert result["reason"] == "unknown_caller"


def test_route_to_public_defender_raises_without_env(monkeypatch):
    monkeypatch.delenv("PUBLIC_DEFENDER_HOTLINE", raising=False)
    with pytest.raises(RuntimeError):
        route_to_public_defender(reason="unknown_caller")
