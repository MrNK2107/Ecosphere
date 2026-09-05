"""
Agora Conversational AI Engine integration — MANDATORY per hackathon rules
(docs.agora.io/en/ai/get-started/quickstart).

Architecture (confirmed against Agora's REST API docs — see
ECHOSPHERE_IMPLEMENTATION_PLAN.md Phase 1 for sources):
  - Agora CAI is a managed agent that joins the RTC channel as a bot and runs
    ASR -> LLM -> TTS turn-by-turn, using either Agora-managed vendors
    (credential_mode="managed"; the hackathon organizers offer Deepgram/OpenAI/
    MiniMax with no extra keys) or a custom endpoint we control per slot.
  - We default ASR + TTS to "managed" (zero extra keys, satisfies the mandate
    with no setup) and LLM to "custom", pointed at our own
    POST /agora/llm/chat/completions webhook — this keeps EchoSphere's own
    cognition engine (Claude) as the in-room conversational brain instead of a
    generic Agora-managed chatbot persona.
  - Transcript delivery is SEPARATE from the LLM webhook: Agora CAI publishes
    speaker-labeled ASR results as Signaling (RTM) channel messages. The
    worker subscribes to that channel and forwards segments to
    POST /incidents/{id}/transcript — our existing cognition/state pipeline
    is unchanged. The custom-LLM webhook only produces the AI's spoken replies.

Auth: HTTP Basic with base64(AGORA_CUSTOMER_ID:AGORA_CUSTOMER_SECRET) — same
scheme as Agora's other RESTful API products (Real-Time STT, Signaling).

NOT independently live-tested in this session — no Agora account/credentials
were available. Request/response shapes are built exactly per Agora's
documented REST API (join/leave under
https://api.agora.io/api/conversational-ai-agent/v2/...); verify against a
real account before relying on this in production.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("agora.conversational_ai")

AGORA_APP_ID = os.getenv("AGORA_APP_ID", "")
AGORA_CUSTOMER_ID = os.getenv("AGORA_CUSTOMER_ID", "")
AGORA_CUSTOMER_SECRET = os.getenv("AGORA_CUSTOMER_SECRET", "")
AGORA_CAI_ASR_MODE = os.getenv("AGORA_CAI_ASR_MODE", "managed")
AGORA_CAI_TTS_MODE = os.getenv("AGORA_CAI_TTS_MODE", "managed")
AGORA_CAI_LLM_MODE = os.getenv("AGORA_CAI_LLM_MODE", "custom")
AGORA_CUSTOM_LLM_URL = os.getenv("AGORA_CUSTOM_LLM_URL", "")

CAI_ENABLED = bool(AGORA_APP_ID and AGORA_CUSTOMER_ID and AGORA_CUSTOMER_SECRET)

_BASE_URL = "https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}"


def _auth_header() -> dict[str, str]:
    token = base64.b64encode(f"{AGORA_CUSTOMER_ID}:{AGORA_CUSTOMER_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def build_join_payload(
    incident_id: str,
    channel: str,
    agent_rtc_uid: str,
    rtc_token: str,
    system_prompt: str,
    greeting: str = "EchoSphere here — I'm listening and tracking this incident.",
) -> dict[str, Any]:
    """Build the exact join request body per Agora's documented schema."""
    llm_section: dict[str, Any] = {
        "system_messages": [{"role": "system", "content": system_prompt}],
        "greeting_message": greeting,
        "failure_message": "Sorry, I couldn't process that just now.",
        "max_history": 20,
    }
    if AGORA_CAI_LLM_MODE == "custom":
        if not AGORA_CUSTOM_LLM_URL:
            raise RuntimeError("AGORA_CUSTOM_LLM_URL must be set when AGORA_CAI_LLM_MODE=custom")
        llm_section.update({
            "credential_mode": "custom",
            "vendor": "custom",
            "style": "openai",
            "url": AGORA_CUSTOM_LLM_URL,
            "params": {"model": "echosphere-cognition"},
        })
    else:
        llm_section.update({
            "credential_mode": "managed",
            "vendor": "openai",
            "style": "openai",
            "params": {"model": "gpt-4o-mini"},
        })

    asr_section: dict[str, Any] = {"credential_mode": AGORA_CAI_ASR_MODE, "vendor": "deepgram", "params": {"language": "en-US"}}
    tts_section: dict[str, Any] = {"credential_mode": AGORA_CAI_TTS_MODE, "vendor": "minimax", "params": {"voice_setting": {"voice_id": "female_1"}}}

    return {
        "name": f"echosphere-{incident_id}",
        "properties": {
            "channel": channel,
            "token": rtc_token,
            "agent_rtc_uid": agent_rtc_uid,
            "enable_string_uid": True,
            "idle_timeout": 600,
            "asr": asr_section,
            "llm": llm_section,
            "tts": tts_section,
        },
    }


async def join_agent(
    incident_id: str, channel: str, agent_rtc_uid: str, rtc_token: str, system_prompt: str,
) -> dict[str, Any]:
    """POST .../join — start the Conversational AI agent on an incident's RTC channel."""
    if not CAI_ENABLED:
        return {"mode": "mock", "agent_id": f"mock-agent-{incident_id}", "status": "RUNNING"}
    payload = build_join_payload(incident_id, channel, agent_rtc_uid, rtc_token, system_prompt)
    url = _BASE_URL.format(app_id=AGORA_APP_ID) + "/join"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json=payload, headers=_auth_header())
        r.raise_for_status()
        return r.json()


async def leave_agent(agent_id: str) -> dict[str, Any]:
    """POST .../agents/{agentId}/leave — stop a running Conversational AI agent."""
    if not CAI_ENABLED or agent_id.startswith("mock-agent-"):
        return {"mode": "mock", "status": "STOPPED"}
    url = _BASE_URL.format(app_id=AGORA_APP_ID) + f"/agents/{agent_id}/leave"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, headers=_auth_header())
        r.raise_for_status()
        return r.json() if r.content else {}
