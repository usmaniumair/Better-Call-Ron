# Better Call Ron — Implementation Plan

**Companion to:** [PRD.md](./PRD.md)
**Status (2026-05-18):** All phases built and verified end-to-end live. The phase-by-phase build narrative below is a historical record of how it was built; the **Current state** section right below captures what's actually shipped. See PRD § 16 ("What changed since draft") for behavior changes.
**Hackathon:** YC "Call My Agent"

---

## Current state (2026-05-18)

- **53 tests passing.** `.venv/bin/pytest -v`.
- **8 tools wired:** `lookup_user`, `match_lawyers`, `connect_to_lawyer`, `research_and_email`, `notify_emergency_contact`, `end_call`, `escalate_to_human`, `route_to_public_defender`.
- **Verified live:** caller-ID identity resolution, urgent triage, matcher cascade, BrowserUse dynamic research, AgentMail lawyer-brief email, AgentPhone cold transfer, emergency-contact SMS, repeat-caller greeting.
- **Prompt caching wired.** `cache_control: ephemeral` on system + tools — ~8k tokens cached per turn after the first. Cuts cold-turn latency from ~22s to ~4s.
- **Transfer mechanic:** `{"text": "...", "action": "transfer"}` only in the webhook response; destination set on the agent record via `c.agents.update(transfer_number=lawyer.phone)` right before returning. Sending `transferNumber` in the response causes silent bridge drops — don't.

## Project layout (actual)

```
better-call-ron/
├── PRD.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── .env                               # local secrets (gitignored)
├── .env.example                       # template
├── .gitignore
├── pyproject.toml
├── data/
│   ├── users.json                     # 3 seeded user profiles
│   ├── lawyers.json                   # 10 seeded lawyers
│   └── calls/                         # per-call JSON event logs (gitignored;
│                                      #  timestamp-prefixed filenames)
├── src/
│   ├── __init__.py
│   ├── config.py                      # constants, weights, env-loading
│   ├── schemas.py                     # pydantic models (User, Lawyer, EmergencyContact, ...)
│   ├── tools.py                       # 8 tool implementations
│   ├── matcher.py                     # filter + cascade + score + floor
│   ├── prompts.py                     # Claude system prompt + BRIDGE/CO-NARRATE rules
│   ├── claude_loop.py                 # Claude tool-use loop; prompt caching; post-transfer text suppression
│   ├── agentphone_client.py           # AgentPhone SDK wrapper (voice webhook sig, set_transfer_number, send_sms)
│   ├── agentmail_client.py            # AgentMail SDK wrapper (lawyer-brief email)
│   ├── browseruse_client.py           # BrowserUse SDK wrapper (async research(task))
│   ├── server.py                      # FastAPI app: /webhook, /transcript WS, TRANSFERRED_CALLS latch
│   ├── transcript_bus.py              # in-process pub/sub for the transcript WS
│   └── call_log.py                    # per-call JSON writer + repeat-caller history lookup
├── public/
│   └── transcript.html                # one-page live transcript view
├── tests/
│   ├── test_matcher.py                # matcher cascade + scoring
│   ├── test_tools.py                  # tool behaviors (including notify_emergency_contact, research)
│   ├── test_claude_loop.py            # tool-def schema consistency vs Python signatures
│   ├── test_signature.py              # AgentPhone HMAC verification regressions
│   └── fixtures/
└── assets/
    ├── signup-mockup.png              # Figma export for pitch slide
    └── backup-demo.mp4                # recorded fallback (filmed Sunday AM)
```

---

## Phase 0 — Preflight (do BEFORE Sunday)

**Goal:** all credentials live, all team members ready, no Sunday-morning blockers.

### 0.1 Accounts and keys

1. **AgentPhone** — sign up at agentphone.ai, provision one US number, generate an API key, note the `agent_id`. Add a credit balance (~$20 — well over what the hackathon needs).
2. **Anthropic** — get an API key with credit on file.
3. **ngrok** — install the CLI, sign in, claim a static subdomain if available (paid plans only — fine to use a fresh URL each session on free).

### 0.2 Repo skeleton

```bash
mkdir -p better-call-ron/{src,data,public,tests/fixtures,assets}
cd better-call-ron
git init
python -m venv .venv && source .venv/bin/activate
```

`pyproject.toml` (actual):
```toml
[project]
name = "better-call-ron"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "agentphone",                # AgentPhone Python SDK (voice + SMS + iMessage)
  "agentmail",                 # AgentMail SDK (lawyer-brief email on connect)
  "browser-use-sdk",           # BrowserUse SDK (per-case dynamic research)
  "anthropic>=0.40",
  "fastapi",
  "uvicorn[standard]",
  "pydantic>=2",
  "python-dotenv",
  "httpx",
  "websockets",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio", "ruff"]
```

`pip install -e ".[dev]"`

`.env.example` (copy to `.env` and fill in):
```
# AgentPhone (voice + SMS + iMessage)
AGENTPHONE_API_KEY=
AGENTPHONE_WEBHOOK_SECRET=
AGENTPHONE_AGENT_ID=
AGENTPHONE_INBOUND_NUMBER=+1XXXXXXXXXX
# Optional: pin outbound `messages.send` to a specific attached number_id
# (useful when one attached number is iMessage-only or 10DLC-cleaner than another).
AGENTPHONE_MESSAGING_NUMBER_ID=

# AgentMail (lawyer-brief email on connect)
AGENTMAIL_API_KEY=
AGENTMAIL_INBOX_ID=             # optional; created on first send if unset

# BrowserUse (dynamic per-case research for non-urgent callers)
BROWSER_USE_API_KEY=            # if unset, research_and_email sends a generic fallback email

# Anthropic Claude
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-sonnet-4-6  # Sonnet for voice TTFT; swap to claude-opus-4-7 if quality is bottleneck

# Routing fallbacks
DISPATCHER_PHONE=+1XXXXXXXXXX   # escalate_to_human destination
PUBLIC_DEFENDER_HOTLINE=+1XXXXXXXXXX  # route_to_public_defender (FR-9 unknown-caller)
WEBHOOK_PUBLIC_URL=             # ngrok https URL for AgentPhone to reach /webhook

# Tunables
RON_DEBOUNCE_SECONDS=0.4        # optional; per-call STT-refinement debounce window
```

### 0.3 Team alignment

- "Sarah" actor — confirm their phone number, confirm they'll be reachable from 10 AM Sunday onward
- Tech operator — confirm laptop, hotspot, second screen for transcript
- Narrator — confirm pitch ownership

### 0.4 The CRITICAL preflight experiment — `transferNumber` discovery

**RESOLVED 2026-05-17 via AgentPhone docs (after several failed live calls).** The webhook response must be `{"text": "...", "action": "transfer"}` **only — no `transferNumber` field.** AgentPhone reads the destination from the agent record's `transfer_number` field. Set that field via `c.agents.update(agent_id, transfer_number=lawyer.phone)` synchronously inside `connect_to_lawyer` BEFORE returning the webhook response. Sending `transferNumber` in the response causes silent bridge drops (AgentPhone returns 200 OK and the call ends in inactivity instead of `call_transfer`).

The original experiment script below is preserved for historical context but is no longer needed.

```python
# scratch_transfer_test.py
import os
from agentphone import AgentPhone

ap = AgentPhone(api_key=os.environ["AGENTPHONE_API_KEY"])
# Configure agent with dummy transferNumber
ap.agents.update(
    os.environ["AGENTPHONE_AGENT_ID"],
    transfer_number="+15555550000",  # dummy
)
print("Agent configured. Now place an inbound call and have your webhook return:")
print('  {"action": "transfer", "transferNumber": "+1<your phone>"}')
print("If your phone rings -> Scenario A (per-call inline) -> you're golden.")
print("If the dummy number gets dialed -> Scenario B/C (per-agent only).")
```

Place the test call. Outcome dictates which connect implementation we ship (see Phase 4).

---

## Phase 1 — Seed data (30 min)

**Goal:** `users.json` and `lawyers.json` with enough variety to exercise the matcher and a deterministic happy-path for the demo.

### 1.1 `data/users.json`

Three users. The first is **you** (the demo caller). Note: `u_002` ships with `budget_max_retainer: 2000` (not 3000 as shown in this skeleton) so the non-urgent budget filter is exercised against `l_004` ($2000 retainer, just inside budget) and `l_005` ($2500 retainer, just outside).

```json
[
  {
    "id": "u_001",
    "name": "Umair Usmani",
    "date_of_birth": "1995-01-01",
    "phone_numbers": ["+1<your registered phone>"],
    "payment_method_token": "pm_mock_umair",
    "emergency_contacts": [
      {"name": "Sara Usmani", "relationship": "spouse", "phone": "+1<emergency contact>"}
    ],
    "budget_max_hourly": 600,
    "budget_max_retainer": 5000,
    "preferred_language": "en",
    "home_jurisdiction": {"state": "CA", "county": "Alameda"},
    "notes": ""
  },
  {
    "id": "u_002",
    "name": "Jordan Reyes",
    "date_of_birth": "1988-07-12",
    "phone_numbers": ["+15555550002"],
    "payment_method_token": "pm_mock_jordan",
    "emergency_contacts": [],
    "budget_max_hourly": 400,
    "budget_max_retainer": 3000,
    "preferred_language": "en",
    "home_jurisdiction": {"state": "IL", "county": "Cook"},
    "notes": ""
  },
  {
    "id": "u_003",
    "name": "Priya Shah",
    "date_of_birth": "1992-11-30",
    "phone_numbers": ["+15555550003"],
    "payment_method_token": "pm_mock_priya",
    "emergency_contacts": [],
    "budget_max_hourly": 350,
    "budget_max_retainer": 2000,
    "preferred_language": "en",
    "home_jurisdiction": {"state": "NY", "county": "Kings"},
    "notes": "Existing relationship with Goldman Civil for civil matters"
  }
]
```

### 1.2 `data/lawyers.json`

Ten lawyers. **Two real-callable** (your teammates' phones):
- `l_001` Sarah Chen — criminal defense, Alameda CA, rating 4.8, `phone = <Sarah actor's phone>`
- `l_002` Mark Davis — divorce/family, Cook IL, rating 4.5, `phone = <Mark actor's phone>`

The other eight are decorative. Seed them so the demo's deterministic triage (Alameda + DUI + urgent) lands on Sarah without ambiguity.

**Required seed coverage:**
- 2-3 criminal_defense / dui lawyers across CA (Sarah + 1-2 others in non-Alameda counties)
- 2-3 family / divorce lawyers across IL and NY
- 1 immigration lawyer (CA)
- 1 civil lawyer (NY)
- 1 personal_injury lawyer (CA)
- 1 low-rated lawyer (rating 2.6, Modoc CA, criminal_defense) — used to exercise the FR-20 quality-floor escalation in §5.7 scenario tests

Skeleton entry:
```json
{
  "id": "l_001",
  "name": "Sarah Chen",
  "firm": "Chen Defense Law",
  "bar_state": "CA",
  "practice_areas": ["criminal_defense", "dui"],
  "jurisdictions": [{"state": "CA", "counties": ["Alameda", "Contra Costa"]}],
  "hourly_rate": 450,
  "flat_consult_rate": null,
  "typical_retainer": 2500,
  "availability_status": "now",
  "accepts_emergencies": true,
  "languages": ["en"],
  "phone": "+1<Sarah actor phone>",
  "years_experience": 12,
  "rating": 4.8,
  "notes": "On-call lawyer for demo"
}
```

### 1.3 Sanity check after seeding

```bash
python -c "import json; print(len(json.load(open('data/lawyers.json'))))"
# expect: 10
```

---

## Phase 2 — Tools and matcher (90 min)

**Goal:** the four agent tools and the matcher logic, all unit-tested. No telephony or LLM yet.

### 2.1 `src/schemas.py`

Pydantic models matching PRD §9. Keep them strict (no `Any`) so type errors surface early.

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class Jurisdiction(BaseModel):
    state: str
    county: Optional[str] = None

class EmergencyContact(BaseModel):
    name: str
    relationship: str
    phone: str

class User(BaseModel):
    id: str
    name: str
    date_of_birth: str  # ISO YYYY-MM-DD
    phone_numbers: list[str]
    payment_method_token: str
    emergency_contacts: list[EmergencyContact]
    budget_max_hourly: int
    budget_max_retainer: int
    preferred_language: str = "en"
    home_jurisdiction: Jurisdiction
    notes: str = ""

class LawyerJurisdiction(BaseModel):
    state: str
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
    years_experience: int
    rating: float
    notes: str = ""

class MatchResult(BaseModel):
    lawyers: list[Lawyer]
    tier_used: Literal[
        "strict", "county_relaxed", "area_broadened",
        "availability_relaxed", "language_dropped", "escalate"
    ]
    relaxed_constraints: list[str] = Field(default_factory=list)
    escalation_reason: Optional[str] = None  # set when tier_used == "escalate"
```

### 2.2 `src/config.py`

PRD §9.5 constants + env loading.

```python
import os
from dotenv import load_dotenv
load_dotenv()

PRACTICE_AREA_PARENTS = {
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
        "county_affinity_weight": 5.0,   # PRD FR-22: lawyer serving caller's county wins ties (local = faster courthouse appearance)
    },
    "non_urgent": {"rating_weight": 20.0, "cost_weight": 0.1},
}

QUALITY_FLOOR = {
    "urgent_min_rating": 3.0,
    "experience_flag_threshold": 3,
    "non_urgent_rating_flag_threshold": 3.0,
}

# Env
AGENTPHONE_API_KEY = os.environ["AGENTPHONE_API_KEY"]
AGENTPHONE_WEBHOOK_SECRET = os.environ["AGENTPHONE_WEBHOOK_SECRET"]
AGENTPHONE_AGENT_ID = os.environ["AGENTPHONE_AGENT_ID"]
AGENTPHONE_INBOUND_NUMBER = os.environ["AGENTPHONE_INBOUND_NUMBER"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")  # Sonnet default for voice TTFT; Opus 4.7 as quality fallback
DISPATCHER_PHONE = os.environ["DISPATCHER_PHONE"]
PUBLIC_DEFENDER_HOTLINE = os.environ["PUBLIC_DEFENDER_HOTLINE"]
```

### 2.3 `src/matcher.py`

Implements PRD §6.4 — FR-15 through FR-22.

```python
from .schemas import User, Lawyer, MatchResult
from .config import PRACTICE_AREA_PARENTS, SCORE_WEIGHTS, QUALITY_FLOOR

def match_lawyers(
    lawyers: list[Lawyer],
    *,
    user: User,
    jurisdiction_state: str,
    jurisdiction_county: str | None,
    practice_area: str,
    urgency: str,  # "urgent" | "non_urgent"
) -> MatchResult:
    # Tier 0: strict
    candidates = _strict_filter(lawyers, user, jurisdiction_state, jurisdiction_county, practice_area, urgency)
    if candidates:
        return _finalize(candidates, "strict", [], urgency)

    if urgency == "urgent":
        # Tier 1: drop county
        candidates = _strict_filter(lawyers, user, jurisdiction_state, None, practice_area, urgency)
        if candidates:
            return _finalize(candidates, "county_relaxed", ["county"], urgency)

        # Tier 2: broaden practice area
        parent = PRACTICE_AREA_PARENTS.get(practice_area)
        if parent:
            candidates = _strict_filter(lawyers, user, jurisdiction_state, None, parent, urgency)
            if candidates:
                return _finalize(candidates, "area_broadened", ["county", "practice_area"], urgency)

        # Tier 3: allow business_hours availability with accepts_emergencies
        candidates = _availability_relaxed_filter(lawyers, user, jurisdiction_state, parent or practice_area)
        if candidates:
            return _finalize(candidates, "availability_relaxed", ["county", "practice_area", "availability"], urgency)

        # Tier 4: drop language (returns candidates, but agent must confirm verbally)
        candidates = _language_dropped_filter(lawyers, jurisdiction_state, parent or practice_area)
        if candidates:
            return _finalize(candidates, "language_dropped", ["county", "practice_area", "availability", "language"], urgency)

    return MatchResult(lawyers=[], tier_used="escalate", relaxed_constraints=[], escalation_reason="no_match_in_network")

def _finalize(candidates: list[Lawyer], tier: str, relaxed: list[str], urgency: str) -> MatchResult:
    ranked = _score_and_sort(candidates, urgency)
    # FR-20: quality floor for urgent transfers
    if urgency == "urgent" and ranked and ranked[0].rating < QUALITY_FLOOR["urgent_min_rating"]:
        return MatchResult(
            lawyers=[], tier_used="escalate", relaxed_constraints=relaxed,
            escalation_reason="below_quality_floor",
        )
    n_results = 1 if urgency == "urgent" else 5
    return MatchResult(lawyers=ranked[:n_results], tier_used=tier, relaxed_constraints=relaxed)

# ... _strict_filter, _availability_relaxed_filter, _language_dropped_filter, _score_and_sort follow
```

**Unit tests in `tests/test_matcher.py`** — at minimum:

1. Alameda + DUI + urgent → returns Sarah, `tier_used = "strict"`
2. Mendocino + DUI + urgent → returns David Park, `tier_used = "area_broadened"`, `relaxed = ["county", "practice_area"]`
3. Modoc + drug_offense + urgent → returns empty, `tier_used = "escalate"`, `escalation_reason = "below_quality_floor"`
4. Cook + divorce + non_urgent, $400/hr budget → returns Mark Davis at top, sorted by score
5. Out-of-jurisdiction state with no lawyers → returns empty, `tier_used = "escalate"`, `escalation_reason = "no_match_in_network"`

These tests are the safety net. Run `pytest tests/test_matcher.py -v` after every change.

### 2.4 `src/tools.py`

**Five** tools as plain Python functions. Each takes typed args and returns a JSON-serializable dict (so they slot directly into Claude tool-use results). The fifth tool, `route_to_public_defender`, was split out from `escalate_to_human` to satisfy PRD FR-9 — unknown callers must route to the static `PUBLIC_DEFENDER_HOTLINE`, not the dispatcher.

```python
import json, hashlib
from pathlib import Path
from .schemas import User, Lawyer, MatchResult
from .matcher import match_lawyers as _match
from .agentphone_client import send_sms, transfer_instruction
from .config import DISPATCHER_PHONE

_USERS = [User(**u) for u in json.loads(Path("data/users.json").read_text())]
_LAWYERS = [Lawyer(**l) for l in json.loads(Path("data/lawyers.json").read_text())]

def lookup_user(*, name: str | None, dob: str | None, phone_number: str | None) -> dict:
    # 1) caller-ID match first
    if phone_number:
        for u in _USERS:
            if phone_number in u.phone_numbers:
                return {"found": True, "user_id": u.id, "name": u.name, "match_method": "caller_id"}
    # 2) name + DOB fallback
    if name and dob:
        for u in _USERS:
            if u.name.lower() == name.lower() and u.date_of_birth == dob:
                return {"found": True, "user_id": u.id, "name": u.name, "match_method": "name_dob"}
    return {"found": False}

def match_lawyers(*, user_id: str, jurisdiction_state: str, jurisdiction_county: str | None,
                  practice_area: str, urgency: str) -> dict:
    user = next(u for u in _USERS if u.id == user_id)
    result: MatchResult = _match(
        _LAWYERS, user=user,
        jurisdiction_state=jurisdiction_state, jurisdiction_county=jurisdiction_county,
        practice_area=practice_area, urgency=urgency,
    )
    return result.model_dump()

def connect_to_lawyer(*, lawyer_id: str, caller_name: str, brief: str) -> dict:
    lawyer = next(l for l in _LAWYERS if l.id == lawyer_id)
    sms_text = f"Better Call Ron: {brief}"
    # NFR-6: SMS failure must NOT block the cold transfer — wrap and surface a flag instead.
    sms_sent = True
    try:
        send_sms(to=lawyer.phone, text=sms_text)
    except Exception:
        sms_sent = False
    return {
        "transfer": transfer_instruction(to=lawyer.phone),
        "lawyer_name": lawyer.name,
        "sms_sent": sms_sent,
        "brief": brief,
        "caller_name": caller_name,
    }

def escalate_to_human(*, reason: str) -> dict:
    return {"transfer": transfer_instruction(to=DISPATCHER_PHONE), "reason": reason}

def route_to_public_defender(*, reason: str) -> dict:
    # PRD FR-9: unknown callers go to the static PD hotline, NOT the dispatcher.
    return {"transfer": transfer_instruction(to=PUBLIC_DEFENDER_HOTLINE), "reason": reason}
```

---

## Phase 3 — Server, webhook, Claude loop (120 min)

**Goal:** end-to-end conversational agent reachable from a phone, no live transfer yet.

### 3.1 `src/agentphone_client.py`

Thin wrapper around the SDK with three functions we control. **Real SDK method names verified during build** (the earlier draft of this plan guessed at them):

- `client.messages.send(agent_id, to_number, body=...)` — note `send`, not `create`; the payload field is `body`, not `text`. The SDK derives the From-number from `agent_id`, so we don't pass `from_number` explicitly.
- `client.agents.update(agent_id, transfer_number=...)` — used for the Scenario B `transferNumber` workaround.
- `verify_webhook(body, signature, secret)` — module-level function from the `agentphone` package; **raises `WebhookVerificationError` on failure rather than returning bool**. Signature header value is formatted as `sha256=<hexdigest>`.

```python
from typing import Optional
from agentphone import AgentPhone, WebhookVerificationError, verify_webhook
from . import config

_client: Optional[AgentPhone] = None

def _get_client() -> AgentPhone:
    global _client
    if _client is None:
        _client = AgentPhone(api_key=config.require_env("AGENTPHONE_API_KEY"))
    return _client

def send_sms(to: str, text: str) -> None:
    _get_client().messages.send(
        agent_id=config.require_env("AGENTPHONE_AGENT_ID"),
        to_number=to,
        body=text,
    )

def transfer_instruction(to: str) -> dict:
    # Phase 0.4 discovery dictates whether this is enough. If Scenario B (per-agent
    # only), uncomment the agents.update call before returning:
    #   _get_client().agents.update(config.AGENTPHONE_AGENT_ID, transfer_number=to)
    return {"action": "transfer", "transferNumber": to}

def verify_signature(body: bytes, signature: str, timestamp: Optional[str] = None) -> bool:
    secret = config.require_env("AGENTPHONE_WEBHOOK_SECRET")
    try:
        verify_webhook(body, signature, secret)
    except WebhookVerificationError:
        return False
    return True
```

### 3.2 `src/prompts.py`

The system prompt. Encodes every flow rule from PRD §6 into natural language Claude can follow. Keep it under ~2K tokens — terse and rule-shaped, not prose.

Skeleton:

```python
SYSTEM_PROMPT = """\
You are Ron, the AI concierge for Better Call Ron — a service that connects people \
to the right attorney in legal emergencies. You are NOT a lawyer. You never give legal advice.

# Your job, one turn at a time
- Listen for the caller's words. Decide what to say next, in one short sentence (≤ 12 words).
- Use tools to look up the caller, find a lawyer, send the SMS brief, transfer the call, \
  or escalate to a human dispatcher.

# Opening
Your first utterance, always:
  "This is Ron. Are you safe right now?"

# Routing
- Caller indicates danger / arrest / custody / not safe → URGENT path.
- Caller indicates calm / planning → NON-URGENT path.

# Identity
- The webhook payload includes the caller's phone number. Call lookup_user first with that number.
- If found → continue.
- If not found → ask: "I don't recognize this number. What's your full name and date of birth?"
- Call lookup_user with the name + DOB.
- If still not found → say: "I can't find an account, but I can still help. I'm connecting you to \
  the local public defender hotline. Stay on the line." Then call escalate_to_human(reason="unknown_caller").

# URGENT triage (in order, one question per turn)
1. "Where are you being held?"     -> jurisdiction state + county
2. "What's the charge, if you know?" -> practice area (use the controlled vocab: dui, drug_offense, ...)
3. "Have you seen a judge yet?"    -> court status (no = pre-arraignment, urgent)

Then call match_lawyers(urgency="urgent", ...).

# NON-URGENT triage
1. "What kind of legal help do you need?"  -> practice area
2. "What state?"                            -> jurisdiction
3. "Is this urgent today, or planning ahead?"  -> urgency

Then call match_lawyers(urgency="non_urgent", ...).

# Match readback (URGENT)
- If tier_used == "strict" and rating >= 3.0 and years_experience >= 3:
  "I found {name}, {practice_area} in {county}, available now. Connect?"
- If tier_used != "strict": prepend relaxation narration (see RULES).
- If years_experience < 3: "Three years in practice — connect, or want me to look further?"
- NEVER mention pricing on urgent calls.

# Match readback (NON-URGENT)
- Read top 3-5 with pricing. Flag any rating < 3.0 verbally.
- Wait for the caller to pick by name. Then connect.

# Connecting
1. Confirm caller said yes.
2. Say: "Texting {name} now. Connecting in three seconds. Stay on the line."
3. Call connect_to_lawyer(lawyer_id, caller_name, brief).
4. The tool's `transfer` field will be applied to your next webhook response.

# UPL refusal — STRICT
If the caller asks for legal advice ("what should I tell them?", "will I go to jail?", \
"was this legal?", "should I sign this?"), refuse and defer:
  "I can't advise on that. {Lawyer name if matched} will be on the line in under a minute and \
   can answer."
You MAY add procedural cautions: "I'd wait to sign anything until you speak with her."

# Escalation
Caller says "human" / "person" / "real lawyer" / expresses serious frustration → \
call escalate_to_human(reason="caller_requested").
If match_lawyers returns tier_used="escalate" → say:
  "I don't have a strong match in our network right now. I'm connecting you to a dispatcher \
   who will find an attorney for you. Stay on the line." Then call escalate_to_human.

# Style
- Sentences ≤ 12 words.
- One question per turn.
- No legal jargon ("arraigned" → "seen a judge yet"; "charges" → "what they said you did").
- No filler. No "I understand." No "I'm sorry to hear that." The caller has limited time.
"""

RELAXATION_NARRATION = {
    "county_relaxed": "Nobody in {county} right now — going statewide.",
    "area_broadened": "Looking at the broader {parent_area} network.",
    "availability_relaxed": "Checking attorneys on call for emergencies.",
    "language_dropped": "I have someone who can help in English — is that okay?",
}
```

### 3.3 `src/claude_loop.py`

One **async** function: take a webhook payload (the turn's transcript + recent history), run Claude's tool-use loop, return the assistant text to speak. We use `AsyncAnthropic` so the FastAPI webhook handler can `await` the LLM call without blocking the event loop — this matters when multiple call webhooks arrive concurrently.

```python
from anthropic import AsyncAnthropic
from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from .prompts import SYSTEM_PROMPT
from . import tools

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
MAX_ITERATIONS = 8  # cap tool-loop length so a confused model can't burn the webhook timeout

TOOL_DEFS = [
    {
        "name": "lookup_user",
        "description": "Look up a user by phone number (preferred) and/or name + DOB.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string", "description": "E.164 format"},
                "name": {"type": "string"},
                "dob": {"type": "string", "description": "YYYY-MM-DD"},
            },
        },
    },
    {
        "name": "match_lawyers",
        "description": "Find the best-match lawyer(s) for this caller. Returns tier_used metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "jurisdiction_state": {"type": "string", "description": "Two-letter US state"},
                "jurisdiction_county": {"type": "string"},
                "practice_area": {"type": "string"},
                "urgency": {"type": "string", "enum": ["urgent", "non_urgent"]},
            },
            "required": ["user_id", "jurisdiction_state", "practice_area", "urgency"],
        },
    },
    {
        "name": "connect_to_lawyer",
        "description": "SMS-brief the matched lawyer, then return a transfer instruction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lawyer_id": {"type": "string"},
                "caller_name": {"type": "string"},
                "brief": {"type": "string", "description": "One-sentence summary for SMS"},
            },
            "required": ["lawyer_id", "caller_name", "brief"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Cold-transfer to the human dispatcher (DISPATCHER_PHONE). Use when matcher returns tier_used='escalate', caller asks for a human, or any tool errors. NOT for unknown callers — use route_to_public_defender for that.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "route_to_public_defender",
        "description": "Cold-transfer to the static public-defender hotline (PUBLIC_DEFENDER_HOTLINE). Use ONLY when lookup_user returns found=false after both caller-ID and name+DOB lookups (PRD FR-9).",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

TOOL_IMPLS = {
    "lookup_user": tools.lookup_user,
    "match_lawyers": tools.match_lawyers,
    "connect_to_lawyer": tools.connect_to_lawyer,
    "escalate_to_human": tools.escalate_to_human,
    "route_to_public_defender": tools.route_to_public_defender,
}

async def run_turn(messages: list[dict]) -> tuple[str, dict | None]:
    """
    Returns (assistant_text, transfer_instruction_or_None).
    The transfer instruction is set if Claude called connect_to_lawyer,
    escalate_to_human, or route_to_public_defender — and ONLY when the loop
    exits naturally via end_turn. If MAX_ITERATIONS trips we return None for
    the transfer so a stale instruction never fires.
    """
    pending_transfer = None
    text_chunks: list[str] = []
    iterations = 0
    while iterations < MAX_ITERATIONS:
        iterations += 1
        resp = await _client.messages.create(
            model=CLAUDE_MODEL,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFS,
            messages=messages,
            max_tokens=512,
        )
        # Capture any text Claude emitted in this turn even if it ALSO called a
        # tool — otherwise interim narration like "Texting Sarah now..." gets dropped.
        for block in resp.content:
            if block.type == "text" and block.text:
                text_chunks.append(block.text)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    try:
                        result = TOOL_IMPLS[block.name](**dict(block.input))
                    except Exception as exc:
                        result = {"error": str(exc), "tool_name": block.name}
                    if isinstance(result, dict) and "transfer" in result:
                        pending_transfer = result["transfer"]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        combined = " ".join(t.strip() for t in text_chunks if t.strip())
        return combined, pending_transfer

    # Iteration cap hit — discard the pending transfer so we don't blind-fire it.
    fallback = " ".join(t.strip() for t in text_chunks if t.strip()) or "One sec — let me get a dispatcher."
    return fallback, None
```

**Key design note:** the loop accumulates the *full conversation* in `messages` across turns. That's how the agent remembers earlier triage answers. State is per-call; we keep a dict keyed by `call_id` in the server.

### 3.4 `src/server.py`

FastAPI app with the webhook and the transcript WebSocket. Three notable behaviors beyond the earlier draft:

1. **Call-lifecycle events.** AgentPhone emits `agent.call_started` / `call.started` when the line connects (before any transcript), and `agent.call_ended` on hang-up. The server returns the hardcoded Ron opener (`"This is Ron. Are you safe right now?"`) on call-start without invoking Claude, and returns `{}` on call-end so Ron stays silent after hang-up. The opener is also returned on an empty first `agent.message` payload as a defensive fallback for SDKs that skip the dedicated start event.
2. **Per-call asyncio.Lock.** `CALL_LOCKS = defaultdict(asyncio.Lock)`, keyed on `call_id`. The webhook handler holds the lock for the duration of message-list mutation + `run_turn`. Without it, two concurrent webhooks for the same call could interleave `tool_use` / `tool_result` pairs and corrupt the Claude conversation.
3. **Webhook payload key fallback.** The SDK's `WebhookEventData` is SMS-shaped (`from`, `to`, `message`, `conversation_id`). Voice events sometimes use `callId` / `transcript`. The extractors run a fallback chain (`callId` → `conversationId`; `message` → `transcript`). This is an **open question** — verify the real keys on first live call.

```python
import asyncio, json, logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import FileResponse
from . import agentphone_client
from .claude_loop import run_turn
from .transcript_bus import bus

app = FastAPI(title="Better Call Ron")
CALL_STATE: dict[str, list[dict]] = {}
CALL_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

RON_OPENER = "This is Ron. Are you safe right now?"
_CALL_START_EVENTS = {"agent.call_started", "call.started", "agent.call.started"}
_CALL_END_EVENTS   = {"agent.call_ended",   "call.ended",   "agent.call.ended"}

@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-webhook-signature", "")
    if not agentphone_client.verify_signature(raw, sig):
        raise HTTPException(401, "invalid signature")

    event = json.loads(raw)
    name  = event.get("event", "")
    data  = event.get("data", {}) or {}
    call_id = data.get("callId") or data.get("conversationId") or "unknown"

    async with CALL_LOCKS[call_id]:
        if name in _CALL_START_EVENTS:
            return await _emit_opener(call_id)
        if name in _CALL_END_EVENTS:
            CALL_STATE.pop(call_id, None)
            return {}
        if name != "agent.message":
            return {}

        transcript = (data.get("message") or data.get("transcript") or "").strip()
        from_number = data.get("from") or data.get("fromNumber") or ""

        if not transcript:
            # Some SDKs send an empty first agent.message in lieu of a call-start event.
            if call_id not in CALL_STATE:
                return await _emit_opener(call_id)
            return {}

        msgs = CALL_STATE.setdefault(call_id, [])
        first_user_turn = not any(m.get("role") == "user" for m in msgs)
        msgs.append({
            "role": "user",
            "content": f"[caller_phone={from_number}] {transcript}" if first_user_turn else transcript,
        })
        await bus.publish(call_id, {"speaker": "caller", "text": transcript})

        text, transfer = await run_turn(msgs)
        msgs.append({"role": "assistant", "content": text})
        await bus.publish(call_id, {"speaker": "agent", "text": text})

        response: dict = {"text": text}
        if transfer:
            response.update(transfer)
        return response

async def _emit_opener(call_id: str) -> dict:
    msgs = CALL_STATE.setdefault(call_id, [])
    if not msgs:
        msgs.append({"role": "assistant", "content": RON_OPENER})
        await bus.publish(call_id, {"speaker": "agent", "text": RON_OPENER})
    return {"text": RON_OPENER}

@app.websocket("/transcript/{call_id}")
async def transcript_ws(ws: WebSocket, call_id: str):
    await ws.accept()
    async for msg in bus.subscribe(call_id):
        await ws.send_json(msg)

@app.get("/transcript.html")
def transcript_page():
    return FileResponse("public/transcript.html")
```

> **NFR-2 deferral.** The current handler returns plain JSON, not a streaming `NDJSON` response. The filler-chunk masking NFR-2 calls for is **deferred to Phase 4 live testing**: if AgentPhone accepts plain JSON and starts TTS without noticeable buffering, no work is needed. If voice turns feel laggy on tool calls, swap the return value for a `StreamingResponse` that emits an interim `{"text": "One sec, looking now.", "interim": true}` chunk before the final reply.

### 3.5 Smoke test (no phone yet)

```bash
uvicorn src.server:app --reload --port 8000
# In another shell:
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: <correctly signed for the body>" \
  -d '{"event":"agent.message","channel":"voice","data":{"callId":"test_1","transcript":"hello","from":"+15555550001","to":"+15555550000","direction":"inbound"}}'
# Expect: a JSON response with {"text": "This is Ron. Are you safe right now?"}
```

If that works, you're 80% done.

---

## Phase 4 — Connect mechanic (45 min)

**Goal:** SMS brief + cold transfer actually fire on a real call.

### 4.1 Apply Phase 0.4 outcome

Based on the transferNumber discovery:

- **Scenario A** (per-call inline): `agentphone_client.transfer_instruction` returns `{"action": "transfer", "transferNumber": to}`. Done.
- **Scenario B** (per-agent updatable): inside `transfer_instruction`, first call `_client.agents.update(AGENTPHONE_AGENT_ID, transfer_number=to)`, then return `{"action": "transfer"}`. The update API call is synchronous — wait for it to return before responding.
- **Scenario C** (static only): switch to outbound-callback pattern. Instead of transferring, Ron says *"{Lawyer} will call you back in 30 seconds, stay near the phone"*, ends the call, then `_client.calls.create(to_number=lawyer.phone, initial_greeting="<brief>")` dials the lawyer with the brief.

### 4.2 Real-phone test

Place an inbound call from your phone. Trigger the full flow:
1. "I've been arrested" → identify (caller-ID match)
2. "Alameda" → "DUI" → "no" → triage complete
3. Agent says "Texting Sarah, connecting in three seconds"
4. Sarah's phone receives the SMS, then rings
5. Sarah picks up, brief exchange happens

If step 5 fails: check (a) Sarah's number is correctly E.164 in `lawyers.json`, (b) Sarah's phone isn't on DND, (c) AgentPhone outbound-call billing is enabled on your account.

---

## Phase 5 — Live transcript display (45 min)

**Goal:** a webpage that mirrors the call's transcript in real time, on a second screen during the demo.

### 5.1 `src/transcript_bus.py`

Tiny in-process pub/sub. Don't reach for Redis — it's a hackathon.

```python
import asyncio
from collections import defaultdict
from typing import AsyncIterator

class TranscriptBus:
    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, call_id: str, msg: dict):
        for q in self._queues[call_id]:
            await q.put(msg)

    async def subscribe(self, call_id: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[call_id].append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues[call_id].remove(q)

bus = TranscriptBus()
```

### 5.2 `public/transcript.html`

One file, no build step.

```html
<!doctype html>
<meta charset="utf-8">
<title>Better Call Ron — live</title>
<style>
  body { font: 24px/1.4 -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }
  .turn { padding: 12px 18px; margin: 8px 0; border-radius: 12px; max-width: 75%; }
  .caller { background: #e8eaf0; margin-left: auto; }
  .agent  { background: #1f2a44; color: #fff; }
  .speaker { font-size: 12px; opacity: 0.6; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
</style>
<h1 style="text-align:center">Better Call Ron — Live</h1>
<div id="log"></div>
<script>
  const callId = new URLSearchParams(location.search).get("call") || "demo";
  const ws = new WebSocket(`ws://${location.host}/transcript/${callId}`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    const div = document.createElement("div");
    div.className = `turn ${m.speaker}`;
    div.innerHTML = `<div class="speaker">${m.speaker}</div>${m.text}`;
    document.getElementById("log").appendChild(div);
    window.scrollTo(0, document.body.scrollHeight);
  };
</script>
```

### 5.3 Hook up

When the demo starts, before the call comes in, open `http://<ngrok or localhost>/transcript.html?call=<known_call_id>` on the second screen. Each turn streams to the page within ~100ms of speech-to-text completing.

For the demo, the tech operator pre-loads the transcript page; the `call_id` is whatever AgentPhone assigns. Two options:
- Manually copy-paste the call_id when the first webhook fires (slow but simple)
- Make the page subscribe to `*` and auto-detect the active call (more code but smoother)

Go with the first for a hackathon. The operator hits F5 with the new call_id when the call starts.

---

## Phase 6 — Signup mockup slide (15 min)

Open Figma. Use a free iPhone-frame template. Add fields:

- Better Call Ron logo at top
- Name, DOB
- Phone numbers (primary + alt)
- Payment method (just a card-icon placeholder)
- Budget (two fields: max hourly, max retainer)
- Home state + county
- Security word (label only — note it's for the *real* product, skipped in V1)
- Emergency contact

Export PNG, save as `assets/signup-mockup.png`. Drop into a one-slide deck.

---

## Phase 7 — Demo dry run + backup video (30 min)

1. Full run through the custody scenario, recorded screen + audio
2. Full run through the non-urgent scenario
3. Test the UPL refusal explicitly ("what should I tell the cops?")
4. Test the escalation path (call from an unknown unregistered number)
5. Save the cleanest custody run as `assets/backup-demo.mp4` (target ~60 seconds)

Failure-mode rehearsal:
- Kill WiFi mid-demo, switch to hotspot — does ngrok survive?
- Pull the SIM out of Sarah's phone, retry — does the cold transfer error gracefully and escalate?
- Ask Ron "am I going to jail?" — does he refuse cleanly?

---

## Phase 8 — Pitch rehearsal (30 min)

Three full run-throughs of the 2.5-minute pitch with the live demo embedded. See PRD §11 for the structure and the build plan (`~/.claude/plans/hey-so-this-is-noble-squid.md`) for stage choreography.

---

## Local dev workflow

```bash
# Terminal 1: server
source .venv/bin/activate
uvicorn src.server:app --reload --port 8000

# Terminal 2: ngrok tunnel
ngrok http 8000
# Note the https URL. Set WEBHOOK_PUBLIC_URL in .env to this.
# Update AgentPhone agent's webhook URL to <ngrok-url>/webhook.

# Terminal 3: transcript display in browser
open http://localhost:8000/transcript.html?call=<call_id>

# Terminal 4: tail logs
# uvicorn --reload prints tool calls and errors to stdout
```

---

## Testing strategy

After Phases 2, 3, 5 the suite is **31 tests passing** across:

- `tests/test_matcher.py` — covers every cascade tier (strict, county_relaxed, area_broadened, availability_relaxed, language_dropped, escalate), the FR-20 quality floor, the FR-22 county-affinity tiebreaker, and the non-urgent relaxations list (`over_budget`, `statewide`, `practice_area`).
- `tests/test_tools.py` — covers `lookup_user` (caller-ID, name+DOB, no-match), `match_lawyers` return shape, `connect_to_lawyer` SMS-failure passthrough (NFR-6), `escalate_to_human` and `route_to_public_defender` transfer targets.
- `tests/test_claude_loop.py` — async tool-use loop, MAX_ITERATIONS guard, mid-turn text capture, error-to-tool-result propagation.

Run before every commit:

```bash
pytest -v   # ~1s, expect 31 passed
```

Plus integration checkpoints:

- Manual webhook test (Phase 3.5) — confirms the server returns sensible text.
- Live phone test (Phase 4.2) — confirms end-to-end including SMS + transfer.
- Failure-mode rehearsal (Phase 7) — confirms graceful degradation.

---

## Risk log (live)

Maintain this list during build. Cross out as resolved.

- [x] **Phases 2, 3, 5 built and tested — 39 tests passing** (31 original + 8 signature regression).
- [x] **AgentPhone signature scheme — RESOLVED.** SDK v0.6.1's `verify_webhook` is buggy: it hashes only the body, but AgentPhone actually signs `{X-Webhook-Timestamp}.{body}` (Stripe-style). Bypassed the SDK helper; `agentphone_client.verify_signature` now implements the correct HMAC scheme. Locked by `tests/test_signature.py` (8 tests).
- [x] **Webhook URL + secret round-tripped via API.** `set_webhook` returns `Webhook.secret` which matches what AgentPhone signs with. The dashboard UI was stale relative to API state during testing; trust the API.
- [x] **AgentPhone webhook event names observed in the wild:** `agent.message` (per-turn transcript), `agent.call_started` (call connect), `agent.call_ended` (hang-up). Voice payload uses keys: `event`, `channel: "voice"`, `timestamp`, `agentId`, `data.{callId, numberId, from, to, contact, direction, status, transcript}`. Server handles all three event types; transcript flows in `data.transcript` (not `data.message` like SMS).
- [ ] `transferNumber` per-call vs per-agent — **resolve in Phase 0.4 before relying on transfers.** Real SDK call is `client.agents.update(agent_id, transfer_number=...)`. First live transfer attempt will tell us whether AgentPhone honors the inline `{"action": "transfer", "transferNumber": "+1..."}` response shape.
- [ ] **NFR-2 filler-chunk masking — DEFERRED.** Server returns plain JSON today, not NDJSON. If voice turns feel laggy on tool calls in live testing, swap to `StreamingResponse` and emit an interim `{"text": "One sec, looking now.", "interim": true}` chunk.
- [ ] SMS delivery time to Sarah's phone — if > 2s, send earlier in the flow (right after match, before readback).
- [ ] ngrok tunnel survives WiFi swap to hotspot — test in Phase 7.

---

## Demo runbook (Sunday)

**T-60 min:**
- Start server, ngrok, transcript page
- Verify AgentPhone webhook URL points to current ngrok URL
- Place a test call to yourself — full flow runs clean
- Sarah's phone: plugged in, screen on, max volume, DND off, propped facing audience
- Backup video queued in a tab, ready

**T-10 min:**
- Final test call
- Refresh transcript display, confirm WebSocket connected
- Confirm hotspot is online as backup

**Pitch:**
1. Hook (20s) — "You've been arrested..."
2. Live demo (90s) — call placed from unknown phone, full custody flow, watch SMS land
3. Business model (40s) — three bullets
4. Close (10s) — "Built on Agent Phone in a weekend, looking for our first ten partner attorneys"

**If the live demo breaks:** stop talking, say *"We had this filmed in case the venue WiFi got weird"*, play the backup video, continue with the business-model slide. Don't try to debug live.

---

## Reference: cross-doc map

- Product spec: [PRD.md](./PRD.md)
- Stage choreography, pitch script, team roles: `~/.claude/plans/hey-so-this-is-noble-squid.md`
- Memory & context: `~/.claude/projects/-Users-umair-Desktop-AI-Lawyer-Concierge/memory/`
