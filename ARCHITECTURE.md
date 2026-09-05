# EchoSphere — End-to-End Architecture

> AI Incident Commander that listens to a live incident-room conversation, tells facts from
> guesses, catches contradictions, tracks who owns what, and keeps a structured audit trail —
> instead of just transcribing. See `EchoSphere_PRD.md` for the full product spec and
> `ECHOSPHERE_IMPLEMENTATION_PLAN.md` for what's built vs. still open, phase by phase.

## 1. The story, start to finish

```
 Voice room (Agora RTC)
        │  engineers talk through an incident live
        ▼
 Speech-to-text (Agora Conversational AI Engine — managed ASR, speaker-labeled)
        │  or: demo/seed.py replays a scripted transcript for presentations
        ▼
 POST /incidents/{id}/transcript          [apps/api/main.py]
        │  1. store the segment
        │  2. run cognition — classify the utterance
        ▼
 Cognition (two layers, in order)                          [apps/api/main.py + cognition.py]
   a. Deterministic fixture/regex map — the scripted demo scenario always classifies the
      same way, every run, so a presentation never depends on an LLM answering consistently
   b. LLM classifier fallback — anything the deterministic map doesn't recognize goes to
      cognition.extract() → Claude / OpenAI / a local Ollama model (whichever is configured),
      which returns the same structured shape: Fact | Hypothesis | Decision | ActionItem | Chatter
        │
        ▼
 Structured incident state (Postgres, or SQLite for local/demo use) — Facts, Hypotheses,
 Decisions, Actions, Conflicts, Gaps, Timeline — this is the source of truth, not the transcript
        │
        ▼
 Gap & conflict detection (runs after every transcript push)     [_detect_and_store_gaps]
   - ConflictingInfo: two people reporting contradictory numbers → a first-class Conflict record
   - MissingOwner / StaleAction: an action with nobody on it, or open too long (+ one Slack nudge)
   - UnverifiedAssumption / AssumptionCreep: a theory being repeated without ever being confirmed
   - DuplicateWork: two different owners investigating the same thing
   - DecisionHygiene: a decision marked Approved without owner/outcome/risk/rollback filled in
        │
        ▼
 Broadcast — every change fans out over WebSocket (ws/incidents/{id}) to the dashboard
        │
        ▼
 Dashboard (React, Vite)                                          [apps/web]
   Transcript · Facts · Hypotheses · Decisions · Gaps · Timeline · Tools · Summary
        │
        ▼
 Human approval gate — a Decision/Action flagged requiresConfirmation cannot fire its tool
 (e.g. create a Jira ticket) until someone clicks Approve                [tools.py adapters]
        │
        ▼
 Postmortem — POST /incidents/{id}/summary generates the final markdown report on demand
```

## 2. Components

| Path | What it is | Status |
|---|---|---|
| `apps/api` | FastAPI backend — incident state, cognition, gap detection, WS fanout, tool adapters, Agora Conversational AI integration | Working, 67 tests passing |
| `apps/worker` | Perception worker — Agora RTC audio capture, VAD, Deepgram fallback STT | Built, mock-first (works without real Agora/Deepgram keys) |
| `apps/web` | React/Vite dashboard | Working — 8 tabs, connects over WebSocket |
| `packages/shared` | Zod (TS) + Pydantic (Python) schemas — the two must stay mirrored | Kept in sync |
| `demo/` | `payment_outage.json` fixture (12 scripted utterances) + `seed.py` replayer | Deterministic, safe to re-run |

## 3. The cognition engine in detail

- **Facts vs. Hypotheses**: a Fact needs a source (something someone reported or a tool
  confirmed); a Hypothesis is a guess ("I think it's the deploy") and stays `Active` until
  confirmed or disproven — the system never silently promotes a guess to a fact.
- **Assumption-Creep**: if a hypothesis gets referenced 3+ times across the conversation without
  ever being verified, a high-severity gap fires — this is the "don't let a repeated guess become
  treated as truth" guardrail (PRD §8.5), and it's driven by actual word-overlap analysis of the
  transcript, not a hardcoded trigger.
- **Conflicts**: when two facts report contradictory numbers (e.g. 2% vs 12% error rate), both a
  `ConflictingInfo` gap and a first-class `Conflict` record are created (claim A, claim B, review
  status) — this is the "the AI caught two engineers contradicting each other" moment.
- **LLM providers**: `LLM_PROVIDER` env var selects between `claude` (default), `openai`, or
  `ollama` (fully local, no key — `apps/api/cognition.py`). All three return the same JSON shape,
  so switching providers changes nothing else in the pipeline.

## 4. Human-in-the-loop

Nothing dangerous fires automatically. An `ActionItem` or tool call marked
`requiresConfirmation` sits behind an Approve button; only after a human clicks it does the tool
adapter (`apps/api/tools.py` — Jira/Slack/PagerDuty/Datadog, mocked by default) actually run.

## 5. Agora integration

- **Conversational AI Engine** (mandatory per hackathon rules): `apps/api/agora_conversational_ai.py`
  starts/stops a managed voice agent per incident. ASR + TTS use Agora-managed vendors
  (Deepgram/MiniMax — no extra keys); the LLM slot points at our own webhook
  (`POST /agora/llm/chat/completions`) so our own cognition engine stays the in-room voice
  instead of a generic bot. Built and tested at the request/response-shape level; not yet
  live-verified against a real Agora account.
- **RTC audio capture / worker fallback**: `apps/worker` — mock-runnable without real credentials.

## 6. Running it

**Fastest path (SQLite, no Docker, local Ollama for the LLM layer):**

```powershell
cd C:\Ecosphere
.\start-demo.ps1
```

Starts the API and dashboard each in their own window, seeds the `payment-001` scenario, and
prints the dashboard URL (`http://localhost:5173`). Safe to re-run any time.

**Manually, piece by piece:**

```powershell
# API
cd apps\api
$env:DATABASE_URL = "sqlite+aiosqlite:///./demo_run.db"
$env:REDIS_URL = ""
$env:TTS_PROVIDER = "mock"
$env:LLM_PROVIDER = "ollama"          # or "claude"/"openai" with the matching API key set
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000

# Dashboard (separate terminal)
cd apps\web
npx vite --host 0.0.0.0 --port 5173

# Seed the demo incident (separate terminal, safe to re-run)
python demo/seed.py --incident payment-001 --api-url http://localhost:8000 --replay-rate 30
```

**Full stack with Docker** (Postgres + pgvector, Redis, all 3 services):
```bash
cp .env.example .env   # fill in whatever keys you have
docker compose -f infra/docker-compose.yml up --build
```

**Tests:**
```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/ -q
```

## 7. What's real vs. what's a stand-in right now

| Area | State |
|---|---|
| Structured state, gap/conflict detection, approval gate, postmortem | Real, tested against the scripted fixture |
| LLM classification (Claude/OpenAI/Ollama) | Real, tested — deterministic fixture path is what runs during the scripted demo; the LLM path handles anything outside the script |
| Live voice room, real-time STT | Built, needs a real Agora account to demo live — the scripted `demo/seed.py` replay is the reliable presentation path |
| Cross-incident precedent recall (pgvector) | Portable Python cosine-similarity implementation now; native pgvector column is wired for when it's needed at scale |
| Tool adapters (Jira/Slack/PagerDuty/Datadog) | Mocked by default; real credentials in `.env` switch them live |
