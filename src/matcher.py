from typing import Optional

from .config import PRACTICE_AREA_PARENTS, QUALITY_FLOOR, SCORE_WEIGHTS
from .schemas import Lawyer, MatchResult, User


_AVAILABILITY_SCORE = {"now": 1.0, "business_hours": 0.3, "unavailable": 0.0}


def match_lawyers(
    lawyers: list[Lawyer],
    *,
    user: User,
    jurisdiction_state: str,
    jurisdiction_county: Optional[str],
    practice_area: str,
    urgency: str,
) -> MatchResult:
    parent_area = PRACTICE_AREA_PARENTS.get(practice_area)

    strict = _filter(
        lawyers,
        user=user,
        state=jurisdiction_state,
        county=jurisdiction_county,
        practice_area=practice_area,
        urgency=urgency,
        allow_business_hours=False,
        drop_language=False,
    )

    if urgency == "non_urgent":
        relaxations = _available_relaxations_non_urgent(
            lawyers,
            user=user,
            state=jurisdiction_state,
            county=jurisdiction_county,
            practice_area=practice_area,
            parent_area=parent_area,
            strict_ids={lawyer.id for lawyer in strict},
        )
        ranked = _score_and_sort(strict, urgency)
        return MatchResult(
            lawyers=ranked[:5],
            tier_used="strict",
            relaxed_constraints=relaxations,
        )

    if strict:
        return _finalize_urgent(strict, "strict", [], jurisdiction_county)

    county_relaxed = _filter(
        lawyers,
        user=user,
        state=jurisdiction_state,
        county=None,
        practice_area=practice_area,
        urgency=urgency,
        allow_business_hours=False,
        drop_language=False,
    )
    if county_relaxed:
        return _finalize_urgent(county_relaxed, "county_relaxed", ["county"], jurisdiction_county)

    area_relaxations = ["county", "practice_area"] if parent_area else ["county"]
    if parent_area:
        area_broadened = _filter(
            lawyers,
            user=user,
            state=jurisdiction_state,
            county=None,
            practice_area=parent_area,
            urgency=urgency,
            allow_business_hours=False,
            drop_language=False,
        )
        if area_broadened:
            return _finalize_urgent(
                area_broadened, "area_broadened", area_relaxations, jurisdiction_county
            )

    cascade_area = parent_area or practice_area
    availability_relaxed = _filter(
        lawyers,
        user=user,
        state=jurisdiction_state,
        county=None,
        practice_area=cascade_area,
        urgency=urgency,
        allow_business_hours=True,
        drop_language=False,
    )
    if availability_relaxed:
        return _finalize_urgent(
            availability_relaxed,
            "availability_relaxed",
            area_relaxations + ["availability"],
            jurisdiction_county,
        )

    language_dropped = _filter(
        lawyers,
        user=user,
        state=jurisdiction_state,
        county=None,
        practice_area=cascade_area,
        urgency=urgency,
        allow_business_hours=True,
        drop_language=True,
    )
    if language_dropped:
        return _finalize_urgent(
            language_dropped,
            "language_dropped",
            area_relaxations + ["availability", "language"],
            jurisdiction_county,
        )

    return MatchResult(
        lawyers=[],
        tier_used="escalate",
        relaxed_constraints=[],
        escalation_reason="no_match_in_network",
    )


def _filter(
    lawyers: list[Lawyer],
    *,
    user: User,
    state: str,
    county: Optional[str],
    practice_area: str,
    urgency: str,
    allow_business_hours: bool,
    drop_language: bool,
) -> list[Lawyer]:
    out: list[Lawyer] = []
    for lawyer in lawyers:
        if not _matches_jurisdiction(lawyer, state, county):
            continue
        if practice_area not in lawyer.practice_areas:
            continue
        if not _matches_availability(lawyer, urgency, allow_business_hours):
            continue
        if not drop_language and not _matches_language(lawyer, user):
            continue
        if urgency == "non_urgent" and not _matches_budget(lawyer, user):
            continue
        out.append(lawyer)
    return out


def _matches_jurisdiction(lawyer: Lawyer, state: str, county: Optional[str]) -> bool:
    for jurisdiction in lawyer.jurisdictions:
        if jurisdiction.state != state:
            continue
        if county is None:
            return True
        if county in jurisdiction.counties:
            return True
    return False


def _matches_availability(lawyer: Lawyer, urgency: str, allow_business_hours: bool) -> bool:
    if lawyer.availability_status == "unavailable":
        return False
    if urgency != "urgent":
        return True
    if lawyer.availability_status == "now" and lawyer.accepts_emergencies:
        return True
    if (
        allow_business_hours
        and lawyer.availability_status == "business_hours"
        and lawyer.accepts_emergencies
    ):
        return True
    return False


def _matches_language(lawyer: Lawyer, user: User) -> bool:
    if user.preferred_language == "en":
        return True
    return user.preferred_language in lawyer.languages


def _matches_budget(lawyer: Lawyer, user: User) -> bool:
    if lawyer.hourly_rate <= user.budget_max_hourly:
        return True
    if lawyer.typical_retainer is not None and lawyer.typical_retainer <= user.budget_max_retainer:
        return True
    return False


def _lawyer_serves_county(lawyer: Lawyer, county: Optional[str]) -> bool:
    if county is None:
        return False
    return any(county in j.counties for j in lawyer.jurisdictions)


def _score_and_sort(
    lawyers: list[Lawyer], urgency: str, caller_county: Optional[str] = None
) -> list[Lawyer]:
    if urgency == "urgent":
        weights = SCORE_WEIGHTS["urgent"]

        def key(lawyer: Lawyer) -> tuple[float, float, str]:
            affinity = 1.0 if _lawyer_serves_county(lawyer, caller_county) else 0.0
            score = (
                weights["availability_weight"] * _AVAILABILITY_SCORE[lawyer.availability_status]
                + weights["experience_weight"] * lawyer.years_experience
                + weights["county_affinity_weight"] * affinity
            )
            return (score, lawyer.rating, lawyer.id)
    else:
        weights = SCORE_WEIGHTS["non_urgent"]

        def key(lawyer: Lawyer) -> tuple[float, float, str]:
            score = (
                weights["rating_weight"] * lawyer.rating
                - weights["cost_weight"] * lawyer.hourly_rate
            )
            return (score, lawyer.rating, lawyer.id)

    return sorted(lawyers, key=key, reverse=True)


def _finalize_urgent(
    candidates: list[Lawyer],
    tier: str,
    relaxed: list[str],
    caller_county: Optional[str],
) -> MatchResult:
    if max(lawyer.rating for lawyer in candidates) < QUALITY_FLOOR["urgent_min_rating"]:
        return MatchResult(
            lawyers=[],
            tier_used="escalate",
            relaxed_constraints=relaxed,
            escalation_reason="below_quality_floor",
        )
    above_floor = [lw for lw in candidates if lw.rating >= QUALITY_FLOOR["urgent_min_rating"]]
    ranked = _score_and_sort(above_floor, "urgent", caller_county)
    return MatchResult(
        lawyers=ranked[:1],
        tier_used=tier,
        relaxed_constraints=relaxed,
    )


def _available_relaxations_non_urgent(
    lawyers: list[Lawyer],
    *,
    user: User,
    state: str,
    county: Optional[str],
    practice_area: str,
    parent_area: Optional[str],
    strict_ids: set[str],
) -> list[str]:
    relaxations: list[str] = []

    over_budget = _filter_ignoring_budget(
        lawyers,
        user=user,
        state=state,
        county=county,
        practice_area=practice_area,
    )
    if any(lawyer.id not in strict_ids for lawyer in over_budget):
        relaxations.append("over_budget")

    if county is not None:
        statewide = _filter(
            lawyers,
            user=user,
            state=state,
            county=None,
            practice_area=practice_area,
            urgency="non_urgent",
            allow_business_hours=False,
            drop_language=False,
        )
        if any(lawyer.id not in strict_ids for lawyer in statewide):
            relaxations.append("statewide")

    if parent_area:
        broadened = _filter(
            lawyers,
            user=user,
            state=state,
            county=county,
            practice_area=parent_area,
            urgency="non_urgent",
            allow_business_hours=False,
            drop_language=False,
        )
        if any(lawyer.id not in strict_ids for lawyer in broadened):
            relaxations.append("practice_area")

    return relaxations


def _filter_ignoring_budget(
    lawyers: list[Lawyer],
    *,
    user: User,
    state: str,
    county: Optional[str],
    practice_area: str,
) -> list[Lawyer]:
    out: list[Lawyer] = []
    for lawyer in lawyers:
        if not _matches_jurisdiction(lawyer, state, county):
            continue
        if practice_area not in lawyer.practice_areas:
            continue
        if not _matches_availability(lawyer, "non_urgent", allow_business_hours=False):
            continue
        if not _matches_language(lawyer, user):
            continue
        out.append(lawyer)
    return out
