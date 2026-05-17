import json
from pathlib import Path

import pytest

from src.matcher import match_lawyers
from src.schemas import Lawyer, User


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def users() -> list[User]:
    return [User(**u) for u in json.loads((DATA_DIR / "users.json").read_text())]


@pytest.fixture(scope="module")
def lawyers() -> list[Lawyer]:
    return [Lawyer(**lw) for lw in json.loads((DATA_DIR / "lawyers.json").read_text())]


def _user(users: list[User], uid: str) -> User:
    return next(u for u in users if u.id == uid)


def test_alameda_dui_urgent_returns_sarah_strict(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="dui",
        urgency="urgent",
    )
    assert result.tier_used == "strict"
    assert result.relaxed_constraints == []
    assert len(result.lawyers) == 1
    assert result.lawyers[0].id == "l_001"


def test_alameda_domestic_violence_urgent_broadens_to_criminal_defense(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="domestic_violence",
        urgency="urgent",
    )
    assert result.tier_used == "area_broadened"
    assert result.relaxed_constraints == ["county", "practice_area"]
    assert len(result.lawyers) == 1
    assert result.lawyers[0].id == "l_001"


def test_multnomah_drug_offense_urgent_below_quality_floor(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="OR",
        jurisdiction_county="Multnomah",
        practice_area="drug_offense",
        urgency="urgent",
    )
    assert result.tier_used == "escalate"
    assert result.escalation_reason == "below_quality_floor"
    assert result.lawyers == []


def test_cook_divorce_non_urgent_budget_filter(users, lawyers):
    user = _user(users, "u_002")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="IL",
        jurisdiction_county="Cook",
        practice_area="divorce",
        urgency="non_urgent",
    )
    assert result.tier_used == "strict"
    ids = [lw.id for lw in result.lawyers]
    assert "l_002" in ids
    assert "l_004" in ids
    assert "l_005" not in ids
    assert ids[0] == "l_002"


def test_wyoming_civil_urgent_no_match_in_network(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="WY",
        jurisdiction_county=None,
        practice_area="civil",
        urgency="urgent",
    )
    assert result.tier_used == "escalate"
    assert result.escalation_reason == "no_match_in_network"
    assert result.lawyers == []


def test_spanish_user_immigration_matches_spanish_speaking_lawyer(users, lawyers):
    user = _user(users, "u_003")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="immigration",
        urgency="non_urgent",
    )
    assert result.tier_used == "strict"
    assert len(result.lawyers) == 1
    assert result.lawyers[0].id == "l_006"
    assert "es" in result.lawyers[0].languages


def test_county_relaxed_tier_for_urgent_criminal_defense_in_la(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="San Diego",
        practice_area="criminal_defense",
        urgency="urgent",
    )
    assert result.tier_used == "county_relaxed"
    assert result.relaxed_constraints == ["county"]
    assert len(result.lawyers) == 1
    assert result.lawyers[0].id in {"l_001", "l_003"}


def test_non_urgent_returns_strict_only_with_relaxations_listed(users, lawyers):
    user = _user(users, "u_002")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="IL",
        jurisdiction_county="Cook",
        practice_area="divorce",
        urgency="non_urgent",
    )
    assert result.tier_used == "strict"
    assert "over_budget" in result.relaxed_constraints


def test_non_urgent_does_not_auto_relax(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="WY",
        jurisdiction_county=None,
        practice_area="civil",
        urgency="non_urgent",
    )
    assert result.tier_used == "strict"
    assert result.lawyers == []


def test_urgent_returns_single_lawyer_non_urgent_up_to_five(users, lawyers):
    user_urgent = _user(users, "u_001")
    urgent_result = match_lawyers(
        lawyers,
        user=user_urgent,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="dui",
        urgency="urgent",
    )
    assert len(urgent_result.lawyers) == 1

    user_non = _user(users, "u_002")
    non_urgent_result = match_lawyers(
        lawyers,
        user=user_non,
        jurisdiction_state="IL",
        jurisdiction_county="Cook",
        practice_area="divorce",
        urgency="non_urgent",
    )
    assert 0 < len(non_urgent_result.lawyers) <= 5


def test_spanish_user_falls_back_through_cascade_to_language_dropped(users, lawyers):
    user = _user(users, "u_003")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="dui",
        urgency="urgent",
    )
    assert result.tier_used in {"county_relaxed", "area_broadened", "availability_relaxed", "language_dropped"}
    assert result.lawyers


def test_availability_relaxed_tier_for_urgent_asylum_in_alameda(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="asylum",
        urgency="urgent",
    )
    assert result.tier_used == "availability_relaxed"
    assert result.relaxed_constraints == ["county", "practice_area", "availability"]
    assert len(result.lawyers) == 1
    assert result.lawyers[0].id == "l_006"


def test_county_affinity_local_lawyer_beats_more_experienced_remote_one(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="CA",
        jurisdiction_county="Alameda",
        practice_area="domestic_violence",
        urgency="urgent",
    )
    assert result.lawyers[0].id == "l_001"


def test_budget_filter_passes_via_retainer_when_hourly_over(users, lawyers):
    user = _user(users, "u_001")
    result = match_lawyers(
        lawyers,
        user=user,
        jurisdiction_state="IL",
        jurisdiction_county="Cook",
        practice_area="divorce",
        urgency="non_urgent",
    )
    assert result.tier_used == "strict"
    ids = [lw.id for lw in result.lawyers]
    assert "l_005" in ids
