# Mentor / Review Feedback — raw notes

Captured from a live mentoring session. These are the actual questions asked and the honest
current answers — not aspirational answers. Use this as the checklist for what to fix.

## Question 1: Where does the transcript data come from — a real source, or fabricated?

**Honest answer: fabricated.** `demo/payment_outage.json` is a scripted fixture — 12 hand-written
utterances simulating a payment-outage incident call, written as demo/test data, not sourced from
a real incident recording, real transcript corpus, or any external dataset. The mentor's question
implies this needs to be disclosed honestly (it's fine as a *demo* fixture — every voice-AI demo
uses a script — but it must never be presented as if it came from a real incident).

## Question 2: What input sources does the system actually take right now?

**Honest answer: exactly one path, and it's not the live voice path.** Right now the only way
data enters the system is `POST /incidents/{id}/transcript` — a plain JSON text endpoint. The
demo fixture is replayed into that endpoint by `demo/seed.py`. There is no other ingestion path
currently wired up:
- **Live Agora voice room → real speech → real ASR → this endpoint**: code exists
  (`apps/worker`, `agora_conversational_ai.py`) but has **never been run against a real Agora
  account** (see `CONFLICT.md`). This is the core thing PS41 actually asks for and it's not
  proven to work.
- **Slack (or any other live conversation source) as an input**: **does not exist at all.** No
  code listens to Slack messages, no code picks up speech from any source other than a
  hypothetical Agora RTC channel. The mentor's framing — "while they are speaking, or in a Slack
  community, or talking in general, it should listen and turn it into text" — describes a
  general-purpose "listen anywhere, transcribe anywhere" capability that isn't built and isn't
  actually required by PS41 (which specifically asks for the Agora voice room, not omnichannel
  listening) — but the underlying complaint is valid: **the one input path that matters (real
  speech → real text) has never been demonstrated working**, which is the same root issue as
  question 1: everything shown so far is text typed/scripted in, not voice heard and understood.

## Question 3: Where, specifically, is Agora actually being used?

Needs a precise, confident, specific answer — not vague. Current precise answer (from
`ARCHITECTURE.md` §5, `apps/api/agora_conversational_ai.py`):
- Agora Conversational AI Engine agent joins the incident's RTC channel per-incident via
  `POST .../conversational-ai-agent/v2/projects/:appid/join`.
- ASR + TTS slots use Agora-managed vendors (Deepgram, MiniMax) — no separate keys needed.
- LLM slot is set to `custom`, pointed at our own `POST /agora/llm/chat/completions` webhook —
  this is the one part of the loop we control, and it's SSE-streaming, OpenAI-Chat-Completions
  protocol-compatible per Agora's actual contract.
- **Caveat that must be said out loud when answering this**: none of the above has been run
  against a real Agora account yet. The answer is architecturally precise but not yet
  demonstrated live.

## Feedback on build quality / process

- "Not complete," "somewhat vague," "not production level."
- Criticism of process: work has been reactive — fixing things "every time you say it" rather
  than being built against a known-good reference pattern from the start.
- Explicit ask: **find and follow real reference implementations** for this class of system
  (Agora's own official sample apps, and comparable production "AI incident commander" /
  voice-agent products) instead of improvising the architecture from scratch.

## What's changing as a result

1. Researching Agora's own official sample/reference implementation for a custom-LLM
   Conversational AI agent, and comparable production incident-commander products, to align the
   rebuild with proven patterns rather than ad-hoc decisions (in progress).
2. Agora account is being obtained by the user — once available, the live voice path gets tested
   for real, which resolves questions 1–3 by replacing "fabricated/never tested" with an actual
   working demonstration.
3. Any further changes to the ingestion/voice pipeline will be checked against the reference
   pattern found in (1) before being written, not designed fresh each time.
