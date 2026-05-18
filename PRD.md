# Better Call Ron — Product Requirements Document

> *"Better Call Ron"* — a voice-first AI lawyer concierge. Brand name of the service; the agent itself is named **Ron** in the conversation.

**Status:** Working end-to-end as of 2026-05-18 (verified live). Some FRs evolved past the 2026-05-15 draft — see § "What changed since draft" at the end.
**Owner:** Umair
**Last updated:** 2026-05-18
**Required infrastructure:** [AgentPhone](https://agentphone.ai) (YC mandate for "All My Agents" hackathon), plus AgentMail (lawyer-brief delivery) and BrowserUse (dynamic per-case research)

---

## 1. Overview

Better Call Ron is a voice-first AI service that connects people to the right attorney in legal emergencies. The agent introduces itself on calls as **Ron**; the service brand is **Better Call Ron**. Users pre-register an account with their identity, payment method, jurisdiction, budget, and emergency contacts. Later, in a crisis — most acutely a custody/arrest situation — they call a single phone number. An AI agent verifies them (even if they're calling from someone else's phone), conducts a fast triage, selects the best-fit attorney from a curated network, briefs the attorney via SMS, and cold-transfers the live call. End-to-end target: under 90 seconds from pickup to attorney on the line.

The headline scenario is **"one phone call from jail"** — the moment when the caller is most stressed, on the worst line, with the least time, and the most at stake. The product is designed for that case first; every other use case (planning ahead, civil/divorce shopping, immigration consult) is a degraded-urgency variant of the same flow.

---

## 2. Problem

When a person needs a lawyer urgently — especially after an arrest — they typically have:

- No memorized attorney number
- A single phone call from custody, often on a payphone or jail phone
- High stress, limited cognition, possibly impaired speech
- No way to search, browse, or compare lawyers in real time
- Family members who, when called, must improvise a search at 2 AM

The default outcomes are: (a) take an over-burdened public defender, (b) burn the one call on a relative who then loses hours finding an attorney, or (c) sit in a cell longer than necessary. Existing "find a lawyer" products (Avvo, LegalZoom, lawyer.com directories) assume the user is comfortable, internet-connected, and shopping — none of which holds in custody.

---

## 3. Goals & non-goals

### Goals (must achieve)

1. Caller can be identified and authenticated even when calling from a phone not on their profile.
2. Triage extracts jurisdiction, practice area, and urgency in under 30 seconds.
3. The system selects a deterministic, defensible best-match attorney from the network.
4. The attorney is briefed on the situation *before* answering the call.
5. The caller is connected to the attorney within 90 seconds of call pickup.
6. The agent strictly refuses to give legal advice (UPL compliance).
7. The agent adapts UX to urgency: urgent calls skip pricing; non-urgent calls comparison-shop.
8. The system refuses to transfer an urgent caller to any attorney below the network's quality floor; in that case it routes to a human dispatcher rather than connecting a poor-fit lawyer. A bad transfer is worse than no transfer because the caller has one phone call.

### Non-goals (for V1 / hackathon)

- Building the signup web application (referenced in pitch via mockup only)
- Real Stripe payment authorization (mocked token field on user profile)
- Real lawyer onboarding and vetting workflow (seeded JSON only)
- Multi-language support beyond English (data model supports it; UX only English)
- Geographic coverage outside US/Canada (AgentPhone limitation)
- Native mobile app
- Lawyer-side dashboard, scheduling, or matter-management
- Recording / archiving call audio for compliance
- Real warm transfer / 3-way bridging (AgentPhone does not support it; SMS-brief substitutes)

---

## 4. Target users

### Primary persona — "The caller in crisis"

- Adult who has pre-registered with the service (typically at a calm prior moment)
- Currently in legal emergency: arrest, detention, ICE custody, restraining-order service
- May be calling from a jail phone, payphone, family member's phone, or any number not on their profile
- Stressed, possibly intoxicated, possibly injured, possibly on a recorded line
- Has limited time on the call (collect-call clock, jail-phone time limits)

### Secondary persona — "The shopper"

- Adult who needs legal help non-urgently (planning a divorce, drafting a will, consulting on a business matter)
- Calling from their own phone in a calm setting
- Comparison-shopping on price and fit
- Comfortable with longer, more conversational agent interaction

### Tertiary persona — "The dispatcher" (operations)

- Human operator who receives escalated calls when the agent fails or the caller asks for a human
- In V1 demo, this is the founder's phone

### The lawyers (supply side)

- Licensed attorneys in the network, pre-vetted, with declared practice areas, jurisdictions, rates, availability, and willingness to accept emergency calls
- Receive SMS briefs immediately before transferred calls

---

## 5. User scenarios

### 5.1 Custody scenario (primary / demo)

```
Caller (from registered phone) -> dials concierge number
Agent: "Hey, this is Ron. How can I help you?"
Caller: "I just got arrested for DUI."
Agent (identity already resolved from caller-ID): "Hey Umair. Where are you being held?"
Caller: "Tenderloin Police Station, San Francisco."
Agent: "What's the charge, if you know?"
Caller: "DUI."
Agent: "Have you seen a judge yet?"
Caller: "No."
Agent (BRIDGE — text + match_lawyers tool call in same turn):
       "One sec — finding a DUI lawyer in San Francisco."
[matcher cascade: county_relaxed -> Haris Jalal, criminal_defense/dui, Alameda]
Agent: "Nothing in San Francisco. I found Haris Jalal, DUI in Alameda, available now.
        Want me to get Haris on the line?"
Caller: "Yes."
Agent (CO-NARRATE — text + connect_to_lawyer + notify_emergency_contact in same turn):
       "Briefing Haris now. Texting Sara to let her know. Connecting in three seconds.
        Stay on the line."
[Email sent to Haris with brief via AgentMail.]
[SMS sent to Sara (caller's emergency contact) from the agent's SMS line.]
[Webhook response to AgentPhone: {"text": "Briefing Haris now...", "action": "transfer"}.
 Agent record's transfer_number was set to Haris's phone via API call right before.]
[AgentPhone cold-transfers caller's leg to Haris's number.]
```

### 5.2 Shopper / non-urgent scenario

Two-step: research email FIRST (always), then ask if they also want a lawyer.

```
Caller (from registered phone) -> dials concierge number
Agent: "Hey, this is Ron. How can I help you?"
Caller: "I'm thinking about filing for divorce."
Agent: "Hey Umair. What state?"
Caller: "Illinois."
Agent: "In one sentence, what's going on?"
Caller: "My wife and I are separating and I need to file for divorce."
Agent (CO-NARRATE — text + research_and_email in same turn):
       "Looking into Illinois divorce for you now. I'll email you the resources
        in about a minute. Want me to also find you a lawyer?"
[Background: BrowserUse runs a per-case research task, emails the resource pack
 via AgentMail in 15-60s with state AG, court self-help, state bar, statewide
 legal aid, and relevant statutes.]
Caller: "Yeah."
Agent (BRIDGE): "One sec — finding a divorce lawyer in Illinois."
[match_lawyers(urgency="non_urgent") -> 3-5 IL divorce lawyers]
Agent: "Here are three options:
        1. Ibrahim Kamal, divorce, $250 consult.
        2. Lisa Wong, divorce, $300 consult.
        3. Priya Mehta, divorce, $500/hr.
        Who do you want to go with?"
Caller: "Ibrahim."
Agent (CO-NARRATE): "Briefing Ibrahim now. Connecting in three seconds. Stay on the line."
[Email to Ibrahim + cold transfer.]
```

If the caller declines the lawyer ("No, I'll read first") → Ron fires `end_call(reason="caller_done")` with "Alright, good luck. Bye." The research email still arrives in their inbox 30s later.

### 5.3 Unknown-caller fallback

```
Caller (unknown number, no matching account) -> dials concierge number
Agent: triage proceeds normally, but identity lookup fails
Agent: "I can't find an account for you, but I can still help.
        I'm connecting you to the local public defender hotline.
        Stay on the line."
[Agent invokes route_to_public_defender; cold transfer to PUBLIC_DEFENDER_HOTLINE.]
```

### 5.4 Legal-advice refusal

```
Caller: "What should I tell the cops?"
Agent: "I can't advise on that. Sarah will be on the line in under a minute and she can answer.
        I'd wait to sign anything until you speak with her."
```

### 5.5 Human escalation

```
Caller: "I want to talk to a real person."
Agent: "Connecting you with a dispatcher now."
[Cold transfer to dispatcher phone.]
```

### 5.6 Relaxation cascade (urgent, no local match)

```
Caller (from a Mendocino County jail phone) -> dials concierge number
Agent: "This is Ron. Are you safe right now?"
Caller: "No, I was arrested."
Agent: [identity verified via name + DOB]
Agent: "Where are you being held?"
Caller: "Mendocino County."
Agent: "What's the charge?"
Caller: "DUI."
Agent: "Have you seen a judge yet?"
Caller: "No."
[Matcher: tier 0 strict search returns zero — no DUI lawyer in Mendocino with availability=now.
 Tier 1 county_relaxed: still zero in CA with DUI specifically.
 Tier 2 area_broadened: dui -> criminal_defense, finds 2 statewide. Highest rating 4.2.
 tier_used = "area_broadened", relaxed_constraints = ["county", "practice_area"]]
Agent: "Nobody in Mendocino right now — going statewide with criminal defense.
        I found David Park, criminal defense, rated 4.2, fifteen years in practice. Connect?"
Caller: "Yes."
[SMS sent to David Park: "Better Call Ron: Umair Usmani, DUI arrest in Mendocino County,
                         not yet arraigned, retainer authorized. Connecting now."]
[Cold transfer initiated to David Park's number.]
```

### 5.7 Quality-floor escalation (urgent, only weak matches)

```
Caller (from a small-county jail phone) -> dials concierge number
Agent: "This is Ron. Are you safe right now?"
Caller: "No, I'm in jail."
Agent: [identity verified]
Agent: "Where are you being held?"
Caller: "Modoc County."
Agent: "What's the charge?"
Caller: "Drug possession."
Agent: "Have you seen a judge yet?"
Caller: "No."
[Matcher: tier 0 strict -> zero. Tier 1 county -> zero.
 Tier 2 area -> 1 result, rating 2.6. Below FR-20 quality floor of 3.0.
 tier_used = "escalate", reason = "below_quality_floor"]
Agent: "I don't have a strong match in our network for you right now.
        I'm connecting you to a dispatcher who will find an attorney for you directly.
        Stay on the line."
[Cold transfer to dispatcher phone. Dispatcher takes over and dials attorneys manually.]
```

---

## 6. Functional requirements

### 6.1 Telephony

- **FR-1:** System receives inbound voice calls on a provisioned AgentPhone number (US/Canada).
- **FR-2:** System receives transcribed user utterances via webhook on each turn.
- **FR-3:** System responds with streamed NDJSON text; AgentPhone synthesizes TTS.
- **FR-4:** System supports barge-in (caller can interrupt agent mid-utterance).
- **FR-5:** System initiates outbound SMS to lawyer phone numbers via AgentPhone.
- **FR-6:** System initiates cold transfer of the active inbound call to an arbitrary phone number determined at runtime.

### 6.2 Identity & authentication

- **FR-7:** When `from` phone number matches `phone_numbers[]` on a user profile, that user is automatically authenticated.
- **FR-8:** When `from` phone number does not match, agent prompts for full name and date of birth, performs case-insensitive name match with date-of-birth equality.
- **FR-9:** When no user is identified after the verbal challenge, agent invokes the `route_to_public_defender` tool, which cold-transfers to the static `PUBLIC_DEFENDER_HOTLINE` number. This is a separate tool from `escalate_to_human` (which routes to the dispatcher); unknown callers must go to the public-defender hotline, not the dispatcher.

### 6.3 Triage

- **FR-10:** Agent's opening utterance is the concierge greeting: *"Hey, this is Ron. How can I help you?"* (Earlier draft used a "are you safe?" safety-check opener; changed to concierge tone because Better Call Ron is a marketplace, not a 911 service. Urgency is inferred from the caller's own words, not asked up front.)
- **FR-11:** Agent classifies the call as **urgent** or **non-urgent** silently from the caller's first utterance — keywords like "arrested", "in jail", "in custody" → urgent; "thinking about", "planning", "looking for" → non-urgent. If genuinely ambiguous after the first turn, agent asks ONCE: *"Are you in trouble right now, or planning ahead?"*
- **FR-12:** Urgent path: agent collects location (→ jurisdiction), charge (→ practice area), and court status (*"Have you seen a judge yet?"*). One question per turn. Skip any slot the caller already filled in their opening.
- **FR-13:** Non-urgent path: agent collects practice area, state, and a one-sentence situation summary. ALWAYS fires `research_and_email` first (per-case BrowserUse research → email), then asks if the caller also wants to be matched with a lawyer. Only if yes → `match_lawyers` + readback + `connect_to_lawyer`.
- **FR-14:** Agent does not ask about budget at call time. Budget is read from the user profile.

### 6.4 Matching

Matching runs in four stages: **strict hard filters → relaxation cascade (if zero) → weighted score → quality floor**. The matcher returns the chosen lawyer(s) along with metadata describing which tier produced the result, so the agent can narrate honestly to the caller.

- **FR-15:** Matching is deterministic. No LLM in the ranking path. Rationale: demo predictability, defensibility ("why was I matched with this lawyer?" must have a clean rules answer), and sub-millisecond latency.

- **FR-16:** Strict hard filter constraints (tier 0):
  - Jurisdiction state must match; county is preferred but not required.
  - Practice area must be in lawyer's `practice_areas[]`.
  - For urgent calls: `availability_status = "now"` AND `accepts_emergencies = true`.
  - Language: if user's `preferred_language` is non-English, must appear in lawyer's `languages[]`.
  - Budget (**non-urgent calls only**): `hourly_rate ≤ user.budget_max_hourly` OR `typical_retainer ≤ user.budget_max_retainer`. Urgent calls skip the budget filter entirely.

- **FR-17:** Relaxation cascade for **urgent** calls. If tier 0 returns zero candidates, the matcher attempts each tier below in order until one returns ≥ 1 candidate. The matcher relaxes silently; the agent narrates the relaxation to the caller per FR-19.

  | Tier | Relaxation |
  |---|---|
  | 1 | Drop county requirement (statewide search) |
  | 2 | Broaden practice area to parent category (e.g., `dui` → `criminal_defense`) |
  | 3 | Allow `availability_status = "business_hours"` provided `accepts_emergencies = true` |
  | 4 | Drop language preference (English-only) — **requires verbal caller confirmation before transfer** |
  | 5 | Total fallback → `escalate_to_human` |

- **FR-18:** Relaxation for **non-urgent** calls is never silent. If tier 0 returns < 3 candidates, the matcher returns whatever it has plus the list of *available* relaxations (e.g., `["over_budget", "statewide"]`). The agent offers each relaxation explicitly; the caller must affirmatively consent before any relaxed result is read back or any over-budget lawyer is transferred.

- **FR-19:** Tier disclosure. The matcher returns `tier_used` (one of `"strict"`, `"county_relaxed"`, `"area_broadened"`, `"availability_relaxed"`, `"language_dropped"`, `"escalate"`) and a list of `relaxed_constraints`. The agent must verbally disclose any non-strict tier before transferring. Stock phrasings:
  - County dropped: *"Nobody in {county} right now — going statewide."*
  - Area broadened: *"Looking at the broader {parent_area} network."*
  - Availability relaxed: *"Checking attorneys on call for emergencies."*
  - Language dropped: *"I have someone who can help in English — is that okay?"* (agent must wait for "yes" before transferring)

- **FR-20:** **Quality floor for urgent transfers.** A lawyer must have `rating ≥ 3.0/5.0` to be auto-transferred on an urgent call. If, after the relaxation cascade, the highest-rated surviving candidate has `rating < 3.0`, the matcher returns `tier_used = "escalate"` and the agent invokes `escalate_to_human` instead of transferring.

  **Rationale:** The caller in custody has *one* phone call. Transferring them to a sub-3.0 attorney burns that call on a poor outcome with no recourse — they cannot try again. A human dispatcher can hunt outside the network, dial multiple attorneys in parallel, or escalate to a senior partner; the AI cannot. The dispatcher is the correct backstop, not a low-quality referral.

- **FR-21:** Weak-but-passing flag (urgent). If the matched lawyer passes the rating floor (≥ 3.0) but has `years_experience < 3`, the agent flags the experience verbally and offers to keep looking. See FR-23 readback rule.

- **FR-22:** Score function. Within the candidate set that survives filters and cascade:
  - Urgent → maximize `(availability_weight × availability_score) + (experience_weight × years_experience) + (county_affinity_weight × serves_caller_county)`. `serves_caller_county` is 1.0 if the lawyer's `jurisdictions[].counties` includes the caller's county, else 0.0. Rationale: in custody matters a local lawyer can physically appear at the courthouse faster, so a 4.8★/12yr lawyer in the caller's county should beat a 4.2★/15yr lawyer in a different county.
  - Non-urgent → maximize `(rating × rating_weight) − (hourly_rate × cost_weight)`.

  Result count: urgent → 1 result; non-urgent → up to 5.

### 6.5 Match readback (UX-adaptive)

- **FR-23:** Urgent readback. Single-lawyer presentation, no pricing mentioned. Base format: *"I found {name}, {practice area} in {county}, available now. Connect?"*

  Additions per matcher metadata:
  - If `tier_used ≠ "strict"`, the relaxation narration (per FR-19) precedes the readback. Example: *"Nobody in Alameda right now — I have Sarah Chen statewide. Criminal defense, available now. Connect?"*
  - If matched lawyer has `years_experience < 3` (FR-21), agent flags this and offers to keep looking before transferring: *"Mike Patel, criminal defense, Alameda — three years in practice. Connect, or want me to look further?"*

- **FR-24:** Non-urgent readback. Top 3-5 lawyers with name, practice area, and either hourly rate or flat consult rate. Per FR-18, the agent presents only within-strict-constraint matches first, then offers any relaxed options explicitly.

  Additions:
  - If any presented lawyer has `rating < 3.0`, agent flags the rating verbally when reading: *"Mike Patel, $300/hr, rated 2.8 stars — want to skip him?"* No hard floor in non-urgent mode; the caller has agency to pick anyway.
  - If results required a budget or jurisdiction relaxation, agent says: *"Nobody in {strict criteria} — I have {N} options outside your {budget|county}. Want to hear them?"* Wait for affirmative consent before reading.

- **FR-25:** Navigation. Caller can respond *"next"*, *"someone else"*, *"cheaper"*, or *"someone more experienced"* on either path to advance through alternatives. On non-urgent, *"cheapest"* re-sorts the surviving candidates by ascending hourly rate.

### 6.6 Connection mechanic

- **FR-26:** Before initiating transfer, agent calls `connect_to_lawyer` tool which:
  1. Sends an **email** (not SMS) to the matched lawyer's address via AgentMail with caller name, jurisdiction, practice area, urgency level, and (urgent only) court status. Stock body:
     > *"{caller name}, {practice area} matter in {jurisdiction}. {Court status if urgent}. Retainer authorized."*
  2. Sets the AgentPhone agent record's `transfer_number` field to the lawyer's phone via `c.agents.update(...)` API call. AgentPhone reads the destination from this field at bridge time.
  3. Returns `{"transfer": {"action": "transfer"}}` (no `transferNumber` field — AgentPhone uses the agent record).
- **FR-27:** Agent's webhook response is `{"text": "...", "action": "transfer"}` ONLY. **Do NOT include a `transferNumber` key in the response** — undocumented per AgentPhone's spec, observed to cause silent bridge drops. The destination comes from the agent record (FR-26 step 2).
- **FR-28:** Agent's spoken line immediately before transfer is canonical: *"Briefing {name} now. Connecting in three seconds. Stay on the line."* On URGENT calls where the caller has an emergency contact on file, this is bundled in the SAME turn with a `notify_emergency_contact` tool call and an additional clause: *"Briefing {name} now. Texting {contact name} to let her know. Connecting in three seconds. Stay on the line."*
- **FR-28a:** **`notify_emergency_contact` tool (URGENT-only).** When the caller's `# Caller identity` block lists one or more `emergency_contacts`, the agent fires `notify_emergency_contact(user_id, message)` in the SAME response as `connect_to_lawyer`. Sends SMS (or iMessage when the line is iMessage-capable) to each contact. Body: *"Hi, this is Ron from Better Call Ron. {caller} was just connected with attorney {lawyer name} on an urgent matter and asked me to text you. You'll hear from them as soon as they can call."* Skipped on non-urgent calls.

### 6.7 UPL guardrails

- **FR-29:** Agent must refuse all questions asking for legal advice, prediction, or characterization. Refusal phrase: *"I can't advise on that. {Lawyer name} will be on the line in under a minute and she can answer."*
- **FR-30:** Agent may proactively volunteer procedural cautions that are not legal advice. Example: *"I'd wait to sign anything until you speak with her."*
- **FR-31:** Agent must not characterize the legal situation. Use neutral facts only ("DUI charge") not legal characterization ("you've been charged with a felony").

### 6.8 Human fallback

The agent has two distinct "give up" tools and they route to different numbers:

| Tool | Destination | When |
|---|---|---|
| `escalate_to_human` | `DISPATCHER_PHONE` | Caller asks for a human; matcher returns `tier_used = "escalate"`; any tool errors out |
| `route_to_public_defender` | `PUBLIC_DEFENDER_HOTLINE` | Unknown caller (FR-9) — `lookup_user` returns `found=false` after both caller-ID and name+DOB lookups |

- **FR-32:** At any turn, if the caller says any of {"human", "person", "operator", "real lawyer right now"} or expresses frustration, agent invokes `escalate_to_human` and cold-transfers to the configured dispatcher number.
- **FR-33:** Agent invokes `escalate_to_human` whenever the matcher returns `tier_used = "escalate"`. This occurs in three cases: (a) zero candidates after the full relaxation cascade, (b) urgent call where the top surviving candidate falls below the 3.0 rating floor (FR-20), (c) caller declines a language-dropped match (FR-19, tier 4).

### 6.9 Observability

- **FR-34:** Each agent turn is broadcast to a WebSocket channel for the live transcript display.
- **FR-35:** Tool calls and their results are logged to stdout with timestamps.

---

## 7. Non-functional requirements

### 7.1 Performance

- **NFR-1:** Each webhook turn returns first NDJSON chunk in ≤ 1500 ms in the median case, ≤ 2500 ms in the 95th percentile.
- **NFR-2:** For tool-using turns where Claude requires > 1500 ms, agent must emit a filler NDJSON chunk (`{"text": "One sec, looking now.", "interim": true}`) within 800 ms to mask latency.
- **NFR-3:** SMS to lawyer arrives at lawyer's phone within 2 seconds of `connect_to_lawyer` tool invocation.
- **NFR-4:** Total call time from inbound pickup to transferred-call ring on lawyer's phone: ≤ 90 seconds for the canonical custody scenario.

### 7.2 Reliability

- **NFR-5:** Webhook handler must complete within AgentPhone's 30-second default timeout.
- **NFR-6:** Service must degrade gracefully. The matcher's relaxation cascade (FR-17) and quality floor (FR-20) ensure no urgent caller is transferred to a poor-fit attorney; any unrecoverable case routes to `escalate_to_human` (FR-33). On tool errors: if SMS fails, still attempt cold transfer; if cold transfer fails, escalate to human dispatcher.
- **NFR-7:** A pre-recorded backup demo video must be ready for stage if the live demo fails.

### 7.3 Compliance / safety

- **NFR-8:** Agent must not give legal advice in any form (see FR-29, FR-30, FR-31).
- **NFR-9:** Agent must not record, store, or transmit call audio outside AgentPhone's pipeline in V1.
- **NFR-10:** Identity verification failures must not leak which users exist (no "user not found"; instead "I can't find an account for you, but I can still help").

### 7.4 Security

- **NFR-11:** API keys (AgentPhone, Anthropic) loaded from `.env`, never committed.
- **NFR-12:** AgentPhone webhook signature (`X-Webhook-Signature` HMAC-SHA256) verified on every inbound request.

---

## 8. System architecture

```
+----------------+      +-----------------------------+
|  Caller phone  |----->|  AgentPhone                 |
+----------------+      |  - Inbound number           |
                        |  - STT (streaming)          |
                        |  - TTS (sub-second start)   |
                        |  - SMS send                 |
                        |  - Cold transfer            |
                        +--------------+--------------+
                                       |
                       webhook (per turn, JSON)
                                       |
                                       v
                        +--------------+--------------+
                        |  Our backend (FastAPI)      |
                        |  - /webhook  POST           |
                        |  - /transcript GET (WS)     |
                        +--------------+--------------+
                                       |
                                       v
                        +--------------+--------------+
                        |  Claude (Anthropic SDK)     |
                        |  - System prompt            |
                        |  - Tool use loop            |
                        |  - Streaming reply          |
                        +--------------+--------------+
                                       |
       +----+------+-----------+------------------+--------+-----------+----------+-----------+
       |    |      |           |                  |        |           |          |           |
       v    v      v           v                  v        v           v          v           v
 lookup_   match_  connect_   research_and_   notify_       end_   escalate_  route_to_public_
   user   lawyers  to_lawyer  email           emergency_    call   to_human   defender
                              (BrowserUse +   contact
                              AgentMail)      (URGENT only;
                                              SMS/iMessage
                                              via AgentPhone)
       |    |        |            |               |          |          |          |
       v    v        v            v               v          v          v          v
   users.  lawyers  AgentMail   BrowserUse +   AgentPhone  AgentPhone  AgentPhone  AgentPhone
   json    .json    email +     AgentMail      messages    hangup      transfer →  transfer →
                    AgentPhone  research                                dispatcher  PD hotline
                    set_xfer    email                                              (FR-9)
                    + action:
                    transfer
```

**Component responsibilities:**

| Component | Responsibility |
|---|---|
| AgentPhone | Audio in/out, transcription, TTS synthesis, SMS, cold transfer execution |
| FastAPI webhook | Webhook ingress, signature verification, conversation state pass-through, WebSocket broadcast |
| Claude (tool-use loop) | Triage extraction, dialogue policy, UPL refusal, tool selection |
| `tools.py` | **Eight tool implementations** as Python functions: `lookup_user`, `match_lawyers`, `connect_to_lawyer`, `research_and_email` (dynamic per-case BrowserUse), `notify_emergency_contact` (URGENT-only SMS to caller's contacts), `end_call`, `escalate_to_human`, `route_to_public_defender` |
| `prompts.py` | System prompt encoding all flow rules + BRIDGE/CO-NARRATE tool-discipline categories |
| `claude_loop.py` | Claude tool-use loop with **ephemeral prompt caching** on system + tools (~8k tokens cache-hit per turn after the first); post-transfer text suppression |
| `agentphone_client.py` | AgentPhone SDK wrapper: voice webhook signature, `set_transfer_number`, `send_sms` (pinned to a specific number via `AGENTPHONE_MESSAGING_NUMBER_ID`) |
| `agentmail_client.py` | AgentMail SDK wrapper: lawyer-brief email send |
| `browseruse_client.py` | BrowserUse SDK wrapper: async `research(task)` for dynamic per-case web research |
| `call_log.py` | Per-call JSON event log (timestamped filenames in `data/calls/`); prior-call history lookup for repeat-caller personalization |
| JSON files | User and lawyer state |
| `transcript.html` | Read-only live transcript for stage projection |

---

## 9. Data model

### 9.1 User

```json
{
  "id": "u_001",
  "name": "Umair Usmani",
  "date_of_birth": "1995-01-01",
  "phone_numbers": ["+14155551234"],
  "payment_method_token": "pm_mock_abc123",
  "emergency_contacts": [
    {"name": "Sara Usmani", "relationship": "spouse", "phone": "+14155559876"}
  ],
  "budget_max_hourly": 500,
  "budget_max_retainer": 5000,
  "preferred_language": "en",
  "home_jurisdiction": {"state": "CA", "county": "Alameda"},
  "notes": ""
}
```

### 9.2 Lawyer

```json
{
  "id": "l_001",
  "name": "Sarah Chen",
  "firm": "Chen Defense Law",
  "bar_state": "CA",
  "practice_areas": ["criminal_defense", "dui"],
  "jurisdictions": [
    {"state": "CA", "counties": ["Alameda", "Contra Costa"]}
  ],
  "hourly_rate": 450,
  "flat_consult_rate": null,
  "typical_retainer": 2500,
  "availability_status": "now",
  "accepts_emergencies": true,
  "languages": ["en"],
  "phone": "+14155557777",
  "years_experience": 12,
  "rating": 4.8,
  "notes": "Available 24/7 for emergencies"
}
```

**Field semantics:**

- `rating` — internal curated quality score on a 1.0–5.0 scale, set during lawyer onboarding by Better Call Ron operations. Composite of: bar standing, prior-engagement outcomes (when available), responsiveness during vetting, and references from existing network lawyers. **Not** a scrape of public review-site ratings (Avvo/Yelp/Google). FR-20's 3.0 floor is calibrated against this internal scale.
- `years_experience` — years since bar admission, not years at the current firm.
- `availability_status` — `"now"` means reachable within 5 minutes; `"business_hours"` means reachable Mon-Fri 9-6 local; `"unavailable"` excludes from all matching.
- `accepts_emergencies` — willing to take a call between 11 PM and 7 AM local, or on weekends.
- `flat_consult_rate` — null if lawyer does not offer flat consults; otherwise dollar amount for an initial consultation.

### 9.3 Practice-area vocabulary (hierarchical)

Practice areas are organized as a two-level tree: **parents** (broad categories) and **children** (specific sub-areas). The matcher's relaxation cascade (FR-17 tier 2) broadens a child to its parent.

```python
PRACTICE_AREA_PARENTS = {
    # Parent categories — also valid as practice areas in their own right
    "criminal_defense": None,
    "family": None,
    "immigration": None,
    "civil": None,
    "business": None,
    "estate": None,
    "employment": None,
    "personal_injury": None,
    "landlord_tenant": None,

    # Child sub-areas — broaden to the parent when relaxing
    "dui": "criminal_defense",
    "drug_offense": "criminal_defense",
    "assault": "criminal_defense",
    "domestic_violence": "criminal_defense",
    "divorce": "family",
    "custody": "family",
    "immigration_detention": "immigration",
    "asylum": "immigration",
}
```

Lawyers may declare both child and parent areas in their `practice_areas[]` — a criminal defense attorney who specializes in DUI lists `["criminal_defense", "dui"]`. The matcher prefers child-area matches at tier 0, then falls back to parent matches at tier 2.

### 9.4 Conversation turn (broadcast to transcript WS)

```json
{
  "callId": "call_abc123",
  "ts": "2026-05-17T18:32:01.456Z",
  "speaker": "caller" | "agent",
  "text": "..."
}
```

### 9.5 Score-function configuration

Constants used by the score function (FR-22). Defined in `config.py` so they can be tuned without code edits.

```python
SCORE_WEIGHTS = {
    "urgent": {
        "availability_weight": 10.0,    # "now" availability dominates
        "experience_weight": 0.5,       # years_experience as tiebreaker
        "county_affinity_weight": 5.0,  # local lawyer can physically appear faster — geography matters in custody
    },
    "non_urgent": {
        "rating_weight": 20.0,          # rating × 20 dominates (max 100)
        "cost_weight": 0.1,             # dollars-per-hour as a small drag (raised from 0.05 so a $400/hr lawyer with the same rating loses ground)
    },
}

QUALITY_FLOOR = {
    "urgent_min_rating": 3.0,         # FR-20 hard floor
    "experience_flag_threshold": 3,   # FR-21 verbal flag if years_experience < this
    "non_urgent_rating_flag_threshold": 3.0,  # FR-24 verbal flag if below this
}

RELAXATION_TIERS = [
    "strict",
    "county_relaxed",
    "area_broadened",
    "availability_relaxed",
    "language_dropped",
    "escalate",
]
```

---

## 10. External dependencies

### 10.1 Software dependencies

| Dependency | Purpose | Required version / notes |
|---|---|---|
| AgentPhone | Telephony, SMS, transfer | Python SDK (`pip install agentphone`); REST API |
| Anthropic Claude | LLM brain (tool use) | Claude Sonnet 4.6 or Opus 4.7 via Python SDK |
| Python | Runtime | 3.11+ |
| FastAPI | HTTP server | latest stable |
| uvicorn | ASGI server | latest stable |
| ngrok (or equivalent) | Tunnel local webhook to public URL so AgentPhone can reach it | Free tier sufficient for demo |

### 10.1 Software dependencies (updated)

| Dependency | Purpose | Required version / notes |
|---|---|---|
| AgentPhone | Telephony, SMS/iMessage, transfer | Python SDK (`pip install agentphone`); REST API |
| AgentMail | Lawyer-brief email | Python SDK (`pip install agentmail`) |
| BrowserUse | Per-case dynamic legal research | Python SDK (`pip install browser-use-sdk`) — `AsyncBrowserUse` |
| Anthropic Claude | LLM brain (tool use + prompt caching) | Claude Sonnet 4.6 default; Opus 4.7 fallback |
| Python | Runtime | 3.11+ |
| FastAPI / uvicorn | HTTP server | latest stable |
| ngrok (or equivalent) | Tunnel local webhook to public URL so AgentPhone can reach it | Free tier sufficient for demo |

### 10.2 Configuration values (`.env`)

| Variable | Purpose |
|---|---|
| `AGENTPHONE_API_KEY` | Bearer token for AgentPhone REST API |
| `AGENTPHONE_WEBHOOK_SECRET` | HMAC-SHA256 secret for verifying inbound webhook signatures (NFR-12) |
| `AGENTPHONE_AGENT_ID` | Agent identifier on AgentPhone for our number |
| `AGENTPHONE_INBOUND_NUMBER` | Our provisioned inbound voice number (informational; not used in routing logic) |
| `AGENTPHONE_MESSAGING_NUMBER_ID` | Optional. Pins outbound `messages.send` (including `notify_emergency_contact`) to a specific attached `number_id`. Currently set to the SMS line so any recipient is reachable. Leave unset to let AgentPhone pick. |
| `ANTHROPIC_API_KEY` | API key for Claude |
| `CLAUDE_MODEL` | Default `claude-sonnet-4-6` (chosen for lower TTFT on voice turns). Fall back to `claude-opus-4-7` if dialogue quality becomes the bottleneck rather than latency. |
| `AGENTMAIL_API_KEY` | API key for AgentMail (sends lawyer-brief emails on connect) |
| `AGENTMAIL_INBOX_ID` | Optional. If unset, an inbox is created on first send and the id is logged so you can paste it back to reuse across restarts. |
| `BROWSER_USE_API_KEY` | API key for BrowserUse cloud (powers `research_and_email`). When unset, `research_and_email` sends a small jurisdiction-agnostic fallback email instead of failing. |
| `DISPATCHER_PHONE` | E.164 phone routed to when `escalate_to_human` fires (the founder's phone for the demo) |
| `PUBLIC_DEFENDER_HOTLINE` | E.164 fallback number for callers with no matching account (FR-9) |
| `WEBHOOK_PUBLIC_URL` | The ngrok URL exposing `/webhook` to AgentPhone |
| `RON_DEBOUNCE_SECONDS` | Optional. Default 0.4. Per-call debounce window for AgentPhone STT refinement webhooks (multiple webhooks per utterance as STT converges). |

---

## 11. Success metrics (demo / hackathon)

- Custody-scenario demo completes end-to-end in ≤ 90 seconds, ten consecutive practice runs.
- SMS visibly arrives on Sarah's phone in front of the audience *before* the call rings through.
- Agent correctly refuses at least one legal-advice question during the live demo.
- Non-urgent scenario demonstrates top-3 readback with pricing.
- Live transcript on second screen mirrors conversation with < 1-second lag.

**Long-term product metrics (post-hackathon):**

- Time from call pickup to attorney on the line (target: median < 90s)
- Match acceptance rate (caller accepts first proposed lawyer)
- Lawyer pickup rate (lawyer answers the transferred call within 30s)
- Per-call cost (AgentPhone + Anthropic API)
- Subscriber churn

---

## 12. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AgentPhone `transferNumber` cannot be set dynamically per-call | Medium | High | Investigate SDK before phase 4; fallback is agent-update API call right before transfer |
| Webhook latency exceeds 2.5s on tool turns | Medium | Medium | Pre-emit filler NDJSON chunk while tool runs |
| SMS delay > 2s, lands after the ring | Low | Medium | Send SMS earlier in flow (right after match decision, before readback) |
| Cold transfer rings to voicemail on stage | Low | High | Lawyer phone setup checklist: plugged in, screen on, max volume, DND off |
| Venue WiFi flakes | Medium | High | Mobile hotspot backup; pre-recorded video fallback |
| Legal-advice slip-up during demo | Low | High | Refusal phrasing hard-coded into system prompt; tested against known traps |
| Caller-ID match fails because seeded number differs from demo phone | Low | Medium | Verify all demo phone numbers in `users.json` are exactly E.164 format |

---

## 13. Out of scope (post-hackathon backlog)

- Real signup web application with Stripe payment authorization
- Lawyer onboarding portal and vetting workflow
- Multi-language UX (data model already supports it)
- Spanish-language agent variant
- Call recording for compliance (with explicit consent flow)
- Lawyer-side scheduling, billing, and matter-management
- Multi-jurisdiction handling (caller in TX needs CA lawyer, etc.)
- Family/friend authorization: spouse can call on user's behalf
- Public-defender hotline routing by jurisdiction (V1 uses one static number)
- Warm transfer or 3-way bridge if AgentPhone (or substitutable infra) adds it
- Native mobile apps
- Voice biometric verification as an additional auth factor

---

## 14. Open questions

1. **~~`transferNumber` dynamics~~** — RESOLVED 2026-05-17 via AgentPhone docs. The webhook response must contain ONLY `{"text": "...", "action": "transfer"}`. AgentPhone reads the destination from the agent record's `transfer_number` field, which `connect_to_lawyer` sets via `c.agents.update(...)` right before returning. Sending an extra `transferNumber` field in the webhook response causes silent bridge drops.
2. **~~Voice webhook payload shape~~** — RESOLVED. Voice uses `data.callId` and `data.transcript` (not the SMS-shaped `conversation_id`/`message`). Fallback chain in `_extract_call_id` handles both. Known caveat: AgentPhone occasionally fires `agent.message` webhooks with empty `data.from` / missing `data.callId`; the metadata-extraction fallback collapses those into a shared bucket file. Not blocking for the demo (registered callers usually get correct metadata) but a known intermittent issue.
3. **~~Response format — NDJSON streaming~~** — RESOLVED (deferred). Plain JSON `{"text": "..."}` is acceptable. Prompt caching (~8k system+tools cached per turn) brought TTFT into a workable range without streaming.
4. **~~Filler chunk timing~~** — N/A (no NDJSON path).
5. **~~Practice-area extraction~~** — Inline with triage, as expected.
6. **Lawyer SMS opt-in:** In a real product, lawyers must consent to receiving briefs via email/SMS. For the demo all "lawyers" are teammates so this is moot, but stays in the post-hackathon backlog.
7. **What happens if the caller's payment method is declined?** Out of scope for V1; mocked as always-authorized.
8. **Shared-iMessage line outbound restrictions:** AgentPhone's `shared-imessage` line type can only send to pre-registered contacts (HTTP 403 on first-touch). Project uses the SMS line for `notify_emergency_contact` to avoid this. If/when blue-bubble delivery matters, register specific contacts on the iMessage line via dashboard.

---

## 16. What changed since the 2026-05-15 draft

- **Opener** — was "Are you safe right now?", now "Hey, this is Ron. How can I help you?" (FR-10). Concierge tone, not 911.
- **Non-urgent flow** — was a binary split between self-serve research and lawyer match. Now: ALWAYS research first (dynamic per-case BrowserUse), then ASK if the caller also wants a lawyer (FR-13).
- **Lawyer brief delivery** — was SMS, now email via AgentMail (FR-26).
- **Transfer mechanism** — was understood as inline `transferNumber` per webhook response, actually requires the agent record's `transfer_number` field set via API before returning `{"action": "transfer"}` (FR-26, FR-27).
- **Tools** — was five, now eight: added `research_and_email` (dynamic per-case research with generic fallback), `notify_emergency_contact` (URGENT-only SMS to caller's emergency contacts), `end_call` (clean hangup for self-serve close-outs).
- **Prompt** — added BRIDGE category for `lookup_user` / `match_lawyers` (short statement-of-action like "One sec — finding a DUI lawyer in SF." must accompany the tool_use). CO-NARRATE category covers `connect_to_lawyer`, `research_and_email`, `notify_emergency_contact`, `end_call`, `escalate_to_human`, `route_to_public_defender`.
- **Caching** — Anthropic prompt caching wired with `cache_control: ephemeral` on system + tools (~8k tokens cached per turn after the first). Logged per iteration.
- **Server hardening** — `TRANSFERRED_CALLS` latch suppresses post-transfer chatter; post-transfer text-accumulation suppression in the claude loop prevents duplicate "Briefing X now..." narration on two-tool turns.
- **Call logs** — per-call JSON files in `data/calls/` are now timestamp-prefixed for chronological sort.
- **Tests** — 53 passing (was 31 in original plan; added research dynamic-prompt tests, notify_emergency_contact tests, schema-vs-signature consistency checks).

---

## 15. Appendix — pitch reference

The PRD is the engineering artifact. The pitch artifact (slides + script) lives separately. The pitch references:

- A signup mockup slide (single Figma frame)
- Three business-model bullets: $9/month subscription, 10–15% retainer commission, lawyer-network moat with network effects
- Closing ask: first ten partner attorneys to seed the criminal-defense network

The full pitch arc, demo choreography, and stage-role assignments are documented in the build plan at `~/.claude/plans/hey-so-this-is-noble-squid.md`.
