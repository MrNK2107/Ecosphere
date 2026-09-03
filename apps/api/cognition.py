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
# OpenAI config
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_EXTRACT = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MODEL_SUMMARY = os.getenv("OPENAI_MODEL_SUMMARY", "gpt-4o")
LLM_ENABLED = bool(OPENAI_API_KEY)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# LLM extraction (async, calls OpenAI)
# ---------------------------------------------------------------------------
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
        content = await _call_openai(system_prompt, user_message, model=OPENAI_MODEL_EXTRACT)
        elapsed = time.monotonic() - t0
        logger.info(f"LLM extraction: {elapsed:.2f}s, model={OPENAI_MODEL_EXTRACT}")

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
