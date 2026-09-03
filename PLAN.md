# PS41 — Real-Time AI Incident Commander — Implementation Plan (Orchestrator)

## 0. Orchestration Model
You (main orchestrator: Muse Spark) spawn 5 specialist sub-agents in parallel. Each owns a workstream with clear contracts.

```
Orchestrator
 ├─ Agent A: Repo Scaffold & Shared Types
 ├─ Agent B: Backend API + State + WS Timeline
 ├─ Agent C: Perception Pipeline (Agora + STT + Diarization)
 ├─ Agent D: Cognition Engine (LLM Extraction + Conflict/Gap)
 └─ Agent E: Frontend + Tools + TTS + Summary
         \-> Phase 6: All agents converge on Demo Seeder + E2E Test
```

Handoff via `packages/shared` JSON schemas + `docker-compose` services.

## 1. Repo Scaffold (Agent A)
**Stack:** pnpm monorepo, Turborepo optional. Docker-compose for infra.
```
/
 /apps
  /api      # FastAPI Python 3.11
  /web      # React Vite + TS + Tailwind + shadcn
  /worker   # Python perception worker
 /packages/shared  # zod/py schemas, TS types, event contracts
 /prompts   # extraction prompts YAML
 /infra     # docker-compose.yml, mocks
 /demo      # seed fixtures
 PLAN.md
 README.md
 .env.example
```
Tasks:
- init pnpm, vite, fastapi skeleton
- docker-compose: postgres:15, redis:7, api, worker, web
- shared types: Incident, Fact, Hypothesis, Decision, ActionItem, TimelineEvent, Gap (Zod + Pydantic mirrored)
- .env.example: AGORA_APP_ID, AGORA_CERT, DEEPGRAM_API_KEY, OPENAI_API_KEY, JIRA_URL, SLACK_TOKEN, PAGERDUTY_KEY, TTS_PROVIDER
- CI: lint, typecheck scripts

## 2. Backend API + State (Agent B)
**Tech:** FastAPI, SQLAlchemy/Pydantic, Postgres, Redis Streams/PubSub, WebSockets
**Endpoints:**
- POST /incidents -> create incident
- GET /incidents/{id} -> state
- WS /ws/incidents/{id} -> fanout: transcript, timeline, gaps, actions
- POST /incidents/{id}/transcript (worker pushes)
- POST /incidents/{id}/approve/{actionId}
- POST /incidents/{id}/summary -> generate final
- GET /health, /tools/status
**State Machine:**
- Store: Postgres tables + Redis cache for live view
- Append-only timeline table; materialized views for facts/actions
- PubSub: redis channel `incident:{id}` -> WS broadcast
- Concurrency: optimistic locking on action status
**Deliverable:** WS live, CRUD, tests with pytest

## 3. Perception Pipeline (Agent C)
**Tech:** Agora RTC SDK NG, Deepgram Nova-2 Streaming, Silero VAD, pyannote (optional)
**Flow:**
```
Browser Agora mic -> Agora channel -> Worker joins as bot (agora-python-server-sdk) 
-> PCM 16k -> VAD -> Deepgram WS (interim/final) -> speaker map -> POST /transcript
```
- Worker service: `worker/perception.py` loops audio frames
- Diarization: Deepgram `diarize=true` + client-side enrollment (`"I am Priya, SRE Lead"` regex)
- Role lexicon: SRE, Backend, Support, Biz, Comms
- Fallback: Browser WebAudio -> WS relay if server SDK unavailable (demo mode: playback wav)
- Transcript schema validation via shared types
**Deliverable:** Real-time transcript with speaker/role in UI <800ms

## 4. Cognition Engine (Agent D)
**Tech:** OpenAI GPT-4o-mini (realtime), GPT-4o for summary, instructor, LiteLLM abstraction
**Pipeline:**
- On transcript final -> Cognition service (FastAPI background task or separate worker)
- 3 LLM calls (parallel, <1.5s):
  1. Extractor: classify Fact/Hypothesis/Decision/Action/Chatter, extract status/confidence, cite utteranceIds
  2. Ownership Resolver: assign owner, set requiresConfirmation
  3. Conflict/Gap Detector: cross-check Fact store (cosine sim via embeddings or keyword)
- Rules engine supplements LLM: overdue, unassigned, contradiction heuristics
- Update Postgres + publish to Redis
- Prompt files: `prompts/extractor.yaml` with few-shot payment outage examples, chain-of-thought disabled, JSON-only
**Guardrails:** No source -> hypothesis, Never assert RCA, confidence calibrated
**Deliverable:** Facts vs Hypotheses columns, gaps, tests on fixture

## 5. Frontend + Tools + TTS (Agent E)
**Tech:** React Vite, shadcn/ui, Agora RTC NG, Zustand, ws, Tailwind
**Panes:**
- Voice Room bar (join/mute, participants with role badges)
- Transcript (virtualized)
- Facts | Hypotheses (conflict red, confidence bar)
- Decisions
- Action Kanban (Todo/Doing/Done, owner avatar, approve button)
- Timeline vertical
**Tools:**
- Adapter interface: `ToolAdapter` -> MockJira, MockSlack, MockPD, MockDatadog
- UI: Tool status dots, Jira key links
- Approval gate: modal -> POST approve -> adapter call -> ToolEvent
**TTS:**
- Provider: OpenAI TTS / ElevenLabs, cached mp3, publish to Agora as audio track (unmute bot 10s)
- Scheduler: every 5m or 3+ facts, VAD silence gate, manual button
**Final Summary:** Generate markdown, export PDF, list unresolved risks
**Deliverable:** Live dashboard, spoken summaries audible in Agora room

## 6. Demo Seeder + E2E (All Agents Converge)
- Fixture: `demo/payment_outage.json` with timestamped utterances + expected extractions
- Seeder: `python demo/seed.py --incident payment-001 --replay-rate 1.5x` -> feeds transcript API + optionally plays wav via Agora
- Verification: `pytest tests/e2e/test_payment_scenario.py` asserts: 4 facts, 1 hypothesis, 1 conflict, 1 overdue, timeline length, tool calls require approval
- Demo script: 5-min walkthrough for judges

## 7. Contracts Between Agents
- Shared types are source of truth; any change -> PR to orchestrator
- Worker -> API: POST transcript JSON, API -> WS -> Web
- Cognition reads Postgres fact store, writes back via API internal call
- All services log to stdout, healthcheck via /health

## 8. Risks & Mitigations
- Agora server SDK complexity -> fallback to browser relay + Deepgram directly (demo still works)
- LLM latency -> use mini model + parallel calls + cache
- Diarization errors -> enrollment prompt + manual role override in UI
- Cost -> mock tools by default, real keys only if provided

## 9. Orchestrator Execution Order
1. Agent A scaffold (blocking, 10m) -> then B,C,D,E parallel
2. Orchestrator polls each agent's file outputs, resolves type conflicts
3. Final integration: seed + e2e test + `docker-compose up` verification

## 10. Verification Checklist
- [ ] `docker-compose up` brings 4 services healthy
- [ ] Join Agora channel, speak, see transcript <1s
- [ ] Fact vs Hypothesis split correct on fixture
- [ ] Conflict flagged for error rate
- [ ] Action ownership tracked, overdue pulsed
- [ ] TTS summary audible in room
- [ ] Jira creation blocked until approval
- [ ] Final summary lists unresolved risks
