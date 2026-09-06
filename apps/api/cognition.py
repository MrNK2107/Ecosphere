"""
Agora Cognition Engine — LLM + heuristic extraction.

Modes:
 - LLM mode if OPENAI_API_KEY present: calls OpenAI GPT-4o-mini via httpx using prompts/extractor.yaml.
 - Heuristic mode otherwise: keyword rules + fixture lookup for payment_outage.json.

Exports:
 - extract(segment_dict, incident_id, snapshot) -> {extractions: [...]}
 - generate_summary(snapshot) -> {markdown, ttsScript, unresolvedRisks}
 - detect_conflicts(facts) -> list[Gap-like dicts]
 - detect_gaps(snapshot) -> list[Gap-like dicts]
"""
from __future__ import annotations

import os
import re
import json
import logging
import uuid
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger("agora.cognition")

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------
_PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
_EXTRACTOR_YAML = _PROMPT_DIR / "extractor.yaml"
_SUMMARY_YAML = _PROMPT_DIR / "summary.yaml"

try:
    import yaml  # type: ignore
    HAS_YAML = True
except Exception:
    yaml = None  # type: ignore
    HAS_YAML = False


def _load_extractor_prompt() -> dict[str, Any]:
    if HAS_YAML and _EXTRACTOR_YAML.exists():
        try:
            data = yaml.safe_load(_EXTRACTOR_YAML.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to parse extractor.yaml: {e}")
    return {"system": "", "few_shot": [], "output_schema": {}}


def _load_summary_prompt() -> dict[str, Any]:
    if HAS_YAML and _SUMMARY_YAML.exists():
        try:
            data = yaml.safe_load(_SUMMARY_YAML.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to parse summary.yaml: {e}")
    return {"system": ""}


_EXTRACTOR_PROMPT = _load_extractor_prompt()
_SUMMARY_PROMPT = _load_summary_prompt()

# ---------------------------------------------------------------------------
# LLM config — PRD names Claude as the primary LLM layer; OpenAI and a local Ollama server
# are kept as opt-in alternate providers for environments without an Anthropic key (e.g. a
# laptop running Ollama with no cloud API keys at all).
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL_EXTRACT = os.getenv("ANTHROPIC_MODEL_EXTRACT", "claude-sonnet-5")
ANTHROPIC_MODEL_SUMMARY = os.getenv("ANTHROPIC_MODEL_SUMMARY", "claude-opus-5")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_EXTRACT = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MODEL_SUMMARY = os.getenv("OPENAI_MODEL_SUMMARY", "gpt-4o")

# Ollama — local, no API key required. Needs `ollama serve` running (default port 11434) and
# the model already pulled (`ollama pull llama3.1:8b`).
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL_EXTRACT = os.getenv("OLLAMA_MODEL_EXTRACT", "llama3.1:8b")
OLLAMA_MODEL_SUMMARY = os.getenv("OLLAMA_MODEL_SUMMARY", "llama3.1:8b")

# LLM_PROVIDER=claude|openai|ollama — explicit override; otherwise prefer Claude when its key
# is present, OpenAI if only that key is set. Ollama needs no key, so it's never auto-selected —
# it must be requested explicitly (LLM_PROVIDER=ollama) to avoid a silent probe-and-guess.
_PROVIDER_OVERRIDE = os.getenv("LLM_PROVIDER", "").strip().lower()
if _PROVIDER_OVERRIDE in ("claude", "anthropic"):
    LLM_PROVIDER = "claude"
elif _PROVIDER_OVERRIDE == "openai":
    LLM_PROVIDER = "openai"
elif _PROVIDER_OVERRIDE in ("ollama", "local"):
    LLM_PROVIDER = "ollama"
elif ANTHROPIC_API_KEY:
    LLM_PROVIDER = "claude"
elif OPENAI_API_KEY:
    LLM_PROVIDER = "openai"
else:
    LLM_PROVIDER = "claude"  # irrelevant when no key is set; LLM_ENABLED gates the call

LLM_ENABLED = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY or LLM_PROVIDER == "ollama")

# VOICE_LLM_PROVIDER — separate override for generate_voice_reply[_stream] only (the live-voice
# webhook), independent of LLM_PROVIDER (extraction + summary). Added 2026-09-06: LLM_PROVIDER
# was being set to "ollama" for local/free extraction+summary, which silently also routed voice
# replies through Ollama — measured at ~33s/reply, unusable for real-time voice (see CONFLICT.md).
# Falls back to LLM_PROVIDER when unset, so existing single-provider setups are unaffected.
_VOICE_PROVIDER_OVERRIDE = os.getenv("VOICE_LLM_PROVIDER", "").strip().lower()
if _VOICE_PROVIDER_OVERRIDE in ("claude", "anthropic"):
    VOICE_LLM_PROVIDER = "claude"
elif _VOICE_PROVIDER_OVERRIDE == "openai":
    VOICE_LLM_PROVIDER = "openai"
elif _VOICE_PROVIDER_OVERRIDE in ("ollama", "local"):
    VOICE_LLM_PROVIDER = "ollama"
else:
    VOICE_LLM_PROVIDER = LLM_PROVIDER

try:
    import anthropic  # type: ignore
    _anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except Exception:
    anthropic = None  # type: ignore
    _anthropic_client = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Structured-output JSON schemas (mirror prompts/extractor.yaml and
# prompts/summary.yaml output_schema; used for Claude's output_config.format)
# ---------------------------------------------------------------------------
EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "extractions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["Fact", "Hypothesis", "Decision", "ActionItem", "Chatter"]},
                    "statement": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "status": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "sourceSegmentIds": {"type": "array", "items": {"type": "string"}},
                    "ownerName": {"type": ["string", "null"]},
                    "ownerRole": {"type": ["string", "null"]},
                    "requiresConfirmation": {"type": "boolean"},
                    "toolKey": {"type": ["string", "null"], "enum": ["jira", "slack", "pagerduty", "datadog", "github", None]},
                    "dueAt": {"type": ["string", "null"]},
                },
                "required": [
                    "kind", "statement", "title", "status", "confidence", "sourceSegmentIds",
                    "ownerName", "ownerRole", "requiresConfirmation", "toolKey", "dueAt",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["extractions"],
    "additionalProperties": False,
}

SUMMARY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "markdown": {"type": "string"},
        "ttsScript": {"type": "string"},
        "unresolvedRisks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["markdown", "ttsScript", "unresolvedRisks"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# LLM calls — Claude (primary) and OpenAI (alternate provider)
# ---------------------------------------------------------------------------
async def _call_claude(system: str, user: str, model: str, json_schema: dict[str, Any]) -> str:
    """Call Claude via the Anthropic SDK with structured JSON output. Returns raw JSON text."""
    if _anthropic_client is None:
        raise RuntimeError("Anthropic client not configured (ANTHROPIC_API_KEY missing)")
    response = await _anthropic_client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": json_schema}},
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise RuntimeError("Claude response contained no text block")
    return text_block.text


VOICE_REPLY_SYSTEM_PROMPT = (
    "You are EchoSphere, an AI Incident Commander joining a live incident-response voice call as "
    "a participant (PRD FR-03/FR-07). You are NOT a general chatbot — you are here to help the "
    "team run the incident. Rules: keep replies to 1-3 short sentences suitable for text-to-speech "
    "playback in a live call; never invent facts, root causes, or metrics you were not told; if "
    "asked for a status update and you don't have enough context, say so plainly; never claim an "
    "action was taken unless it was explicitly confirmed in the conversation; stay calm, concise, "
    "and professional — this is a live SEV1-4 incident, not small talk."
)


def _normalize_voice_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """OpenAI-chat-format messages -> Claude Messages API format ({user, assistant} roles only —
    fold any embedded "system" turns into user context)."""
    normalized = []
    for m in messages:
        role = "assistant" if m.get("role") == "assistant" else "user"
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if content:
            normalized.append({"role": role, "content": str(content)})
    return normalized or [{"role": "user", "content": "(no transcript yet)"}]


async def generate_voice_reply(messages: list[dict[str, Any]], model: Optional[str] = None) -> str:
    """
    Plain-text conversational reply for the Agora Conversational AI custom-LLM webhook
    (apps/api/agora_conversational_ai.py). Distinct from extract_llm/generate_summary: this is
    the AI's spoken voice in the room, not the structured Fact/Hypothesis/Decision extraction
    pipeline (which is fed separately via POST /incidents/{id}/transcript).
    Non-streaming — prefer generate_voice_reply_stream for the actual webhook (real Agora traffic
    requires streaming; see the "chat completions require streaming" contract in
    docs.agora.io/en/conversational-ai/develop/custom-llm). This is kept for callers that just
    want the final text (e.g. tests, or a non-Agora caller).
    """
    if not LLM_ENABLED:
        return "I'm here, but no language model is configured yet — set LLM_PROVIDER and a key, or LLM_PROVIDER=ollama for a local model."
    claude_messages = _normalize_voice_messages(messages)
    try:
        if VOICE_LLM_PROVIDER == "claude" and _anthropic_client is not None:
            response = await _anthropic_client.messages.create(
                model=model or ANTHROPIC_MODEL_EXTRACT, max_tokens=300,
                system=VOICE_REPLY_SYSTEM_PROMPT, messages=claude_messages,
            )
            text_block = next((b for b in response.content if b.type == "text"), None)
            return text_block.text if text_block else ""
        elif VOICE_LLM_PROVIDER == "ollama":
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in claude_messages)
            return await _call_ollama(VOICE_REPLY_SYSTEM_PROMPT, history_text, model=model or OLLAMA_MODEL_EXTRACT, json_mode=False)
        else:
            # _call_openai only takes a single system+user turn; fold history into one user string.
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in claude_messages)
            return await _call_openai(VOICE_REPLY_SYSTEM_PROMPT, history_text, model=model or OPENAI_MODEL_EXTRACT)
    except Exception as e:
        logger.warning(f"generate_voice_reply failed: {e}")
        return "Sorry, I couldn't process that just now."


async def generate_voice_reply_stream(messages: list[dict[str, Any]], model: Optional[str] = None):
    """
    Async generator yielding text deltas as they're generated — real token-by-token streaming,
    not the full-response-then-fake-chunk pattern. Matches the official Agora custom-LLM
    reference (server-custom-llm/python/custom_llm.py), which streams real provider chunks
    rather than buffering the whole reply first — this matters for perceived latency in a live
    voice call. Falls back to yielding the whole reply as one chunk for non-Claude providers
    (OpenAI/Ollama streaming wasn't implemented for this secondary path — Claude is primary).
    """
    if not LLM_ENABLED:
        yield "I'm here, but no language model is configured yet."
        return
    claude_messages = _normalize_voice_messages(messages)
    try:
        if VOICE_LLM_PROVIDER == "claude" and _anthropic_client is not None:
            async with _anthropic_client.messages.stream(
                model=model or ANTHROPIC_MODEL_EXTRACT, max_tokens=300,
                system=VOICE_REPLY_SYSTEM_PROMPT, messages=claude_messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        else:
            yield await generate_voice_reply(messages, model)
    except Exception as e:
        logger.warning(f"generate_voice_reply_stream failed: {e}")
        yield "Sorry, I couldn't process that just now."


async def _call_openai(system: str, user: str, model: str = "", temperature: float = 0) -> str:
    """Call OpenAI chat completions API. Returns response content string."""
    model = model or OPENAI_MODEL_EXTRACT
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


async def _call_ollama(system: str, user: str, model: str = "", json_mode: bool = True) -> str:
    """Call a local Ollama server's native /api/chat endpoint. No API key needed.
    `format: "json"` forces syntactically valid JSON but — unlike Claude's output_config or
    OpenAI's json_schema — doesn't enforce our specific schema shape, so the system prompt
    (extractor.yaml / summary.yaml) doing the schema description in plain text still matters."""
    model = model or OLLAMA_MODEL_EXTRACT
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    # Local inference (esp. on CPU) is much slower than a hosted API — generous timeout.
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["message"]["content"]


async def extract_llm(
    segment: dict[str, Any],
    incident_id: str,
    existing_facts: list[dict[str, Any]],
    existing_hypotheses: list[dict[str, Any]],
    recent_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    LLM-based extraction. Calls GPT-4o-mini with extractor prompt.
    Returns { extractions: [ {kind, statement, status, confidence, sourceSegmentIds, ...} ] }
    """
    if not LLM_ENABLED:
        return {"extractions": []}

    system_prompt = _EXTRACTOR_PROMPT.get("system", "")
    few_shots = _EXTRACTOR_PROMPT.get("few_shot", [])

    # Build user message
    user_parts = [
        f"Incident ID: {incident_id}",
        "",
        "New transcript segment:",
        json.dumps(segment, default=str),
        "",
        "Recent segments:",
        json.dumps(recent_segments[-5:], default=str),
        "",
        "Existing facts:",
        json.dumps([{"id": f["id"], "statement": f["statement"], "status": f["status"]} for f in existing_facts[-10:]], default=str),
        "",
        "Existing hypotheses:",
        json.dumps([{"id": h["id"], "statement": h["statement"], "status": h["status"]} for h in existing_hypotheses[-5:]], default=str),
    ]

    # Add few-shot examples to system prompt
    if few_shots:
        system_prompt += "\n\nExamples:\n"
        for ex in few_shots[:3]:
            system_prompt += f"Utterance: {ex.get('utterance', '')}\nOutput: {json.dumps(ex.get('output', {}), indent=2)}\n\n"

    user_message = "\n".join(user_parts)

    try:
        t0 = time.monotonic()
        if LLM_PROVIDER == "claude":
            content = await _call_claude(system_prompt, user_message, ANTHROPIC_MODEL_EXTRACT, EXTRACTION_JSON_SCHEMA)
            model_used = ANTHROPIC_MODEL_EXTRACT
        elif LLM_PROVIDER == "ollama":
            # Ollama's format:json forces valid JSON syntax but not our schema shape (no
            # json_schema-style enforcement like Claude/OpenAI) — spell the shape out explicitly,
            # local models follow instructions less reliably than hosted frontier models.
            ollama_system = system_prompt + (
                "\n\nRespond with ONLY a JSON object of exactly this shape (no other text):\n"
                '{"extractions": [{"kind": "Fact|Hypothesis|Decision|ActionItem|Chatter", '
                '"statement": "...", "title": null, "status": "...", "confidence": 0.0-1.0, '
                '"sourceSegmentIds": ["..."], "ownerName": null, "ownerRole": null, '
                '"requiresConfirmation": false, "toolKey": null, "dueAt": null}]}\n'
                "Use an empty extractions array for Chatter."
            )
            content = await _call_ollama(ollama_system, user_message, model=OLLAMA_MODEL_EXTRACT)
            model_used = OLLAMA_MODEL_EXTRACT
        else:
            content = await _call_openai(system_prompt, user_message, model=OPENAI_MODEL_EXTRACT)
            model_used = OPENAI_MODEL_EXTRACT
        elapsed = time.monotonic() - t0
        logger.info(f"LLM extraction: {elapsed:.2f}s, provider={LLM_PROVIDER}, model={model_used}")

        result = json.loads(content)
        if "extractions" not in result:
            result = {"extractions": [result] if "kind" in result else []}
        return result
    except Exception as e:
        logger.warning(f"LLM extraction failed: {e} — falling back to heuristic")
        return {"extractions": []}


# ---------------------------------------------------------------------------
# Heuristic extraction (sync, no IO) — deterministic for payment_outage fixture
# ---------------------------------------------------------------------------
_FIXTURE_FACTS: dict[str, dict[str, Any]] = {
    "u-001": {"statement": "Payment checkout error rate ~12% since 14:02 UTC", "status": "Reported", "confidence": 0.75},
    "u-002": {"statement": "DB replica lag on payments-db-03 is ~45s", "status": "Corroborated", "confidence": 0.85},
    "u-005": {"statement": "Support tickets flooded — 80 tickets in 10 minutes, all payment failures", "status": "Reported", "confidence": 0.7},
    "u-008": {"statement": "Error rate dropped to 2% at 14:06 (conflicting with 12%)", "status": "Reported", "confidence": 0.6},
}
_FIXTURE_HYPOTHESIS = {"statement": "Recent deploy (retry logic change at 13:40) may have caused payment failures", "status": "Active", "confidence": 0.45}
_FIXTURE_DECISION = {"statement": "Rollback payment service to v2.14.3", "status": "Proposed", "confidence": 0.7}
_FIXTURE_ACTIONS = {
    "u-010": {"title": "Fix DB replica lag on payments-db-03", "ownerName": "Backend", "toolKey": "jira", "requiresConfirmation": False},
    "u-012": {"title": "Own customer comms / status page update", "ownerName": None, "toolKey": "slack", "requiresConfirmation": False},
}

# Keyword regexes
_RE_ERROR_RATE = re.compile(r"error\s*rate", re.I)
_RE_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_RE_REPLICA = re.compile(r"replica\s*lag|payments-db", re.I)
_RE_5XX = re.compile(r"5xx|340.*5\s*minutes?", re.I)
_RE_TICKETS = re.compile(r"\d+\s*tickets?|flooded", re.I)
_RE_HYPOTHESIS = re.compile(r"\bI think\b|maybe|might be|deploy.*caus|retry logic", re.I)
_RE_DECISION = re.compile(r"rollback|revert|let'?s\s+rollback|decide to|disable.*payments?", re.I)
_RE_ACTION_JIRA = re.compile(r"create.*jira|track.*fix|assign to", re.I)
_RE_ACTION_COMMS = re.compile(r"customer\s*comms|status\s*page|owner for", re.I)
_RE_APPROVAL = re.compile(r"require.*approval|before it posts|confirm after", re.I)


def extract_heuristic(
    segment: dict[str, Any],
    incident_id: str,
) -> list[dict[str, Any]]:
    """
    Heuristic extraction using fixture lookup + keyword regex.
    Returns list of extraction dicts.
    """
    text = segment.get("text", "")
    sid = segment.get("id", "")
    speaker_name = segment.get("speakerName", "unknown")
    now = _now()
    extractions: list[dict[str, Any]] = []

    # Fixture lookup
    if sid in _FIXTURE_FACTS:
        info = _FIXTURE_FACTS[sid]
        extractions.append({
            "kind": "Fact",
            "statement": info["statement"],
            "status": info["status"],
            "confidence": info["confidence"],
            "sourceSegmentIds": [sid],
        })
        return extractions

    if sid == "u-003":
        # Corroboration — don't create new fact, just note it
        extractions.append({
            "kind": "Fact",
            "statement": "Checkout 5xx count is 340 in last 5 minutes",
            "status": "Corroborated",
            "confidence": 0.8,
            "sourceSegmentIds": [sid],
        })
        return extractions

    if sid == "u-004":
        extractions.append({
            "kind": "Hypothesis",
            "statement": _FIXTURE_HYPOTHESIS["statement"],
            "status": _FIXTURE_HYPOTHESIS["status"],
            "confidence": _FIXTURE_HYPOTHESIS["confidence"],
            "sourceSegmentIds": [sid],
        })
        return extractions

    if sid == "u-007":
        extractions.append({
            "kind": "Decision",
            "statement": _FIXTURE_DECISION["statement"],
            "status": _FIXTURE_DECISION["status"],
            "confidence": _FIXTURE_DECISION["confidence"],
            "sourceSegmentIds": [sid],
        })
        return extractions

    if sid in _FIXTURE_ACTIONS:
        info = _FIXTURE_ACTIONS[sid]
        requires_confirmation = sid == "u-011"
        extractions.append({
            "kind": "ActionItem",
            "title": info["title"],
            "statement": info["title"],
            "status": "Open",
            "confidence": 0.8,
            "sourceSegmentIds": [sid],
            "ownerName": info.get("ownerName"),
            "requiresConfirmation": requires_confirmation,
            "toolKey": info.get("toolKey"),
        })
        return extractions

    if sid in ("u-006", "u-009"):
        return []  # chatter

    # Generic regex fallback
    if _RE_ACTION_JIRA.search(text):
        requires = bool(_RE_APPROVAL.search(text))
        extractions.append({
            "kind": "ActionItem",
            "title": text[:80].strip(),
            "statement": text[:80],
            "status": "Open",
            "confidence": 0.7,
            "sourceSegmentIds": [sid],
            "requiresConfirmation": requires,
            "toolKey": "jira" if "jira" in text.lower() else None,
        })
        return extractions

    if _RE_ACTION_COMMS.search(text):
        extractions.append({
            "kind": "ActionItem",
            "title": "Customer comms / status page update",
            "statement": text[:80],
            "status": "Open",
            "confidence": 0.7,
            "sourceSegmentIds": [sid],
        })
        return extractions

    if _RE_DECISION.search(text):
        extractions.append({
            "kind": "Decision",
            "statement": text[:200],
            "status": "Proposed",
            "confidence": 0.7,
            "sourceSegmentIds": [sid],
        })
        return extractions

    if _RE_HYPOTHESIS.search(text):
        extractions.append({
            "kind": "Hypothesis",
            "statement": text[:200],
            "status": "Active",
            "confidence": 0.45,
            "sourceSegmentIds": [sid],
        })
        return extractions

    if _RE_ERROR_RATE.search(text) or _RE_PCT.search(text) or _RE_REPLICA.search(text) or _RE_TICKETS.search(text):
        extractions.append({
            "kind": "Fact",
            "statement": text[:200],
            "status": "Reported",
            "confidence": 0.7,
            "sourceSegmentIds": [sid],
        })
        return extractions

    return []  # chatter


# ---------------------------------------------------------------------------
# Main extract function (LLM first, heuristic fallback)
# ---------------------------------------------------------------------------
async def extract(
    segment: dict[str, Any],
    incident_id: str,
    snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Extract facts/hypotheses/decisions/actions from a transcript segment.
    Tries LLM first, falls back to heuristic.
    Returns { extractions: [...] }
    """
    # Always try heuristic first (deterministic for fixture)
    heuristic_results = extract_heuristic(segment, incident_id)
    if heuristic_results:
        return {"extractions": heuristic_results}

    # If heuristic found nothing and LLM is enabled, try LLM
    if LLM_ENABLED:
        existing_facts = (snapshot or {}).get("facts", [])
        existing_hyps = (snapshot or {}).get("hypotheses", [])
        recent_segments = (snapshot or {}).get("transcript", [])[-5:]
        return await extract_llm(segment, incident_id, existing_facts, existing_hyps, recent_segments)

    return {"extractions": []}


# ---------------------------------------------------------------------------
# Summary generation (LLM or template)
# ---------------------------------------------------------------------------
async def generate_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Generate incident summary. Uses LLM if available, else template.
    Returns { markdown, ttsScript, unresolvedRisks }
    """
    if LLM_ENABLED:
        return await _generate_summary_llm(snapshot)
    return _generate_summary_template(snapshot)


async def _generate_summary_llm(snapshot: dict[str, Any]) -> dict[str, Any]:
    """LLM-based summary generation."""
    system_prompt = _SUMMARY_PROMPT.get("system", "")
    incident = snapshot.get("incident", {})

    user_parts = [
        f"Incident: {incident.get('title', 'Unknown')}",
        f"ID: {incident.get('id')}",
        f"Severity: {incident.get('severity')}",
        f"Status: {incident.get('status')}",
        "",
        "Facts:",
        json.dumps([{"statement": f["statement"], "status": f["status"], "confidence": f["confidence"]} for f in snapshot.get("facts", [])], indent=2),
        "",
        "Hypotheses:",
        json.dumps([{"statement": h["statement"], "status": h["status"]} for h in snapshot.get("hypotheses", [])], indent=2),
        "",
        "Decisions:",
        json.dumps([{"statement": d["statement"], "status": d["status"]} for d in snapshot.get("decisions", [])], indent=2),
        "",
        "Actions:",
        json.dumps([{"title": a["title"], "status": a["status"], "ownerName": a.get("ownerName"), "requiresConfirmation": a.get("requiresConfirmation")} for a in snapshot.get("actions", [])], indent=2),
        "",
        "Gaps:",
        json.dumps([{"kind": g["kind"], "message": g["message"], "severity": g["severity"]} for g in snapshot.get("gaps", [])], indent=2),
    ]

    try:
        if LLM_PROVIDER == "claude":
            content = await _call_claude(system_prompt, "\n".join(user_parts), ANTHROPIC_MODEL_SUMMARY, SUMMARY_JSON_SCHEMA)
        elif LLM_PROVIDER == "ollama":
            ollama_system = system_prompt + (
                '\n\nRespond with ONLY a JSON object of exactly this shape (no other text): '
                '{"markdown": "...", "ttsScript": "...", "unresolvedRisks": ["..."]}'
            )
            content = await _call_ollama(ollama_system, "\n".join(user_parts), model=OLLAMA_MODEL_SUMMARY)
        else:
            content = await _call_openai(system_prompt, "\n".join(user_parts), model=OPENAI_MODEL_SUMMARY, temperature=0.3)
        result = json.loads(content)
        return {
            "markdown": result.get("markdown", ""),
            "ttsScript": result.get("ttsScript", ""),
            "unresolvedRisks": result.get("unresolvedRisks", []),
        }
    except Exception as e:
        logger.warning(f"LLM summary failed: {e} — falling back to template")
        return _generate_summary_template(snapshot)


def _generate_summary_template(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Template-based summary (no LLM)."""
    incident = snapshot.get("incident", {})
    facts = snapshot.get("facts", [])
    hyps = snapshot.get("hypotheses", [])
    decs = snapshot.get("decisions", [])
    acts = snapshot.get("actions", [])
    gaps = snapshot.get("gaps", [])

    lines = [
        f"# Incident {incident.get('id')} — {incident.get('title', 'Unknown')}",
        "",
        f"_Severity: {incident.get('severity')} | Status: {incident.get('status')}_",
        "",
        "## Facts",
    ]
    for f in facts:
        lines.append(f"- [{f['status']}] {f['statement']} (confidence: {f['confidence']})")
    if not facts:
        lines.append("- _No facts yet_")

    lines.extend(["", "## Hypotheses"])
    for h in hyps:
        lines.append(f"- [{h['status']}] {h['statement']}")
    if not hyps:
        lines.append("- _No hypotheses_")

    lines.extend(["", "## Decisions"])
    for d in decs:
        lines.append(f"- [{d['status']}] {d['statement']}")
    if not decs:
        lines.append("- _No decisions_")

    lines.extend(["", "## Actions"])
    for a in acts:
        owner = a.get("ownerName") or "_unassigned_"
        conf = " ⚠️ requires approval" if a.get("requiresConfirmation") else ""
        lines.append(f"- [{a['status']}] {a['title']} — {owner}{conf}")
    if not acts:
        lines.append("- _No actions_")

    lines.extend(["", "## Unresolved Risks"])
    unresolved = [g for g in gaps if g.get("resolvedAt") is None]
    for g in unresolved:
        lines.append(f"- [{g['kind']}] {g['message']}")
    if not unresolved:
        lines.append("- _None_")

    markdown = "\n".join(lines)

    # Build TTS script: plain text summary
    tts_parts = [f"Incident {incident.get('id')}: {incident.get('title', 'Unknown')}."]
    if facts:
        tts_parts.append(f"{len(facts)} facts confirmed.")
    if acts:
        pending = [a for a in acts if a.get("requiresConfirmation")]
        if pending:
            tts_parts.append(f"{len(pending)} actions require approval.")
    if unresolved:
        tts_parts.append(f"{len(unresolved)} unresolved risks remain.")
    tts_script = " ".join(tts_parts)[:800]

    return {
        "markdown": markdown,
        "ttsScript": tts_script,
        "unresolvedRisks": [g["message"] for g in unresolved],
    }


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------
def detect_conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect conflicting facts via percentage heuristic."""
    gaps: list[dict[str, Any]] = []
    pct_facts: list[tuple[dict, list[str]]] = []
    for f in facts:
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", f.get("statement", ""))
        if nums:
            pct_facts.append((f, nums))
    if len(pct_facts) >= 2:
        values = set()
        for _, nums in pct_facts:
            values.update(nums)
        if len(values) >= 2:
            gaps.append({
                "id": "gap-auto-conflict-pct",
                "kind": "ConflictingInfo",
                "severity": "high",
                "message": f"Conflicting facts: different values {values}",
                "relatedIds": [f["id"] for f, _ in pct_facts[:2]],
            })
    return gaps


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------
def detect_gaps(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect gaps from snapshot (missing owner, stale actions, unverified hypotheses)."""
    gaps: list[dict[str, Any]] = []
    now = _now()

    for act in snapshot.get("actions", []):
        if act.get("status") in ("Done", "Overdue"):
            continue
        if not act.get("ownerId") and not act.get("ownerName"):
            gaps.append({
                "id": f"gap-auto-missing-owner-{act['id']}",
                "kind": "MissingOwner",
                "severity": "medium",
                "message": f"Action '{act['title']}' has no owner",
                "relatedIds": [act["id"]],
            })

    for h in snapshot.get("hypotheses", []):
        if h.get("status") == "Active":
            gaps.append({
                "id": f"gap-auto-unverified-{h['id']}",
                "kind": "UnverifiedAssumption",
                "severity": "medium",
                "message": f"Unverified hypothesis: {h['statement']}",
                "relatedIds": [h["id"]],
            })

    return gaps
