"""
Unit tests for Pydantic model validation and round-trip serialization.
"""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError


# Import models from main.py (inline Pydantic models)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def make_timestamp():
    return datetime.now(timezone.utc)


class TestIncidentCreate:
    def test_valid_incident(self):
        from main import IncidentCreate
        inc = IncidentCreate(title="Test Incident", severity="SEV1")
        assert inc.title == "Test Incident"
        assert inc.severity == "SEV1"

    def test_incident_minimal(self):
        from main import IncidentCreate
        inc = IncidentCreate(title="X")
        assert inc.title == "X"
        assert inc.severity == "SEV1"  # default

    def test_empty_title_fails(self):
        from main import IncidentCreate
        with pytest.raises(ValidationError):
            IncidentCreate(title="")

    def test_invalid_severity_fails(self):
        from main import IncidentCreate
        with pytest.raises(ValidationError):
            IncidentCreate(title="Test", severity="SEV5")


class TestTranscriptSegment:
    def test_valid_segment(self):
        from main import TranscriptSegment
        seg = TranscriptSegment(
            id="seg-001", incidentId="inc-001", text="Hello world",
            startMs=0, endMs=1000, createdAt=make_timestamp(),
        )
        assert seg.text == "Hello world"
        assert seg.isFinal is True

    def test_segment_with_speaker(self):
        from main import TranscriptSegment
        seg = TranscriptSegment(
            id="seg-002", incidentId="inc-001", text="Test",
            speakerId="p-001", speakerName="Priya", role="SRE",
            startMs=0, endMs=2000, createdAt=make_timestamp(),
        )
        assert seg.speakerName == "Priya"
        assert seg.role == "SRE"


class TestFact:
    def test_valid_fact(self):
        from main import Fact
        fact = Fact(
            id="fact-001", incidentId="inc-001",
            statement="Error rate is 12%", status="Reported",
            confidence=0.75, sourceSegmentIds=["seg-001"],
            createdAt=make_timestamp(), updatedAt=make_timestamp(),
        )
        assert fact.confidence == 0.75
        assert len(fact.sourceSegmentIds) == 1

    def test_fact_empty_source_fails(self):
        from main import Fact
        with pytest.raises(ValidationError):
            Fact(
                id="fact-002", incidentId="inc-001",
                statement="Test", status="Reported",
                confidence=0.5, sourceSegmentIds=[],
                createdAt=make_timestamp(), updatedAt=make_timestamp(),
            )

    def test_fact_invalid_status_fails(self):
        from main import Fact
        with pytest.raises(ValidationError):
            Fact(
                id="fact-003", incidentId="inc-001",
                statement="Test", status="Invalid",
                confidence=0.5, sourceSegmentIds=["seg-001"],
                createdAt=make_timestamp(), updatedAt=make_timestamp(),
            )


class TestActionItem:
    def test_valid_action(self):
        from main import ActionItem
        action = ActionItem(
            id="act-001", incidentId="inc-001",
            title="Fix DB replica lag", status="Open",
            requiresConfirmation=False,
            createdAt=make_timestamp(), updatedAt=make_timestamp(),
        )
        assert action.title == "Fix DB replica lag"
        assert action.requiresConfirmation is False

    def test_action_requires_confirmation(self):
        from main import ActionItem
        action = ActionItem(
            id="act-002", incidentId="inc-001",
            title="Rollback payment service", status="Open",
            requiresConfirmation=True,
            createdAt=make_timestamp(), updatedAt=make_timestamp(),
        )
        assert action.requiresConfirmation is True


class TestDecision:
    def test_valid_decision(self):
        from main import Decision
        dec = Decision(
            id="dec-001", incidentId="inc-001",
            statement="Rollback to v2.14.3", status="Proposed",
            createdAt=make_timestamp(), updatedAt=make_timestamp(),
        )
        assert dec.status == "Proposed"


class TestGap:
    def test_valid_gap(self):
        from main import Gap
        gap = Gap(
            id="gap-001", incidentId="inc-001",
            kind="ConflictingInfo", severity="high",
            message="Conflicting error rate values",
            createdAt=make_timestamp(),
        )
        assert gap.kind == "ConflictingInfo"


class TestIncidentSnapshot:
    def test_empty_snapshot(self):
        from main import IncidentSnapshot, Incident
        now = make_timestamp()
        inc = Incident(
            id="inc-001", title="Test",
            createdAt=now, updatedAt=now,
        )
        snap = IncidentSnapshot(incident=inc)
        assert len(snap.facts) == 0
        assert len(snap.actions) == 0
