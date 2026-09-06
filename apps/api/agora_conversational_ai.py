"""
Agora Conversational AI Engine integration — MANDATORY per hackathon rules
(docs.agora.io/en/ai/get-started/quickstart).

Built against the OFFICIAL Agora references, cloned and inspected directly (not built from
memory — see MENTOR_FEEDBACK.md for why that distinction matters):
  - github.com/AgoraIO-Conversational-AI/agent-quickstart-nextjs (app/api/invite-agent/route.ts)
  - github.com/AgoraIO-Conversational-AI/server-custom-llm (python/custom_llm.py — the official
    Python/FastAPI custom-LLM reference; our stack matches exactly)
  - The `agora` skill (docs.agora.io/en/introduction/agora-skills), installed via
    `claude plugin install agora@agora-skills`, references/conversational-ai/*.md
  - The `agora-agents` PyPI package's actual installed API (inspected via `inspect`, not
    assumed — this file uses the real SDK, not hand-rolled REST + Basic Auth)

Architecture (unchanged from the earlier version, now built the right way):
  - Agora CAI is a managed agent that joins the RTC channel as a bot and runs
    ASR -> LLM -> TTS turn-by-turn. ASR + TTS default to Agora-managed vendors
    (Deepgram/MiniMax — the hackathon organizers' no-extra-keys option). LLM
    defaults to "custom", pointed at our own POST /agora/llm/chat/completions
    webhook, so EchoSphere's own cognition engine (Claude) stays the in-room
    conversational brain instead of a generic Agora-managed persona.
  - Transcript delivery is separate from the LLM webhook: with
    advanced_features.enable_rtm + parameters.data_channel="rtm", the agent
    publishes transcript/state events to the RTM channel matching the RTC
    channel name — a worker subscribing to that channel is Phase 1's
    remaining piece (see ECHOSPHERE_IMPLEMENTATION_PLAN.md).
  - Auth: App Credentials mode (AGORA_APP_ID + AGORA_APP_CERT) is Agora's
    *recommended* auth — the SDK mints a ConvoAI token per request
    internally. The skill's own docs say Basic Auth (Customer ID/Secret) is
    "for testing only" — the previous version of this file used Basic Auth
    exclusively, which was a real deviation from the recommended pattern.

NOT independently live-tested in this session — no Agora account/credentials were available.
Every shape here is copied from an official source, not invented; still needs verification
against a real account before relying on it in production.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

logger = logging.getLogger("agora.conversational_ai")

AGORA_APP_ID = os.getenv("AGORA_APP_ID", "")
AGORA_APP_CERT = os.getenv("AGORA_APP_CERT", "") or os.getenv("AGORA_CERT", "")
# Optional — App Credentials mode (above) covers the session join/start flow, but some
# account-level management endpoints (e.g. listing agents) reject it with a 401 "Invalid
# authentication type" and require Customer ID/Secret Basic Auth instead. Passing both to
# AsyncAgora lets the SDK use whichever each endpoint actually needs — confirmed live
# 2026-09-06: agents.list() failed with only app_id/app_cert, succeeded once these were added.
AGORA_CUSTOMER_ID = os.getenv("AGORA_CUSTOMER_ID", "")
AGORA_CUSTOMER_SECRET = os.getenv("AGORA_CUSTOMER_SECRET", "")
AGORA_AREA = os.getenv("AGORA_AREA", "US")  # US | EU | AP | CN — see agent-quickstart-nextjs
AGORA_CAI_LLM_MODE = os.getenv("AGORA_CAI_LLM_MODE", "custom")
# Base URL only (no /chat/completions suffix) — matches OpenAI(base_url=...) semantics, e.g.
# https://your-tunnel.ngrok.io/agora — the SDK/Agora will POST base_url + "/chat/completions".
AGORA_CUSTOM_LLM_URL = os.getenv("AGORA_CUSTOM_LLM_URL", "")
AGORA_CUSTOM_LLM_SHARED_SECRET = os.getenv("AGORA_CUSTOM_LLM_SHARED_SECRET", "echosphere-internal")

CAI_ENABLED = bool(AGORA_APP_ID and AGORA_APP_CERT)

# Turn-detection / interruption config copied from the official Next.js quickstart's
# invite-agent route — this is what makes "user interruption handling" (a mandatory,
# universal hackathon requirement) actually work; the earlier version of this file omitted
# turn-detection entirely and relied on undocumented defaults.
_TURN_DETECTION = {
    "config": {
        "speech_threshold": 0.5,
        "start_of_speech": {
            "mode": "vad",
            "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300},
        },
        "end_of_speech": {
            "mode": "vad",
            "vad_config": {"silence_duration_ms": 480},
        },
    }
}
_ADVANCED_FEATURES = {"enable_rtm": True, "enable_tools": True}
_SESSION_PARAMETERS = {
    "audio_scenario": "chorus",
    "data_channel": "rtm",
    "enable_error_message": True,
    "enable_metrics": True,
}

_client = None  # lazy singleton — module-level so join/leave share one AsyncAgora client


def _get_client():
    global _client
    if _client is None:
        from agora_agent import AsyncAgora, Area
        area = getattr(Area, AGORA_AREA, Area.US)
        _client = AsyncAgora(
            area=area, app_id=AGORA_APP_ID, app_certificate=AGORA_APP_CERT,
            customer_id=AGORA_CUSTOMER_ID or None, customer_secret=AGORA_CUSTOMER_SECRET or None,
        )
    return _client


def _build_agent(system_prompt: str, greeting: str):
    from agora_agent import Agent
    from agora_agent.agentkit import OpenAI, DeepgramSTT, MiniMaxTTS

    failure_message = "Sorry, I couldn't process that just now."
    agent = Agent(
        client=_get_client(),
        instructions=system_prompt,
        greeting=greeting,
        failure_message=failure_message,
        max_history=50,
        turn_detection=_TURN_DETECTION,
        advanced_features=_ADVANCED_FEATURES,
        parameters=_SESSION_PARAMETERS,
    )

    if AGORA_CAI_LLM_MODE == "custom":
        if not AGORA_CUSTOM_LLM_URL:
            raise RuntimeError("AGORA_CUSTOM_LLM_URL must be set when AGORA_CAI_LLM_MODE=custom")
        agent = agent.with_llm(OpenAI(
            base_url=AGORA_CUSTOM_LLM_URL,
            api_key=AGORA_CUSTOM_LLM_SHARED_SECRET,
            model="echosphere-cognition",
            greeting_message=greeting,
            failure_message=failure_message,
            max_history=15,
        ))
    else:
        agent = agent.with_llm(OpenAI(
            model="gpt-4o-mini", greeting_message=greeting, failure_message=failure_message, max_history=15,
        ))

    # Omitting api_key on STT/TTS uses Agora-managed reseller billing (the organizers' no-extra-
    # keys option) — matches the official quickstart's default (non-BYOK) branch exactly.
    agent = agent.with_stt(DeepgramSTT(model="nova-3", language="en"))
    agent = agent.with_tts(MiniMaxTTS(model="speech_2_6_turbo", voice_id="English_captivating_female1"))
    return agent


async def join_agent(
    incident_id: str, channel: str, agent_rtc_uid: str, remote_uid: Optional[str], system_prompt: str,
    greeting: str = "EchoSphere here — I'm listening and tracking this incident.",
) -> dict[str, Any]:
    """Start the Conversational AI agent on an incident's RTC channel via the official SDK."""
    if not CAI_ENABLED:
        return {"mode": "mock", "agent_id": f"mock-agent-{incident_id}", "status": "RUNNING"}

    agent = _build_agent(system_prompt, greeting)
    # Agent name must be unique per project (collision -> HTTP 409 per the agora skill's
    # documented gotcha) — short UUID suffix, same pattern the skill recommends.
    session_name = f"echosphere-{incident_id}-{uuid.uuid4().hex[:8]}"
    session = agent.create_async_session(
        channel=channel,
        agent_uid=str(agent_rtc_uid),  # must be a string, not int — documented SDK gotcha
        remote_uids=[str(remote_uid)] if remote_uid else ["*"],
        name=session_name,
        idle_timeout=600,
        enable_string_uid=True,
    )
    agent_id = await session.start()
    return {"agent_id": agent_id, "status": "RUNNING", "session_name": session_name}


async def leave_agent(agent_id: str) -> dict[str, Any]:
    """Stop a running Conversational AI agent — stateless (doesn't need the original session
    object), matching the SDK's documented stateless-handler pattern."""
    if not CAI_ENABLED or agent_id.startswith("mock-agent-"):
        return {"mode": "mock", "status": "STOPPED"}
    client = _get_client()
    await client.stop_agent(agent_id)
    return {"status": "STOPPED"}
