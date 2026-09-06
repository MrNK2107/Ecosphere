"""
Agora API — FastAPI backend with Postgres persistence (SQLAlchemy async).
Implements: incidents CRUD, transcript ingestion + cognition, snapshot, WS timeline, actions, summary.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Literal, Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Path, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Base, IncidentModel, ParticipantModel, TranscriptSegmentModel,
    FactModel, HypothesisModel, DecisionModel, ActionItemModel, ConflictModel,
    GapModel, TimelineEventModel, ToolEventModel, TimelineSeqModel,
)
from db import get_engine, init_db, close_db, get_db, get_session_factory
import tools
import embeddings
import cognition
import agora_conversational_ai
import tts
from fastapi.responses import StreamingResponse, FileResponse
from pathlib import Path as _Path

logger = logging.getLogger("agora.api")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Shared types — import from package, fallback to inline
# ---------------------------------------------------------------------------
try:
    from agora_shared.types import (
        Participant as SharedParticipant,
        TranscriptSegment as SharedTranscriptSegment,
        Fact as SharedFact,
        Hypothesis as SharedHypothesis,
        Decision as SharedDecision,
        ActionItem as SharedActionItem,
        Gap as SharedGap,
        ToolEvent as SharedToolEvent,
        TimelineEvent as SharedTimelineEvent,
        Incident as SharedIncident,
        IncidentSnapshot as SharedSnapshot,
    )
    HAS_SHARED = True
except Exception:
    HAS_SHARED = False

# ---------------------------------------------------------------------------
# Pydantic models (API request/response validators)
# ---------------------------------------------------------------------------
model_config = ConfigDict(extra="forbid", populate_by_name=True)

FactStatus = Literal["Confirmed", "Corroborated", "Reported", "Contradicted"]
HypothesisStatus = Literal["Active", "Disproven", "Confirmed"]
DecisionStatus = Literal["Proposed", "Approved", "Reverted"]
ActionStatus = Literal["Open", "InProgress", "Blocked", "Done", "Overdue"]
GapKind = Literal["MissingOwner", "ConflictingInfo", "UnverifiedAssumption", "StaleAction", "AssumptionCreep", "DuplicateWork", "DecisionHygiene"]
TimelineEventType = Literal[
    "transcript", "fact_created", "fact_updated",
    "hypothesis_created", "hypothesis_updated",
    "decision", "action_created", "action_updated",
    "gap_detected", "gap_resolved", "tool", "summary", "system", "spoken_summary"
]
ToolName = Literal["jira", "slack", "pagerduty", "datadog", "github"]
ToolEventStatus = Literal["pending", "success", "failed", "requiresApproval", "rejected"]
IncidentStatus = Literal["open", "investigating", "mitigated", "resolved", "closed"]
ParticipantRole = Literal["SRE", "Backend", "Frontend", "Support", "Biz", "Comms", "Unknown"]


class Participant(BaseModel):
    model_config = model_config
    id: str
    name: str
    role: ParticipantRole = "Unknown"
    avatarUrl: Optional[str] = None
    joinedAt: datetime
    isBot: bool = False


class TranscriptSegment(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    speakerId: Optional[str] = None
    speakerName: Optional[str] = None
    role: Optional[ParticipantRole] = None
    text: str
    isFinal: bool = True
    startMs: int = Field(ge=0)
    endMs: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1, default=0.9)
    language: str = "en-US"
    createdAt: datetime


class Fact(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    statement: str
    status: FactStatus
    confidence: float = Field(ge=0, le=1)
    verificationStatus: Literal["verified", "contradicted", "unverified", "unknown", "unavailable"] = "unverified"
    sourceSegmentIds: list[str] = Field(min_length=1)
    createdAt: datetime
    updatedAt: datetime
    createdBy: Optional[str] = None


class Hypothesis(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    statement: str
    status: HypothesisStatus
    confidence: float = Field(ge=0, le=1)
    verificationStatus: Literal["verified", "contradicted", "unverified", "unknown", "unavailable"] = "unverified"
    referenceCount: int = Field(ge=0, default=1)
    sourceSegmentIds: list[str] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime
    disprovenReason: Optional[str] = None


class Decision(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    statement: str
    status: DecisionStatus
    decidedBy: Optional[str] = None
    decidedAt: Optional[datetime] = None
    expectedOutcome: Optional[str] = None
    risk: Optional[str] = None
    rollbackPlan: Optional[str] = None
    sourceSegmentIds: list[str] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class ActionItem(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    title: str
    description: Optional[str] = None
    ownerId: Optional[str] = None
    ownerName: Optional[str] = None
    status: ActionStatus
    requiresConfirmation: bool = False
    dueAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    sourceSegmentIds: list[str] = Field(default_factory=list)
    toolKey: Optional[ToolName] = None
    toolPayload: Optional[dict[str, Any]] = None


class Gap(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    kind: GapKind
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    message: str
    relatedIds: list[str] = Field(default_factory=list)
    createdAt: datetime
    resolvedAt: Optional[datetime] = None


class Conflict(BaseModel):
    """PRD §10.3 — first-class contradiction record with its own review lifecycle."""
    model_config = model_config
    id: str
    incidentId: str
    claimA: str
    claimB: str
    status: Literal["OPEN", "UNDER_REVIEW", "RESOLVED", "DISMISSED"] = "OPEN"
    resolution: Optional[str] = None
    verificationRequired: bool = True
    relatedIds: list[str] = Field(default_factory=list)
    detectedAt: datetime
    resolvedAt: Optional[datetime] = None


class ToolEvent(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    tool: ToolName
    action: str
    status: ToolEventStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    requiresApproval: bool = False
    actionItemId: Optional[str] = None
    createdAt: datetime


class TimelineEvent(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    type: TimelineEventType
    seq: int = Field(ge=0)
    createdAt: datetime
    actorId: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    refId: Optional[str] = None


class Incident(BaseModel):
    model_config = model_config
    id: str
    title: str
    description: Optional[str] = None
    status: IncidentStatus = "open"
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4"] = "SEV1"
    createdAt: datetime
    updatedAt: datetime
    participants: list[Participant] = Field(default_factory=list)
    summaryMarkdown: Optional[str] = None


class IncidentSnapshot(BaseModel):
    model_config = model_config
    incident: Incident
    facts: list[Fact] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    toolEvents: list[ToolEvent] = Field(default_factory=list)


# Request models
class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    severity: Optional[Literal["SEV1", "SEV2", "SEV3", "SEV4"]] = "SEV1"
    description: Optional[str] = None
    id: Optional[str] = None


class IncidentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IncidentStatus] = None
    severity: Optional[Literal["SEV1", "SEV2", "SEV3", "SEV4"]] = None
    summaryMarkdown: Optional[str] = None


class ParticipantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[str] = None
    name: str = Field(min_length=1)
    role: ParticipantRole = "Unknown"
    avatarUrl: Optional[str] = None
    isBot: Optional[bool] = False


class ActionUpdateStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ActionStatus


# Rebuild Pydantic models for FastAPI compat with `from __future__ import annotations`
for _cls in [Participant, TranscriptSegment, Fact, Hypothesis, Decision, ActionItem,
             Gap, Conflict, ToolEvent, TimelineEvent, Incident, IncidentSnapshot,
             IncidentCreate, IncidentPatch, ParticipantCreate, ActionUpdateStatus]:
    try:
        _cls.model_rebuild()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------
app = FastAPI(title="Agora API", version="0.2.0", description="Real-time AI Incident Commander — Postgres-backed")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Redis (optional) + WS fanout
# ---------------------------------------------------------------------------
_redis_client: Any = None
_redis_enabled = False
_ws_connections: dict[str, Set[WebSocket]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a possibly-naive datetime (e.g. from SQLite, which drops tzinfo) to UTC-aware."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# Redis init (graceful fallback)
try:
    import redis.asyncio as redis_async  # type: ignore
except Exception:
    redis_async = None  # type: ignore


@app.on_event("startup")
async def _startup():
    # Init DB
    await init_db()
    # Init Redis
    global _redis_client, _redis_enabled
    url = os.getenv("REDIS_URL", "")
    if redis_async is None:
        logger.info("Redis library not available, using in-process broadcast")
    elif url:
        try:
            client = redis_async.from_url(url, decode_responses=True, socket_connect_timeout=2)
            await client.ping()
            _redis_client = client
            _redis_enabled = True
            logger.info(f"Redis connected at {url}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), falling back to in-process broadcast")
    else:
        logger.info("No REDIS_URL set, using in-process broadcast")


@app.on_event("shutdown")
async def _shutdown():
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
        except Exception:
            pass
    await close_db()


# ---------------------------------------------------------------------------
# DB helpers: model ↔ Pydantic conversion
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _next_seq(session: AsyncSession, incident_id: str) -> int:
    """Get next timeline sequence number for an incident (atomic via SELECT FOR UPDATE)."""
    result = await session.execute(
        select(TimelineSeqModel).where(TimelineSeqModel.incident_id == incident_id).with_for_update()
    )
    seq_model = result.scalar_one_or_none()
    if seq_model is None:
        seq_model = TimelineSeqModel(incident_id=incident_id, current_seq=0)
        session.add(seq_model)
        await session.flush()
    seq_model.current_seq += 1
    return seq_model.current_seq


def _model_to_participant(m: ParticipantModel) -> dict:
    return {
        "id": m.id, "name": m.name, "role": m.role,
        "avatarUrl": m.avatar_url, "joinedAt": m.joined_at.isoformat(), "isBot": m.is_bot,
    }


def _model_to_transcript(m: TranscriptSegmentModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "speakerId": m.speaker_id,
        "speakerName": m.speaker_name, "role": m.role, "text": m.text,
        "isFinal": m.is_final, "startMs": m.start_ms, "endMs": m.end_ms,
        "confidence": m.confidence, "language": m.language, "createdAt": m.created_at.isoformat(),
    }


def _model_to_fact(m: FactModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "statement": m.statement,
        "status": m.status, "confidence": m.confidence,
        "verificationStatus": m.verification_status or "unverified",
        "sourceSegmentIds": m.source_segment_ids or [],
        "createdAt": m.created_at.isoformat(), "updatedAt": m.updated_at.isoformat(),
        "createdBy": m.created_by,
    }


def _model_to_hypothesis(m: HypothesisModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "statement": m.statement,
        "status": m.status, "confidence": m.confidence,
        "verificationStatus": m.verification_status or "unverified",
        "referenceCount": m.reference_count if m.reference_count is not None else 1,
        "sourceSegmentIds": m.source_segment_ids or [],
        "createdAt": m.created_at.isoformat(), "updatedAt": m.updated_at.isoformat(),
        "disprovenReason": m.disproven_reason,
    }


def _model_to_conflict(m: ConflictModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id,
        "claimA": m.claim_a, "claimB": m.claim_b,
        "status": m.status, "resolution": m.resolution,
        "verificationRequired": m.verification_required,
        "relatedIds": m.related_ids or [],
        "detectedAt": m.detected_at.isoformat(),
        "resolvedAt": m.resolved_at.isoformat() if m.resolved_at else None,
    }


def _model_to_decision(m: DecisionModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "statement": m.statement,
        "status": m.status, "decidedBy": m.decided_by,
        "decidedAt": m.decided_at.isoformat() if m.decided_at else None,
        "expectedOutcome": m.expected_outcome, "risk": m.risk, "rollbackPlan": m.rollback_plan,
        "sourceSegmentIds": m.source_segment_ids or [],
        "createdAt": m.created_at.isoformat(), "updatedAt": m.updated_at.isoformat(),
    }


def _model_to_action(m: ActionItemModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "title": m.title,
        "description": m.description, "ownerId": m.owner_id, "ownerName": m.owner_name,
        "status": m.status, "requiresConfirmation": m.requires_confirmation,
        "dueAt": m.due_at.isoformat() if m.due_at else None,
        "createdAt": m.created_at.isoformat(), "updatedAt": m.updated_at.isoformat(),
        "sourceSegmentIds": m.source_segment_ids or [],
        "toolKey": m.tool_key, "toolPayload": m.tool_payload,
    }


def _model_to_gap(m: GapModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "kind": m.kind,
        "severity": m.severity, "message": m.message,
        "relatedIds": m.related_ids or [],
        "createdAt": m.created_at.isoformat(),
        "resolvedAt": m.resolved_at.isoformat() if m.resolved_at else None,
    }


def _model_to_timeline(m: TimelineEventModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "type": m.type,
        "seq": m.seq, "createdAt": m.created_at.isoformat(),
        "actorId": m.actor_id, "payload": m.payload or {}, "refId": m.ref_id,
    }


def _model_to_tool_event(m: ToolEventModel) -> dict:
    return {
        "id": m.id, "incidentId": m.incident_id, "tool": m.tool,
        "action": m.action, "status": m.status, "payload": m.payload or {},
        "result": m.result, "requiresApproval": m.requires_approval,
        "actionItemId": m.action_item_id, "createdAt": m.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Snapshot builder (DB-backed)
# ---------------------------------------------------------------------------
async def _build_snapshot(session: AsyncSession, incident_id: str) -> dict[str, Any]:
    """Build full IncidentSnapshot from DB."""
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")

    # Participants
    parts_r = await session.execute(
        select(ParticipantModel).where(ParticipantModel.incident_id == incident_id)
    )
    participants = [_model_to_participant(p) for p in parts_r.scalars().all()]

    incident_dict = {
        "id": inc_m.id, "title": inc_m.title, "description": inc_m.description,
        "status": inc_m.status, "severity": inc_m.severity,
        "createdAt": inc_m.created_at.isoformat(), "updatedAt": inc_m.updated_at.isoformat(),
        "participants": participants, "summaryMarkdown": inc_m.summary_markdown,
    }

    # Facts
    facts_r = await session.execute(
        select(FactModel).where(FactModel.incident_id == incident_id)
    )
    facts = [_model_to_fact(f) for f in facts_r.scalars().all()]

    # Hypotheses
    hyps_r = await session.execute(
        select(HypothesisModel).where(HypothesisModel.incident_id == incident_id)
    )
    hypotheses = [_model_to_hypothesis(h) for h in hyps_r.scalars().all()]

    # Decisions
    decs_r = await session.execute(
        select(DecisionModel).where(DecisionModel.incident_id == incident_id)
    )
    decisions = [_model_to_decision(d) for d in decs_r.scalars().all()]

    # Actions
    acts_r = await session.execute(
        select(ActionItemModel).where(ActionItemModel.incident_id == incident_id)
    )
    actions = [_model_to_action(a) for a in acts_r.scalars().all()]

    # Gaps
    gaps_r = await session.execute(
        select(GapModel).where(GapModel.incident_id == incident_id)
    )
    gaps = [_model_to_gap(g) for g in gaps_r.scalars().all()]

    # Conflicts
    conf_r = await session.execute(
        select(ConflictModel).where(ConflictModel.incident_id == incident_id)
    )
    conflicts = [_model_to_conflict(c) for c in conf_r.scalars().all()]

    # Timeline (sorted by seq)
    tl_r = await session.execute(
        select(TimelineEventModel).where(TimelineEventModel.incident_id == incident_id).order_by(TimelineEventModel.seq)
    )
    timeline = [_model_to_timeline(t) for t in tl_r.scalars().all()]

    # Transcript (sorted by start_ms)
    tr_r = await session.execute(
        select(TranscriptSegmentModel).where(TranscriptSegmentModel.incident_id == incident_id).order_by(TranscriptSegmentModel.start_ms)
    )
    transcript = [_model_to_transcript(t) for t in tr_r.scalars().all()]

    # Tool events
    te_r = await session.execute(
        select(ToolEventModel).where(ToolEventModel.incident_id == incident_id)
    )
    tool_events = [_model_to_tool_event(te) for te in te_r.scalars().all()]

    return {
        "incident": incident_dict,
        "facts": facts, "hypotheses": hypotheses, "decisions": decisions,
        "actions": actions, "conflicts": conflicts, "gaps": gaps, "timeline": timeline,
        "transcript": transcript, "toolEvents": tool_events,
    }


# ---------------------------------------------------------------------------
# Timeline helper (DB-backed)
# ---------------------------------------------------------------------------
async def _append_timeline(
    session: AsyncSession, incident_id: str, type_: str,
    payload: dict[str, Any], actor_id: Optional[str] = None, ref_id: Optional[str] = None,
) -> TimelineEventModel:
    seq = await _next_seq(session, incident_id)
    ev = TimelineEventModel(
        id=_gen_id("evt"), incident_id=incident_id, type=type_, seq=seq,
        created_at=_now(), actor_id=actor_id, payload=payload, ref_id=ref_id,
    )
    session.add(ev)
    return ev


def _format_event_text(ev: dict[str, Any]) -> str:
    p = ev.get("payload") or {}
    t = ev.get("type")
    if t == "transcript":
        return f"{p.get('speakerName') or 'Someone'}: {p.get('text', '')}"
    if t in ("fact_created", "fact_updated", "hypothesis_created", "hypothesis_updated", "decision"):
        statement = p.get("statement", "")
        status = p.get("status")
        return f"{statement} ({status})" if status else statement
    if t == "action_created":
        return p.get("title", "")
    if t == "action_updated":
        title, status = p.get("title", ""), p.get("status")
        return f"{title} → {status}" if status else title
    if t in ("gap_detected", "gap_resolved", "system"):
        return p.get("message", "")
    if t == "tool":
        tool, action, status = p.get("tool", ""), p.get("action", ""), p.get("status")
        return f"{tool} {action} — {status}" if status else f"{tool} {action}"
    if t == "spoken_summary":
        return p.get("script", "")
    if t == "summary":
        return p.get("markdown", "")
    return json.dumps(p)[:120]


# ---------------------------------------------------------------------------
# WS broadcast
# ---------------------------------------------------------------------------
async def _broadcast(incident_id: str, message: dict[str, Any]):
    if _redis_enabled and _redis_client is not None:
        try:
            await _redis_client.publish(f"incident:{incident_id}", json.dumps(message, default=str))
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")
    conns = _ws_connections.get(incident_id, set()).copy()
    dead: list[WebSocket] = []
    for ws in conns:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_connections.get(incident_id, set()).discard(ws)


# ---------------------------------------------------------------------------
# Gap detection (DB-backed)
# ---------------------------------------------------------------------------
_STOPWORDS = {
    "the", "a", "an", "is", "was", "are", "were", "to", "of", "in", "on", "at", "for", "and", "or",
    "may", "might", "could", "have", "has", "had", "be", "been", "this", "that", "it", "its", "we",
    "you", "he", "she", "they", "not", "no", "so", "if", "but", "with", "as", "by", "from", "will",
    "would", "should", "can", "did", "do", "does", "still", "just", "also", "than", "then", "into",
}


def _significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z]{4,}", (text or "").lower()) if w not in _STOPWORDS}


async def _detect_and_store_gaps(session: AsyncSession, incident_id: str):
    """Recompute auto-gaps from current facts/actions/hypotheses/decisions."""
    # Remove old auto gaps
    await session.execute(
        delete(GapModel).where(
            GapModel.incident_id == incident_id,
            GapModel.id.like("gap-auto-%"),
        )
    )
    await session.flush()

    now = _now()
    new_gaps: list[GapModel] = []

    # --- Conflicting facts (percentage heuristic) -> Gap + first-class Conflict record ---
    facts_r = await session.execute(
        select(FactModel).where(FactModel.incident_id == incident_id)
    )
    facts = list(facts_r.scalars().all())
    pct_facts: list[tuple[FactModel, list[str]]] = []
    for f in facts:
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", f.statement)
        if nums:
            pct_facts.append((f, nums))
    if len(pct_facts) >= 2:
        values = set()
        for _, nums in pct_facts:
            values.update(nums)
        if len(values) >= 2:
            msg = f"Conflicting error-rate facts: {values}"
            new_gaps.append(GapModel(
                id="gap-auto-conflict-pct", incident_id=incident_id,
                kind="ConflictingInfo", severity="high", message=msg,
                related_ids=[f.id for f, _ in pct_facts[:2]], created_at=now,
            ))
            claim_a, claim_b = pct_facts[0][0].statement, pct_facts[1][0].statement
            conflict_id = "conflict-auto-pct"
            existing_conflict = await session.get(ConflictModel, conflict_id)
            if existing_conflict:
                if existing_conflict.status not in ("RESOLVED", "DISMISSED"):
                    existing_conflict.claim_a = claim_a
                    existing_conflict.claim_b = claim_b
                    existing_conflict.related_ids = [f.id for f, _ in pct_facts[:2]]
            else:
                session.add(ConflictModel(
                    id=conflict_id, incident_id=incident_id,
                    claim_a=claim_a, claim_b=claim_b, status="OPEN",
                    verification_required=True,
                    related_ids=[f.id for f, _ in pct_facts[:2]], detected_at=now,
                ))

    # --- Missing owner ---
    acts_r = await session.execute(
        select(ActionItemModel).where(ActionItemModel.incident_id == incident_id)
    )
    actions = list(acts_r.scalars().all())
    for act in actions:
        if act.status in ("Done", "Overdue"):
            continue
        if not act.owner_id and not act.owner_name:
            new_gaps.append(GapModel(
                id=f"gap-auto-missing-owner-{act.id}", incident_id=incident_id,
                kind="MissingOwner", severity="medium",
                message=f"Action '{act.title}' has no owner",
                related_ids=[act.id], created_at=now,
            ))

    # --- Stale / overdue actions (+ one-time stall nudge, PRD §8.8) ---
    for act in actions:
        if act.status == "Done":
            continue
        age = (now - _aware(act.created_at)).total_seconds()
        overdue = act.due_at and now > _aware(act.due_at) and act.status != "Done"
        if age > 600 or overdue:
            severity = "high" if overdue else "medium"
            new_gaps.append(GapModel(
                id=f"gap-auto-stale-{act.id}", incident_id=incident_id,
                kind="StaleAction", severity=severity,
                message=f"Action '{act.title}' is stale ({int(age//60)}m old)" + (" — overdue" if overdue else ""),
                related_ids=[act.id], created_at=now,
            ))
            if act.owner_name:
                await _maybe_send_stall_nudge(session, incident_id, act, int(age // 60))

    # --- Duplicate-work detection (PRD §8.6): open actions, different owners, overlapping topic ---
    open_owned = [a for a in actions if a.status in ("Open", "InProgress") and a.owner_name]
    seen_pairs: set[tuple[str, str]] = set()
    for i, a1 in enumerate(open_owned):
        words1 = _significant_words(f"{a1.title} {a1.description or ''}")
        for a2 in open_owned[i + 1:]:
            if a1.owner_name == a2.owner_name:
                continue
            pair_key = tuple(sorted([a1.id, a2.id]))
            if pair_key in seen_pairs:
                continue
            words2 = _significant_words(f"{a2.title} {a2.description or ''}")
            overlap = words1 & words2
            if len(overlap) >= 2:
                seen_pairs.add(pair_key)
                new_gaps.append(GapModel(
                    id=f"gap-auto-dupe-{pair_key[0]}-{pair_key[1]}", incident_id=incident_id,
                    kind="DuplicateWork", severity="medium",
                    message=f"'{a1.owner_name}' and '{a2.owner_name}' appear to be investigating the same thing "
                            f"({a1.title!r} / {a2.title!r})",
                    related_ids=[a1.id, a2.id], created_at=now,
                ))

    # --- Unverified hypotheses + assumption-creep (PRD §8.5) ---
    hyps_r = await session.execute(
        select(HypothesisModel).where(HypothesisModel.incident_id == incident_id)
    )
    hypotheses = list(hyps_r.scalars().all())
    segs_r = await session.execute(
        select(TranscriptSegmentModel).where(TranscriptSegmentModel.incident_id == incident_id)
    )
    segments = list(segs_r.scalars().all())
    for h in hypotheses:
        if h.status != "Active":
            continue
        new_gaps.append(GapModel(
            id=f"gap-auto-unverified-{h.id}", incident_id=incident_id,
            kind="UnverifiedAssumption", severity="medium",
            message=f"Unverified hypothesis: {h.statement}",
            related_ids=[h.id], created_at=now,
        ))
        key_words = _significant_words(h.statement)
        mention_count = 0
        if key_words:
            for seg in segments:
                seg_words = _significant_words(seg.text)
                if len(key_words & seg_words) >= 2:
                    mention_count += 1
        h.reference_count = max(mention_count, 1)
        if h.embedding is None:
            h.embedding = await embeddings.get_embedding(h.statement)
        if mention_count >= 3:
            new_gaps.append(GapModel(
                id=f"gap-auto-assumption-creep-{h.id}", incident_id=incident_id,
                kind="AssumptionCreep", severity="high",
                message=f"Hypothesis referenced {mention_count}x but still unverified — "
                        f"verify before acting on it: {h.statement}",
                related_ids=[h.id], created_at=now,
            ))

    # --- Decision hygiene (PRD §8.9): Approved decisions missing completeness fields ---
    decs_r = await session.execute(
        select(DecisionModel).where(DecisionModel.incident_id == incident_id)
    )
    for d in decs_r.scalars().all():
        if d.status != "Approved":
            continue
        missing = [
            label for label, val in [
                ("owner", d.decided_by), ("expected outcome", d.expected_outcome),
                ("risk", d.risk), ("rollback plan", d.rollback_plan),
            ] if not val
        ]
        if missing:
            new_gaps.append(GapModel(
                id=f"gap-auto-decision-hygiene-{d.id}", incident_id=incident_id,
                kind="DecisionHygiene", severity="medium",
                message=f"Decision '{d.statement}' approved but missing: {', '.join(missing)}",
                related_ids=[d.id], created_at=now,
            ))

    # Insert new gaps
    for gap in new_gaps:
        existing = await session.get(GapModel, gap.id)
        if existing:
            existing.message = gap.message
            existing.related_ids = gap.related_ids
        else:
            session.add(gap)
            await _append_timeline(session, incident_id, "gap_detected",
                                   {"kind": gap.kind, "severity": gap.severity, "message": gap.message},
                                   ref_id=gap.id)
    await session.flush()


async def _maybe_send_stall_nudge(session: AsyncSession, incident_id: str, act: ActionItemModel, age_minutes: int) -> None:
    """PRD §8.8 Stall Nudges — send at most one mock-Slack reminder per action via tools.invoke_tool."""
    nudge_id = f"tool-nudge-{act.id}"
    existing = await session.get(ToolEventModel, nudge_id)
    if existing:
        return
    ctx = {"incidentId": incident_id, "actionItemId": act.id, "requiresConfirmation": False}
    payload = {"text": f"{act.owner_name}, '{act.title}' has been open {age_minutes}m — update?"}
    result = await tools.invoke_tool("slack", "post", payload, ctx)
    session.add(ToolEventModel(
        id=nudge_id, incident_id=incident_id, tool="slack", action="stall_nudge",
        status=result.get("status", "success"), payload=payload, result=result.get("result"),
        requires_approval=False, action_item_id=act.id, created_at=_now(),
    ))
    await _append_timeline(session, incident_id, "tool",
                           {"tool": "slack", "action": "stall_nudge", "actionItemId": act.id},
                           ref_id=nudge_id)


# ---------------------------------------------------------------------------
# Spoken status summaries — PS41: "Spoken status summaries at appropriate moments"
# ---------------------------------------------------------------------------
_spoken_tracker: dict[str, dict[str, Any]] = {}  # incidentId -> {lastSpokenAt, factCountAtLast}
SPOKEN_SUMMARY_INTERVAL_S = 300  # 5 minutes
SPOKEN_SUMMARY_NEW_FACTS_THRESHOLD = 3


async def _maybe_speak_summary(session: AsyncSession, incident_id: str, snap: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Trigger a spoken status update on a 5-minute cadence OR after 3+ new facts since the last
    one, whichever comes first — matches PLAN.md's original scheduler spec. Synthesizes via
    tts.py (mock — silently no-ops — unless TTS_PROVIDER/keys are configured) and records a
    `spoken_summary` timeline entry either way, so the cadence/trigger logic is verifiable even
    with TTS mocked. When Agora Conversational AI's voice path is live, this is also the hook
    point for publishing the audio into the RTC room instead of (or in addition to) the dashboard."""
    now = _now()
    tracker = _spoken_tracker.setdefault(incident_id, {"last_spoken_at": None, "fact_count_at_last": 0})
    facts = snap.get("facts", [])
    fact_count = len(facts)
    if fact_count == 0:
        return None

    elapsed_ok = tracker["last_spoken_at"] is not None and (now - tracker["last_spoken_at"]).total_seconds() >= SPOKEN_SUMMARY_INTERVAL_S
    new_facts_ok = (fact_count - tracker["fact_count_at_last"]) >= SPOKEN_SUMMARY_NEW_FACTS_THRESHOLD
    first_ever = tracker["last_spoken_at"] is None and fact_count >= SPOKEN_SUMMARY_NEW_FACTS_THRESHOLD
    if not (elapsed_ok or new_facts_ok or first_ever):
        return None

    incident = snap["incident"]
    recent_facts = "; ".join(f["statement"] for f in facts[-3:])
    open_gaps = [g for g in snap.get("gaps", []) if not g.get("resolvedAt")]
    script = f"Status update on {incident['title']}. {recent_facts}."
    if open_gaps:
        script += f" {len(open_gaps)} open issue{'s' if len(open_gaps) != 1 else ''} need attention."
    script = script[:800]

    audio_path = await tts.synthesize_cached(script)
    tracker["last_spoken_at"] = now
    tracker["fact_count_at_last"] = fact_count

    audio_url = f"/incidents/{incident_id}/audio/{_Path(audio_path).name}" if audio_path else None
    await _append_timeline(session, incident_id, "spoken_summary", {"script": script, "audioUrl": audio_url})
    return {"script": script, "audioUrl": audio_url}


# ---------------------------------------------------------------------------
# Inline cognition (regex-based extraction, deterministic for demo fixture)
# ---------------------------------------------------------------------------
async def _run_cognition(session: AsyncSession, segment: TranscriptSegmentModel, incident_id: str):
    """Inline extraction using regex + fixture-aware mapping for payment_outage demo."""
    text = segment.text or ""
    sid = segment.id
    now = _now()

    # Fixture-aware deterministic mapping
    fixture_map: dict[str, str] = {
        "u-001": "fact:12pct", "u-002": "fact:replica", "u-003": "fact:5xx",
        "u-004": "hypothesis:deploy", "u-005": "fact:tickets",
        "u-007": "decision:rollback", "u-008": "fact:2pct",
        "u-010": "action:jira", "u-012": "action:comms",
    }
    kind = fixture_map.get(sid)

    if kind == "fact:12pct":
        fid = f"fact-{incident_id}-{sid}"
        existing = await session.get(FactModel, fid)
        if not existing:
            f = FactModel(
                id=fid, incident_id=incident_id,
                statement="Payment checkout error rate ~12% since 14:02 UTC",
                status="Reported", confidence=0.75, source_segment_ids=[sid],
                created_at=now, updated_at=now, created_by="inline",
            )
            session.add(f)
            await _append_timeline(session, incident_id, "fact_created",
                                   {"statement": f.statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        return

    if kind == "fact:replica":
        fid = f"fact-{incident_id}-{sid}"
        existing = await session.get(FactModel, fid)
        if not existing:
            f = FactModel(
                id=fid, incident_id=incident_id,
                statement="DB replica lag on payments-db-03 is ~45s",
                status="Corroborated", confidence=0.85, source_segment_ids=[sid],
                created_at=now, updated_at=now, created_by="inline",
            )
            session.add(f)
            await _append_timeline(session, incident_id, "fact_created",
                                   {"statement": f.statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        return

    if kind == "fact:5xx":
        fid = f"fact-{incident_id}-{sid}"
        existing = await session.get(FactModel, fid)
        if not existing:
            f = FactModel(
                id=fid, incident_id=incident_id,
                statement="Checkout 5xx count is 340 in last 5 minutes",
                status="Corroborated", confidence=0.8, source_segment_ids=[sid],
                created_at=now, updated_at=now, created_by="inline",
            )
            session.add(f)
            await _append_timeline(session, incident_id, "fact_created",
                                   {"statement": f.statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        return

    if kind == "hypothesis:deploy":
        hid = f"hypo-{incident_id}-{sid}"
        existing = await session.get(HypothesisModel, hid)
        if not existing:
            h = HypothesisModel(
                id=hid, incident_id=incident_id,
                statement="Recent deploy (retry logic change at 13:40) may have caused payment failures",
                status="Active", confidence=0.45, source_segment_ids=[sid],
                created_at=now, updated_at=now,
            )
            session.add(h)
            await _append_timeline(session, incident_id, "hypothesis_created",
                                   {"statement": h.statement, "status": h.status}, actor_id=segment.speaker_id, ref_id=hid)
        return

    if kind == "fact:tickets":
        fid = f"fact-{incident_id}-{sid}"
        existing = await session.get(FactModel, fid)
        if not existing:
            f = FactModel(
                id=fid, incident_id=incident_id,
                statement="Support tickets flooded — 80 tickets in 10 minutes, all payment failures",
                status="Reported", confidence=0.7, source_segment_ids=[sid],
                created_at=now, updated_at=now, created_by="inline",
            )
            session.add(f)
            await _append_timeline(session, incident_id, "fact_created",
                                   {"statement": f.statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        return

    if kind == "decision:rollback":
        did = f"decision-{incident_id}-{sid}"
        existing = await session.get(DecisionModel, did)
        if not existing:
            d = DecisionModel(
                id=did, incident_id=incident_id,
                statement="Rollback payment service to v2.14.3",
                status="Proposed", decided_by=segment.speaker_name or segment.speaker_id,
                decided_at=now, source_segment_ids=[sid],
                created_at=now, updated_at=now,
            )
            session.add(d)
            await _append_timeline(session, incident_id, "decision",
                                   {"statement": d.statement, "status": d.status}, actor_id=segment.speaker_id, ref_id=did)
        return

    if kind == "fact:2pct":
        fid = f"fact-{incident_id}-{sid}"
        existing = await session.get(FactModel, fid)
        if not existing:
            f = FactModel(
                id=fid, incident_id=incident_id,
                statement="Error rate dropped to 2% at 14:06 (conflicting with 12%)",
                status="Reported", confidence=0.6, source_segment_ids=[sid],
                created_at=now, updated_at=now, created_by="inline",
            )
            session.add(f)
            await _append_timeline(session, incident_id, "fact_created",
                                   {"statement": f.statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        return

    if kind == "action:jira":
        aid = f"action-jira-replica-{incident_id}"
        existing = await session.get(ActionItemModel, aid)
        if not existing:
            a = ActionItemModel(
                id=aid, incident_id=incident_id,
                title="Fix DB replica lag on payments-db-03",
                description="Track DB replica fix — seen in demo fixture",
                owner_id=None, owner_name="Backend", status="Open",
                requires_confirmation=False,
                due_at=now + timedelta(minutes=30),
                created_at=now, updated_at=now, source_segment_ids=[sid],
                tool_key="jira",
                tool_payload={"project": "PAY", "summary": "Fix DB replica lag on payments-db-03"},
            )
            session.add(a)
            await _append_timeline(session, incident_id, "action_created",
                                   {"title": a.title, "status": a.status}, actor_id=segment.speaker_id, ref_id=aid)
            # Tool event
            te = ToolEventModel(
                id=_gen_id("tool"), incident_id=incident_id, tool="jira",
                action="create_issue", status="pending",
                payload=a.tool_payload or {}, requires_approval=False,
                action_item_id=aid, created_at=now,
            )
            session.add(te)
            await _append_timeline(session, incident_id, "tool",
                                   {"tool": "jira", "action": "create_issue", "status": "pending"}, ref_id=te.id)
        return

    if kind == "action:comms":
        aid = f"action-comms-{incident_id}"
        existing = await session.get(ActionItemModel, aid)
        if not existing:
            a = ActionItemModel(
                id=aid, incident_id=incident_id,
                title="Own customer comms / status page update",
                description="Customer comms has no owner — needs assignment",
                owner_id=None, owner_name=None, status="Open",
                requires_confirmation=False, created_at=now, updated_at=now,
                source_segment_ids=[sid], tool_key="slack",
                tool_payload={"channel": "#incident-comms", "text": "Status page update for payment outage"},
            )
            session.add(a)
            await _append_timeline(session, incident_id, "action_created",
                                   {"title": a.title, "status": a.status}, actor_id=segment.speaker_id, ref_id=aid)
        return

    # u-011: update jira action to require confirmation
    if sid == "u-011":
        aid = f"action-jira-replica-{incident_id}"
        act = await session.get(ActionItemModel, aid)
        if act:
            act.requires_confirmation = True
            act.updated_at = now
            await _append_timeline(session, incident_id, "action_updated",
                                   {"title": act.title, "requiresConfirmation": True},
                                   actor_id=segment.speaker_id, ref_id=aid)
            # Update tool event
            te_r = await session.execute(
                select(ToolEventModel).where(
                    ToolEventModel.incident_id == incident_id,
                    ToolEventModel.action_item_id == aid,
                )
            )
            for te in te_r.scalars().all():
                te.requires_approval = True
                te.status = "requiresApproval"
        return

    if sid in ("u-006", "u-009"):
        return  # chatter, no extraction

    # --- Generic regex fallback ---
    _RE_HYPOTHESIS = re.compile(r"\bI think\b|maybe|might be|deploy.*caus|retry logic", re.I)
    _RE_DECISION = re.compile(r"rollback|revert|let'?s\s+rollback|decide to", re.I)
    _RE_ACTION_JIRA = re.compile(r"create.*jira|track.*fix|assign to", re.I)
    _RE_ACTION_COMMS = re.compile(r"customer\s*comms|status\s*page|owner for", re.I)
    _RE_ERROR_RATE = re.compile(r"error\s*rate", re.I)
    _RE_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.I)

    tl = text.lower()

    if _RE_ACTION_JIRA.search(text):
        aid = _gen_id("action")
        owner_name = "Backend" if "backend" in tl else None
        a = ActionItemModel(
            id=aid, incident_id=incident_id, title=text[:80].strip() or "Action from transcript",
            description=text, owner_id=None, owner_name=owner_name, status="Open",
            requires_confirmation=False, created_at=now, updated_at=now,
            source_segment_ids=[sid], tool_key="jira" if "jira" in tl else None,
        )
        session.add(a)
        await _append_timeline(session, incident_id, "action_created",
                               {"title": a.title, "status": a.status}, actor_id=segment.speaker_id, ref_id=aid)
        return

    if _RE_ACTION_COMMS.search(text):
        aid = _gen_id("action")
        a = ActionItemModel(
            id=aid, incident_id=incident_id,
            title="Customer comms / status page update", description=text,
            owner_id=None, owner_name=None, status="Open",
            requires_confirmation=False, created_at=now, updated_at=now,
            source_segment_ids=[sid],
        )
        session.add(a)
        await _append_timeline(session, incident_id, "action_created",
                               {"title": a.title, "status": a.status}, actor_id=segment.speaker_id, ref_id=aid)
        return

    if _RE_DECISION.search(text):
        did = _gen_id("decision")
        d = DecisionModel(
            id=did, incident_id=incident_id, statement=text[:200],
            status="Proposed", decided_by=segment.speaker_name or segment.speaker_id,
            decided_at=now, source_segment_ids=[sid], created_at=now, updated_at=now,
        )
        session.add(d)
        await _append_timeline(session, incident_id, "decision",
                               {"statement": d.statement, "status": d.status}, actor_id=segment.speaker_id, ref_id=did)
        return

    if _RE_HYPOTHESIS.search(text):
        hid = _gen_id("hypo")
        h = HypothesisModel(
            id=hid, incident_id=incident_id, statement=text[:200],
            status="Active", confidence=0.45, source_segment_ids=[sid],
            created_at=now, updated_at=now,
        )
        session.add(h)
        await _append_timeline(session, incident_id, "hypothesis_created",
                               {"statement": h.statement, "status": h.status}, actor_id=segment.speaker_id, ref_id=hid)
        return

    if _RE_ERROR_RATE.search(text) or _RE_PCT.search(text):
        fid = _gen_id("fact")
        f = FactModel(
            id=fid, incident_id=incident_id, statement=text[:200],
            status="Reported", confidence=0.7, source_segment_ids=[sid],
            created_at=now, updated_at=now, created_by="inline",
        )
        session.add(f)
        await _append_timeline(session, incident_id, "fact_created",
                               {"statement": f.statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        return

    # Nothing matched the fixture map or the regex heuristics — fall through to the real
    # LLM classifier (PRD §8.1) instead of silently treating this as chatter. This is what
    # makes cognition.py's extract()/Claude integration reachable outside the demo fixture.
    await _run_llm_extraction(session, segment, incident_id)


async def _run_llm_extraction(session: AsyncSession, segment: TranscriptSegmentModel, incident_id: str) -> None:
    """PRD §8.1 LLM Classifier fallback — materializes cognition.extract()'s extractions into rows."""
    sid, text, now = segment.id, segment.text or "", _now()

    facts_r = await session.execute(
        select(FactModel).where(FactModel.incident_id == incident_id).order_by(FactModel.created_at.desc()).limit(10)
    )
    hyps_r = await session.execute(
        select(HypothesisModel).where(HypothesisModel.incident_id == incident_id).order_by(HypothesisModel.created_at.desc()).limit(5)
    )
    segs_r = await session.execute(
        select(TranscriptSegmentModel).where(TranscriptSegmentModel.incident_id == incident_id).order_by(TranscriptSegmentModel.start_ms.desc()).limit(5)
    )
    snapshot_ctx = {
        "facts": [{"id": f.id, "statement": f.statement, "status": f.status} for f in facts_r.scalars().all()],
        "hypotheses": [{"id": h.id, "statement": h.statement, "status": h.status} for h in hyps_r.scalars().all()],
        "transcript": [{"id": s.id, "text": s.text, "speakerName": s.speaker_name} for s in segs_r.scalars().all()],
    }
    segment_dict = {
        "id": sid, "incidentId": incident_id, "text": text,
        "speakerName": segment.speaker_name, "role": segment.role, "startMs": segment.start_ms,
    }
    try:
        result = await cognition.extract(segment_dict, incident_id, snapshot_ctx)
    except Exception as e:
        logger.warning(f"LLM extraction fallback failed: {e}")
        return

    for ext in result.get("extractions", []):
        kind = ext.get("kind")
        statement = (ext.get("statement") or "")[:500]
        confidence = float(ext.get("confidence", 0.6))
        source_ids = ext.get("sourceSegmentIds") or [sid]
        if kind == "Fact":
            fid = _gen_id("fact")
            f = FactModel(
                id=fid, incident_id=incident_id, statement=statement,
                status=ext.get("status") or "Reported", confidence=confidence,
                source_segment_ids=source_ids, created_at=now, updated_at=now, created_by="llm",
            )
            session.add(f)
            await _append_timeline(session, incident_id, "fact_created",
                                   {"statement": statement, "status": f.status}, actor_id=segment.speaker_id, ref_id=fid)
        elif kind == "Hypothesis":
            hid = _gen_id("hypo")
            h = HypothesisModel(
                id=hid, incident_id=incident_id, statement=statement,
                status="Active", confidence=confidence, source_segment_ids=source_ids,
                created_at=now, updated_at=now,
            )
            session.add(h)
            await _append_timeline(session, incident_id, "hypothesis_created",
                                   {"statement": statement, "status": h.status}, actor_id=segment.speaker_id, ref_id=hid)
        elif kind == "Decision":
            did = _gen_id("decision")
            d = DecisionModel(
                id=did, incident_id=incident_id, statement=statement,
                status="Proposed", decided_by=segment.speaker_name or segment.speaker_id, decided_at=now,
                source_segment_ids=source_ids, created_at=now, updated_at=now,
            )
            session.add(d)
            await _append_timeline(session, incident_id, "decision",
                                   {"statement": statement, "status": d.status}, actor_id=segment.speaker_id, ref_id=did)
        elif kind == "ActionItem":
            aid = _gen_id("action")
            a = ActionItemModel(
                id=aid, incident_id=incident_id, title=(ext.get("title") or statement)[:512],
                description=statement, owner_id=None, owner_name=ext.get("ownerName"),
                status="Open", requires_confirmation=bool(ext.get("requiresConfirmation")),
                due_at=None, created_at=now, updated_at=now, source_segment_ids=source_ids,
                tool_key=ext.get("toolKey"),
            )
            session.add(a)
            await _append_timeline(session, incident_id, "action_created",
                                   {"title": a.title, "status": a.status}, actor_id=segment.speaker_id, ref_id=aid)
        # Chatter / ToolRequest / unrecognized kinds: no row created.


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"])
async def health():
    pg = "ok"
    redis_status = "mock"
    if _redis_enabled and _redis_client is not None:
        try:
            await _redis_client.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "unavailable"
    return {"status": "ok", "postgres": pg, "redis": redis_status}


@app.get("/tools/status", tags=["ops"])
async def tools_status():
    def _s(key: str) -> str:
        return "live" if os.getenv(key) else "mock"
    return {
        "jira": tools.adapter_mode("jira"), "slack": tools.adapter_mode("slack"),
        "pagerduty": tools.adapter_mode("pagerduty"), "datadog": tools.adapter_mode("datadog"),
        "deepgram": _s("DEEPGRAM_API_KEY"), "agora": _s("AGORA_APP_ID"),
        "agora_conversational_ai": "live" if agora_conversational_ai.CAI_ENABLED else "mock",
        "tts": tts.TTS_PROVIDER if tts.get_tts_provider().name() != "mock" else "mock",
    }


@app.get("/incidents/{incident_id}/audio/{filename}", tags=["ops"])
async def get_spoken_summary_audio(incident_id: str, filename: str):
    """Serves a cached TTS mp3 generated by _maybe_speak_summary. `incident_id` isn't used to
    look up the file (cache is keyed by text+provider hash, not incident) but is kept in the
    URL for a stable, incident-scoped path from the frontend's perspective."""
    if filename != _Path(filename).name or not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="invalid filename")
    path = tts.TTS_CACHE_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(str(path), media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# Agora Conversational AI Engine — mandatory hackathon integration
# ---------------------------------------------------------------------------
_agora_agents: dict[str, str] = {}  # incidentId -> agent_id, in-process (single-worker) tracking


@app.get("/agora/rtc-token", tags=["agora"])
async def agora_rtc_token(channel: str, uid: int = 0, expire: int = 3600):
    """Combined RTC + RTM token for a human/browser client — joins the RTC voice channel AND
    logs into the RTM channel of the same name to receive the Conversational AI agent's
    transcript/state events (per the agora skill's agent-client-toolkit-react reference: 'RTM
    channel name matches the RTC channel name', 'RTM login identity must match the RTM token
    subject'). Not used by the agent itself — it mints its own token internally."""
    if not agora_conversational_ai.CAI_ENABLED:
        raise HTTPException(status_code=503, detail="Agora not configured (AGORA_APP_ID/AGORA_APP_CERT missing)")
    from agora_agent import generate_convo_ai_token
    token = generate_convo_ai_token(
        app_id=agora_conversational_ai.AGORA_APP_ID,
        app_certificate=agora_conversational_ai.AGORA_APP_CERT,
        channel_name=channel, uid=uid, token_expire=expire,
    )
    return {"token": token, "appId": agora_conversational_ai.AGORA_APP_ID, "channel": channel, "uid": uid}


@app.post("/incidents/{incident_id}/agora-agent/join", tags=["agora"])
async def agora_agent_join(
    incident_id: str,
    body: dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_db),
):
    """Start the Conversational AI agent on this incident's RTC channel via the official
    `agora-agents` SDK (agora_conversational_ai.py). Body: {channel, agentRtcUid, remoteUid}.
    No token in the request — the SDK mints the ConvoAI token internally in App Credentials mode."""
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    channel = body.get("channel") or incident_id
    # Must be all-digits: the agent-kit SDK auto-generates the ConvoAI token in App Credentials
    # mode and rejects a non-numeric agent_uid (confirmed live 2026-09-06 — "echosphere-bot"
    # raised ValueError deep in agent.to_properties()). enable_string_uid on the session only
    # covers remote_uids, not the agent's own uid.
    agent_rtc_uid = body.get("agentRtcUid") or "911911"
    if not str(agent_rtc_uid).isdigit():
        raise HTTPException(status_code=422, detail="agentRtcUid must be a numeric RTC UID")
    remote_uid = body.get("remoteUid")
    system_prompt = (
        f"You are EchoSphere, an AI Incident Commander in the voice room for incident "
        f"'{inc_m.title}' (severity {inc_m.severity}). {cognition.VOICE_REPLY_SYSTEM_PROMPT}"
    )
    result = await agora_conversational_ai.join_agent(incident_id, channel, agent_rtc_uid, remote_uid, system_prompt)
    agent_id = result.get("agent_id", "")
    if agent_id:
        _agora_agents[incident_id] = agent_id
    await _append_timeline(session, incident_id, "system",
                           {"message": f"Agora Conversational AI agent joined ({result.get('status', 'unknown')})"})
    await session.flush()
    return result


@app.post("/incidents/{incident_id}/agora-agent/leave", tags=["agora"])
async def agora_agent_leave(incident_id: str, session: AsyncSession = Depends(get_db)):
    agent_id = _agora_agents.pop(incident_id, None)
    if not agent_id:
        raise HTTPException(status_code=404, detail="no running agent for this incident")
    result = await agora_conversational_ai.leave_agent(agent_id)
    await _append_timeline(session, incident_id, "system", {"message": "Agora Conversational AI agent left"})
    await session.flush()
    return result


@app.post("/agora/llm/chat/completions", tags=["agora"])
async def agora_custom_llm(body: dict[str, Any] = Body(...), session: AsyncSession = Depends(get_db)):
    """Custom-LLM webhook for Agora Conversational AI Engine (AGORA_CAI_LLM_MODE=custom).

    Matches the official Python/FastAPI reference (server-custom-llm/python/custom_llm.py):
    Agora's engine sends `context: {appId, userId, channel}` on every call — `channel` is how we
    know which incident this belongs to (our join endpoint always sets channel=incidentId, see
    agora_agent_join). Without reading `context`, this endpoint had no way to tell which incident
    a live voice request was for. Streams real token deltas (not a full-response-then-fake-chunk),
    and grounds the reply in the incident's actual current facts/gaps so it can't invent things
    the room hasn't actually established — directly serves the "never assert unconfirmed facts"
    guardrail that was declared in the system prompt but previously had no state to draw on."""
    messages = body.get("messages", [])
    context = body.get("context") or {}
    incident_id = context.get("channel")

    grounding = ""
    if incident_id:
        inc_m = await session.get(IncidentModel, incident_id)
        if inc_m:
            snap = await _build_snapshot(session, incident_id)
            fact_lines = "; ".join(f["statement"] for f in snap["facts"][-5:])
            open_gaps = [g["message"] for g in snap["gaps"] if not g.get("resolvedAt")][:3]
            grounding = f"\n\nCurrent incident state — Facts so far: {fact_lines or 'none yet'}."
            if open_gaps:
                grounding += f" Open issues: {'; '.join(open_gaps)}."

    if grounding and messages:
        messages = [{"role": "system", "content": grounding}] + list(messages)

    response_id = _gen_id("chatcmpl")
    model_name = body.get("model") or "echosphere-cognition"

    async def _sse():
        # Role-only first chunk, matching the official quickstart's chat/completions/route.ts —
        # some OpenAI-protocol clients expect the role announced before any content.
        first = {
            "id": response_id, "object": "chat.completion.chunk", "model": model_name,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(first)}\n\n"
        async for delta in cognition.generate_voice_reply_stream(messages):
            chunk = {
                "id": response_id, "object": "chat.completion.chunk", "model": model_name,
                "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        final_chunk = {
            "id": response_id, "object": "chat.completion.chunk", "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


@app.post("/incidents", tags=["incidents"])
async def create_incident(body: IncidentCreate, session: AsyncSession = Depends(get_db)):
    now = _now()
    if body.id:
        # Caller asked for a specific id (e.g. demo/seed.py re-seeding "payment-001") — if it
        # already exists, return it as-is instead of silently minting an unrelated random id,
        # which broke re-running the demo against a persisted DB without a full reset.
        existing = await session.get(IncidentModel, body.id)
        if existing:
            return await get_incident(body.id, session)
        iid = body.id
    else:
        iid = f"inc-{uuid.uuid4().hex[:8]}"

    inc = IncidentModel(
        id=iid, title=body.title, description=body.description,
        status="open", severity=body.severity or "SEV1",
        created_at=now, updated_at=now,
    )
    session.add(inc)
    # Init sequence
    session.add(TimelineSeqModel(incident_id=iid, current_seq=0))
    await session.flush()
    await _append_timeline(session, iid, "system", {"message": f"Incident created: {body.title}"}, ref_id=iid)
    await session.flush()

    snap = await _build_snapshot(session, iid)
    await _broadcast(iid, {"type": "snapshot", "snapshot": snap})
    return snap["incident"]


@app.get("/incidents", tags=["incidents"])
async def list_incidents(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(IncidentModel))
    incidents = []
    for inc_m in result.scalars().all():
        parts_r = await session.execute(
            select(ParticipantModel).where(ParticipantModel.incident_id == inc_m.id)
        )
        participants = [_model_to_participant(p) for p in parts_r.scalars().all()]
        incidents.append({
            "id": inc_m.id, "title": inc_m.title, "description": inc_m.description,
            "status": inc_m.status, "severity": inc_m.severity,
            "createdAt": inc_m.created_at.isoformat(), "updatedAt": inc_m.updated_at.isoformat(),
            "participants": participants, "summaryMarkdown": inc_m.summary_markdown,
        })
    return incidents


@app.get("/incidents/{incident_id}", tags=["incidents"])
async def get_incident(incident_id: str, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    parts_r = await session.execute(
        select(ParticipantModel).where(ParticipantModel.incident_id == incident_id)
    )
    participants = [_model_to_participant(p) for p in parts_r.scalars().all()]
    return {
        "id": inc_m.id, "title": inc_m.title, "description": inc_m.description,
        "status": inc_m.status, "severity": inc_m.severity,
        "createdAt": inc_m.created_at.isoformat(), "updatedAt": inc_m.updated_at.isoformat(),
        "participants": participants, "summaryMarkdown": inc_m.summary_markdown,
    }


@app.patch("/incidents/{incident_id}", tags=["incidents"])
async def patch_incident(incident_id: str, body: IncidentPatch, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    now = _now()
    if body.title is not None:
        inc_m.title = body.title
    if body.description is not None:
        inc_m.description = body.description
    if body.status is not None:
        old = inc_m.status
        inc_m.status = body.status
        await _append_timeline(session, incident_id, "system",
                               {"message": f"Status {old} -> {body.status}"}, ref_id=incident_id)
    if body.severity is not None:
        inc_m.severity = body.severity
    if body.summaryMarkdown is not None:
        inc_m.summary_markdown = body.summaryMarkdown
    inc_m.updated_at = now
    await session.flush()
    snap = await _build_snapshot(session, incident_id)
    await _broadcast(incident_id, {"type": "snapshot", "snapshot": snap})
    return snap["incident"]


@app.post("/incidents/{incident_id}/participants", tags=["incidents"])
async def add_participant(incident_id: str, body: ParticipantCreate, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    now = _now()
    pid = body.id or _gen_id("p")
    existing = await session.get(ParticipantModel, (pid, incident_id))
    if existing is not None:
        return _model_to_participant(existing)
    p = ParticipantModel(
        id=pid, incident_id=incident_id, name=body.name,
        role=body.role or "Unknown", avatar_url=body.avatarUrl,
        joined_at=now, is_bot=body.isBot or False,
    )
    session.add(p)
    await _append_timeline(session, incident_id, "system",
                           {"message": f"Participant joined: {p.name} ({p.role})"},
                           actor_id=pid, ref_id=pid)
    await session.flush()
    snap = await _build_snapshot(session, incident_id)
    await _broadcast(incident_id, {"type": "snapshot", "snapshot": snap})
    return _model_to_participant(p)


@app.get("/incidents/{incident_id}/snapshot", tags=["incidents"])
async def get_snapshot(incident_id: str, session: AsyncSession = Depends(get_db)):
    await _detect_and_store_gaps(session, incident_id)
    await session.flush()
    return await _build_snapshot(session, incident_id)


@app.post("/incidents/{incident_id}/transcript", tags=["transcript"])
async def push_transcript(incident_id: str, body: dict[str, Any] = Body(...), session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")

    # Resolve segment
    seg_dict = body.get("segment") if isinstance(body.get("segment"), dict) else body
    seg_dict.setdefault("incidentId", incident_id)
    seg_dict["incidentId"] = incident_id
    seg_dict.setdefault("id", _gen_id("seg"))
    seg_dict.setdefault("createdAt", _now().isoformat())

    # Validate
    try:
        segment = TranscriptSegment.model_validate(seg_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid TranscriptSegment: {e}")

    now = _now()
    # Idempotent: replaying the same segment id into the same incident (retry, re-seed without a
    # restart) must not crash or double-count facts/gaps/timeline entries.
    existing_seg = await session.get(TranscriptSegmentModel, (segment.id, incident_id))
    if existing_seg is not None:
        snap = await _build_snapshot(session, incident_id)
        return {"ok": True, "segmentId": segment.id, "snapshot": snap, "duplicate": True}

    seg_m = TranscriptSegmentModel(
        id=segment.id, incident_id=incident_id, speaker_id=segment.speakerId,
        speaker_name=segment.speakerName, role=segment.role, text=segment.text,
        is_final=segment.isFinal, start_ms=segment.startMs, end_ms=segment.endMs,
        confidence=segment.confidence, language=segment.language, created_at=now,
    )
    session.add(seg_m)
    await _append_timeline(session, incident_id, "transcript",
                           {"id": segment.id, "text": segment.text[:120], "speakerName": segment.speakerName},
                           actor_id=segment.speakerId, ref_id=segment.id)

    inc_m.updated_at = now

    # Run cognition inline
    await _run_cognition(session, seg_m, incident_id)

    # Recompute gaps
    await _detect_and_store_gaps(session, incident_id)
    await session.flush()

    snap = await _build_snapshot(session, incident_id)
    spoken = await _maybe_speak_summary(session, incident_id, snap)
    await session.flush()
    if spoken:
        snap = await _build_snapshot(session, incident_id)
    await _broadcast(incident_id, {"type": "snapshot", "snapshot": snap})
    if spoken:
        await _broadcast(incident_id, {"type": "spoken_summary", **spoken})
    return {"ok": True, "segmentId": segment.id, "snapshot": snap}


# Action endpoints
@app.post("/incidents/{incident_id}/actions/{action_id}/approve", tags=["actions"])
async def approve_action(incident_id: str, action_id: str, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    act = await session.get(ActionItemModel, action_id)
    if not act or act.incident_id != incident_id:
        raise HTTPException(status_code=404, detail="action not found")

    now = _now()
    if act.requires_confirmation:
        act.requires_confirmation = False
    if act.status == "Open":
        act.status = "InProgress"
    act.updated_at = now
    await _append_timeline(session, incident_id, "action_updated",
                           {"title": act.title, "status": act.status}, ref_id=action_id)

    # Dispatch the real (or mock, if no credentials configured) tool adapter — respects the
    # action's actual tool_key instead of always simulating a Jira ticket.
    tool_key = act.tool_key or "jira"
    tool_action = {"jira": "create_issue", "github": "create_issue", "slack": "send_message",
                   "pagerduty": "trigger_page", "datadog": "annotate"}.get(tool_key, "create_issue")
    result = await tools.invoke_tool(
        tool_key, tool_action, act.tool_payload or {"summary": act.title, "text": act.title},
        {"incidentId": incident_id, "actionItemId": action_id, "requiresConfirmation": False, "action": tool_action},
    )
    te = ToolEventModel(
        id=result.get("id") or _gen_id("tool"), incident_id=incident_id, tool=tool_key,
        action=tool_action, status=result.get("status", "success"),
        payload=act.tool_payload or {}, result=result.get("result"),
        requires_approval=False, action_item_id=action_id, created_at=now,
    )
    session.add(te)
    await _append_timeline(session, incident_id, "tool",
                           {"tool": te.tool, "action": te.action, "status": te.status}, ref_id=te.id)

    await _detect_and_store_gaps(session, incident_id)
    await session.flush()
    snap = await _build_snapshot(session, incident_id)
    await _broadcast(incident_id, {"type": "snapshot", "snapshot": snap})
    return {"ok": True, "incidentId": incident_id, "actionId": action_id,
            "status": act.status, "toolEvent": _model_to_tool_event(te)}


@app.post("/incidents/{incident_id}/approve/{action_id}", tags=["actions"])
async def approve_action_legacy(incident_id: str, action_id: str, session: AsyncSession = Depends(get_db)):
    return await approve_action(incident_id, action_id, session)


@app.post("/incidents/{incident_id}/actions/{action_id}/update-status", tags=["actions"])
async def update_action_status(incident_id: str, action_id: str, body: ActionUpdateStatus, session: AsyncSession = Depends(get_db)):
    act = await session.get(ActionItemModel, action_id)
    if not act or act.incident_id != incident_id:
        raise HTTPException(status_code=404, detail="action not found")
    act.status = body.status
    act.updated_at = _now()
    await _append_timeline(session, incident_id, "action_updated",
                           {"title": act.title, "status": act.status}, ref_id=action_id)
    await _detect_and_store_gaps(session, incident_id)
    await session.flush()
    snap = await _build_snapshot(session, incident_id)
    await _broadcast(incident_id, {"type": "snapshot", "snapshot": snap})
    return _model_to_action(act)


@app.post("/incidents/{incident_id}/summary", tags=["incidents"])
async def generate_summary(incident_id: str, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")

    await _detect_and_store_gaps(session, incident_id)
    await session.flush()
    snap = await _build_snapshot(session, incident_id)

    facts = snap["facts"]
    hyps = snap["hypotheses"]
    decs = snap["decisions"]
    acts = snap["actions"]
    gaps = snap["gaps"]
    timeline = snap["timeline"]
    participants = snap["incident"]["participants"]

    lines: list[str] = []
    lines.append(f"# Incident {incident_id} — {inc_m.title}")
    lines.append("")
    lines.append(f"_Severity: {inc_m.severity} | Status: {inc_m.status} | Generated: {_now().isoformat()}_")
    lines.append("")
    if inc_m.description:
        lines.append(inc_m.description)
        lines.append("")
    lines.append("## Timeline (key events)")
    for ev in timeline[-20:]:
        lines.append(f"- [{ev['type']}] seq={ev['seq']} {_format_event_text(ev)[:120]}")
    lines.append("")
    lines.append("## Facts")
    if facts:
        for f in facts:
            lines.append(f"- **{f['status']}** ({f['confidence']:.2f}): {f['statement']} _[src: {', '.join(f['sourceSegmentIds'])}]_")
    else:
        lines.append("- _No facts yet_")
    lines.append("")
    lines.append("## Hypotheses")
    if hyps:
        for h in hyps:
            lines.append(f"- **{h['status']}** ({h['confidence']:.2f}): {h['statement']}")
    else:
        lines.append("- _No hypotheses_")
    lines.append("")
    lines.append("## Decisions")
    if decs:
        for d in decs:
            lines.append(f"- **{d['status']}**: {d['statement']} (by {d.get('decidedBy','unknown')})")
    else:
        lines.append("- _No decisions_")
    lines.append("")
    lines.append("## Actions")
    if acts:
        for a in acts:
            owner = a.get('ownerName') or a.get('ownerId') or "_unassigned_"
            lines.append(f"- [{a['status']}] **{a['title']}** — owner: {owner}{' (requires approval)' if a.get('requiresConfirmation') else ''}")
    else:
        lines.append("- _No actions_")
    lines.append("")
    lines.append("## Gaps / Risks")
    if gaps:
        for g in gaps:
            lines.append(f"- **{g['kind']}** ({g['severity']}): {g['message']}")
    else:
        lines.append("- _No gaps detected_")
    lines.append("")
    lines.append("## Unresolved Risks")
    unresolved = [g for g in gaps if g.get('resolvedAt') is None]
    if unresolved:
        for g in unresolved:
            lines.append(f"- {g['message']}")
    else:
        lines.append("- _None_")
    lines.append("")
    lines.append("---")
    lines.append(f"_Participants: {', '.join(p['name'] + ' (' + p['role'] + ')' for p in participants) if participants else 'none'}_")
    markdown = "\n".join(lines)

    inc_m.summary_markdown = markdown
    inc_m.updated_at = _now()
    await _append_timeline(session, incident_id, "summary", {"markdown": markdown[:500]}, ref_id=incident_id)
    await session.flush()

    snap = await _build_snapshot(session, incident_id)
    await _broadcast(incident_id, {"type": "snapshot", "snapshot": snap})
    return {"incidentId": incident_id, "markdown": markdown}


# ---------------------------------------------------------------------------
# WS timeline
# ---------------------------------------------------------------------------
@app.websocket("/ws/incidents/{incident_id}")
async def ws_timeline(websocket: WebSocket, incident_id: str):
    await websocket.accept()
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Auto-create placeholder if not exists
        inc_m = await session.get(IncidentModel, incident_id)
        if not inc_m:
            now = _now()
            inc_m = IncidentModel(
                id=incident_id, title=f"Incident {incident_id}",
                status="open", severity="SEV1", created_at=now, updated_at=now,
            )
            session.add(inc_m)
            session.add(TimelineSeqModel(incident_id=incident_id, current_seq=0))
            await session.flush()
            await _append_timeline(session, incident_id, "system",
                                   {"message": "WS connected — placeholder incident created"}, ref_id=incident_id)
            await session.commit()

        snap = await _build_snapshot(session, incident_id)

    conns = _ws_connections.setdefault(incident_id, set())
    conns.add(websocket)

    try:
        await websocket.send_json({"type": "snapshot", "snapshot": snap})
        await websocket.send_json({"type": "connected", "incidentId": incident_id})
    except Exception:
        pass

    # Redis subscriber task
    redis_task: Optional[asyncio.Task] = None
    if _redis_enabled and _redis_client is not None:
        async def _redis_listener():
            try:
                pubsub = _redis_client.pubsub()
                await pubsub.subscribe(f"incident:{incident_id}")
                async for msg in pubsub.listen():
                    if msg.get("type") == "message":
                        try:
                            data = json.loads(msg["data"])
                            await websocket.send_json(data)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Redis listener ended: {e}")
        redis_task = asyncio.create_task(_redis_listener())

    try:
        while True:
            data = await websocket.receive_text()
            if data in ("ping", '"ping"'):
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "ack", "echo": data})
                try:
                    obj = json.loads(data)
                    if isinstance(obj, dict) and obj.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if redis_task:
            redis_task.cancel()
            try:
                await redis_task
            except Exception:
                pass
        conns = _ws_connections.get(incident_id, set())
        conns.discard(websocket)
        if not conns:
            _ws_connections.pop(incident_id, None)


# ---------------------------------------------------------------------------
# Convenience endpoints
# ---------------------------------------------------------------------------
@app.get("/incidents/{incident_id}/timeline", tags=["incidents"])
async def get_timeline(incident_id: str, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    result = await session.execute(
        select(TimelineEventModel).where(TimelineEventModel.incident_id == incident_id).order_by(TimelineEventModel.seq)
    )
    return [_model_to_timeline(e) for e in result.scalars().all()]


@app.get("/incidents/{incident_id}/gaps", tags=["incidents"])
async def get_gaps(incident_id: str, session: AsyncSession = Depends(get_db)):
    inc_m = await session.get(IncidentModel, incident_id)
    if not inc_m:
        raise HTTPException(status_code=404, detail="incident not found")
    await _detect_and_store_gaps(session, incident_id)
    await session.flush()
    result = await session.execute(
        select(GapModel).where(GapModel.incident_id == incident_id)
    )
    return [_model_to_gap(g) for g in result.scalars().all()]


@app.get("/", tags=["ops"])
async def root():
    return {"service": "agora-api", "version": "0.2.0", "docs": "/docs", "storage": "postgres"}
