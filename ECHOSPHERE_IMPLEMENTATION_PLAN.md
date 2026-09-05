# EchoSphere — PRD → Implementation Gap Plan

> Source of truth for scope: `EchoSphere_PRD.md`. This file maps every PRD requirement to current
> code state and tracks what's being built, in what order. Supersedes the old `PLAN.md` (which
> described the pre-PRD "Agora" prototype — Deepgram-based, no pgvector, no RTM). `PLAN.md` and
> `context.md` remain useful as a record of the prototype's internals; this file is the live plan.

## Legend
`[x]` done · `[~]` partially done, needs work · `[ ]` not started

## Phase 0 — Baseline (already true before this plan)
Prototype (`apps/api`, `apps/worker`, `apps/web`, `packages/shared`) has: Postgres-backed incident
state (Incident/Participant/TranscriptSegment/Fact/Hypothesis/Decision/ActionItem/Gap/
TimelineEvent/ToolEvent), plain-WebSocket snapshot fanout, Deepgram-based worker STT, LLM (OpenAI)
extraction + summary, mock tool adapters (Jira/Slack/PagerDuty/Datadog/GitHub), approval gate,
Redis pubsub. All previously found bugs (relative imports, tz-naive datetime crash, missing
`aiosqlite`, broken test fixtures, tsconfig composite) are fixed — 52/52 backend tests + E2E
fixture scenario pass, frontend typechecks/builds clean.

## Phase 1 — Realtime: Agora Conversational AI (MANDATORY per hackathon organizers) — CORE DONE
Architecture confirmed against Agora's docs (docs.agora.io/en/ai, .../conversational-ai/rest-api):
Agora CAI is a managed agent that joins the RTC channel and runs ASR→LLM→TTS per turn. Each slot
(asr/llm/tts) is independently `credential_mode: managed` (Agora-managed vendor, zero extra keys —
organizers offer Deepgram/OpenAI/MiniMax) or pointed at our own endpoint. **Key finding: the LLM
slot supports a custom OpenAI-compatible webhook**, so our own cognition engine (Claude) stays the
in-room conversational brain instead of a generic Agora-managed persona — this was the critical
open question and it resolves cleanly. Transcript delivery is architecturally separate from the
LLM webhook: Agora CAI publishes speaker-labeled ASR results (up to 3 simultaneous speakers) as
**Signaling (RTM) channel messages** — confirms RTM is the right transport for both transcript
egress and state sync, unifying what were two separate research threads.

- [x] `apps/api/agora_conversational_ai.py` — REST client for agent join/leave
      (`POST .../conversational-ai-agent/v2/projects/:appid/join` and `.../agents/:agentId/leave`),
      builds the exact documented request shape (asr/llm/tts sections), Basic auth via
      `AGORA_CUSTOMER_ID`/`AGORA_CUSTOMER_SECRET`. Defaults: ASR+TTS `managed` (Deepgram/MiniMax,
      no extra keys), LLM `custom` → our own webhook. Mock-mode fallback when credentials absent
      (matches the rest of the codebase's mock-first convention). **Not live-tested** — no Agora
      account/credentials available in this session; request/response shapes are built exactly per
      Agora's documented schema, not guessed, but need verification against a real account.
- [x] `POST /agora/llm/chat/completions` (`apps/api/main.py`) — the custom-LLM webhook Agora calls;
      SSE-streams `chat.completion.chunk` objects per the documented contract, backed by
      `cognition.generate_voice_reply()` (new, Claude-backed, separate from the structured
      extraction path — this endpoint produces the AI's spoken conversational replies only).
      Fully tested (`tests/test_agora_conversational_ai.py`) — request/response shape verified
      without needing live Agora infra, since it's our own endpoint being called in the documented
      shape.
- [x] `POST /incidents/{id}/agora-agent/join` / `.../leave` — orchestrates agent lifecycle per
      incident; RTC token minting stays in the worker (already has a token builder) rather than
      duplicated here. Tested in mock mode.
- [ ] **Signaling (RTM) transcript subscription in the worker** — NOT implemented. This is what
      would replace the Deepgram/VAD/PCM-relay path in `apps/worker/main.py` (~lines 160-340) as
      primary: subscribe to the incident's Signaling channel, parse speaker-labeled ASR messages,
      forward to the existing (unchanged) `POST /incidents/{id}/transcript`. Deferred because it
      needs the real Agora RTM SDK (not pure REST) to hold a live subscription, which can't be
      meaningfully written or tested without a live Agora account in this session — implementing
      it blind risks the same "confidently wrong API guess" trap the auth-mechanism research
      already caught once. Deepgram-relay path kept as the interim/fallback transcript source.
- [x] `.env.example` — `AGORA_CAI_ASR_MODE`, `AGORA_CAI_TTS_MODE`, `AGORA_CAI_LLM_MODE`,
      `AGORA_CUSTOM_LLM_URL` added alongside the existing `AGORA_CUSTOMER_ID`/`AGORA_CUSTOMER_SECRET`
      (confirmed correct — same Basic-auth RESTful-API credential pair Agora uses across STT/
      Signaling/Conversational-AI products).

**Side discovery while wiring this in:** `apps/api/tools.py` (Slack/Jira/PagerDuty/Datadog mock
adapters), `apps/api/embeddings.py` (semantic similarity), and `apps/api/cognition.py` (the entire
LLM classifier — extraction AND summary) were **never imported by `main.py`** — fully dead code
despite being fully built. Fixed as part of this session: `tools.invoke_tool` now backs the new
stall-nudge feature (Phase 4), `cognition.extract()` now backs a new LLM-classifier fallback path
in `_run_cognition` (see Phase 4a below) so the Claude integration in Phase 2 is actually reachable,
and `embeddings.py` now backs cross-incident precedent recall (Phase 4, 8.10). `cognition.py`'s
`generate_summary()`/`_generate_summary_llm()` (Claude-backed) is **still not wired into the
`/summary` endpoint**, which has its own separate hand-rolled markdown template — noted as a
follow-up, not yet fixed.

## Phase 4a — LLM Classifier now actually in the request path (new, not in original phase list)
- [x] `_run_cognition`'s fixture-map + regex-heuristic path is unchanged (demo fixture still 100%
      deterministic), but anything matching neither now falls through to a new
      `_run_llm_extraction()` which calls `cognition.extract()` (heuristic → Claude LLM) and
      materializes Fact/Hypothesis/Decision/ActionItem rows from the result. Tested with a mocked
      `cognition.extract` (`tests/test_intelligence.py::TestLLMExtractionFallback`) to prove the
      wiring works without needing a live key.

## Phase 2 — LLM provider: swap to Claude (PRD §15 names "Claude / LLM layer" explicitly) — DONE
- [x] `apps/api/cognition.py`: Claude backend added via Anthropic SDK (`_call_claude`, structured
      JSON output via `output_config.format`), `LLM_PROVIDER=claude|openai` switch, defaults to
      Claude when `ANTHROPIC_API_KEY` set. Extraction model `claude-sonnet-5`, summary model
      `claude-opus-5`. OpenAI path kept as alternate provider.
- [x] `.env.example`: `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL_EXTRACT`,
      `ANTHROPIC_MODEL_SUMMARY`
- [x] Heuristic-first behavior (mock-first principle) intact — verified via full 52-test suite pass
- [ ] **Not live-tested** — no `ANTHROPIC_API_KEY` available in this environment. Code reviewed
      against the `claude-api` skill's Python reference but needs a real key to confirm end-to-end.
- **Resolved:** Agora Conversational AI Engine's LLM slot supports a custom OpenAI-compatible
      webhook (see Phase 1) — Claude runs both as the in-call conversational LLM (via
      `generate_voice_reply` behind `/agora/llm/chat/completions`) and as the structured-extraction
      classifier (`extract`/`extract_llm`, now reachable via `_run_llm_extraction`, Phase 4a). No
      conflict; these were never mutually exclusive.

## Phase 3 — Data model alignment with PRD vocabulary — MOSTLY DONE
- [x] `verification_status` (`verified|contradicted|unverified|unknown|unavailable`) added to
      Fact/Hypothesis models, Pydantic schemas, converters, and shared TS/Python mirrors. Field
      exists and round-trips; **not yet populated by a real verification engine** (Phase 5) — sits
      at the "unverified" default until that lands.
- [x] `Conflict` promoted to a first-class model (`apps/api/models.py: ConflictModel`) with
      `claim_a`/`claim_b`/`status[OPEN|UNDER_REVIEW|RESOLVED|DISMISSED]`/`resolution`/
      `verification_required`, wired into `_detect_and_store_gaps` (creates/updates
      `conflict-auto-pct` alongside the existing `ConflictingInfo` Gap), exposed in
      `IncidentSnapshot.conflicts`, mirrored in shared TS/Python types. Covered by
      `tests/test_intelligence.py::TestConflictRecord`. Review-lifecycle transitions
      (OPEN→UNDER_REVIEW→RESOLVED/DISMISSED) have no endpoint yet — only auto-creation exists.
- [ ] `IncidentStatus` PRD vocabulary (`DETECTED→INVESTIGATING→MITIGATION_IN_PROGRESS→RECOVERY→
      RESOLVED→POSTMORTEM`) — **deliberately deferred**: current vocabulary
      (open/investigating/mitigated/resolved/closed) is functionally equivalent and renaming touches
      Pydantic validators, DB defaults, and the frontend; judged not worth the churn/regression risk
      this session. Revisit if a reviewer specifically checks for the literal PRD strings.

## Phase 4 — Intelligence engine modules (PRD §8) — DONE except cross-incident memory
- [x] 8.5 Assumption-Creep Detection — `_detect_and_store_gaps` computes a word-overlap mention
      count per Active hypothesis against all transcript segments, persists it to
      `Hypothesis.referenceCount`, and raises `Gap(kind=AssumptionCreep, severity=high)` at ≥3
      mentions. Verified emergent (not hardcoded) on the payment-outage fixture: fires at exactly
      3x for the "recent deploy" hypothesis.
- [x] 8.6 Duplicate-Work Detection — pairwise keyword-overlap check across open/in-progress
      Actions with different owners → `Gap(kind=DuplicateWork)`. Tested (positive + negative case).
- [x] 8.8 Stall Nudges — `_maybe_send_stall_nudge` sends one mock-Slack reminder per stale owned
      Action via `tools.invoke_tool` (this also fixed a pre-existing gap: `tools.py`'s adapters were
      dead code, never imported by `main.py`, until now), idempotent via a deterministic
      `tool-nudge-{actionId}` id. Tested for idempotency (two gap-detection passes → one nudge).
- [x] 8.9 Decision Hygiene — added `expected_outcome`/`risk`/`rollback_plan` fields to Decision;
      `Gap(kind=DecisionHygiene)` raised when a Decision is `Approved` without owner/outcome/risk/
      rollback filled in. Soft warning, not a hard block (matches PRD's "AI proposes, human
      disposes" — didn't want to break the existing approve flow this late without a UI to fill
      these fields in yet). Tested (positive + negative case).
- [ ] 8.10 Cross-Incident Memory — pgvector extension + embeddings table + precedent recall on
      new Hypothesis/Fact against past resolved incidents. **Not started** — biggest remaining
      infra lift in Phase 4 (Postgres image swap, embeddings model choice, docker-compose change).

## Phase 5 — Monitoring Verification (PRD §9.1, called out as "Key Differentiator")
- [ ] Verification engine: `Claim → query monitoring source (mock Datadog + real if configured) →
      CONFIRMED|CONTRADICTED|UNKNOWN|UNAVAILABLE`
- [ ] Wire into Fact/Hypothesis lifecycle + surfaced in snapshot/UI

## Phase 6 — Integrations direction fixes (PRD §11)
- [ ] PagerDuty: currently outbound-only (`trigger_page`); PRD wants it **inbound** — webhook
      endpoint ingesting alerts into incident state
- [ ] Datadog: currently outbound `annotate`; PRD wants it **inbound** for verification (Phase 5)
- [ ] Confluence: not implemented — in/out (postmortem publish + KB retrieval)
- [ ] Prometheus/Grafana: not implemented — alt monitoring source for Phase 5

## Phase 7 — Postmortem report fields (PRD §7 FR-06)
- [ ] Extend `cognition.py` summary template + `prompts/summary.yaml` to guarantee: Name,
      Severity, Start/End/Duration, Executive Summary, Timeline, Confirmed Facts, Hypotheses,
      Decisions, Actions+Owners, Resolution, Customer Impact, What Went Well/Wrong, Unresolved
      Risks, Lessons Learned

## Phase 8 — Frontend dashboard relayout (PRD §13)
- [ ] Replace tab-based `App.tsx` with persistent layout: header (Incident Overview | AI Status
      Update | Risk Indicators), 3-column (Live Timeline | Action Items | Conflict Alerts),
      bottom Incident Reports/Postmortem tabs
- [ ] New components: `IncidentOverview`, `AIStatusBanner`, `RiskIndicators`, `ConflictAlerts`
- [ ] Degraded-mode banner (AC-13): show when STT/LLM/monitoring unavailable

## Phase 9 — Security/Auditability (PRD §16)
- [ ] Minimal RBAC (Commander/Engineer/Viewer) — lightweight token/role header given hackathon
      timeline; document as MVP-simplified vs. full auth
- [ ] Audit trail already mostly covered by TimelineEvent/ToolEvent; verify completeness

## Acceptance criteria (PRD §19) cross-check
Tracked per-item as work lands; current pass/fail noted inline in commit messages and re-verified
with the existing `apps/api/tests` suite + new tests added per phase.

---
**Working order for this session:** Phase 2 (Claude swap) and Phase 4 (intelligence modules) and
Phase 3 (data model) first — self-contained, no external API research needed. Phase 1 (Agora
STT/RTM) proceeds in parallel once research returns. Phases 5-9 follow as time allows, in the
order listed.
