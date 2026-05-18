# Better Call Ron

Voice-first AI lawyer concierge. Built for YC's "All My Agents" hackathon.

> *"Hey, this is Ron. How can I help you?"*

## What this is

A pre-registered user in a legal situation calls one number. Ron (the AI agent) authenticates them via caller-ID (or name + DOB if calling from someone else's phone), triages the situation, and either:

- **Urgent path** (arrest, custody, crisis): picks the right attorney from a curated network, briefs them via email, cold-transfers the live call, and SMS-notifies the caller's emergency contact in the same turn. Target: under 90 seconds from pickup to attorney on the line.
- **Non-urgent path** (browsing / research): kicks off a per-case BrowserUse web research run (live-browsed jurisdiction-specific resources), emails the resource pack to the caller, then asks if they'd also like to be matched with a lawyer. If yes, runs the match + connect flow with pricing readback.

The headline scenario is **"one phone call from jail"** — read the [PRD](./PRD.md) for the full product spec.

## Docs

- **[PRD.md](./PRD.md)** — product requirements, scenarios, data model, FRs/NFRs
- **[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)** — the concrete build doc; what files exist, what they do, in what order

## Quick start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Fill in secrets
cp .env.example .env
# Edit .env with real keys (see PRD §10.2)

# 3. Run tests (expect 53 passed)
pytest -v

# 4. Run server
uvicorn src.server:app --reload --port 8000

# 5. Expose to AgentPhone via ngrok
ngrok http 8000
# Copy the https URL into AgentPhone's webhook config and into .env's WEBHOOK_PUBLIC_URL
```

## Architecture in one breath

AgentPhone (transport: STT, TTS, SMS/iMessage, cold transfer) ↔ our FastAPI webhook ↔ Claude tool-use loop (with prompt caching) ↔ eight tools (`lookup_user`, `match_lawyers`, `connect_to_lawyer`, `research_and_email`, `notify_emergency_contact`, `end_call`, `escalate_to_human`, `route_to_public_defender`) ↔ JSON files + AgentMail (lawyer briefs) + BrowserUse (dynamic per-case research).

## Layout

```
src/         server, matcher, tools, prompts, schemas, claude_loop,
             agentphone_client, agentmail_client, browseruse_client, call_log
data/        users.json, lawyers.json (seeded fixtures); calls/ (per-call JSON logs, gitignored)
public/      live transcript HTML for stage projection
tests/       pytest suite (matcher cascade + tools + signature verification + claude_loop schema)
assets/      pitch slide + backup demo video
```
