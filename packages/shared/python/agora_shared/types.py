"""
Pydantic mirror of packages/shared/src/index.ts — keep enums/fields in sync.
Source of truth is Zod; this file must be updated together with TS changes.
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field, ConfigDict

FactStatus = Literal["Confirmed", "Corroborated", "Reported", "Contradicted"]
HypothesisStatus = Literal["Active", "Disproven", "Confirmed"]
DecisionStatus = Literal["Proposed", "Approved", "Reverted"]
ActionStatus = Literal["Open", "InProgress", "Blocked", "Done", "Overdue"]
GapKind = Literal["MissingOwner", "ConflictingInfo", "UnverifiedAssumption", "StaleAction"]
TimelineEventType = Literal[
    "transcript", "fact_created", "fact_updated",
    "hypothesis_created", "hypothesis_updated",
    "decision", "action_created", "action_updated",
    "gap_detected", "gap_resolved", "tool", "summary", "system"
]
ToolName = Literal["jira", "slack", "pagerduty", "datadog", "github"]
ToolEventStatus = Literal["pending", "success", "failed", "requiresApproval", "rejected"]
IncidentStatus = Literal["open", "investigating", "mitigated", "resolved", "closed"]
ParticipantRole = Literal["SRE", "Backend", "Frontend", "Support", "Biz", "Comms", "Unknown"]

model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=False)

class Participant(BaseModel):
    model_config = model_config
    id: str = Field(description="participant id")
    name: str
    role: ParticipantRole = "Unknown"
    avatarUrl: Optional[str] = None
    joinedAt: datetime
    isBot: bool = False

class TranscriptSegment(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    speakerId: Optional[str] = Field(default=None, description="participant id or null if unknown")
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
    sourceSegmentIds: list[str] = Field(min_length=1, description="utteranceIds that support this fact")
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
    requiresConfirmation: bool = Field(default=False, description="if true, tool call blocked until approved")
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

class ToolEvent(BaseModel):
    model_config = model_config
    id: str
    incidentId: str
    tool: ToolName
    action: str = Field(description="e.g. create_issue, send_message, trigger_page")
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
    seq: int = Field(ge=0, description="monotonic ordering")
    createdAt: datetime
    actorId: Optional[str] = None
    payload: dict[str, Any] = Field(description="one of Fact|Hypothesis|Decision|ActionItem|Gap|ToolEvent|TranscriptSegment")
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
    """Aggregate snapshot published over WS / returned by GET /incidents/{id}"""
    model_config = model_config
    incident: Incident
    facts: list[Fact] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    toolEvents: list[ToolEvent] = Field(default_factory=list)
