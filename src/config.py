import os

from dotenv import load_dotenv

load_dotenv()


PRACTICE_AREA_PARENTS: dict[str, str | None] = {
    "criminal_defense": None,
    "family": None,
    "immigration": None,
    "civil": None,
    "business": None,
    "estate": None,
    "employment": None,
    "personal_injury": None,
    "landlord_tenant": None,
    "dui": "criminal_defense",
    "drug_offense": "criminal_defense",
    "assault": "criminal_defense",
    "domestic_violence": "criminal_defense",
    "divorce": "family",
    "custody": "family",
    "immigration_detention": "immigration",
    "asylum": "immigration",
}


SCORE_WEIGHTS = {
    "urgent": {
        "availability_weight": 10.0,
        "experience_weight": 0.5,
        "county_affinity_weight": 5.0,
    },
    "non_urgent": {"rating_weight": 20.0, "cost_weight": 0.1},
}


QUALITY_FLOOR = {
    "urgent_min_rating": 3.0,
    "experience_flag_threshold": 3,
    "non_urgent_rating_flag_threshold": 3.0,
}


RELAXATION_TIERS = [
    "strict",
    "county_relaxed",
    "area_broadened",
    "availability_relaxed",
    "language_dropped",
    "escalate",
]


AGENTPHONE_API_KEY = os.environ.get("AGENTPHONE_API_KEY")
AGENTPHONE_WEBHOOK_SECRET = os.environ.get("AGENTPHONE_WEBHOOK_SECRET")
AGENTPHONE_AGENT_ID = os.environ.get("AGENTPHONE_AGENT_ID")
AGENTPHONE_INBOUND_NUMBER = os.environ.get("AGENTPHONE_INBOUND_NUMBER")
AGENTPHONE_MESSAGING_NUMBER_ID = os.environ.get("AGENTPHONE_MESSAGING_NUMBER_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
DISPATCHER_PHONE = os.environ.get("DISPATCHER_PHONE")
PUBLIC_DEFENDER_HOTLINE = os.environ.get("PUBLIC_DEFENDER_HOTLINE")
WEBHOOK_PUBLIC_URL = os.environ.get("WEBHOOK_PUBLIC_URL")


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Required env var {name} is not set")
    return val
