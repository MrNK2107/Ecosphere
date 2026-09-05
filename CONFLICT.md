# CONFLICT.md — What's actually required vs. what's actually built

Source of truth for requirements: the official hackathon page
(commudle.com/communities/knotic/hackathons/echosphere) + PS41 text you pasted. This file exists
because there's a real gap between the two, and the most important part of that gap could get the
project **disqualified**, not just marked incomplete. Read section 1 first.

## 1. Critical — disqualification risk, not just a missing feature

The hackathon page states projects may be disqualified if:
- **"Agora is not central to the solution"**
- **"Voice-enabled chatbots only"** (i.e. text-based, not actually voice) — insufficient
- **"Entirely prerecorded demos"**

And every project **must** demonstrate: real-time voice interaction, natural conversation,
**user interruption handling**, contextual memory, external tool/API integration, at least one
meaningful action, human escalation options. Agora Conversational AI is stated as **mandatory**,
not optional.

**What's actually built right now:** the entire working demo (everything I verified and had you
present to your mentor) runs on `demo/seed.py` — a script that POSTs a hardcoded, scripted
transcript to a text API endpoint. There is no live voice room in that path. It is, literally,
the "entirely prerecorded" / "text-based" pattern the rules call out as disqualifying.

The real-time voice path (`apps/api/agora_conversational_ai.py`, the custom-LLM webhook,
`apps/worker`) is **built and unit-tested but never run against a real Agora account** — I don't
have Agora credentials, so nothing in that path has ever actually joined a live voice channel,
transcribed real speech, or spoken a reply back. `.env` still has placeholder values
(`AGORA_APP_ID=your_agora_app_id_here`).

**This is the #1 priority, full stop.** Everything else in this file is secondary until a real
person can join a real Agora voice room and watch EchoSphere listen, classify, and speak back.

## 2. Mock data / mock integrations inventory (everything currently standing in for something real)

| What | Where | Currently | Needed for "real" |
|---|---|---|---|
| Voice room | `apps/worker`, `agora_conversational_ai.py` | Never live-tested | Real `AGORA_APP_ID`/`AGORA_APP_CERT`/`AGORA_CUSTOMER_ID`/`AGORA_CUSTOMER_SECRET` |
| STT | `apps/worker/main.py` | `MOCK_DEEPGRAM` fallback returns canned text | Real `DEEPGRAM_API_KEY`, or rely on Agora-managed ASR (needs Agora creds above) |
| LLM classification | `cognition.py` | Real (Claude/OpenAI/Ollama all genuinely work) | Already real — not a mock |
| TTS / spoken summaries | `apps/api/tts.py` | `TTS_PROVIDER=mock` → returns empty audio | Real `TTS_PROVIDER=openai` + key, or Agora-managed MiniMax (needs Agora creds) |
| Jira | `apps/api/tools.py` `MockJira` | Fabricates a ticket key, no real API call | Real `JIRA_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN` |
| Slack | `apps/api/tools.py` `MockSlack` | Logs only, no real message sent | Real `SLACK_TOKEN`/`SLACK_CHANNEL` |
| PagerDuty | `apps/api/tools.py` `MockPD` | Fabricates a page, no real trigger | Real `PAGERDUTY_KEY`/`PAGERDUTY_SERVICE_ID` |
| Datadog | `apps/api/tools.py` `MockDatadog` | Logs only | Real `DATADOG_API_KEY` (also needed for PRD §9.1 monitoring-verification, which was never built for real) |
| Transcript source | `demo/seed.py` | Scripted fixture replay | Live speaker-attributed ASR from the voice room |

## 3. PS41's 10 required capabilities — honest status

| # | Requirement | Status |
|---|---|---|
| 1 | Real-time participation in a live team voice room | **Not demonstrated live.** Code exists, untested against real Agora |
| 2 | Recognition of participant roles | Partial — role tagging exists in the data model and scripted fixture; never proven against live speaker diarization |
| 3 | Extraction of facts/hypotheses/decisions/action items | **Real** — tested, works, including the LLM fallback path |
| 4 | Assignment and tracking of task ownership | **Real** — ActionItem.ownerName, tracked in state |
| 5 | Detection of missing or conflicting information | **Real** — Gap/Conflict detection tested and working |
| 6 | Continuously updated incident timeline | **Real** — timeline + live WebSocket push, verified working |
| 7 | Integration with Jira/Slack/PagerDuty/monitoring | **Mocked only** — see table above, zero real calls ever made |
| 8 | Spoken status summaries at appropriate moments | **Not real** — TTS is mocked, no scheduler exists that decides "now is a good moment to speak" |
| 9 | Human confirmation before critical actions | **Real** — approval gate tested and working |
| 10 | Final incident summary with unresolved risks | **Real** — summary generation tested and working |

**Net: the "brain" (4/10 fully solid, 2 more nearly there) is genuinely good. The "live, voice,
integrated" half of the requirement (1, 2, 7, 8) is the part that's actually missing**, and it's
also exactly the half the disqualification criteria are about.

## 4. What I need from you to fix section 1 and 3

I cannot make the voice path real without real credentials — this isn't something more code
solves. To move forward I need to know, for each of these, whether you have it or need to get it:

- **Agora**: App ID + App Certificate (RTC), Customer ID + Customer Secret (REST APIs for
  Conversational AI / Signaling) — from Agora Console
- **A publicly reachable URL** for the custom-LLM webhook, since Agora's servers need to reach it
  (ngrok, or a real deployment) — local `localhost:8000` won't work for this specific piece
- **At least one of**: Deepgram key, OpenAI key (for TTS), or confirmation you want to run
  entirely on Agora-managed ASR/TTS (no extra keys, per the organizers' guidance)
- **Real Jira/Slack/PagerDuty/Datadog** access, if you want those integrations genuinely live
  rather than honestly-labeled "mocked, credentials not provided" in the known-limitations doc

Everything else (fixing bugs, building missing pieces like the spoken-summary scheduler and real
monitoring verification) I can do without waiting on you. The plan below sequences it so the
disqualification-risk item comes first.

## 5. One more thing worth flagging, not acting on

The page I fetched shows submissions closing **Sep 4, 11:59 PM IST**, and today is Sep 5 per this
session's clock. I'm not treating this as settled — dates get extended, and you're clearly still
in active mentoring rounds — but you should confirm the actual current deadline with the
organizers rather than assume, since it changes how much of this plan is realistic to execute.
