"""
E2E test suite — payment outage scenario.
Converts demo/e2e_test.py into proper pytest with fixtures.
Validates: 4 facts, 1 hypothesis, 1 decision, 2 actions, conflict gap, approval gate.
"""
import json
import pathlib
import pytest
import pytest_asyncio
from httpx import AsyncClient

FIXTURE_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "demo" / "payment_outage.json"


@pytest.fixture
def fixture():
    """Load payment outage fixture."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def seeded_incident(client: AsyncClient, fixture):
    """Create incident, add participants, replay fixture, return incident_id."""
    # Create incident
    inc = fixture["incident"]
    r = await client.post("/incidents", json={
        "id": inc["id"], "title": inc["title"],
        "severity": inc["severity"], "description": inc.get("description", ""),
    })
    assert r.status_code == 200
    incident_id = r.json()["id"]

    # Add participants
    for p in fixture["participants"]:
        r = await client.post(f"/incidents/{incident_id}/participants", json={
            "name": p["name"], "role": p["role"], "id": p["id"],
        })
        assert r.status_code == 200

    # Replay utterances
    for u in fixture["utterances"]:
        seg = {
            "id": u["id"], "incidentId": incident_id,
            "speakerId": u.get("speakerId"), "speakerName": u.get("speakerName"),
            "role": u.get("role"), "text": u["text"],
            "isFinal": u.get("isFinal", True),
            "startMs": u["startMs"], "endMs": u["endMs"],
            "confidence": 0.92,
            "createdAt": "2026-09-02T14:00:00+00:00",
        }
        r = await client.post(f"/incidents/{incident_id}/transcript", json={"segment": seg})
        assert r.status_code == 200, f"transcript {u['id']} failed: {r.status_code} {r.text[:200]}"

    return incident_id


@pytest.mark.asyncio
class TestPaymentScenarioFacts:
    async def test_has_enough_facts(self, client: AsyncClient, seeded_incident, fixture):
        """Should have at least 4 facts."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        expected = fixture["expectedExtractions"]["facts"]
        assert len(snap["facts"]) >= expected, \
            f"Expected >= {expected} facts, got {len(snap['facts'])}"

    async def test_fact_statements(self, client: AsyncClient, seeded_incident):
        """Facts should contain expected statements."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        statements = [f["statement"] for f in snap["facts"]]
        # Should have error rate fact
        assert any("12%" in s for s in statements), "Missing error rate 12% fact"
        # Should have replica lag fact
        assert any("replica" in s.lower() for s in statements), "Missing DB replica lag fact"


@pytest.mark.asyncio
class TestPaymentScenarioHypothesis:
    async def test_has_hypothesis(self, client: AsyncClient, seeded_incident, fixture):
        """Should have 1 hypothesis."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        expected = fixture["expectedExtractions"]["hypotheses"]
        assert len(snap["hypotheses"]) == expected, \
            f"Expected {expected} hypotheses, got {len(snap['hypotheses'])}"

    async def test_hypothesis_is_active(self, client: AsyncClient, seeded_incident):
        """Hypothesis should be Active."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        assert snap["hypotheses"][0]["status"] == "Active"


@pytest.mark.asyncio
class TestPaymentScenarioDecisions:
    async def test_has_decision(self, client: AsyncClient, seeded_incident, fixture):
        """Should have 1 decision."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        expected = fixture["expectedExtractions"]["decisions"]
        assert len(snap["decisions"]) == expected, \
            f"Expected {expected} decisions, got {len(snap['decisions'])}"

    async def test_decision_is_proposed(self, client: AsyncClient, seeded_incident):
        """Decision should be Proposed."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        assert snap["decisions"][0]["status"] == "Proposed"


@pytest.mark.asyncio
class TestPaymentScenarioActions:
    async def test_has_actions(self, client: AsyncClient, seeded_incident, fixture):
        """Should have 2 action items."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        expected = fixture["expectedExtractions"]["actionItems"]
        assert len(snap["actions"]) == expected, \
            f"Expected {expected} actions, got {len(snap['actions'])}"

    async def test_requires_confirmation(self, client: AsyncClient, seeded_incident):
        """At least one action should require confirmation."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        assert any(a["requiresConfirmation"] for a in snap["actions"]), \
            "No action requires confirmation"

    async def test_approve_action(self, client: AsyncClient, seeded_incident):
        """Approving an action should clear requiresConfirmation."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        confirm_action = next(a for a in snap["actions"] if a["requiresConfirmation"])
        r = await client.post(f"/incidents/{seeded_incident}/actions/{confirm_action['id']}/approve")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Verify approval
        snap_r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        updated = snap_r.json()
        approved = next(a for a in updated["actions"] if a["id"] == confirm_action["id"])
        assert approved["requiresConfirmation"] is False


@pytest.mark.asyncio
class TestPaymentScenarioGaps:
    async def test_has_conflict_gap(self, client: AsyncClient, seeded_incident):
        """Should detect conflicting info gap (error rate 12% vs 2%)."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        conflict_gaps = [g for g in snap["gaps"] if g["kind"] == "ConflictingInfo"]
        assert len(conflict_gaps) >= 1, "No ConflictingInfo gap detected"

    async def test_has_missing_owner_gap(self, client: AsyncClient, seeded_incident):
        """Should detect missing owner gap for customer comms."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        owner_gaps = [g for g in snap["gaps"] if g["kind"] == "MissingOwner"]
        assert len(owner_gaps) >= 1, "No MissingOwner gap detected"


@pytest.mark.asyncio
class TestPaymentScenarioTimeline:
    async def test_timeline_length(self, client: AsyncClient, seeded_incident, fixture):
        """Timeline should have at least 12 events."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        expected = fixture["expectedExtractions"]["timelineMinLength"]
        assert len(snap["timeline"]) >= expected, \
            f"Expected >= {expected} timeline events, got {len(snap['timeline'])}"


@pytest.mark.asyncio
class TestPaymentScenarioSummary:
    async def test_summary_generation(self, client: AsyncClient, seeded_incident):
        """Summary should be generated successfully."""
        r = await client.post(f"/incidents/{seeded_incident}/summary")
        assert r.status_code == 200
        data = r.json()
        assert "markdown" in data
        assert len(data["markdown"]) > 100


@pytest.mark.asyncio
class TestPaymentScenarioToolEvents:
    async def test_tool_events_exist(self, client: AsyncClient, seeded_incident):
        """Should have tool events (jira creation)."""
        r = await client.get(f"/incidents/{seeded_incident}/snapshot")
        snap = r.json()
        assert len(snap["toolEvents"]) >= 1, "No tool events"
