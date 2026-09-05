"""
Integration tests — full API flow with database persistence.
"""
import pytest
import json
from httpx import AsyncClient


@pytest.mark.asyncio
class TestIncidentCRUD:
    async def test_create_incident(self, client: AsyncClient):
        r = await client.post("/incidents", json={"title": "Test Outage", "severity": "SEV1"})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Test Outage"
        assert data["severity"] == "SEV1"
        assert "id" in data

    async def test_create_with_explicit_id_is_idempotent(self, client: AsyncClient):
        """Re-POSTing the same explicit id (e.g. demo/seed.py re-seeding "payment-001") must
        return the existing incident, not silently mint an unrelated random id."""
        r1 = await client.post("/incidents", json={"id": "payment-001", "title": "Payment Outage"})
        assert r1.status_code == 200
        assert r1.json()["id"] == "payment-001"

        r2 = await client.post("/incidents", json={"id": "payment-001", "title": "Payment Outage"})
        assert r2.status_code == 200
        assert r2.json()["id"] == "payment-001"

        r3 = await client.get("/incidents")
        ids = [i["id"] for i in r3.json()]
        assert ids.count("payment-001") == 1

    async def test_list_incidents(self, client: AsyncClient):
        await client.post("/incidents", json={"title": "Incident 1"})
        await client.post("/incidents", json={"title": "Incident 2"})
        r = await client.get("/incidents")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2

    async def test_get_incident(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Get Test"})
        inc_id = create_r.json()["id"]
        r = await client.get(f"/incidents/{inc_id}")
        assert r.status_code == 200
        assert r.json()["title"] == "Get Test"

    async def test_get_incident_not_found(self, client: AsyncClient):
        r = await client.get("/incidents/nonexistent")
        assert r.status_code == 404

    async def test_patch_incident(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Original"})
        inc_id = create_r.json()["id"]
        r = await client.patch(f"/incidents/{inc_id}", json={"title": "Updated"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated"


@pytest.mark.asyncio
class TestParticipants:
    async def test_add_participant(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "With Participants"})
        inc_id = create_r.json()["id"]
        r = await client.post(f"/incidents/{inc_id}/participants", json={"name": "Priya", "role": "SRE"})
        assert r.status_code == 200
        assert r.json()["name"] == "Priya"
        assert r.json()["role"] == "SRE"

    async def test_same_participant_id_across_two_incidents_does_not_collide(self, client: AsyncClient):
        """demo/seed.py's fixture uses fixed participant ids (e.g. "p-priya") regardless of
        which incident it's seeded into — a global PK on ParticipantModel.id broke this."""
        inc1 = (await client.post("/incidents", json={"title": "Incident A"})).json()["id"]
        inc2 = (await client.post("/incidents", json={"title": "Incident B"})).json()["id"]

        r1 = await client.post(f"/incidents/{inc1}/participants", json={"id": "p-priya", "name": "Priya", "role": "SRE"})
        assert r1.status_code == 200
        r2 = await client.post(f"/incidents/{inc2}/participants", json={"id": "p-priya", "name": "Priya", "role": "SRE"})
        assert r2.status_code == 200

        snap1 = (await client.get(f"/incidents/{inc1}/snapshot")).json()
        snap2 = (await client.get(f"/incidents/{inc2}/snapshot")).json()
        assert len(snap1["incident"]["participants"]) == 1
        assert len(snap2["incident"]["participants"]) == 1

    async def test_re_adding_same_participant_is_idempotent(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Idempotent Participant Test"})
        inc_id = create_r.json()["id"]
        for _ in range(2):
            r = await client.post(f"/incidents/{inc_id}/participants", json={"id": "p-priya", "name": "Priya", "role": "SRE"})
            assert r.status_code == 200
        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert len(snap["incident"]["participants"]) == 1


@pytest.mark.asyncio
class TestTranscriptIngestion:
    async def test_push_transcript(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Transcript Test"})
        inc_id = create_r.json()["id"]
        seg = {
            "id": "u-001", "incidentId": inc_id,
            "text": "Error rate is 12%", "speakerName": "Priya", "role": "SRE",
            "startMs": 0, "endMs": 4500, "confidence": 0.9,
        }
        r = await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "snapshot" in data

    async def test_transcript_triggers_extraction(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Extraction Test"})
        inc_id = create_r.json()["id"]
        # Push u-001 fixture segment
        seg = {
            "id": "u-001", "incidentId": inc_id,
            "text": "I am Priya, SRE Lead. Payments are failing hard — error rate spiked to 12% at checkout since 14:02 UTC.",
            "speakerName": "Priya", "role": "SRE",
            "startMs": 0, "endMs": 4500, "confidence": 0.92,
        }
        await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})
        # Check snapshot has fact
        snap_r = await client.get(f"/incidents/{inc_id}/snapshot")
        snap = snap_r.json()
        assert len(snap["facts"]) >= 1
        assert "12%" in snap["facts"][0]["statement"]


@pytest.mark.asyncio
class TestActions:
    async def test_approve_action(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Action Test"})
        inc_id = create_r.json()["id"]
        # Push u-010 to create action
        seg10 = {
            "id": "u-010", "incidentId": inc_id,
            "text": "Can someone create a Jira to track the DB replica fix?",
            "speakerName": "Alex", "role": "Backend",
            "startMs": 31000, "endMs": 33500, "confidence": 0.92,
        }
        await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg10})
        # Push u-011 to require confirmation
        seg11 = {
            "id": "u-011", "incidentId": inc_id,
            "text": "Do it — but require approval before it posts to Jira.",
            "speakerName": "Priya", "role": "SRE",
            "startMs": 34000, "endMs": 36000, "confidence": 0.92,
        }
        await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg11})
        # Get snapshot to find action
        snap_r = await client.get(f"/incidents/{inc_id}/snapshot")
        snap = snap_r.json()
        assert len(snap["actions"]) >= 1
        action_id = snap["actions"][0]["id"]
        # Approve
        r = await client.post(f"/incidents/{inc_id}/actions/{action_id}/approve")
        assert r.status_code == 200
        assert r.json()["ok"] is True


@pytest.mark.asyncio
class TestSummary:
    async def test_generate_summary(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Summary Test", "severity": "SEV1"})
        inc_id = create_r.json()["id"]
        r = await client.post(f"/incidents/{inc_id}/summary")
        assert r.status_code == 200
        data = r.json()
        assert "markdown" in data
        assert "Summary Test" in data["markdown"]


@pytest.mark.asyncio
class TestSnapshot:
    async def test_get_snapshot(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Snapshot Test"})
        inc_id = create_r.json()["id"]
        r = await client.get(f"/incidents/{inc_id}/snapshot")
        assert r.status_code == 200
        snap = r.json()
        assert "incident" in snap
        assert "facts" in snap
        assert "hypotheses" in snap
        assert "actions" in snap
        assert "gaps" in snap
        assert "timeline" in snap
        assert "transcript" in snap
        assert "toolEvents" in snap


@pytest.mark.asyncio
class TestHealth:
    async def test_health(self, client: AsyncClient):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
