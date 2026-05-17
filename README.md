# Better Call Ron

Voice-first AI lawyer concierge. Built for YC's "All My Agents" hackathon.

> *"This is Ron. Are you safe right now?"*

## What this is

A pre-registered user in a legal emergency calls one number. Ron (the AI agent) authenticates them (even when they're on someone else's phone), triages the situation in under 30 seconds, picks the right attorney from a curated network, briefs the lawyer via SMS, and cold-transfers the live call. Target: under 90 seconds from pickup to attorney on the line.

The headline use case is **"one phone call from jail"** — read the [PRD](./PRD.md) for the full product spec.

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

# 3. Run tests (expect 31 passed)
pytest -v

# 4. Run server
uvicorn src.server:app --reload --port 8000

# 5. Expose to AgentPhone via ngrok
ngrok http 8000
# Copy the https URL into AgentPhone's webhook config and into .env's WEBHOOK_PUBLIC_URL
```

## Architecture in one breath

AgentPhone (transport: STT, TTS, SMS, cold transfer) ↔ our FastAPI webhook ↔ Claude tool-use loop ↔ five tools (`lookup_user`, `match_lawyers`, `connect_to_lawyer`, `escalate_to_human`, `route_to_public_defender`) ↔ JSON files.

## Layout

```
src/         server, matcher, tools, prompts, schemas
data/        users.json, lawyers.json (seeded fixtures)
public/      live transcript HTML for stage projection
tests/       pytest suite (matcher cascade + tools)
assets/      pitch slide + backup demo video
```
