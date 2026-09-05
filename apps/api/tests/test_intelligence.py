"""
Tests for the PRD §8 intelligence-engine additions: Conflict as a first-class record,
Duplicate-Work detection, Decision Hygiene, Stall Nudges, and the LLM-classifier fallback.
Assumption-Creep is covered end-to-end by test_e2e_payment.py's fixture replay.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActionItemModel, DecisionModel, ToolEventModel


def _now():
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
class TestConflictRecord:
    async def test_conflicting_facts_create_conflict_record(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Conflict Test"})
        inc_id = create_r.json()["id"]
        for i, text in enumerate([
            "Error rate is at 12% and rising.",
            "Error rate has dropped to 2% already.",
        ]):
            seg = {
                "id": f"u-conf-{i}", "incidentId": inc_id, "text": text,
                "speakerName": "Alex", "role": "Backend",
                "startMs": i * 1000, "endMs": i * 1000 + 500, "confidence": 0.9,
            }
            await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert len(snap["conflicts"]) >= 1
        conflict = snap["conflicts"][0]
        assert conflict["status"] == "OPEN"
        assert conflict["verificationRequired"] is True
        assert any(g["kind"] == "ConflictingInfo" for g in snap["gaps"])


@pytest.mark.asyncio
class TestDuplicateWorkDetection:
    async def test_two_owners_same_topic_flagged(self, client: AsyncClient, db_session: AsyncSession):
        create_r = await client.post("/incidents", json={"title": "Dupe Test"})
        inc_id = create_r.json()["id"]
        now = _now()
        db_session.add(ActionItemModel(
            id="act-a", incident_id=inc_id, title="Investigate database replica lag issue",
            description="checking replica health", owner_id=None, owner_name="Priya",
            status="Open", requires_confirmation=False, created_at=now, updated_at=now,
            source_segment_ids=[],
        ))
        db_session.add(ActionItemModel(
            id="act-b", incident_id=inc_id, title="Look into database replica lag problem",
            description="also checking replica health", owner_id=None, owner_name="Arun",
            status="Open", requires_confirmation=False, created_at=now, updated_at=now,
            source_segment_ids=[],
        ))
        await db_session.flush()

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        dupe_gaps = [g for g in snap["gaps"] if g["kind"] == "DuplicateWork"]
        assert len(dupe_gaps) == 1
        assert "Priya" in dupe_gaps[0]["message"] and "Arun" in dupe_gaps[0]["message"]

    async def test_same_owner_not_flagged(self, client: AsyncClient, db_session: AsyncSession):
        create_r = await client.post("/incidents", json={"title": "No Dupe Test"})
        inc_id = create_r.json()["id"]
        now = _now()
        for i in range(2):
            db_session.add(ActionItemModel(
                id=f"act-same-{i}", incident_id=inc_id, title="Investigate database replica lag",
                description="checking replica health", owner_id=None, owner_name="Priya",
                status="Open", requires_confirmation=False, created_at=now, updated_at=now,
                source_segment_ids=[],
            ))
        await db_session.flush()

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert not [g for g in snap["gaps"] if g["kind"] == "DuplicateWork"]


@pytest.mark.asyncio
class TestDecisionHygiene:
    async def test_approved_decision_missing_fields_flagged(self, client: AsyncClient, db_session: AsyncSession):
        create_r = await client.post("/incidents", json={"title": "Hygiene Test"})
        inc_id = create_r.json()["id"]
        now = _now()
        db_session.add(DecisionModel(
            id="dec-incomplete", incident_id=inc_id, statement="Rollback to v2.4",
            status="Approved", decided_by=None, decided_at=now,
            expected_outcome=None, risk=None, rollback_plan=None,
            source_segment_ids=[], created_at=now, updated_at=now,
        ))
        await db_session.flush()

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        hygiene_gaps = [g for g in snap["gaps"] if g["kind"] == "DecisionHygiene"]
        assert len(hygiene_gaps) == 1
        assert "owner" in hygiene_gaps[0]["message"]

    async def test_approved_decision_complete_not_flagged(self, client: AsyncClient, db_session: AsyncSession):
        create_r = await client.post("/incidents", json={"title": "Hygiene OK Test"})
        inc_id = create_r.json()["id"]
        now = _now()
        db_session.add(DecisionModel(
            id="dec-complete", incident_id=inc_id, statement="Rollback to v2.4",
            status="Approved", decided_by="Priya", decided_at=now,
            expected_outcome="Error rate returns to baseline", risk="Brief downtime during redeploy",
            rollback_plan="Redeploy v2.5 if issue persists",
            source_segment_ids=[], created_at=now, updated_at=now,
        ))
        await db_session.flush()

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert not [g for g in snap["gaps"] if g["kind"] == "DecisionHygiene"]


@pytest.mark.asyncio
class TestStallNudge:
    async def test_stale_owned_action_gets_one_nudge(self, client: AsyncClient, db_session: AsyncSession):
        create_r = await client.post("/incidents", json={"title": "Nudge Test"})
        inc_id = create_r.json()["id"]
        stale_time = _now() - timedelta(minutes=20)
        db_session.add(ActionItemModel(
            id="act-stale", incident_id=inc_id, title="Check replica health",
            description="", owner_id=None, owner_name="Karan",
            status="Open", requires_confirmation=False, created_at=stale_time, updated_at=stale_time,
            source_segment_ids=[],
        ))
        await db_session.flush()

        # Trigger gap detection twice — nudge must be idempotent (sent once, not duplicated)
        await client.get(f"/incidents/{inc_id}/snapshot")
        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()

        nudges = [te for te in snap["toolEvents"] if te.get("action") == "stall_nudge"]
        assert len(nudges) == 1
        assert nudges[0]["actionItemId"] == "act-stale"
        assert any(g["kind"] == "StaleAction" for g in snap["gaps"])


@pytest.mark.asyncio
class TestLLMExtractionFallback:
    async def test_unmatched_utterance_falls_through_to_llm_classifier(self, client: AsyncClient):
        """An utterance matching neither the fixture map nor the regex heuristics should reach
        cognition.extract() (PRD §8.1 LLM Classifier), not be silently dropped as chatter."""
        create_r = await client.post("/incidents", json={"title": "LLM Fallback Test"})
        inc_id = create_r.json()["id"]

        async def fake_extract(segment, incident_id, snapshot):
            return {"extractions": [{
                "kind": "Fact", "statement": "Payment gateway certificate expires in 2 days",
                "title": None, "status": "Reported", "confidence": 0.8,
                "sourceSegmentIds": [segment["id"]], "ownerName": None, "ownerRole": None,
                "requiresConfirmation": False, "toolKey": None, "dueAt": None,
            }]}

        with patch("cognition.extract", side_effect=fake_extract):
            seg = {
                "id": "u-novel-1", "incidentId": inc_id,
                "text": "Heads up, the payment gateway TLS cert expires in two days.",
                "speakerName": "Maya", "role": "Comms",
                "startMs": 0, "endMs": 1000, "confidence": 0.9,
            }
            r = await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})
            assert r.status_code == 200

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert any("certificate" in f["statement"] for f in snap["facts"])
        assert any(f.get("createdBy") == "llm" for f in snap["facts"])
