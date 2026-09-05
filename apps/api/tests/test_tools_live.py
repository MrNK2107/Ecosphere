"""
Tests for the real (non-mock) tool adapters — verifies the correct HTTP request shape is built
for each service's public API, using a mocked transport since no real credentials are configured
in this environment. Also verifies the mock fallback stays correct when no credentials are set.
"""
import httpx
import pytest

import tools


class _CapturingTransport(httpx.MockTransport):
    """Records the last request made through it and returns a canned response."""
    def __init__(self, response_json: dict, status_code: int = 200):
        self.captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.captured.append(request)
            return httpx.Response(status_code, json=response_json)

        super().__init__(handler)


@pytest.fixture
def patch_httpx_client(monkeypatch):
    """Patch httpx.AsyncClient so every call in tools.py routes through a capturing transport."""
    def _install(response_json: dict, status_code: int = 200):
        transport = _CapturingTransport(response_json, status_code)
        real_client_cls = httpx.AsyncClient

        class PatchedClient(real_client_cls):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)
        return transport

    return _install


@pytest.mark.asyncio
class TestJiraLive:
    async def test_live_create_issue_request_shape(self, monkeypatch, patch_httpx_client):
        monkeypatch.setattr(tools, "JIRA_LIVE", True)
        monkeypatch.setattr(tools, "JIRA_URL", "https://example.atlassian.net")
        monkeypatch.setattr(tools, "JIRA_EMAIL", "bot@example.com")
        monkeypatch.setattr(tools, "JIRA_API_TOKEN", "tok123")
        transport = patch_httpx_client({"key": "PAY-42", "id": "10001"})

        result = await tools.JiraAdapter().create(
            {"summary": "Fix replica lag", "description": "details", "project": "PAY"},
            {"incidentId": "inc-1"},
        )

        assert result["status"] == "success"
        assert result["result"]["key"] == "PAY-42"
        assert "PAY-42" in result["result"]["url"]
        req = transport.captured[0]
        assert req.url == "https://example.atlassian.net/rest/api/3/issue"
        assert req.headers["authorization"].startswith("Basic ")

    async def test_mock_mode_when_no_credentials(self):
        assert tools.JIRA_LIVE is False  # module-level default in this test env: no creds set
        result = await tools.JiraAdapter().create({"summary": "x", "project": "PAY"}, {"incidentId": "inc-1"})
        assert result["status"] == "success"
        assert result["result"]["mock"] is True

    async def test_blocked_when_requires_confirmation(self):
        result = await tools.JiraAdapter().create(
            {"summary": "dangerous"}, {"incidentId": "inc-1", "requiresConfirmation": True}
        )
        assert result["status"] == "requiresApproval"


@pytest.mark.asyncio
class TestSlackLive:
    async def test_live_send_message_request_shape(self, monkeypatch, patch_httpx_client):
        monkeypatch.setattr(tools, "SLACK_LIVE", True)
        monkeypatch.setattr(tools, "SLACK_TOKEN", "xoxb-test")
        transport = patch_httpx_client({"ok": True, "ts": "123.456", "channel": "C123"})

        result = await tools.SlackAdapter().post({"channel": "#incidents", "text": "hello"}, {"incidentId": "inc-1"})

        assert result["status"] == "success"
        assert result["result"]["ts"] == "123.456"
        req = transport.captured[0]
        assert req.url == "https://slack.com/api/chat.postMessage"
        assert req.headers["authorization"] == "Bearer xoxb-test"

    async def test_live_send_message_slack_error_marks_failed(self, monkeypatch, patch_httpx_client):
        monkeypatch.setattr(tools, "SLACK_LIVE", True)
        monkeypatch.setattr(tools, "SLACK_TOKEN", "xoxb-test")
        patch_httpx_client({"ok": False, "error": "channel_not_found"})

        result = await tools.SlackAdapter().post({"channel": "#nope", "text": "hi"}, {"incidentId": "inc-1"})
        assert result["status"] == "failed"


@pytest.mark.asyncio
class TestPagerDutyLive:
    async def test_live_trigger_page_request_shape(self, monkeypatch, patch_httpx_client):
        monkeypatch.setattr(tools, "PAGERDUTY_LIVE", True)
        monkeypatch.setattr(tools, "PAGERDUTY_KEY", "routingkey123")
        transport = patch_httpx_client({"status": "success", "dedup_key": "abc123"})

        result = await tools.PagerDutyAdapter().trigger(
            {"summary": "Payment outage", "severity": "critical"}, {"incidentId": "inc-1"}
        )

        assert result["status"] == "success"
        req = transport.captured[0]
        assert req.url == "https://events.pagerduty.com/v2/enqueue"


@pytest.mark.asyncio
class TestDatadogLive:
    async def test_live_annotate_request_shape(self, monkeypatch, patch_httpx_client):
        monkeypatch.setattr(tools, "DATADOG_LIVE", True)
        monkeypatch.setattr(tools, "DATADOG_API_KEY", "ddkey123")
        transport = patch_httpx_client({"event": {"id": 999}})

        result = await tools.DatadogAdapter().create({"title": "outage", "text": "spike"}, {"incidentId": "inc-1"})

        assert result["status"] == "success"
        req = transport.captured[0]
        assert req.url == "https://api.datadoghq.com/api/v1/events"
        assert req.headers["dd-api-key"] == "ddkey123"

    async def test_query_metric_returns_none_without_app_key(self):
        assert await tools.query_datadog_metric("avg:x") is None
