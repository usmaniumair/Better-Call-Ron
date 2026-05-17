# CLAUDE.md — Better Call Ron

Project guide for Claude Code sessions in this repo. Read this first.

## What this is

**Better Call Ron** is a voice-first AI concierge for the **lawyer-marketplace vertical**, built for Y Combinator's "All My Agents" hackathon (demo day 2026-05-17). A caller dials one number; Ron authenticates them (caller-ID for pre-registered users), infers urgency from how they talk, and adapts:

- **Urgent path** — caller signals distress (arrest, in custody, crisis). Ron triages in under 30 seconds, picks an attorney from the curated network, briefs the lawyer, and cold-transfers the live call. Target: under 90 seconds from pickup to attorney on the line. The "one phone call from jail" demo scenario showcases this path — it is **one demo scenario, not the entire product scope**.
- **Shopper path** — caller is on their own phone, not in crisis, browsing or evaluating lawyers (e.g. divorce, family, general consult). Ron walks them through the marketplace at a normal pace — discovery, fit, scheduling, hand-off.

Expect the vertical to expand further. Don't treat the urgent flow as the canonical path or wire shopper-mode behavior through urgent-mode plumbing (or vice versa). Ron decides which path from the caller's own words.

**Naming:** Service brand is "Better Call Ron." The agent introduces itself in conversation as just "Ron."

## Canonical docs (read these before re-deriving anything)

- [PRD.md](PRD.md) — product spec, scenarios, data model, FRs/NFRs
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — concrete build doc; what files exist, in what order
- [README.md](README.md) — quick start
- `~/.claude/plans/` — saved plans from prior sessions. The current ones for this project:
  - `hey-so-this-is-noble-squid.md` — original hackathon build plan
  - `what-do-we-have-indexed-lampson.md` — Ron's prompt tone/guardrail upgrades
  - `is-this-winnable-warm-globe.md` — polish path to 10/10 for "Best Overall / Most Fundable"
- `~/.claude/projects/-Users-umair-Documents-Github-Better-Call-Ron/memory/` — auto-memory exported from the prior project directory (user profile, collaboration feedback, AgentPhone reference, project state snapshot)

## Stack

- FastAPI + Anthropic Python SDK (AsyncAnthropic) + AgentPhone Python SDK + JSON files (no DB)
- Default LLM: `claude-sonnet-4-6` (for voice TTFT). Opus 4.7 is the quality fallback.
- Python ≥ 3.11. Tests via `pytest`. Lint via `ruff` (line-length 110).
- Transport (STT, TTS, SMS/email, cold transfer): [AgentPhone](https://agentphone.ai) — required by hackathon rules.

## Architecture in one breath

AgentPhone webhook → [src/server.py](src/server.py) → Claude tool-use loop in [src/claude_loop.py](src/claude_loop.py) → tools in [src/tools.py](src/tools.py) → matcher in [src/matcher.py](src/matcher.py) → JSON files in [data/](data/). Prompts in [src/prompts.py](src/prompts.py).

## File map

```
src/
  server.py              FastAPI app, AgentPhone webhook handler, interim-transcript debounce
  claude_loop.py         AsyncAnthropic tool-use loop
  tools.py               Tool implementations (lookup_user, match_lawyers, connect_to_lawyer, etc.)
  matcher.py             Deterministic rules+score lawyer matching (NOT an LLM)
  prompts.py             Ron's system prompt + persona/voice rules
  schemas.py             Pydantic models
  agentphone_client.py   AgentPhone SDK wrapper + HMAC signature verification
  agentmail_client.py    Email transport (AgentMail)
  browseruse_client.py   Browser-use SDK wrapper
  call_log.py            Per-call event log
  transcript_bus.py      Live transcript pub/sub for the projection page
  config.py              Env config
data/
  users.json, lawyers.json   Seeded fixtures (real demo team numbers live here)
  calls/                     Per-call logs
public/transcript.html       Live transcript HTML for stage projection
tests/                       pytest suite (matcher + tools + signature)
scripts/
  dev_harness.py             Drives scripted scenarios through live Claude with mocked transport
  setup_agent.py             Pushes begin_message, sets webhook URL, writes new secret to .env
assets/                      Pitch slide + backup demo video
```

## Key locked decisions

- Product scope is the **lawyer-marketplace vertical** — covers both urgent (jail/arrest/crisis) and non-urgent (shopper/browser) callers. The jail scenario is one demo, not the whole product. Don't collapse the scope back to "emergency hotline" in prompts, code paths, or framing.
- Matching is **deterministic rules+score, not LLM**. Don't rewrite it as an LLM call.
- Connect mechanic is **brief + cold transfer**. AgentPhone supports cold transfer only — no warm transfer, no 3-way bridge, no conference. Workaround: send the brief to the recipient *immediately before* issuing the transfer action.
- Tool surface is intentionally small. `route_to_public_defender` was split out from `escalate_to_human` so unknown callers route to the PD hotline, not the dispatcher. **Each transfer tool's behavior is scoped to itself** — they are not interchangeable in Umair's mental model.
- Three-plus-person team on demo day; Umair is not solo.

## AgentPhone gotchas (already solved — don't re-discover)

- **Cold transfer only.** `{"action": "transfer", "transferNumber": "+1..."}` inline in the webhook response works (Scenario A); no `agents.update(transfer_number=...)` call needed.
- **SDK signature helper is broken** (v0.6.1). AgentPhone signs `{X-Webhook-Timestamp}.{body}` Stripe-style; the SDK only hashes the body. We implement HMAC verification ourselves in [src/agentphone_client.py](src/agentphone_client.py) — see `tests/test_signature.py` for the regression suite.
- **Voice payload shape:** `data.callId` + `data.transcript` (not `data.message`/`conversation_id` as SMS-shaped SDK models suggest).
- **Interim transcripts spam the webhook.** One spoken sentence can fire 3–5 events as STT refines. Solved via per-call sequence-number debounce in `src/server.py` (default 0.4s, env `RON_DEBOUNCE_SECONDS`). Don't remove it.
- **`set_webhook` rotates the signing secret on every call.** After `scripts/setup_agent.py`, update `.env`'s `AGENTPHONE_WEBHOOK_SECRET` AND restart the server.
- AgentPhone speaks `begin_message` BEFORE firing any webhook — Ron's opener is set via `agents.update`, not in code.

## Working with Umair (from prior-session feedback memory)

- **Surface design questions structurally.** If a response contains embedded design choices ("two options here…", "I'd lean…", "open question"), bundle them into an `AskUserQuestion` call with up to 4 questions — don't leave them buried in prose. Lead with the recommended option labeled "(Recommended)" when there's a clear preference.
- **Don't overengineer adjacent branches.** Implement exactly the path Umair named. If a related branch looks like it might want the same logic (e.g. the three transfer tools), *ask* before extending — don't ship it speculatively. He's pushed back on this before.
- He thinks about edge cases up-front and has sharp product instincts — when he challenges a design assumption, take it seriously rather than defending the assumption.
- Workflow he's chosen for this build: Dev agent (writes code) → Reviewer agent (verifies, tests) → Docs/Memory agent (reconciles drift in PRD/IMPLEMENTATION_PLAN/README/memory).

## Updating project memory

**Keep memory in sync with the code as we work.** When changes here invalidate something in `~/.claude/projects/-Users-umair-Documents-Github-Better-Call-Ron/memory/` — a tool rename, a new constraint, a resolved gotcha, a changed seed file, a removed workaround — update the relevant memory file in the same session, don't defer it. Stale memory becomes worse than no memory because it gets cited as fact. Specifically:

- After changing any tool name, signature, or behavior → update [project_lawyer_concierge.md](~/.claude/projects/-Users-umair-Documents-Github-Better-Call-Ron/memory/project_lawyer_concierge.md).
- After discovering or resolving an AgentPhone quirk → update [reference_agentphone.md](~/.claude/projects/-Users-umair-Documents-Github-Better-Call-Ron/memory/reference_agentphone.md).
- After Umair gives new collaboration guidance (a correction OR a confirmed approach) → add or update a `feedback_*.md` file.
- After a build phase completes → update the "Build progress" section of [project_lawyer_concierge.md](~/.claude/projects/-Users-umair-Documents-Github-Better-Call-Ron/memory/project_lawyer_concierge.md) with absolute dates.
- If something in this CLAUDE.md goes stale, update it here too.

If you find memory that contradicts the current code, trust the code and fix the memory.

## Quick commands

```bash
# tests
pytest -v

# server
uvicorn src.server:app --reload --port 8000

# expose to AgentPhone
ngrok http 8000
python -u scripts/setup_agent.py <ngrok-https-url>   # then restart the server (secret rotated)

# scripted scenarios through live Claude, mocked transport
python -u -m scripts.dev_harness <scenario>   # or `all`
```
