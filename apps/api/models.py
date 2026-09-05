"""
SQLAlchemy declarative models — Postgres persistence layer.
Mirrors packages/shared/python/agora_shared/types.py.
"""
from __future__ import annotations

import datetime
from typing import Optional, Any

from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime, JSON,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

try:
    from pgvector.sqlalchemy import Vector  # type: ignore
    HAS_PGVECTOR = True
except Exception:
    HAS_PGVECTOR = False

# PRD §8.10 Cross-Incident Memory — Hypothesis.embedding is a native pgvector `vector(N)` column
# on Postgres (enables future `<=>` similarity queries / ivfflat indexing) and a plain JSON column
# of floats on SQLite (used in tests), via SQLAlchemy's per-dialect type variant. Application code
# (cognition.find_precedents) computes cosine similarity in Python either way, so behavior is
# identical across both — only the storage representation differs.
EMBED_DIM = 256


def _embedding_column():
    base = JSON()
    if HAS_PGVECTOR:
        return Column(base.with_variant(Vector(EMBED_DIM), "postgresql"), nullable=True)
    return Column(base, nullable=True)


class Base(DeclarativeBase):
    pass


class IncidentModel(Base):
    __tablename__ = "incidents"

    id = Column(String(64), primary_key=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="open")
    severity = Column(String(8), nullable=False, default="SEV1")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    summary_markdown = Column(Text, nullable=True)

    participants = relationship("ParticipantModel", back_populates="incident", cascade="all, delete-orphan")
    transcript_segments = relationship("TranscriptSegmentModel", back_populates="incident", cascade="all, delete-orphan")
    facts = relationship("FactModel", back_populates="incident", cascade="all, delete-orphan")
    hypotheses = relationship("HypothesisModel", back_populates="incident", cascade="all, delete-orphan")
    decisions = relationship("DecisionModel", back_populates="incident", cascade="all, delete-orphan")
    actions = relationship("ActionItemModel", back_populates="incident", cascade="all, delete-orphan")
    conflicts = relationship("ConflictModel", back_populates="incident", cascade="all, delete-orphan")
    gaps = relationship("GapModel", back_populates="incident", cascade="all, delete-orphan")
    timeline_events = relationship("TimelineEventModel", back_populates="incident", cascade="all, delete-orphan")
    tool_events = relationship("ToolEventModel", back_populates="incident", cascade="all, delete-orphan")


class ParticipantModel(Base):
    __tablename__ = "participants"
    # Composite PK: fixture participant ids (e.g. "p-priya") are only unique per incident, not
    # globally — same bug class as TranscriptSegmentModel (see models.py note there). A global
    # PK on `id` alone broke re-seeding the same fixture into a second incident.
    __table_args__ = (UniqueConstraint("incident_id", "name", name="uq_participant_incident_name"),)

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True, index=True)
    name = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, default="Unknown")
    avatar_url = Column(String(1024), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False)
    is_bot = Column(Boolean, nullable=False, default=False)

    incident = relationship("IncidentModel", back_populates="participants")


class TranscriptSegmentModel(Base):
    __tablename__ = "transcript_segments"
    # Composite PK: segment ids (e.g. fixture utterance ids "u-001") are only guaranteed unique
    # per incident, not globally — a global PK on `id` alone breaks re-seeding the same fixture
    # into a second incident, or replaying a demo twice, with a UNIQUE constraint violation.
    __table_args__ = (Index("ix_transcript_incident_start", "incident_id", "start_ms"),)

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True, index=True)
    speaker_id = Column(String(64), nullable=True)
    speaker_name = Column(String(256), nullable=True)
    role = Column(String(32), nullable=True)
    text = Column(Text, nullable=False)
    is_final = Column(Boolean, nullable=False, default=True)
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False, default=0.9)
    language = Column(String(16), nullable=False, default="en-US")
    created_at = Column(DateTime(timezone=True), nullable=False)

    incident = relationship("IncidentModel", back_populates="transcript_segments")


class FactModel(Base):
    __tablename__ = "facts"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    statement = Column(Text, nullable=False)
    status = Column(String(32), nullable=False)  # Confirmed|Corroborated|Reported|Contradicted
    confidence = Column(Float, nullable=False)
    # PRD §8 "Confidence & Evidence Schema" / §10 verification_status — set by the monitoring
    # verification engine (cognition.verify_claim); independent of `status` above, which is the
    # evidence-corroboration tier, not the monitoring-verification outcome.
    verification_status = Column(String(16), nullable=False, default="unverified")  # verified|contradicted|unverified|unknown|unavailable
    source_segment_ids = Column(JSON, nullable=False, default=list)  # list of segment ids
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(128), nullable=True)

    incident = relationship("IncidentModel", back_populates="facts")


class HypothesisModel(Base):
    __tablename__ = "hypotheses"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    statement = Column(Text, nullable=False)
    status = Column(String(32), nullable=False)  # Active|Disproven|Confirmed
    confidence = Column(Float, nullable=False)
    verification_status = Column(String(16), nullable=False, default="unverified")  # verified|contradicted|unverified|unknown|unavailable
    reference_count = Column(Integer, nullable=False, default=1)  # PRD §8.5 assumption-creep: times referenced/reinforced
    embedding = _embedding_column()  # PRD §8.10 cross-incident memory; see _embedding_column() docstring above
    source_segment_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    disproven_reason = Column(Text, nullable=True)

    incident = relationship("IncidentModel", back_populates="hypotheses")


class DecisionModel(Base):
    __tablename__ = "decisions"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    statement = Column(Text, nullable=False)
    status = Column(String(32), nullable=False)  # Proposed|Approved|Reverted
    decided_by = Column(String(256), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    # PRD §8.9 Decision Hygiene — completeness fields required before a decision should move
    # to Approved; a DecisionHygiene gap is raised when Approved without these filled in.
    expected_outcome = Column(Text, nullable=True)
    risk = Column(Text, nullable=True)
    rollback_plan = Column(Text, nullable=True)
    source_segment_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    incident = relationship("IncidentModel", back_populates="decisions")


class ActionItemModel(Base):
    __tablename__ = "action_items"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(String(64), nullable=True)
    owner_name = Column(String(256), nullable=True)
    status = Column(String(32), nullable=False)  # Open|InProgress|Blocked|Done|Overdue
    requires_confirmation = Column(Boolean, nullable=False, default=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    source_segment_ids = Column(JSON, nullable=False, default=list)
    tool_key = Column(String(32), nullable=True)  # jira|slack|pagerduty|datadog|github
    tool_payload = Column(JSON, nullable=True)

    incident = relationship("IncidentModel", back_populates="actions")


class ConflictModel(Base):
    """PRD §10.3 Conflict — first-class contradiction record, distinct from Gap(kind=ConflictingInfo).

    Gap remains the generic "something needs attention" signal surfaced in the dashboard's Risk
    Indicators; Conflict is the specific claim_a/claim_b record with its own review lifecycle
    (OPEN -> UNDER_REVIEW -> RESOLVED/DISMISSED) per PRD §10.2.
    """
    __tablename__ = "conflicts"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_a = Column(Text, nullable=False)
    claim_b = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="OPEN")  # OPEN|UNDER_REVIEW|RESOLVED|DISMISSED
    resolution = Column(Text, nullable=True)
    verification_required = Column(Boolean, nullable=False, default=True)
    related_ids = Column(JSON, nullable=False, default=list)  # Fact/Hypothesis ids behind claim_a/claim_b
    detected_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("IncidentModel", back_populates="conflicts")


class GapModel(Base):
    __tablename__ = "gaps"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)  # MissingOwner|ConflictingInfo|UnverifiedAssumption|StaleAction
    severity = Column(String(16), nullable=False, default="medium")
    message = Column(Text, nullable=False)
    related_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("IncidentModel", back_populates="gaps")


class TimelineEventModel(Base):
    __tablename__ = "timeline_events"
    __table_args__ = (Index("ix_timeline_incident_seq", "incident_id", "seq"),)

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(32), nullable=False)
    seq = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    actor_id = Column(String(64), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    ref_id = Column(String(64), nullable=True)

    incident = relationship("IncidentModel", back_populates="timeline_events")


class ToolEventModel(Base):
    __tablename__ = "tool_events"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    tool = Column(String(32), nullable=False)
    action = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)  # pending|success|failed|requiresApproval|rejected
    payload = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    requires_approval = Column(Boolean, nullable=False, default=False)
    action_item_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    incident = relationship("IncidentModel", back_populates="tool_events")


# Sequence counter table for timeline ordering per incident
class TimelineSeqModel(Base):
    __tablename__ = "timeline_sequences"

    incident_id = Column(String(64), primary_key=True)
    current_seq = Column(Integer, nullable=False, default=0)
