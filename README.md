# Agora — PS41 Real-Time AI Incident Commander

Monorepo for real-time incident command: voice (Agora RTC) → STT (Deepgram) → cognition (LLM) → live dashboard + TTS summaries.

## Structure

```
/apps
  /api      # FastAPI 3.11 — incidents, WS timeline, health
  /web      # Vite React TS + Tailwind + shadcn
  /worker   # Perception worker (Agora + Deepgram + VAD)
/packages/shared  # Zod (TS) + Pydantic (Python) mirrored schemas
/prompts    # extractor.yaml, summary.yaml
/infra      # docker-compose.yml
/demo       # payment_outage.json + seed.py
```

## Quick Start

```bash
cp .env.example .env
# fill AGORA_APP_ID, OPENAI_API_KEY, DEEPGRAM_API_KEY
docker compose -f infra/docker-compose.yml up --build
# api: http://localhost:8000  docs: /docs  health: /health
# web: http://localhost:5173
```

Seed demo incident:
```bash
python demo/seed.py --incident payment-001 --replay-rate 1.5
# or replay as transcript pushes:
python demo/seed.py --incident payment-001 --api-url http://localhost:8000
```

## Shared Types

Source of truth: `packages/shared/src/index.ts` (Zod) ↔ `packages/shared/python/agora_shared/types.py` (Pydantic).  
Keep them mirrored — PR required for changes.

Types: `Incident`, `Participant`, `Fact` (Confirmed/Corroborated/Reported/Contradicted), `Hypothesis` (Active/Disproven/Confirmed), `Decision` (Proposed/Approved/Reverted), `ActionItem` (Open/InProgress/Blocked/Done/Overdue + requiresConfirmation), `TimelineEvent`, `Gap` (MissingOwner/ConflictingInfo/UnverifiedAssumption/StaleAction), `TranscriptSegment`, `ToolEvent`.

## Services

| service | port | healthcheck |
|---------|------|-------------|
| postgres | 5432 | pg_isready |
| redis | 6379 | redis-cli ping |
| api | 8000 | GET /health |
| worker | 8001 | GET /health (or process probe) |
| web | 5173 | Vite dev server |

## Dev Scripts (pnpm)

```bash
pnpm install
pnpm --filter @agora/web dev
pnpm --filter @agora/api dev   # uvicorn
pnpm lint && pnpm typecheck
```

## Handoff Contracts

- Worker → API: `POST /incidents/{id}/transcript` (TranscriptSegment)
- API → Web: `WS /ws/incidents/{id}` fanout (timeline/gaps/actions)
- Cognition reads Postgres fact store, writes via internal API

See `PLAN.md` for full orchestration.
