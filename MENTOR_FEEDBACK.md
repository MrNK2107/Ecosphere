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

## What changed as a result

1. **Installed Agora's own official Claude Code skill** (`claude plugin install agora@agora-skills`
   — this is a real, official product: docs.agora.io/en/introduction/agora-skills). Its own
   enforcement rules state almost exactly the mentor's criticism: *"if the agent has generated a
   `/join` payload from memory... without first inspecting the quickstart source... stop the
   custom path."* That's precisely what had happened.
2. **Cloned and directly inspected the official source** (not just read about it):
   `agent-quickstart-nextjs` (the reference client+server), and
   `server-custom-llm/python` (the official Python/FastAPI custom-LLM reference — our exact
   stack).
3. **Rewrote `apps/api/agora_conversational_ai.py`** to use the real `agora-agents` PyPI package
   (the official Python SDK) instead of hand-rolled REST calls with Basic Auth. Concrete
   corrections made from the real source, not guessed:
   - Auth: App Credentials mode (App ID + Certificate) — Agora's own docs call Basic Auth
     (Customer ID/Secret), which the old version used exclusively, *"for testing only."*
   - Turn-detection/VAD config was completely missing before — this is what actually makes
     "user interruption handling" (a mandatory site-wide requirement) work, copied from the
     official quickstart's exact values.
   - `agent_rtc_uid` must be a string (was previously a documented risk, not yet verified).
   - Agent names now get a UUID suffix (Agora returns HTTP 409 on name collision).
4. **Rewrote the custom-LLM webhook** (`POST /agora/llm/chat/completions`) to match the official
   Python reference's actual pattern:
   - Reads `context.channel` from Agora's request to know which incident a live voice call
     belongs to — **the old version had no way to do this at all**, a real correctness gap.
   - Grounds the spoken reply in the incident's actual current facts/gaps (queried from the DB),
     instead of answering with zero awareness of incident state.
   - Streams real token deltas from Claude as they're generated, instead of buffering the whole
     reply and faking a two-chunk stream.
5. All of this is now backed by 83 passing tests (10 new/rewritten for the Agora integration
   specifically) exercising the real SDK's config construction and the webhook's context-routing.
6. **Still unresolved**: none of this has been run against a real Agora account — that remains
   entirely blocked on the user obtaining Agora credentials (`SETUP.md` §1). Code correctness is
   now verified against official sources; live behavior is not yet verified at all.
