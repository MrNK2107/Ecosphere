# EchoSphere — Product Requirements Document

**Product:** EchoSphere — Real-Time AI Incident Commander  
**Team:** PANGnovates (Aman Singh, Paul Shervin P, Ganesh Kumar, Nanda Kishor Suresh Priya)  
**Hackathon:** Agora Hackathon 2026 — Round II  
**Category:** Real-Time AI Incident Commander  
**Primary Platform:** Agora (RTC / Real-Time STT / RTM)  
**Status:** Proposed / Hackathon MVP  
**Version:** 1.0 — 2026-09-05  
**Document Type:** Detailed PRD

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Product Vision & Principles](#3-product-vision--principles)
4. [Goals & Non-Goals](#4-goals--non-goals)
5. [Target Users](#5-target-users)
6. [Core Product Concept & System Flow](#6-core-product-concept--system-flow)
7. [Functional Requirements](#7-functional-requirements)
8. [AI Intelligence Engine](#8-ai-intelligence-engine)
9. [Validation, Safety & Verification](#9-validation-safety--verification)
10. [Incident State & Data Models](#10-incident-state--data-models)
11. [Integration Layer](#11-integration-layer)
12. [Data Ingestion & Event Architecture](#12-data-ingestion--event-architecture)
13. [Frontend Requirements](#13-frontend-requirements)
14. [Agora Technology Usage](#14-agora-technology-usage)
15. [Technology Stack](#15-technology-stack)
16. [Security, Auditability & Failure Handling](#16-security-auditability--failure-handling)
17. [MVP Scope & Phasing](#17-mvp-scope--phasing)
18. [Success Metrics](#18-success-metrics)
19. [Acceptance Criteria](#19-acceptance-criteria)
20. [Team Responsibilities](#20-team-responsibilities)
21. [Repository Structure](#21-repository-structure)
22. [Appendices](#22-appendices)

---

## 1. Executive Summary

### 1.1 One-Line Description
> A real-time AI Incident Commander that listens to live incident-room conversations, understands what is happening, verifies information, tracks actions and ownership, and maintains a structured source of truth for the entire incident.

### 1.2 Core Idea
Modern incidents are managed in live voice rooms with multiple engineers, operators, managers, and support. Facts mix with assumptions, responsibilities blur, decisions are untraceable, actions are forgotten, and conflicting information persists.

EchoSphere embeds an **AI Incident Commander** directly into the live Agora room. Instead of transcribing, it continuously:

`Listen → Transcribe (speaker-attributed) → Classify → Structure → Verify → Track → Detect → Summarize → Preserve`

**Outcome:** `Chaotic conversations → Structured incident intelligence → Aligned teams → Faster resolution`

### 1.3 Product Principle
> Build a genuinely good Incident Commander, not just a transcription tool. Actively bring structure and discipline while keeping humans in control.

---

## 2. Problem Statement

### 2.1 Problem
Critical information is lost inside chaotic incident conversations:

- High-volume, unstructured, overlapping speech
- Facts mixed with assumptions/hypotheses
- Important information buried
- Unclear responsibilities & ownership
- Poor decision traceability
- Unresolved tasks & delayed decisions
- Rework and poor incident outcomes

### 2.2 Why This Matters
Incident response is time-sensitive. Even with expertise and monitoring, teams lose time reconstructing:

| Question | Example Failure |
|---|---|
| What happened? | No single timeline |
| What is confirmed vs suspected? | Hypothesis treated as fact |
| Who is doing what? | Anonymous/duplicate tasks |
| What was decided? | Decisions not logged with rationale |
| What remains unresolved? | Gaps undetected |

**Impact:** Increased MTTR, degraded business continuity, repeated investigations.

---

## 3. Product Vision & Principles

EchoSphere functions as an **always-on AI teammate** inside the incident room.

**Principles:**
1.  **State > Transcript** — Transcript is evidence; structured incident state is the source of truth.
2.  **Evidence-based** — Distinguish confirmed vs assumed; verify against monitoring.
3.  **Accountability** — Every action has an owner, deadline, status.
4.  **Human-in-the-loop** — AI proposes, human disposes for critical actions.
5.  **Memory** — Incidents become institutional knowledge, not forgotten docs.

---

## 4. Goals & Non-Goals

### 4.1 Goals

| ID | Goal | Description |
|---|---|---|
| G1 | Real-Time Understanding | Understand live conversations as they happen |
| G2 | Structured Incident State | Convert unstructured speech → continuously updated structured state |
| G3 | Source of Truth | Single state: facts, hypotheses, decisions, actions, owners, timeline, risks, questions |
| G4 | Evidence-Based Management | Distinguish confirmed vs assumption; verify via monitoring |
| G5 | Action Accountability | Track actions, owners, deadlines, stalls |
| G6 | Faster Resolution | Reduce delays from information loss, rework, unclear ownership |
| G7 | Post-Incident Knowledge | Auto-preserve timeline, decisions, outcomes, lessons |

### 4.2 Non-Goals
- ❌ Completely replace human incident commander
- ❌ Autonomously execute dangerous production changes
- ❌ Blindly trust incident-room statements
- ❌ Act as conventional meeting transcription app
- ❌ Replace monitoring infra (Datadog/Prometheus/Grafana) or ticketing/chat (Jira/Slack/PagerDuty)
- ❌ Make irreversible decisions without human approval

---

## 5. Target Users

| Persona | Needs |
|---|---|
| **Incident Commander** | Overall visibility, decision tracking, ownership, timeline, unresolved issues, risk |
| **Engineers** | Relevant facts, assigned actions, current state, technical context |
| **Operations / SRE** | Monitoring signals, status, impact, investigation progress, escalation |
| **Support / Customer Teams** | Reliable updates, customer impact, status, ETA |
| **Engineering Managers / Leadership** | Concise summaries, severity, business impact, progress, resolution |

---

## 6. Core Product Concept & System Flow

### 6.1 Six-Stage Concept
```
Live Incident Conversation
        ↓
Real-Time Speech-to-Text (Agora STT)
        ↓
AI Intelligence Engine
        ↓
Structured Incident State
        ↓
Validation + Action Tracking
        ↓
Aligned Team + Faster Resolution
```

### 6.2 End-to-End Flow
```
Incident Participants → Agora RTC (Live Audio) → Agora Real-Time STT → Segmenter/Normalizer
        → AI Intelligence (Classifier, Ownership, State, Conflict, Verification, Memory, Orchestrator)
        → PostgreSQL + pgvector (Incident State / Actions / Verification)
        → Dashboard + RTM + Integrations (Slack/Jira/Datadog) → AI Voice Output
```

### 6.3 Central Loop: Chaotic Conversation → Auto Postmortem
```
CHAOTIC CONVERSATION → AGORA REAL-TIME → SPEECH→TEXT → AI INTELLIGENCE
  → [FACTS | ACTIONS | DECISIONS] → INCIDENT STATE → [VERIFY | DETECT | TRACK]
  → HUMAN APPROVAL → SAFE EXECUTION → RESOLVED → AUTO POSTMORTEM → CROSS-INCIDENT MEMORY
```

---

## 7. Functional Requirements

### FR-01 — Live Incident Room (Agora RTC)
**Shall** operate inside a live Agora incident room.
- Allow participants to join live room, bidirectional audio, active speaker detection
- AI joins as a participant
- **Agora RTC responsibilities:** audio transport, active speaker detection, AI participation

### FR-02 — Real-Time Speech-to-Text
**Shall** convert live speech → speaker-attributed transcripts.
- Requirements: real-time, speaker attribution, timestamps, interim + final transcripts
- Example:
  ```
  14:02:15  Raj: Payment API is returning 500 errors. [Fact]
  14:02:21  Priya: Latency increased by four seconds around 14:01. [Fact]
  14:02:31  Arun: The database might be the cause. [Hypothesis]
  ```
- **Critical distinction:** Observed Fact vs Hypothesis must be preserved.

### FR-03 — AI Incident Commander Presence
- Continuously listen, understand, extract, organize, validate, track, detect, communicate, assist, preserve
- Follow the reasoning loop: `New Input → Understand → Classify/Extract → Update State → Detect Conflicts/Gaps → Verify Claims → Decide Assistance → Communicate → Observe`

### FR-04 — Smart Summaries
- Continuously generate contextual summaries: state, facts, hypotheses, decisions, actions, questions, risks, recent changes

### FR-05 — Incident Timeline
- Chronological timeline (example 10:31 Payment API errors → 10:40 Payment API recovered) as backbone for report

### FR-06 — Incident Reports & Auto-Drafted Postmortem
- Generated from structured state, not hallucinated; traceable to transcript/monitoring/decision/action
- Must contain: Name, Severity, Start/End/Duration, Executive Summary, Timeline, Confirmed Facts, Hypotheses, Decisions, Actions+Owners, Resolution, Customer Impact, What Went Well/Wrong, Unresolved Risks, Lessons Learned

### FR-07 — Voice Output
- AI converts important updates to speech via Agora RTC (e.g., "rollback completed, error rates returning to baseline")

---

## 8. AI Intelligence Engine

Modular intelligence, not monolithic LLM call:

```
Incoming Event → LLM Classifier → [Ownership Resolver | State Manager | Conflict Detector] 
  → Monitoring Verification → Cross-Incident Memory → Orchestrator → [Human Approval / Safe Outputs]
```

| Component | Responsibility | Example |
|---|---|---|
| **8.1 LLM Classifier** | Categorize → `Fact, Hypothesis, Decision, Action, Question, Chatter` | Input: "Rollback to v2.4 fixed API errors" → `{"type":"fact","content":"Rollback fixed...","confidence":0.94}` |
| **8.2 Ownership Resolver** | Identify who owns action/investigation/decision | "Verify replica health" → Owner: Karan, Status: Open |
| **8.3 State Manager** | Maintain structured state: `Incident{Severity, Timeline, Facts, Hypotheses, Decisions, Actions{Owner,Status,Deadline}, Conflicts, Gaps, Risks, Participants}` | Every meaningful utterance updates state |
| **8.4 Conflict & Gap Detector** | Flag contradictions & missing info | A: latency normal vs B: latency increased → ⚠️ Conflict |
| **8.5 Assumption-Creep Detection** | Track unverified hypothesis referenced as fact (e.g., "database failure" ×7) → Warn before building on it | `⚠ Assumption-Creep: DB failure referenced 7× but unverified → Verify before restart` |
| **8.6 Duplicate-Work Detection** | Detect overlapping investigations (Priya + Arun → DB latency) | `Priya and Arun appear to investigate same hypothesis` |
| **8.7 Action Tracking** | Task+Owner+Created/Status/Deadline/Completion | "Karan, check replica health" → Action created |
| **8.8 Stall Nudges** | Remind owners of open actions (e.g., 18 min elapsed) | `Karan, replica-health check open 18m — update?` |
| **8.9 Decision Hygiene** | Enforce completeness: decision, owner, expected outcome, risk, ETA, rollback plan | `Let's rollback → need target version 2.4, impact, rollback plan, pending confirmation` |
| **8.10 Cross-Incident Memory** | Recall similar incidents (pgvector) | Current: Payment latency → Precedent #184: connection pool exhaustion → increased pool + restart |

**Confidence & Evidence Schema:**
```json
{
  "type": "hypothesis",
  "content": "Database failure",
  "confidence": 0.71,
  "verification_status": "unverified | verified | contradicted | unknown | unavailable",
  "source": "transcript",
  "timestamp": "10:33:20"
}
```

---

## 9. Validation, Safety & Verification

### 9.1 Monitoring Verification (Key Differentiator)
**Shall** verify claims against Datadog/Prometheus/Grafana where available.
```
CLAIM → MONITORING DATA → VERIFICATION → CONFIRMED / CONTRADICTED / UNKNOWN
```
Example: Claim "Latency returned to normal" → Check p95 420ms vs baseline 180ms → `Not yet verified`

### 9.2 Human-in-the-Loop Safety (Critical)
**MUST:** AI may detect/recommend/summarize/propose, but critical actions require explicit human approval.
```
AI detects → AI proposes → Human reviews → Human approves → Integration executes → Result → State updated
```
Example gate: `Recommended: Rollback v2.4 [Approve] [Reject]` → only then execute bounded action.

---

## 10. Incident State & Data Models

### 10.1 Core Principle
> Transcript is raw evidence. Structured incident state is source of truth.

```
Raw Conversation → Transcript → Extracted → Validated → Structured Incident State
```

### 10.2 Incident State Machine
```
DETECTED → INVESTIGATING → MITIGATION_IN_PROGRESS → RECOVERY → RESOLVED → POSTMORTEM

Action: OPEN → IN_PROGRESS → COMPLETED  (alt: OPEN→BLOCKED, OPEN→CANCELLED)
Conflict: OPEN → UNDER_REVIEW → RESOLVED / DISMISSED
```

### 10.3 Data Models

**Incident**
```
Incident { id, severity(SEV-1..4), title, status, start_time, end_time, duration, participants[] }
```

**Transcript**
```
Transcript { id, incident_id, speaker_id, timestamp, text, confidence, interim|final }
```

**IncidentItem** (type = FACT | HYPOTHESIS | DECISION | ACTION_ITEM | QUESTION | CHATTER)
```
IncidentItem { id, incident_id, type, content, confidence, source, timestamp, verification_status }
```

**Action**
```
Action { id, incident_id, title, description, owner, status[OPEN|IN_PROGRESS|BLOCKED|COMPLETED|CANCELLED], created_at, due_at, completed_at }
```

**Decision**
```
Decision { id, incident_id, decision, owner, rationale, risk, rollback_plan, timestamp, approval_status[PENDING|APPROVED|REJECTED] }
```

**Conflict**
```
Conflict { id, incident_id, claim_a, claim_b, detected_at, status[OPEN|UNDER_REVIEW|RESOLVED|DISMISSED], resolution, verification_required }
```

**Timeline Event**
```
TimelineEvent { timestamp, event_type, description, status, source_ref }
```

---

## 11. Integration Layer

| Integration | Direction | Uses |
|---|---|---|
| **Slack** | Out | #incident-updates: structured summaries, notifications. Ex: `SEV-1 Payment: 18% errors, Rollback v2.4 Owner Arun, checkout failures elevated` |
| **Jira** | Out | Create/update tasks, assign ownership, track work |
| **PagerDuty** | In | Incident context, alerts, escalation → into state |
| **Datadog** | In | Metrics, health, verification of claims |
| **Confluence** | In/Out | Institutional knowledge retrieval + postmortem publishing |
| **Prometheus/Grafana** | In | Alternative monitoring verification |

All integrations use least-privilege, controlled credentials, auditable.

---

## 12. Data Ingestion & Event Architecture

### 12.1 Ingestion Layer
- **Input:** Agora STT Events `{speaker, text, timestamp, interim/final, confidence, segment_id}`
- **Segmenter/Normalizer:** cleaning, dedup, chunking, structuring
- **Event Bus:** Kafka / Redis (async streaming)

### 12.2 Event-Driven Processing
Incoming:
```json
{ "event": "transcript.final", "incident_id": "INC-1042", "speaker": "Arun", "timestamp": "10:35:42", "text": "Let's rollback to version 2.4." }
```
Out:
```
decision.detected → action.created → timeline.updated → state.updated → approval.required
```
Frontend sync via **Agora RTM / Signaling** for state, actions, conflicts, timeline.

---

## 13. Frontend Requirements — Incident Command Dashboard

### 13.1 Layout
```
┌─────────────────────────────────────────────────────┐
│ Incident Overview | AI Status Update | Risk Indicators │
├──────────────┬──────────────────┬───────────────────┤
│ Live Timeline│  Action Items    │  Conflict Alerts  │
│ (chronological│  Owner | Status  │  ⚠ Verification   │
│  FACT/HYP/DEC)│  Karan Active    │  required         │
├──────────────┴──────────────────┴───────────────────┤
│              Incident Reports / Postmortem           │
└─────────────────────────────────────────────────────┘
```

### 13.2 Component Specs

**Incident Overview:** name, severity (SEV-1), duration (00:47:18), impact, participant count, status.

**Live Timeline:** timestamp, type, description, status
```
10:32 AM FACT Latency spiked on Payment API
10:33 AM HYPOTHESIS Possible DB failure
10:35 AM DECISION Rollback to v2.4
10:37 AM ACTION Verify replica health
```

**Action Items Panel:** Table `Action | Owner | Status | Elapsed | Due`
- Ownership immediately visible; color for Active/Pending/Blocked/Stalled.

**AI Status Update:** Concise evolving summary
> `AI STATUS UPDATE — 10:37 AM: Rollback initiated for Payment API. Latency remains elevated but error rate declining. Karan verifying replica health. Customer impact active.`

**Conflict Alerts:** Prominent `⚠ CONFLICT DETECTED: A: DB latency normal vs B: latency increased → Verification required`

**Risk Indicators:** Unresolved risks, unverified claims, stalled actions, customer impact, incomplete decisions.

**Incident Reports:** Tabs — Summary, Timeline, Actions, Decisions, Risks + Auto-Drafted Postmortem view.

---

## 14. Agora Technology Usage

| Agora Capability | Usage |
|---|---|
| **Agora RTC** | Live incident-room audio, bidirectional, active speaker detection, AI as participant |
| **Agora Real-Time STT** | Real-time, speaker-attributed, timestamped, interim/final transcripts → Intelligence Layer feed |
| **Agora RTM / Signaling** | Real-time state updates, messages, action/conflict/timeline sync |
| **Voice Output via RTC** | AI spoken updates, status announcements, reminders, hands-free |

> Agora is not a video-conferencing wrapper; it is the real-time fabric (audio + STT + signaling + voice).

---

## 15. Technology Stack

| Layer | Tech |
|---|---|
| **Frontend** | React / Next.js, Real-time dashboard |
| **Backend** | Python, FastAPI |
| **Database** | PostgreSQL + pgvector (embeddings for precedent recall) |
| **AI** | Claude / LLM layer (classifier, reasoning, summarization) |
| **Communication** | Agora RTC, Agora Real-Time STT, Agora RTM/Signaling |
| **Monitoring** | Datadog, Prometheus, Grafana |
| **Integrations** | Slack, Jira, PagerDuty, Confluence |
| **Infra** | Docker, Docker Compose |
| **Event Processing** | Kafka / Redis |

---

## 16. Security, Auditability & Failure Handling

### 16.1 Security Requirements
- Authenticated incident rooms, role-based access (Commander, Engineer, Viewer)
- Encrypted communication (TLS) + encrypted storage at rest
- Controlled integration credentials, least-privilege
- Action approval gating
- No secrets in logs

### 16.2 Auditability
Preserve for every item:
`Who said it? When? What did AI infer? Evidence? Recommendation? Who approved? Action executed? Result?`
All auditable and traceable to source.

### 16.3 Failure Handling (Degraded Modes)

| Failure | Behavior |
|---|---|
| **STT Failure** | `STT unavailable → Degraded Mode` display; conversation continues; AI must NOT invent transcripts |
| **LLM Failure** | Live room continues; Agora comms independent of AI; queue events, retry |
| **Monitoring Failure** | `Verification Status: UNAVAILABLE`; must NOT claim verified |
| **Integration Failure** | `Action: Queued/Failed (Integration unavailable)`; core state intact |
| **DB/Event Bus Failure** | Local cache, retry queue, backpressure |

---

## 17. MVP Scope & Phasing

### Must Have (Hackathon MVP — Core Loop)
```
Agora RTC room + AI join → Real-Time STT (speaker+timestamp+interim/final)
 → AI Classification (fact/hypothesis/decision/action) → Live Timeline + Incident State
 → Action Extraction + Ownership → Basic Conflict Detection → AI Summary → Postmortem + Approval Gate
```
Checklist:
- [ ] Agora RTC incident room (create/join, active speaker)
- [ ] Agora Real-Time STT integration
- [ ] AI Incident Commander (classifier + state manager)
- [ ] Fact/Hypothesis/Decision/Action classification
- [ ] Live timeline auto-update
- [ ] Action extraction + ownership detection
- [ ] Dashboard (overview, timeline, actions, AI status)
- [ ] Basic conflict detection
- [ ] Human approval for critical actions
- [ ] Structured post-incident report generation
- [ ] Degraded mode if AI fails

### Should Have
- Monitoring verification (Datadog)
- Slack integration (updates)
- Duplicate-work detection
- Assumption-creep detection
- Stall nudges (timed reminders)
- Cross-incident memory (pgvector precedent recall)
- RTM sync + voice output

### Can Be Extended (Post-MVP)
- Jira/PagerDuty/Confluence full bi-dir
- Advanced monitoring (Prometheus/Grafana)
- Sophisticated precedent retrieval + lessons engine
- Advanced voice UX, mobile

---

## 18. Success Metrics

| Category | Metric | Target (MVP) |
|---|---|---|
| **Incident Response** | MTTR reduction vs baseline | -15-25% |
| | Time to first useful action | <5 min from detection |
| | Time to likely cause identified | Track |
| **Information Quality** | % claims classified | >90% meaningful utterances |
| | % critical claims verified | >60% where monitoring available |
| | Conflicts detected / resolved | Track |
| | Open information gaps | Trend ↓ |
| **Action Management** | % actions with owner | 100% |
| | Stalled actions detected & nudged | >80% within SLA |
| | Duplicate work detected | Track |
| | Action completion rate | Track |
| **Communication** | Time to create update | <30s (auto) |
| | Repeated status requests avoided | Qualitative ↓ |
| **Knowledge** | Postmortem generation time | <2 min auto |
| | Precedent reuse count | Track |

---

## 19. Acceptance Criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-01 | Participant can join Agora incident room | Manual join test |
| AC-02 | EchoSphere joins as AI participant | AI appears in participant list |
| AC-03 | Live speech → speaker-attributed text | Speak → transcript with speaker+ts visible <2s |
| AC-04 | AI classifies statements into incident concepts | 10 utterances → correct types |
| AC-05 | Facts & hypotheses distinguishable | Fact/hypothesis labeled differently |
| AC-06 | Actions extracted from conversation | "Karan, check X" → action created |
| AC-07 | Actions have owners | Action.owner != null |
| AC-08 | Timeline updates automatically | New classified item → timeline append |
| AC-09 | Evolving summary generated | Summary changes with state |
| AC-10 | Basic conflict identified | Contradictory statements → alert |
| AC-11 | Critical actions require human confirmation | Rollback shows Approve/Reject gate |
| AC-12 | Final summary/postmortem from state | Generate → contains timeline/facts/decisions |
| AC-13 | Usable if AI layer fails | Kill AI → room+STT+dshboard still usable, degraded banner |
| AC-14 | Unverified not shown as confirmed | Unverified hypothesis → status unverified, warning |

---

## 20. Team Responsibilities (PANGnovates)

| Member | Role | Owns |
|---|---|---|
| **Aman Singh** | Real-Time & Agora Engineer | Agora RTC, audio, STT pipeline, RTM/Signaling, AI participant, voice output |
| **Paul Shervin P** | AI Intelligence & Agent Engineer | LLM classifier, reasoning, state interpretation, conflict/assumption/gap detection, ownership, summaries, precedent recall, orchestrator |
| **Ganesh Kumar** | Backend & Data Systems Engineer | FastAPI, PostgreSQL+pgvector, event processing (Kafka/Redis), incident state APIs, persistence |
| **Nanda Kishor Suresh Priya** | Frontend, UX & Integration Engineer | Dashboard, timeline, actions UI, AI status, reports, Slack/Jira/PagerDuty integrations, UX |

---

## 21. Repository Structure

```
echosphere/
├── apps/
│   ├── web/                          # Next.js dashboard
│   │   ├── dashboard/
│   │   ├── incident-room/
│   │   ├── timeline/
│   │   ├── actions/
│   │   ├── conflicts/
│   │   └── reports/
│   └── api/                          # FastAPI
│       ├── incidents/
│       ├── transcripts/
│       ├── actions/
│       ├── decisions/
│       ├── conflicts/
│       ├── integrations/
│       └── reports/
├── intelligence/
│   ├── classifier/                   # LLM classifier
│   ├── state_manager/
│   ├── ownership/
│   ├── conflict_detection/
│   ├── gap_detection/
│   ├── assumption_detection/
│   ├── action_tracking/
│   ├── precedent/                    # pgvector recall
│   ├── summarization/
│   └── orchestrator/
├── realtime/
│   ├── agora_rtc/
│   ├── agora_stt/
│   ├── agora_rtm/
│   └── voice_output/
├── integrations/
│   ├── slack/
│   ├── jira/
│   ├── pagerduty/
│   ├── datadog/
│   └── confluence/
├── database/
│   ├── models/
│   ├── migrations/
│   └── repositories/
├── infrastructure/
│   ├── docker/
│   └── compose/
└── docs/
    ├── architecture/
    ├── api/
    └── incident-model/
```

---

## 22. Appendices

### Appendix A — Example End-to-End Scenario (SEV-1 Payment Outage)
| Step | Actor | Utterance / Event | EchoSphere Creates |
|---|---|---|---|
| 1 | System | Participants join (Commander, BE, SRE, Support, AI) | Incident INC-1042 SEV-1 created |
| 2 | Engineer | "Payment API returning 500s" | FACT |
| 3 | Engineer | "Database might be failing" | HYPOTHESIS (unverified) |
| 4 | AI | Checks monitoring → DB healthy | HYPOTHESIS → NOT SUPPORTED |
| 5 | Engineer | "Looks like new payment deployment" | HYPOTHESIS: v2.4 |
| 6 | Commander | "Let's rollback v2.4" | DECISION Rollback v2.4 Owner Arun PENDING |
| 7 | Commander | Approves | Executes via integration |
| 8 | AI | Observes error↓ latency↓ | State → RECOVERY |
| 9 | Engineer | "API back to normal" → AI verifies p95→baseline | VERIFIED |
| 10 | AI | Generates postmortem | SEV-1 report: Root cause v2.4, mitigation rollback |

### Appendix B — Key Differentiators
1.  **Live Fact Verification** — Not blind trust; checks monitoring.
2.  **Assumption-Creep Detection** — Prevents unverified hypothesis becoming "fact".
3.  **Stall Nudges** — Proactive ownership accountability.
4.  **Decision Hygiene** — Completeness enforcement (owner, risk, rollback).
5.  **Cross-Incident Memory** — Institutional recall via pgvector.
6.  **Duplicate-Work Detection** — Avoids parallel redundant investigation.
7.  **Human-Controlled Execution** — Recommend but require approval.

### Appendix C — Glossary
| Term | Definition |
|---|---|
| Incident State | Structured, continuously updated representation; source of truth |
| Verification Status | verified / contradicted / unverified / unknown / unavailable |
| Assumption-Creep | Unverified hypothesis repeatedly referenced as established fact |
| Stall Nudge | Automated reminder for action open beyond SLA |

### Appendix D — Open Questions for Build
- STT language model: Agora Real-Time STT accuracy for overlapping speech?
- LLM latency budget for <2s classification?
- pgvector embedding model choice for precedent recall?
- Slack channel naming convention (`#incident-*`)?
- Datadog API rate limits for verification polling?

---

**End of PRD — EchoSphere v1.0**
> This PRD is intentionally constrained to concepts in the original submission (Agora RTC/STT/RTM, structured state, verification, ownership, action tracking, conflict/gap, memory, integrations, human-in-the-loop, postmortem) without adding unrelated features.

