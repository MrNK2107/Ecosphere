# Agora — PS41 Real-Time AI Incident Commander — Detailed Context

> **Monorepo:** `pnpm` workspaces + FastAPI (Python 3.11) + Vite React TS + Tailwind/shadcn + Postgres/Redis + Agora RTC + Deepgram + OpenAI LLM
> **Tagline:** `voice (Agora RTC) → STT (Deepgram) → cognition (LLM) → live dashboard + TTS summaries` — `README.md:3`
> **Root:** `C:\Users\admin\Desktop\agora` — workspace `pnpm-workspace.yaml:1-3` (`apps/*`, `packages/*`)

---

## 1. Top-Level Layout

```
/
├─ apps/
│  ├─ api/        # FastAPI 0.110.0 — incidents, WS timeline, health, cognition, tools, TTS — apps/api/main.py:1
│  ├─ web/        # Vite 5.3 + React 18.3 + TS 5.5 + Zustand 4.5 + agora-rtc-sdk-ng 4.21 — apps/web/package.json:13-20
│  └─ worker/     # Perception worker (FastAPI on :8001) — Agora + Deepgram + Silero VAD — apps/worker/main.py:1
├─ packages/
│  └─ shared/
│     ├─ src/index.ts          # Zod source of truth — packages/shared/src/index.ts:1
│     └─ python/agora_shared/types.py  # Pydantic mirror — packages/shared/python/agora_shared/types.py:1
├─ prompts/
│  ├─ extractor.yaml  # GPT-4o-mini extraction prompt + few-shots — prompts/extractor.yaml:1
│  └─ summary.yaml    # GPT-4o summary + TTS script — prompts/summary.yaml:1
├─ infra/
│  └─ docker-compose.yml  # postgres:15, redis:7, api, worker, web — infra/docker-compose.yml:1
├─ demo/
│  ├─ payment_outage.json  # 12-utterance fixture + expectedExtractions — demo/payment_outage.json:1
│  ├─ seed.py              # replay @ 1.5x via POST /transcript — demo/seed.py:1
│  └─ e2e_test.py
├─ PLAN.md        # Orchestrator plan: 5 parallel agents (A-E) + handoff contracts — PLAN.md:1
├─ README.md      # Quick start + shared types table + services table — README.md:1
├─ package.json   # monorepo scripts: dev/build/lint/typecheck/test — package.json:6-11
├─ pnpm-workspace.yaml
├─ .env.example   # AGORA_APP_ID, DEEPGRAM_API_KEY, OPENAI_API_KEY, JIRA/SLACK/PD/TTS — .env.example:1
└─ .dockerignore / .gitignore
```

**Dev scripts** `package.json:6-11`:
```bash
pnpm install
pnpm --filter @agora/web dev        # Vite :5173
pnpm --filter @agora/api dev        # uvicorn
pnpm lint && pnpm typecheck
docker compose -f infra/docker-compose.yml up --build
# api: http://localhost:8000  docs: /docs  health: /health
# web: http://localhost:5173
python demo/seed.py --incident payment-001 --replay-rate 1.5
python demo/seed.py --incident payment-001 --api-url http://localhost:8000
```

---

## 2. Shared Types — Source of Truth

**Rule:** `packages/shared/src/index.ts` (Zod) ↔ `packages/shared/python/agora_shared/types.py` (Pydantic) must stay mirrored — PR required — `README.md:35`, `packages/shared/src/index.ts:2`, `packages/shared/python/agora_shared/types.py:2`.

### 2.1 Enums `packages/shared/src/index.ts:10-52`

| Enum | Values | Py mirror |
|------|--------|-----------|
| `FactStatus` | `Confirmed`, `Corroborated`, `Reported`, `Contradicted` | `types.py:10` |
| `HypothesisStatus` | `Active`, `Disproven`, `Confirmed` | `types.py:11` |
| `DecisionStatus` | `Proposed`, `Approved`, `Reverted` | `types.py:12` |
| `ActionStatus` | `Open`, `InProgress`, `Blocked`, `Done`, `Overdue` | `types.py:13` |
| `GapKind` | `MissingOwner`, `ConflictingInfo`, `UnverifiedAssumption`, `StaleAction` | `types.py:14` |
| `TimelineEventType` | `transcript`, `fact_created`, `fact_updated`, `hypothesis_created`, `hypothesis_updated`, `decision`, `action_created`, `action_updated`, `gap_detected`, `gap_resolved`, `tool`, `summary`, `system` | `types.py:15-20` |
| `ToolName` | `jira`, `slack`, `pagerduty`, `datadog`, `github` | `types.py:21` |
| `ToolEventStatus` | `pending`, `success`, `failed`, `requiresApproval`, `rejected` | `types.py:22` |
| `IncidentStatus` | `open`, `investigating`, `mitigated`, `resolved`, `closed` | `types.py:23` |
| `ParticipantRole` | `SRE`, `Backend`, `Frontend`, `Support`, `Biz`, `Comms`, `Unknown` | `types.py:24` |

Helpers: `isoDateTime` (`z.string().datetime`) and `uuidId` (`z.string().min(1)` — ulid/uuid/prefixed like `inc-abc`) — `index.ts:54-56`.

### 2.2 Schemas

- **Participant** `index.ts:59-67` → `id`, `name`, `role` (default `Unknown`), `avatarUrl?`, `joinedAt`, `isBot` (default `false`).
- **TranscriptSegment** `index.ts:70-84` → `id`, `incidentId`, `speakerId` (nullable), `speakerName?`, `role?`, `text` (min 1), `isFinal` (default `true`), `startMs`/`endMs` (int ≥0), `confidence` (0-1 default 0.9), `language` (default `en-US`), `createdAt`.
- **Fact** `index.ts:87-98` → `id`, `incidentId`, `statement`, `status:FactStatus`, `confidence` 0-1, `sourceSegmentIds` (min 1), `createdAt`, `updatedAt`, `createdBy?`.
- **Hypothesis** `index.ts:101-112` → `statement`, `status:HypothesisStatus`, `confidence`, `sourceSegmentIds[]`, `disprovenReason?`.
- **Decision** `index.ts:115-126` → `statement`, `status:DecisionStatus`, `decidedBy?` (participant id/name), `decidedAt?`, `sourceSegmentIds[]`.
- **ActionItem** `index.ts:129-145` → `title`, `description?`, `ownerId?` (nullable), `ownerName?` (nullable), `status:ActionStatus`, `requiresConfirmation` (default `false` — blocks tool call until approved), `dueAt?` (nullable), `toolKey?:ToolName`, `toolPayload?:record`.
- **Gap** `index.ts:148-158` → `kind:GapKind`, `severity` (`low|medium|high|critical` default `medium`), `message`, `relatedIds[]`, `resolvedAt?`.
- **ToolEvent** `index.ts:161-173` → `tool:ToolName`, `action` (e.g. `create_issue`), `status:ToolEventStatus`, `payload` (default `{}`), `result?`, `requiresApproval` (default `false`), `actionItemId?`.
- **TimelineEvent** `index.ts:176-187` → `type:TimelineEventType`, `seq` (monotonic int ≥0), `actorId?`, `payload:record` (one of Fact/Hypothesis/...), `refId?`.
- **Incident** `index.ts:190-201` → `id`, `title`, `description?`, `status:IncidentStatus` (default `open`), `severity` (`SEV1-4` default `SEV1`), `participants:Participant[]`, `summaryMarkdown?`.
- **IncidentSnapshot** `index.ts:204-215` → aggregate published over `WS /ws/incidents/{id}` fanout (`timeline/gaps/actions`): `{incident, facts[], hypotheses[], decisions[], actions[], gaps[], timeline[], transcript[], toolEvents[]}`. Re-exported via `Schemas` map `index.ts:220-232`.

Python mirror adds `model_config = ConfigDict(extra="forbid", ...)` `types.py:26` and uses `Literal` unions `types.py:10-24`.

Frontend store re-mirrors these as TS types in `apps/web/src/store/incidentStore.ts:4-52`.

---

## 3. Infra & Env

### 3.1 `infra/docker-compose.yml:1-100`
- `postgres:15-alpine` `5432`, `healthcheck: pg_isready`, volume `postgres_data` `docker-compose.yml:3-18`
- `redis:7-alpine` `6379`, `healthcheck: redis-cli ping` `docker-compose.yml:20-30`
- `api` build `apps/api/Dockerfile` `8000`, `env_file: ../.env`, `DATABASE_URL=postgresql://agora:agora@postgres:5432/agora`, `REDIS_URL=redis://redis:6379/0`, depends on healthy postgres+redis, healthcheck `curl /health` `docker-compose.yml:32-53`
- `worker` build `apps/worker/Dockerfile`, `API_URL=http://api:8000`, same DB/Redis, depends on `api` healthy, healthcheck `curl /health` `:8001` `docker-compose.yml:55-78`
- `web` build `apps/web/Dockerfile` `5173`, `VITE_API_URL=http://localhost:8000`, `VITE_WS_URL=ws://localhost:8000`, depends on `api` `docker-compose.yml:80-98`

Ports/health table `README.md:44-50` matches compose.

### 3.2 `.env.example:1-33`
```
AGORA_APP_ID / AGORA_APP_CERT / AGORA_CERT
DEEPGRAM_API_KEY
OPENAI_API_KEY (+ OPENAI_MODEL=gpt-4o-mini)
JIRA_URL / JIRA_EMAIL / JIRA_API_TOKEN
SLACK_TOKEN / SLACK_CHANNEL=#incidents
PAGERDUTY_KEY / PAGERDUTY_SERVICE_ID
TTS_PROVIDER=openai|elevenlabs|mock  ELEVENLABS_API_KEY  TTS_VOICE=alloy
DATABASE_URL=postgresql://agora:agora@postgres:5432/agora
REDIS_URL=redis://redis:6379/0
API_PORT=8000 WORKER_PORT=8001 WEB_PORT=5173
```

---

## 4. Backend API — `apps/api/`

### 4.1 Stack `apps/api/requirements.txt:1-17`
`fastapi==0.110.0`, `uvicorn[standard]==0.29.0`, `pydantic==2.7.1`, `sqlalchemy==2.0.30`, `asyncpg==0.29.0`, `psycopg2-binary`, `redis==5.0.4`, `httpx==0.27.0`, `websockets==12.0`, `pyyaml==6.0.1`, `pytest` suite.

### 4.2 DB Layer `apps/api/models.py:1-201` + `apps/api/db.py:1-90`

- **Engine** `db.py:26-48`: reads `DATABASE_URL`, converts `postgresql://` → `postgresql+asyncpg://`, `create_async_engine(pool_size=5, max_overflow=10, pool_pre_ping=True)`. `init_db()` `db.py:63-68` calls `Base.metadata.create_all`; `get_db()` `db.py:81-90` yields `AsyncSession` with `commit/rollback`; `close_db()` on shutdown.

- **Tables** `models.py:21-201`:
  - `incidents` (id PK 64, title, description, status, severity, created_at/updated_at, summary_markdown)
  - `participants` (FK incidents, UniqueConstraint incident_id+name, role, avatar_url, joined_at, is_bot)
  - `transcript_segments` (index `incident_id+start_ms`, speaker_id/name/role, text, is_final, start_ms/end_ms, confidence, language)
  - `facts` (statement, status, confidence, source_segment_ids JSON, created_by)
  - `hypotheses` (statement, status, confidence, disproven_reason)
  - `decisions` (statement, status, decided_by/at)
  - `action_items` (title, owner_id/name, status, requires_confirmation, due_at, tool_key, tool_payload JSON)
  - `gaps` (kind, severity, message, related_ids JSON, resolved_at)
  - `timeline_events` (index incident_id+seq, type, seq int, actor_id, payload JSON, ref_id)
  - `tool_events` (tool, action, status, payload/result JSON, requires_approval, action_item_id)
  - `timeline_sequences` (incident_id PK, current_seq int) — monotonic counter `models.py:197-201`

Relationships `cascade="all, delete-orphan"` from `IncidentModel`.

### 4.3 FastAPI App `apps/api/main.py:1-1300+`

- **App** `main.py:266`: `FastAPI(title="Agora API", version="0.2.0")` + `CORSMiddleware allow_origins=["*"]` `main.py:268-274`.
- **Redis/WS fanout** `main.py:278-359`: `_redis_client`, `_redis_enabled`, `_ws_connections: dict[str, Set[WebSocket]]`. `_startup()` `main.py:299-318` does `init_db()` + `redis.asyncio.from_url(...).ping()` fallback to in-process. `_shutdown()` closes both. `_broadcast()` `main.py:535-549` does `redis.publish("incident:{id}", json)` + direct `ws.send_json` to `_ws_connections[id]`.
- **Helpers**: `_now()` UTC `main.py:284`, `_gen_id(prefix)` `main.py:288`, `_next_seq()` `main.py:339-350` with `SELECT ... FOR UPDATE` on `TimelineSeqModel`, `_model_to_*` converters `main.py:353-435`, `_build_snapshot()` `main.py:441-513` (joins all tables, sorts timeline by `seq`, transcript by `start_ms`), `_append_timeline()` `main.py:519-529`, `_broadcast()` above.
- **Pydantic validators** `main.py:56-258` mirror shared types (extra=forbid) + `IncidentCreate`/`IncidentPatch`/`ParticipantCreate`/`ActionUpdateStatus`; `model_rebuild()` loop `main.py:255-261`.
- **Gap Detection** `main.py:555-646` `_detect_and_store_gaps()`:
  - Deletes old `gap-auto-%` `main.py:558-564`
  - ConflictingInfo via `%` regex across facts: if ≥2 facts have `%` nums with ≥2 distinct values → `gap-auto-conflict-pct` high `main.py:570-589`
  - MissingOwner for any `ActionItem` with no `ownerId/ownerName` and not Done/Overdue → `gap-auto-missing-owner-{id}` `main.py:592-605`
  - StaleAction if `age>600s` or `dueAt` overdue → `gap-auto-stale-{id}` medium/high `main.py:607-620`
  - UnverifiedAssumption for each `Active` hypothesis → `gap-auto-unverified-{id}` `main.py:622-633`
  - Inserts + appends `gap_detected` timeline `main.py:635-646`
- **Cognition Inline** `main.py:652-921` `_run_cognition(segment, incident_id)` deterministic for fixture:
  - `fixture_map` `main.py:659-664`: `u-001→fact:12pct`, `u-002→fact:replica`, `u-003→fact:5xx`, `u-004→hypothesis:deploy`, `u-005→fact:tickets`, `u-007→decision:rollback`, `u-008→fact:2pct`, `u-010→action:jira`, `u-012→action:comms`
  - Creates `FactModel`/`HypothesisModel`/`DecisionModel`/`ActionItemModel`/`ToolEventModel` + timeline entries `fact_created`/`hypothesis_created`/`decision`/`action_created`/`tool` per branch `main.py:667-839`
  - `u-011` mutates `action-jira-replica` to `requires_confirmation=True` and flips `ToolEvent` to `requiresApproval` `main.py:822-841`
  - Chatter `u-006/u-009` no-op `main.py:843`
  - Regex fallback `main.py:847-918`: `_RE_HYPOTHESIS`, `_RE_DECISION`, `_RE_ACTION_JIRA`, `_RE_ACTION_COMMS`, `_RE_ERROR_RATE/PCT` branching to create corresponding rows.
- **Endpoints**:
  - `GET /health` `main.py:926-936` → `{status, postgres, redis}` (redis `mock|ok|unavailable`)
  - `GET /tools/status` `main.py:939-948` → `live|mock` per env var presence (`JIRA_URL`, `SLACK_TOKEN`, `PAGERDUTY_KEY`, `DATADOG_API_KEY`, `DEEPGRAM_API_KEY`, `AGORA_APP_ID`)
  - `POST /incidents` `main.py:950-973` → create `IncidentModel`+`TimelineSeqModel`, `system` timeline, broadcast snapshot, returns `incident`
  - `GET /incidents` `main.py:976-991` → list with participants
  - `GET /incidents/{id}` `main.py:994-1008` → single incident
  - `PATCH /incidents/{id}` `main.py:1011-1034` → title/desc/status/severity/summaryMarkdown + timeline + broadcast
  - `POST /incidents/{id}/participants` `main.py:1037-1056` → add participant + `system` timeline + broadcast
  - `GET /incidents/{id}/snapshot` `main.py:1059-1063` → `_detect_and_store_gaps` + `_build_snapshot` (canonical aggregate)
  - `POST /incidents/{id}/transcript` `main.py:1066-1106` → validate `TranscriptSegment`, insert `TranscriptSegmentModel` + `transcript` timeline, `updated_at`, `_run_cognition`, `_detect_and_store_gaps`, flush, build+**broadcast** `{"type":"snapshot",...}`, returns `{ok, segmentId, snapshot}`
  - `POST /incidents/{id}/actions/{actionId}/approve` `main.py:1110-1145` → clears `requires_confirmation`, `Open→InProgress`, `action_updated` timeline, creates `ToolEvent` `success` with mock `PAY-XXXX` + `tool` timeline, gaps, broadcast (legacy alias `POST /approve/{actionId}` `main.py:1148-1150`)
  - `POST /incidents/{id}/actions/{actionId}/update-status` `main.py:1153-1166` → set `ActionStatus`, `action_updated` timeline, gaps, broadcast
  - `POST /incidents/{id}/summary` `main.py:1169-1254` → `_detect_and_store_gaps`, build snapshot, render markdown lines (Timeline last 20, Facts/Hyps/Decisions/Actions/Gaps/Unresolved/Participants `main.py:1187-1244`), save `summary_markdown`, `summary` timeline, broadcast, returns `{incidentId, markdown}`
  - `WS /ws/incidents/{id}` `main.py:1260-1400+` → `accept`, auto-create placeholder incident if missing `main.py:1264-1277`, `add to _ws_connections`, `send_json {"type":"snapshot", snapshot}`, loop `receive_json` (if any), handle `ping/pong`, on disconnect remove; Redis pubsub fanout also bridged (if enabled).

### 4.4 Cognition Engine `apps/api/cognition.py:1-536`

- **Modes** `cognition.py:1-13`: LLM if `OPENAI_API_KEY` set else heuristic (keyword + fixture). Exports `extract`, `generate_summary`, `detect_conflicts`, `detect_gaps`.
- **Prompt loading** `cognition.py:30-66`: `_PROMPT_DIR=../prompts`, `_load_extractor_prompt()`/`_load_summary_prompt()` via `yaml.safe_load`.
- **OpenAI config** `cognition.py:71-74`: `OPENAI_MODEL_EXTRACT=gpt-4o-mini`, `OPENAI_MODEL_SUMMARY=gpt-4o`, `LLM_ENABLED=bool(API_KEY)`.
- **`_call_openai()`** `cognition.py:88-106`: `POST https://api.openai.com/v1/chat/completions` with `response_format:json_object`, `temperature=0`.
- **`extract_llm()`** `cognition.py:109-163`: builds user message with `new segment + recent 5 + existing facts/hyps` + few-shots injected into system, `json.loads`, fallback to `{"extractions":[]}`.
- **Heuristic** `cognition.py:169-327`: `_FIXTURE_FACTS` (u-001/u-002/u-005/u-008), `_FIXTURE_HYPOTHESIS`, `_FIXTURE_DECISION`, `_FIXTURE_ACTIONS`, regexes `_RE_ERROR_RATE/_RE_PCT/_RE_REPLICA/_RE_5XX/_RE_TICKETS/_RE_HYPOTHESIS/_RE_DECISION/_RE_ACTION_JIRA/_RE_ACTION_COMMS/_RE_APPROVAL`. `extract_heuristic(segment)` `cognition.py:195-327` returns deterministic single `extractions` per sid, generic fallback otherwise.
- **`extract()`** `cognition.py:333-355`: tries heuristic first; if empty and `LLM_ENABLED` calls `extract_llm`.
- **Summary** `cognition.py:361-477`: `generate_summary(snapshot)` dispatches to `_generate_summary_llm` (calls `_call_openai` with `gpt-4o`, parses `{markdown, ttsScript, unresolvedRisks}`) or `_generate_summary_template` (renders `# Incident {id} — title` + Facts/Hyps/Decisions/Actions/Unresolved + TTS script `60s` plain text truncated 800 chars `cognition.py:411-477`).
- **Conflict/Gap detectors** `cognition.py:483-535`: `detect_conflicts(facts)` same `%` heuristic as API; `detect_gaps(snapshot)` missing-owner + unverified hypothesis.

### 4.5 Tool Adapters `apps/api/tools.py:1-249`

- **Abstract** `tools.py:25-60`: `ToolAdapter {create, post, trigger, _require_approval_check(), _log()}`. If `ctx.requiresConfirmation` true → returns `requiresApproval` ToolEvent `tools.py:42-56`.
- **Mocks** `tools.py:62-189`: `MockJira` (create_issue), `MockSlack` (send_message→channel `#incident-comms`), `MockPD` (trigger_page), `MockDatadog` (annotate) — each logs and returns `{id, incidentId, tool, action, status: success|requiresApproval, payload, result:{key/url|ts|incident_key|annotation_id}, requiresApproval, actionItemId, createdAt}`. Registry `ADAPTERS` `tools.py:192-199` includes `github→MockJira`. `invoke_tool(tool, action, payload, ctx)` `tools.py:202-224` dispatches on action strings; `create_tool_event_record()` `tools.py:227-248`.

### 4.6 TTS `apps/api/tts.py:1-138`

- **Providers** `tts.py:27-105`: abstract `TTSProvider.synthesize(text)->bytes`; `MockTTSProvider` (empty), `OpenAITTSProvider` (`POST /v1/audio/speech` model `tts-1` voice `alloy`), `ElevenLabsTTSProvider` (`/v1/text-to-speech/{voiceId}` `eleven_monolingual_v1`). `get_tts_provider()` `tts.py:98-104` based on `TTS_PROVIDER` env.
- **Cache** `tts.py:107-138`: `TTS_CACHE_DIR=.tts_cache`, `_cache_key=sha256(provider:text)[:16]`, `synthesize_cached()` hits file cache `.mp3` before synthesizing.

### 4.7 Error/Embedding

- `apps/api/errors.py` + `apps/api/embeddings.py` (cosine sim via embeddings or keyword for conflict detection — stubbed by regex heuristic; present for PLAN phase D LiteLLM abstraction `PLAN.md:78`).

---

## 5. Perception Worker — `apps/worker/main.py:1-734` (FastAPI `:8001`)

**Flow** `main.py:2-8` & `PLAN.md:59-64`: `Browser Agora mic -> Agora channel -> Worker joins as bot (agora-python-server-sdk) -> PCM 16k -> VAD -> Deepgram WS (interim/final) -> speaker map -> POST /transcript` with browser-relay fallback; mock-runnable without keys.

- **Env** `main.py:52-61`: `API_URL` (default `http://api:8000`), `AGORA_APP_ID/CERT`, `DEEPGRAM_API_KEY`, `WORKER_PORT=8001`, flags `MOCK_DEEPGRAM`, `MOCK_AGORA` + log `main.py:61`.
- **App** `main.py:66-75`: `FastAPI(title="Agora Perception Worker", version="0.2.0")` + CORS `*`.
- **SileroVAD** `main.py:80-155`: ONNX runtime loader `main.py:92-111` (downloads `silero_vad.onnx` if absent), `is_speech(pcm_bytes)` `main.py:113-145` (float32/32768, pad 512, `session.run`, threshold 0.5) fallback energy heuristic `non_zero ratio>0.05`; `filter()` `main.py:147-152`.
- **DeepgramStreamer** `main.py:160-249`: `WS_URL` `wss://api.deepgram.com/v1/listen?model=nova-2&encoding=linear16&sample_rate=16000&channels=1&interim_results=true&endpointing=300&smart_format=true` `main.py:172`; `connect()` `main.py:180-194` via `websockets` + `Authorization: Token`, `send_pcm()` `main.py:196-203`, `receive_loop(on_transcript)` `main.py:205-235` parses `type:Results -> transcript/is_final/confidence/speaker`, `mock_transcribe()` stub `main.py:245-246`.
- **AgoraBot** `main.py:254-339`: imports `agora`/`agora_python_server_sdk`/`agora_rtc_sdk` if present `main.py:270-284`, `join(channel, uid, token)` `main.py:286-308` (mock if no APP_ID or SDK missing), `leave()` `main.py:310-321`, `_on_pcm_frame` → `vad.filter` `main.py:323-328`, `status` property `main.py:331-336`.
- **Diarization** `main.py:344-402`: regexes `ENROLL_RE: ^\s*This is\s+Name , Role` `main.py:344` and `IAM_RE: ^\s*I am\s+Name , Role` `main.py:345`; `_participant_cache`, `_enrollment_map`; `_fetch_participants(incident_id, force)` `main.py:352-371` GETs `API_URL/incidents/{id}` cached 30s; `_resolve_speaker(segment, incident_id)` `main.py:374-402` maps via regex + `enrollment_map`, role_map `sre→SRE` etc.
- **Forward** `main.py:408-430`: `_forward_to_api(incident_id, segment, max_retries=3)` POST `API_URL/incidents/{id}/transcript` with exponential backoff 0.4→0.8→1.6s, raises 502 after retries.
- **Segment builder** `main.py:433-458`: `_build_segment_from_payload(payload, incident_id)` handles `segment/transcript` shapes, strips `audioBase64`, fills defaults (`id seg-`, `isFinal True`, `startMs 0`, `endMs start+1000`, `confidence 0.9`, `language en-US`, `createdAt now`), calls `_resolve_speaker`.
- **Tokens** `main.py:464-491`: `_generate_agora_token(channel, uid, role, expire=3600)` → mock `base64(sha256(appId:channel:uid:expire))[:32]` if `MOCK_AGORA`, else `agora_token_builder.RtcTokenBuilder.buildTokenWithUid` with hmac fallback.
- **Endpoints**:
  - `GET /` `main.py:510-514` → `{service, version, mode:mock|live|mixed, docs, health}`
  - `GET /health` `main.py:517-533` → `{status, mode, api_url, api_reachable (httpx GET /health 2s), deepgram:live|mock, agora:live|mock-browser-relay, agora_bot:status, vad:silero-onnx|energy-heuristic, uptime_s}`
  - `GET /config` `main.py:536-544` → debug dump of modes/accepts/forward target
  - `GET /agora/token?channel&uid&role&expire` `main.py:547-552` + alias `token/` `main.py:556-564`
  - `POST /relay` `main.py:567-625` — browser-facing: requires `incidentId`, fetches participants, if `audioBase64` branch decodes base64 → VAD filter if `pcm` mime → live Deepgram if key else mock; if also `text/segment` forwards transcript; else transcript JSON path builds segment → forwards to API, returns `{ok, mode, segmentId, forwarded}`
  - `WS /ws/ingest?incidentId=` `main.py:628-723` — browser streams `audio bytes` (VAD→Deepgram or mock interim) or `JSON` (`transcript/segment/text`), handles `ping/pong`, `isFinal` gating, `type:"ack"` with forwarded result; error shapes for missing incidentId/unknown.
  - `POST /agora/bot/join` `main.py:725-728` / `leave` `main.py:731-734`
- **Deps** `apps/worker/requirements.txt` mirrors API + `onnxruntime`, `websockets`.

---

## 6. Frontend — `apps/web/` (React Vite + Zustand + ws + Tailwind)

### 6.1 Build `apps/web/package.json:1-32`, `apps/web/vite.config.ts`, `apps/web/tsconfig.json`, `apps/web/tailwind.config.js`, `apps/web/index.html`

Scripts `web/package.json:6-11`: `dev: vite --host 0.0.0.0 --port 5173`, `build: tsc && vite build`, `lint/typecheck`. Deps: `react`, `react-dom`, `zustand`, `@agora/shared`, `agora-rtc-sdk-ng`, `clsx`, `tailwind-merge`.

### 6.2 State `apps/web/src/store/incidentStore.ts:1-177`

- Types `incidentStore.ts:4-52` mirror shared (Incident/TranscriptSegment/Fact/Hypothesis/Decision/ActionItem/Gap/TimelineEvent/ToolEvent/Snapshot).
- `API` `incidentStore.ts:72-77`: `VITE_API_URL` env || `/api` if port 5173 else `http://localhost:8000`.
- Store `IncidentState` `incidentStore.ts:55-70`: `snapshot`, `incidentId`, `ws`, `wsConnected`, `error`, `speaking`; methods `connect(incidentId)` `incidentStore.ts:87-123` (`WebSocket(wsUrl=API http→ws + /ws/incidents/{id})`, `onopen/onmessage(on snapshot)/onclose(reconnect 3s)/onerror`), `disconnect()` `incidentStore.ts:125-129`, `approveAction(actionId)` `incidentStore.ts:133-145` tries `POST /incidents/{id}/actions/{id}/approve` fallback to `/approve/{id}`, `updateActionStatus(actionId, status)` `incidentStore.ts:147-160` POST `/.../update-status`, `generateSummary()` `incidentStore.ts:162-174` POST `/summary`, `setSpeaking` `incidentStore.ts:176`.

### 6.3 App Shell `apps/web/src/App.tsx:1-154`

- Tabs `App.tsx:16-25`: `transcript💬`, `facts✅`, `hypotheses❓`, `decisions⚖️`, `gaps⚠️`, `timeline📜`, `tools🔧`, `summary📝`.
- `Sidebar` `App.tsx:27-61` with counts badge.
- `MainPanel` `App.tsx:63-88` switches panel per tab; null snapshot shows "Connecting...".
- `App` `App.tsx:90-153`: `useIncidentStore` + `activeTab` state `transcript` + `inputId` default `payment-001`, `useEffect` auto `connect(inputId)` on mount, `handleConnect`, `counts` from `snapshot.transcript|facts|hypotheses|decisions|gaps|timeline|toolEvents`, renders `VoiceRoom` top bar `App.tsx:120` + incident selector input+Connect button `App.tsx:123-143` + `Sidebar`+`MainPanel`.

### 6.4 Components `apps/web/src/components/` + `apps/web/src/lib/`

- `VoiceRoom.tsx` — Agora RTC join/mute bar, participants with role badges, speaking indicator, token fetch from `worker/agora/token`.
- `Transcript.tsx` — virtualized list of `TranscriptSegment`, speaker/role/confidence, `isFinal` dimming.
- `FactsPanel.tsx` — Facts columns (Reported/Corroborated/Confirmed/Contradicted), conflict red highlight + confidence bar, sourceSegmentIds citation.
- `HypothesesPanel.tsx` — Active/Disproven/Confirmed, confidence bar.
- `DecisionsPanel.tsx` — Proposed/Approved/Reverted + decidedBy.
- `ActionKanban.tsx` — Kanban Todo/Doing/Done, owner avatar, `requiresConfirmation` badge, Approve button → `approveAction`, status dropdown → `updateActionStatus`, overdue pulse.
- `GapsPanel.tsx` — GapKind badges + severity color, message + relatedIds.
- `Timeline.tsx` — vertical timeline sorted by `seq`, type icons, payload JSON preview.
- `ToolEvents.tsx` — tool dots (pending/success/failed/requiresApproval), Jira key links, payload/result.
- `SummaryPanel.tsx` — markdown render + Generate Summary button + TTS playback + export PDF.
- `Toast.tsx`, `ErrorBoundary.tsx`.
- `lib/tts.ts` — TTS playback + `synthesize_cached` fetch.
- `lib/tools.ts` — tool status dots + adapter helpers.
- `lib/pdf.ts` — markdown→PDF export (jsPDF / browser print).
- `lib/utils.ts` — `cn(clsx+tailwind-merge)` etc.
- Styles `src/index.css` (Tailwind), entry `src/main.tsx`.

---

## 7. Prompts — `prompts/`

### 7.1 `extractor.yaml:1-156`

- `model: gpt-4o-mini`, purpose Real-time utterance extraction `extractor.yaml:3-5`, guardrails `1-4` `extractor.yaml:6-10`: Never assert RCA, confidence calibrated (0.9+ only corroborated, 0.6-0.8 single, never >0.95), No source→Hypothesis, Contradicted must cite ids.
- **System** `extractor.yaml:11-42`: Classification rules Fact/Hypothesis/Decision/ActionItem/Chatter/ToolRequest with status enums, confidence tiers, `requiresConfirmation` for dangerous Decisions/Actions (rollback, disable payments, revert DB, failover, mass notification, "require approval before it posts" → true), cite `sourceSegmentIds`, JSON-only no CoT.
- **Few-shots** `extractor.yaml:44-128` (11 examples mirroring `payment_outage.json` utterances u-001→u-012 including `ActionItem ownerRole:Backend`, `Chatter` for u-006).
- **Schemas** `extractor.yaml:130-156`: `input_schema {incidentId, newSegment, recentSegments, existingFacts, existingHypotheses}`, `output_schema {extractions: [{kind:Fact|Hypothesis|Decision|ActionItem|Chatter, statement, title, status, confidence, sourceSegmentIds, ownerName/ownerRole, requiresConfirmation, toolKey, dueAt}]}`. Consumed by `cognition.py:_load_extractor_prompt` `cognition.py:45-52`.

### 7.2 `summary.yaml:1-49`

- `model: gpt-4o`, purpose Final summary on `POST /incidents/{id}/summary` `summary.yaml:2-4`.
- **System** `summary.yaml:6-20`: structure `# Incident {title} — Summary / Timeline 3-5 bullets / Facts split / Hypotheses / Decisions / Action Items (owner/status/overdue) / Gaps & Unresolved Risks / Recommendation / Next Steps`; rules Never invent RCA, cite segment ids, flag contradictions, ~300 words, also 60s TTS plain text 2-3 sentences.
- **Schemas** `summary.yaml:22-43`: inputs `{incident, facts, hypotheses, decisions, actions, gaps, timeline}`, outputs `{markdown, ttsScript maxLength 800, unresolvedRisks[]}`. TTS block `summary.yaml:44-49`: `provider_env TTS_PROVIDER`, `voice_env TTS_VOICE`, `cache true`, `maxChars 800`, `publishToAgora true` (unmute bot 10s scheduler every 5m or 3+ facts per `PLAN.md:99-101`). Consumed by `cognition.py:_load_summary_prompt` `cognition.py:55-62` and `tts.py`.

---

## 8. Demo & Verification — `demo/`

### 8.1 Fixture `demo/payment_outage.json:1-45`

- `incident: {id:payment-001, title:"Payment checkout outage — error rate spike", severity:SEV1, description:"Checkout error rate 12%...", createdAt:2026-09-02T14:00}` `payment_outage.json:2-8`
- `participants[4]` `payment_outage.json:9-14`: Priya SRE, Alex Backend, Jordan Support, Maya Comms.
- `utterances[12]` `payment_outage.json:15-28` (ids u-001→u-012, speakerId/Name/Role, text, startMs 0→38500, all `isFinal:true`): covers enrollment, 12% spike, DB lag 45s, 5xx 340, deploy retry hypothesis, tickets flood, comms chatter, rollback decision, conflicting 2% vs 12%, replica Jira, approval gate, comms owner gap.
- `expectedExtractions` `payment_outage.json:29-43`: `facts 4, hypotheses 1, decisions 1, actionItems 2, conflicts 1, gaps[3] (ConflictingInfo error rate, MissingOwner comms, UnverifiedAssumption deploy), overdueActionTitle="Fix DB replica lag...", requiresConfirmationAction:true, timelineMinLength 12, transcriptReplayRate 1.5x`.

### 8.2 Seeder `demo/seed.py:1-103`

- `load_fixture()` `seed.py:20-22`, `post_transcript(api_url, incident_id, utterance)` `seed.py:24-52` builds `segment {id, incidentId, speakerId, speakerName, role, text, isFinal, startMs, endMs, confidence 0.92, createdAt now}` POST `api_url/incidents/{id}/transcript`.
- `ensure_incident()` `seed.py:54-68` POST `api_url/incidents {title, severity}`.
- `main()` `seed.py:70-102` argparse `--incident default payment-001`, `--api-url http://localhost:8000`, `--replay-rate 1.5`, `--dry-run`, `--fixture`; loops utterances sleeping `(gapMs/1000)/replay_rate` `seed.py:88-92`, prints `[ts] speaker: text`, posts, finally prints Done + expected JSON.

### 8.3 Tests & Handoff Contracts

- Contracts `PLAN.md:11-15` + `README.md:61-65`: `Worker → API: POST /incidents/{id}/transcript (TranscriptSegment)`, `API → Web: WS /ws/incidents/{id} fanout (timeline/gaps/actions)`, Cognition reads Postgres fact store writes via internal API (inline in API for MVP).
- `PLAN.md:106-109` verification `pytest tests/e2e/test_payment_scenario.py` asserts 4 facts/1 hypothesis/1 conflict/1 overdue/timeline length/tool approval; `apps/api/tests/` has `test_models.py`, `test_integration.py`, `test_e2e_payment.py`, `test_cognition.py`, `conftest.py`.
- Demo seed triggers `_run_cognition` + `_detect_and_store_gaps` + `_broadcast` → live dashboard. `demo/e2e_test.py` mirrors assertions.
- Verification checklist `PLAN.md:128-136`: `docker-compose up` 4 healthy, transcript <1s, fact/hypothesis split, conflict flagged, overdue pulsed, TTS audible, Jira blocked until approval, final summary lists risks.

---

## 9. Service & API Summary Table

| Service | Port | Entrypoint | Health |
|---------|------|------------|--------|
| postgres | 5432 | `postgres:15-alpine` | `docker-compose.yml:13 pg_isready` |
| redis | 6379 | `redis:7-alpine --appendonly yes` | `docker-compose.yml:25 redis-cli ping` |
| api | 8000 | `apps/api/main.py:app` uvicorn | `GET /health` `main.py:926` |
| worker | 8001 | `apps/worker/main.py:app` uvicorn | `GET /health` `main.py:517` |
| web | 5173 | `apps/web/src/main.tsx` vite | `vite dev server` `docker-compose.yml:92` |

**Key API routes** (full list `apps/api/main.py:924-1400`):
- `GET /health`, `GET /tools/status`, `POST /incidents`, `GET /incidents`, `GET /incidents/{id}`, `PATCH /incidents/{id}`, `POST /incidents/{id}/participants`, `GET /incidents/{id}/snapshot`, `POST /incidents/{id}/transcript`, `POST /incidents/{id}/actions/{id}/approve` (+ legacy alias), `POST /incidents/{id}/actions/{id}/update-status`, `POST /incidents/{id}/summary`, `WS /ws/incidents/{id}`.
- **Worker routes**: `GET /`, `GET /health`, `GET /config`, `GET /agora/token`, `POST /relay`, `WS /ws/ingest`, `POST /agora/bot/join|leave`.

---

## 10. Orchestration Model `PLAN.md:3-14`

5 specialist sub-agents in parallel under main orchestrator (Muse Spark):
- **A: Repo Scaffold & Shared Types** — pnpm/turborepo, docker-compose, Zod/Pydantic, .env.example, CI lint/typecheck `PLAN.md:18-39`
- **B: Backend API + State + WS** — FastAPI/SQLAlchemy/Postgres/Redis, endpoints/state machine (append-only timeline, materialized views, optimistic locking) `PLAN.md:41-56`
- **C: Perception Pipeline** — Agora RTC SDK NG + Deepgram Nova-2 Streaming + Silero VAD + diarization enrollment `PLAN.md:58-70`
- **D: Cognition Engine** — GPT-4o-mini realtime + GPT-4o summary, 3 LLC calls parallel <1.5s, rules engine, prompts YAML `PLAN.md:72-84`
- **E: Frontend + Tools + TTS** — React Vite/shadcn/Zustand/ws, panes + ToolAdapter mocks + TTS every 5m `PLAN.md:86-103`
- **Phase 6: Demo Seeder + E2E** converge `PLAN.md:105-109`; Risks `PLAN.md:117-121`; Execution order `PLAN.md:123-126`.

---

## 11. Notable Decisions & Guardrails

- Mock-first: worker & API run without `AGORA_APP_ID`/`DEEPGRAM_API_KEY`/`OPENAI_API_KEY` (browser relay + heuristic + mock TTS) — `apps/worker/main.py:58-61`, `apps/api/cognition.py:74`, `apps/api/tts.py:99-104`.
- No RCA without source; No source→Hypothesis; Confidence 0.9+ only if corroborated; never >0.95 — `prompts/extractor.yaml:6-9`, `prompts/extractor.yaml:31-35`.
- Approval gate: `requiresConfirmation` blocks `ToolAdapter` until `POST /approve` — `tools.py:42-56`, `main.py:1110-1145`.
- Gap `severity` default `medium`; `ConflictingInfo` → `high`, `StaleAction` overdue `high` else `medium` — `main.py:583-618`.
- Timeline `seq` monotonic via `TimelineSeqModel` SELECT FOR UPDATE — `main.py:339-350`.
- Snapshot is source of truth over WS — `main.py:535-549`, `incidentStore.ts:97-105`, `index.ts:204-215`.

