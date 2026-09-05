"""
Tests for Agora Conversational AI Engine integration (mandatory per hackathon rules).
Covers: mock-mode agent lifecycle, the custom-LLM webhook's context-based incident routing
(the critical correctness fix — without reading `context.channel`, the webhook couldn't tell
which incident a live voice request belonged to), and real token streaming.

Rewritten after switching from hand-rolled REST+Basic Auth to the official `agora-agents` SDK
(agora_conversational_ai.py) — see MENTOR_FEEDBACK.md for why. SDK request construction against
a real Agora account is not tested here (no live account available); these tests cover our own
call correctness and the parts of the system we fully control.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

import agora_conversational_ai as cai


@pytest.mark.asyncio
class TestAgentLifecycleMockMode:
    async def test_join_and_leave_mock_mode(self, client: AsyncClient):
        """Without AGORA_APP_ID/AGORA_APP_CERT configured, CAI_ENABLED is False and the
        endpoints must still succeed in mock mode (mock-first principle)."""
        assert cai.CAI_ENABLED is False
        create_r = await client.post("/incidents", json={"title": "CAI Mock Test"})
        inc_id = create_r.json()["id"]

        join_r = await client.post(f"/incidents/{inc_id}/agora-agent/join", json={"channel": inc_id})
        assert join_r.status_code == 200
        data = join_r.json()
        assert data["status"] == "RUNNING"
        assert data["agent_id"].startswith("mock-agent-")

        leave_r = await client.post(f"/incidents/{inc_id}/agora-agent/leave")
        assert leave_r.status_code == 200
        assert leave_r.json()["status"] == "STOPPED"

    async def test_leave_without_join_is_404(self, client: AsyncClient):
        create_r = await client.post("/incidents", json={"title": "No Agent Test"})
        inc_id = create_r.json()["id"]
        r = await client.post(f"/incidents/{inc_id}/agora-agent/leave")
        assert r.status_code == 404


class TestBuildAgent:
    def test_custom_mode_requires_url(self, monkeypatch):
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "custom")
        monkeypatch.setattr(cai, "AGORA_CUSTOM_LLM_URL", "")
        with pytest.raises(RuntimeError, match="AGORA_CUSTOM_LLM_URL"):
            cai._build_agent("system prompt", "hi")

    def test_custom_mode_builds_agent_with_our_webhook(self, monkeypatch):
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "custom")
        monkeypatch.setattr(cai, "AGORA_CUSTOM_LLM_URL", "https://example.ngrok.io/agora")
        agent = cai._build_agent("system prompt", "hello there")
        # llm config was set via .with_llm() — inspect the underlying join-payload representation
        # (the SDK serializes base_url -> "url" and model -> params.model internally)
        assert agent.llm is not None
        llm = agent.llm if isinstance(agent.llm, dict) else agent.llm.model_dump()
        assert llm["url"] == "https://example.ngrok.io/agora"
        assert llm["params"]["model"] == "echosphere-cognition"

    def test_managed_mode_uses_agora_managed_openai(self, monkeypatch):
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "managed")
        agent = cai._build_agent("system prompt", "hello there")
        assert agent.llm is not None
        llm = agent.llm if isinstance(agent.llm, dict) else agent.llm.model_dump()
        assert llm["params"]["model"] == "gpt-4o-mini"

    def test_turn_detection_configured_for_interruption_handling(self, monkeypatch):
        """PS41 site-wide requirement: 'user interruption handling' must actually be
        configured, not left to undocumented defaults."""
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "managed")
        agent = cai._build_agent("system prompt", "hello")
        assert agent.turn_detection is not None


@pytest.mark.asyncio
class TestCustomLLMWebhook:
    async def test_webhook_streams_real_deltas_and_routes_by_context_channel(self, client: AsyncClient):
        """The critical correctness fix: Agora sends context.channel, which must be used to
        find the right incident (join always sets channel=incidentId)."""
        create_r = await client.post("/incidents", json={"title": "Webhook Routing Test"})
        inc_id = create_r.json()["id"]

        async def fake_stream(messages, model=None):
            for piece in ["Rollback ", "looks stable."]:
                yield piece

        with patch("cognition.generate_voice_reply_stream", side_effect=fake_stream):
            r = await client.post("/agora/llm/chat/completions", json={
                "model": "echosphere-cognition",
                "messages": [{"role": "user", "content": "What's the status?"}],
                "stream": True,
                "context": {"appId": "app1", "userId": "u1", "channel": inc_id},
            })
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = r.text
        assert "chat.completion.chunk" in body
        assert "Rollback " in body and "looks stable." in body
        assert body.strip().endswith("data: [DONE]")

    async def test_webhook_grounds_reply_in_real_incident_facts(self, client: AsyncClient):
        """The reply-generation call must receive the incident's actual current facts, not
        just the raw Agora messages — otherwise it can invent things the room never said."""
        create_r = await client.post("/incidents", json={"title": "Grounding Test"})
        inc_id = create_r.json()["id"]
        seg = {
            "id": "u-ground-1", "incidentId": inc_id, "text": "Error rate is at 9% right now.",
            "speakerName": "Alex", "role": "Backend", "startMs": 0, "endMs": 500, "confidence": 0.9,
        }
        await client.post(f"/incidents/{inc_id}/transcript", json={"segment": seg})

        captured_messages = []

        async def fake_stream(messages, model=None):
            captured_messages.append(messages)
            yield "ack"

        with patch("cognition.generate_voice_reply_stream", side_effect=fake_stream):
            await client.post("/agora/llm/chat/completions", json={
                "messages": [{"role": "user", "content": "status?"}],
                "context": {"appId": "app1", "userId": "u1", "channel": inc_id},
            })

        assert captured_messages
        grounding_msg = captured_messages[0][0]
        assert grounding_msg["role"] == "system"
        assert "9%" in grounding_msg["content"] or "Error rate" in grounding_msg["content"]

    async def test_webhook_without_context_still_replies(self, client: AsyncClient):
        """No context (e.g. a manual/test call) must not crash — just skips grounding."""
        async def fake_stream(messages, model=None):
            yield "ok"

        with patch("cognition.generate_voice_reply_stream", side_effect=fake_stream):
            r = await client.post("/agora/llm/chat/completions", json={
                "messages": [{"role": "user", "content": "hi"}],
            })
        assert r.status_code == 200

    async def test_webhook_sse_chunks_are_valid_json(self, client: AsyncClient):
        async def fake_stream(messages, model=None):
            yield "ack"

        with patch("cognition.generate_voice_reply_stream", side_effect=fake_stream):
            r = await client.post("/agora/llm/chat/completions", json={
                "messages": [{"role": "user", "content": "hi"}],
            })
        lines = [l for l in r.text.split("\n\n") if l.strip() and l.strip() != "data: [DONE]"]
        for line in lines:
            assert line.startswith("data: ")
            json.loads(line[len("data: "):])  # must not raise
