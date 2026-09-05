"""
Tests for the spoken-status-summary scheduler (PS41: "Spoken status summaries at appropriate
moments") — cadence/threshold logic, and the audio-serving endpoint.
"""
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

import main as main_module


@pytest.mark.asyncio
class TestSpokenSummaryScheduler:
    async def test_no_speak_with_zero_facts(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "Quiet Incident"})
        inc_id = create_r.json()["id"]
        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert not [t for t in snap["timeline"] if t["type"] == "spoken_summary"]

    async def test_speaks_after_three_facts(self, client: AsyncClient):
        main_module._spoken_tracker.clear()
        create_r = await client.post("/incidents", json={"title": "Three Facts Test"})
        inc_id = create_r.json()["id"]

        # Three distinct utterances that each land as a Fact via the regex fallback (percent/error-rate pattern)
        texts = [
            "Error rate is at 5% right now.",
            "Error rate climbed to 8% a minute later.",
            "Error rate is now 11% and climbing.",
        ]
        for i, text in enumerate(texts):
            seg = {
                "id": f"u-spoken-{i}", "incidentId": inc_id, "text": text,
                "speakerName": "Alex", "role": "Backend",
                "startMs": i * 1000, "endMs": i * 1000 + 500, "confidence": 0.9,
            }
            await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})

        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert len(snap["facts"]) >= 3
        spoken_events = [t for t in snap["timeline"] if t["type"] == "spoken_summary"]
        assert len(spoken_events) >= 1
        assert "script" in spoken_events[0]["payload"]

    async def test_speaks_again_after_interval_elapses(self, client: AsyncClient):
        main_module._spoken_tracker.clear()
        create_r = await client.post("/incidents", json={"title": "Interval Test"})
        inc_id = create_r.json()["id"]
        seg = {
            "id": "u-interval-1", "incidentId": inc_id, "text": "Error rate is at 5% right now.",
            "speakerName": "Alex", "role": "Backend", "startMs": 0, "endMs": 500, "confidence": 0.9,
        }
        # First fact alone isn't enough to trigger the 3-facts threshold, and there's no prior
        # spoken timestamp yet, so nothing should have been said.
        await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})
        snap = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert not [t for t in snap["timeline"] if t["type"] == "spoken_summary"]

        # Simulate the 5-minute cadence having already elapsed since a prior spoken update.
        main_module._spoken_tracker[inc_id] = {
            "last_spoken_at": datetime.now(timezone.utc) - timedelta(seconds=400),
            "fact_count_at_last": 0,
        }
        seg2 = {**seg, "id": "u-interval-2", "text": "Error rate now 6%.", "startMs": 1000, "endMs": 1500}
        await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg2})
        snap2 = (await client.get(f"/incidents/{inc_id}/snapshot")).json()
        assert [t for t in snap2["timeline"] if t["type"] == "spoken_summary"]


@pytest.mark.asyncio
class TestAudioEndpoint:
    async def test_missing_audio_404s(self, client: AsyncClient):
        r = await client.get("/incidents/inc-1/audio/does-not-exist.mp3")
        assert r.status_code == 404

    async def test_path_traversal_rejected(self, client: AsyncClient):
        r = await client.get("/incidents/inc-1/audio/..%2F..%2Fetc%2Fpasswd.mp3")
        assert r.status_code in (400, 404)
