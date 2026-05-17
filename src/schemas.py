from typing import Literal, Optional

from pydantic import BaseModel, Field


class Jurisdiction(BaseModel):
    state: str = Field(min_length=2, max_length=2)
    county: Optional[str] = None


class EmergencyContact(BaseModel):
    name: str
    relationship: str
    phone: str


class User(BaseModel):
    id: str
    name: str
    date_of_birth: str
    phone_numbers: list[str]
    email: Optional[str] = None
    payment_method_token: str
    emergency_contacts: list[EmergencyContact] = Field(default_factory=list)
    budget_max_hourly: int
    budget_max_retainer: int
    preferred_language: str = "en"
    home_jurisdiction: Jurisdiction
    notes: str = ""


class LawyerJurisdiction(BaseModel):
    state: str = Field(min_length=2, max_length=2)
    counties: list[str] = Field(default_factory=list)


class Lawyer(BaseModel):
    id: str
    name: str
    firm: str
    bar_state: str
    practice_areas: list[str]
    jurisdictions: list[LawyerJurisdiction]
    hourly_rate: int
    flat_consult_rate: Optional[int] = None
    typical_retainer: Optional[int] = None
    availability_status: Literal["now", "business_hours", "unavailable"]
    accepts_emergencies: bool
    languages: list[str]
    phone: str
    email: Optional[str] = None
    years_experience: int
    rating: float
    notes: str = ""


TierUsed = Literal[
    "strict",
    "county_relaxed",
    "area_broadened",
    "availability_relaxed",
    "language_dropped",
    "escalate",
]


class MatchResult(BaseModel):
    lawyers: list[Lawyer] = Field(default_factory=list)
    tier_used: TierUsed
    relaxed_constraints: list[str] = Field(default_factory=list)
    escalation_reason: Optional[str] = None
