"""
Tool adapters — Jira / Slack / PagerDuty / Datadog.
Real HTTP calls when credentials are configured; falls back to a mock (logs only, fabricated
result) when they're not — same mock-first pattern as cognition.py/tts.py/apps/worker.

Requirement: interface ToolAdapter { create, post, trigger } that logs and creates ToolEvent,
gates on human approval (requiresConfirmation) before ever making the live call.
"""
from __future__ import annotations

import logging
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("agora.tools")

# ---------------------------------------------------------------------------
# Credentials — presence of a real key switches an adapter from mock to live.
# ---------------------------------------------------------------------------
JIRA_URL = os.getenv("JIRA_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "PAY")
JIRA_LIVE = bool(JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN)

SLACK_TOKEN = os.getenv("SLACK_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#incident-comms")
SLACK_LIVE = bool(SLACK_TOKEN)

PAGERDUTY_KEY = os.getenv("PAGERDUTY_KEY", "")  # PagerDuty Events API v2 routing key
PAGERDUTY_LIVE = bool(PAGERDUTY_KEY)

DATADOG_API_KEY = os.getenv("DATADOG_API_KEY", "")
DATADOG_APP_KEY = os.getenv("DATADOG_APP_KEY", "")
DATADOG_SITE = os.getenv("DATADOG_SITE", "datadoghq.com")
DATADOG_LIVE = bool(DATADOG_API_KEY)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _tool_event(tool: str, action: str, status: str, payload: dict, result: Optional[dict], ctx: dict) -> dict[str, Any]:
    return {
        "id": _gen_id("tool"),
        "incidentId": ctx.get("incidentId", "unknown"),
        "tool": tool,
        "action": action,
        "status": status,
        "payload": payload,
        "result": result,
        "requiresApproval": status == "requiresApproval",
        "actionItemId": ctx.get("actionItemId"),
        "createdAt": _now().isoformat(),
    }


class ToolAdapter(ABC):
    """Abstract adapter: create (e.g. Jira issue), post (Slack message), trigger (PD page/Datadog)."""

    tool_name: str = "unknown"

    @abstractmethod
    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        ...

    def _require_approval_check(self, ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
        """If action requiresConfirmation and not yet approved, return requiresApproval ToolEvent payload."""
        if ctx.get("requiresConfirmation"):
            return _tool_event(self.tool_name, ctx.get("action", "create"), "requiresApproval", ctx.get("payload", {}), None, ctx)
        return None

    def _log(self, action: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        logger.info(f"[{self.tool_name}] {action} payload={payload} result={result}")


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------
class JiraAdapter(ToolAdapter):
    tool_name = "jira"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "create_issue"})
        if blocked:
            self._log("create_issue blocked requiresApproval", payload, blocked)
            return blocked

        summary = payload.get("summary", "Untitled incident action")
        description = payload.get("description", "")
        project = payload.get("project", JIRA_PROJECT_KEY)

        if JIRA_LIVE:
            try:
                url = f"{JIRA_URL.rstrip('/')}/rest/api/3/issue"
                body = {
                    "fields": {
                        "project": {"key": project},
                        "summary": summary,
                        "description": {
                            "type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description or summary}]}],
                        },
                        "issuetype": {"name": "Task"},
                    }
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(url, json=body, auth=(JIRA_EMAIL, JIRA_API_TOKEN))
                    r.raise_for_status()
                    data = r.json()
                key = data.get("key", "UNKNOWN")
                result = {"key": key, "url": f"{JIRA_URL.rstrip('/')}/browse/{key}", "payload": payload}
                status = "success"
            except Exception as e:
                logger.warning(f"[jira] live create_issue failed: {e}")
                result = {"error": str(e)}
                status = "failed"
        else:
            result = {"key": f"{project}-{uuid.uuid4().hex[:4].upper()}", "url": f"https://jira.example.com/browse/{project}-{uuid.uuid4().hex[:4]}", "payload": payload, "mock": True}
            status = "success"

        self._log("create_issue", payload, result)
        return _tool_event("jira", "create_issue", status, payload, result, ctx)

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
class SlackAdapter(ToolAdapter):
    tool_name = "slack"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.post(payload, ctx)

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "send_message"})
        if blocked:
            self._log("send_message blocked requiresApproval", payload, blocked)
            return blocked

        channel = payload.get("channel", SLACK_CHANNEL)
        text = payload.get("text", "")

        if SLACK_LIVE:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json; charset=utf-8"},
                        json={"channel": channel, "text": text},
                    )
                    r.raise_for_status()
                    data = r.json()
                if not data.get("ok"):
                    raise RuntimeError(data.get("error", "unknown slack error"))
                result = {"ts": data.get("ts"), "channel": data.get("channel", channel)}
                status = "success"
            except Exception as e:
                logger.warning(f"[slack] live send_message failed: {e}")
                result = {"error": str(e)}
                status = "failed"
        else:
            result = {"ts": str(_now().timestamp()), "channel": channel, "mock": True}
            status = "success"

        self._log("send_message", payload, result)
        return _tool_event("slack", "send_message", status, payload, result, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.post(payload, ctx)


# ---------------------------------------------------------------------------
# PagerDuty (Events API v2)
# ---------------------------------------------------------------------------
class PagerDutyAdapter(ToolAdapter):
    tool_name = "pagerduty"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.trigger(payload, ctx)

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.trigger(payload, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "trigger_page"})
        if blocked:
            self._log("trigger_page blocked requiresApproval", payload, blocked)
            return blocked

        summary = payload.get("summary", "Incident page")
        severity = payload.get("severity", "critical")
        source = payload.get("source", "echosphere")

        if PAGERDUTY_LIVE:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        "https://events.pagerduty.com/v2/enqueue",
                        json={
                            "routing_key": PAGERDUTY_KEY,
                            "event_action": "trigger",
                            "payload": {"summary": summary, "severity": severity, "source": source},
                        },
                    )
                    r.raise_for_status()
                    data = r.json()
                result = {"incident_key": data.get("dedup_key"), "status": data.get("status", "triggered")}
                status = "success"
            except Exception as e:
                logger.warning(f"[pagerduty] live trigger_page failed: {e}")
                result = {"error": str(e)}
                status = "failed"
        else:
            result = {"incident_key": f"pd-{uuid.uuid4().hex[:6]}", "status": "triggered", "mock": True}
            status = "success"

        self._log("trigger_page", payload, result)
        return _tool_event("pagerduty", "trigger_page", status, payload, result, ctx)


# ---------------------------------------------------------------------------
# Datadog
# ---------------------------------------------------------------------------
class DatadogAdapter(ToolAdapter):
    tool_name = "datadog"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "annotate"})
        if blocked:
            self._log("annotate blocked requiresApproval", payload, blocked)
            return blocked

        title = payload.get("title", "EchoSphere incident event")
        text = payload.get("text", payload.get("query", ""))

        if DATADOG_LIVE:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        f"https://api.{DATADOG_SITE}/api/v1/events",
                        headers={"DD-API-KEY": DATADOG_API_KEY, "Content-Type": "application/json"},
                        json={"title": title, "text": text, "tags": ["source:echosphere"]},
                    )
                    r.raise_for_status()
                    data = r.json()
                result = {"annotation_id": str(data.get("event", {}).get("id", "")), "query": payload.get("query", "")}
                status = "success"
            except Exception as e:
                logger.warning(f"[datadog] live annotate failed: {e}")
                result = {"error": str(e)}
                status = "failed"
        else:
            result = {"annotation_id": _gen_id("dd"), "query": payload.get("query", "avg:payments.errors"), "mock": True}
            status = "success"

        self._log("annotate", payload, result)
        return _tool_event("datadog", "annotate", status, payload, result, ctx)

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)


async def query_datadog_metric(query: str, from_seconds_ago: int = 600) -> Optional[dict[str, Any]]:
    """PRD §9.1 Monitoring Verification — query a real Datadog metric to check a claim against
    actual data. Returns None (verification_status="unavailable") when Datadog isn't configured."""
    if not (DATADOG_LIVE and DATADOG_APP_KEY):
        return None
    import time
    now = int(time.time())
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.{DATADOG_SITE}/api/v1/query",
                headers={"DD-API-KEY": DATADOG_API_KEY, "DD-APPLICATION-KEY": DATADOG_APP_KEY},
                params={"query": query, "from": now - from_seconds_ago, "to": now},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[datadog] query_metric failed: {e}")
        return None


# Registry
ADAPTERS: Dict[str, ToolAdapter] = {
    "jira": JiraAdapter(),
    "slack": SlackAdapter(),
    "pagerduty": PagerDutyAdapter(),
    "datadog": DatadogAdapter(),
    # github alias to jira for demo purposes
    "github": JiraAdapter(),
}


def adapter_mode(tool: str) -> str:
    return {
        "jira": "live" if JIRA_LIVE else "mock",
        "slack": "live" if SLACK_LIVE else "mock",
        "pagerduty": "live" if PAGERDUTY_LIVE else "mock",
        "datadog": "live" if DATADOG_LIVE else "mock",
        "github": "live" if JIRA_LIVE else "mock",
    }.get(tool, "mock")


async def invoke_tool(
    tool: str,
    action: str,
    payload: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to correct adapter based on tool+action; handles requiresApproval."""
    adapter = ADAPTERS.get(tool)
    if not adapter:
        logger.warning(f"Unknown tool {tool}, using jira adapter")
        adapter = ADAPTERS["jira"]
    # Map generic action strings to adapter methods
    if action in ("create", "create_issue", "create_ticket"):
        return await adapter.create(payload, ctx)
    if action in ("post", "send_message", "notify", "send"):
        return await adapter.post(payload, ctx)
    if action in ("trigger", "trigger_page", "page", "annotate"):
        return await adapter.trigger(payload, ctx)
    # default: try create -> post -> trigger chain
    try:
        return await adapter.create(payload, ctx)
    except Exception:
        return await adapter.post(payload, ctx)


def create_tool_event_record(
    incident_id: str,
    tool: str,
    action: str,
    payload: dict[str, Any],
    status: str = "pending",
    requires_approval: bool = False,
    action_item_id: Optional[str] = None,
    result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Helper to build a ToolEvent dict suitable for storing in _tool_events."""
    return {
        "id": _gen_id("tool"),
        "incidentId": incident_id,
        "tool": tool,
        "action": action,
        "status": status,
        "payload": payload,
        "result": result,
        "requiresApproval": requires_approval,
        "actionItemId": action_item_id,
        "createdAt": _now().isoformat(),
    }
