"""
Tests for Agora Conversational AI Engine integration (mandatory per hackathon rules).
Covers: custom-LLM webhook SSE contract, join-request payload shape, and agent
lifecycle endpoints in mock mode (no live Agora credentials available in CI/dev).
"""
import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

import agora_conversational_ai as cai


class TestJoinPayloadShape:
    def test_custom_llm_mode_payload(self, monkeypatch):
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "custom")
        monkeypatch.setattr(cai, "AGORA_CUSTOM_LLM_URL", "https://example.com/agora/llm/chat/completions")
        payload = cai.build_join_payload(
            incident_id="inc-1", channel="incident-inc-1", agent_rtc_uid="bot-1",
            rtc_token="tok", system_prompt="be helpful",
        )
        assert payload["name"] == "echosphere-inc-1"
        props = payload["properties"]
        assert props["channel"] == "incident-inc-1"
        assert props["llm"]["credential_mode"] == "custom"
        assert props["llm"]["url"] == "https://example.com/agora/llm/chat/completions"
        assert props["llm"]["system_messages"] == [{"role": "system", "content": "be helpful"}]
        assert props["asr"]["credential_mode"] == "managed"
        assert props["asr"]["vendor"] == "deepgram"
        assert props["tts"]["credential_mode"] == "managed"
        assert props["tts"]["vendor"] == "minimax"

    def test_custom_llm_mode_requires_url(self, monkeypatch):
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "custom")
        monkeypatch.setattr(cai, "AGORA_CUSTOM_LLM_URL", "")
        with pytest.raises(RuntimeError):
            cai.build_join_payload("inc-1", "ch", "bot-1", "tok", "prompt")

    def test_managed_llm_mode_payload(self, monkeypatch):
        monkeypatch.setattr(cai, "AGORA_CAI_LLM_MODE", "managed")
        payload = cai.build_join_payload("inc-1", "ch", "bot-1", "tok", "prompt")
        assert payload["properties"]["llm"]["credential_mode"] == "managed"
        assert payload["properties"]["llm"]["vendor"] == "openai"


@pytest.mark.asyncio
class TestAgentLifecycleMockMode:
    async def test_join_and_leave_mock_mode(self, client: AsyncClient):
        """Without AGORA_CUSTOMER_ID/SECRET configured, CAI_ENABLED is False and the
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


@pytest.mark.asyncio
class TestCustomLLMWebhook:
    async def test_webhook_returns_sse_stream(self, client: AsyncClient):
        async def fake_reply(messages, model=None):
            return "Rollback looks stable — error rate is trending back to baseline."

        with patch("cognition.generate_voice_reply", side_effect=fake_reply):
            r = await client.post("/agora/llm/chat/completions", json={
                "model": "echosphere-cognition",
                "messages": [{"role": "user", "content": "What's the status?"}],
                "stream": True,
            })
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = r.text
        assert "chat.completion.chunk" in body
        assert "Rollback looks stable" in body
        assert body.strip().endswith("data: [DONE]")

    async def test_webhook_sse_chunks_are_valid_json(self, client: AsyncClient):
        async def fake_reply(messages, model=None):
            return "ack"

        with patch("cognition.generate_voice_reply", side_effect=fake_reply):
            r = await client.post("/agora/llm/chat/completions", json={
                "messages": [{"role": "user", "content": "hi"}],
            })
        lines = [l for l in r.text.split("\n\n") if l.strip() and l.strip() != "data: [DONE]"]
        for line in lines:
            assert line.startswith("data: ")
            json.loads(line[len("data: "):])  # must not raise
