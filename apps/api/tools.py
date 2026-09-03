"""
Agora Tool Adapters — Agent E.
Mock implementations for Jira / Slack / PagerDuty / Datadog.
Requirement: interface ToolAdapter { create, post, trigger } that logs and creates ToolEvent, requires approval check.
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("agora.tools")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


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
            return {
                "id": _gen_id("tool"),
                "incidentId": ctx.get("incidentId", "unknown"),
                "tool": self.tool_name,
                "action": ctx.get("action", "create"),
                "status": "requiresApproval",
                "payload": ctx.get("payload", {}),
                "requiresApproval": True,
                "actionItemId": ctx.get("actionItemId"),
                "createdAt": _now().isoformat(),
            }
        return None

    def _log(self, action: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        logger.info(f"[{self.tool_name}] {action} payload={payload} result={result}")


class MockJira(ToolAdapter):
    tool_name = "jira"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "create_issue"})
        if blocked:
            self._log("create_issue blocked requiresApproval", payload, blocked)
            return blocked
        result = {"key": f"PAY-{uuid.uuid4().hex[:4].upper()}", "url": f"https://jira.example.com/browse/PAY-{uuid.uuid4().hex[:4]}", "payload": payload}
        self._log("create_issue", payload, result)
        return {
            "id": _gen_id("tool"),
            "incidentId": ctx.get("incidentId", "unknown"),
            "tool": "jira",
            "action": "create_issue",
            "status": "success",
            "payload": payload,
            "result": result,
            "requiresApproval": False,
            "actionItemId": ctx.get("actionItemId"),
            "createdAt": _now().isoformat(),
        }

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)


class MockSlack(ToolAdapter):
    tool_name = "slack"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.post(payload, ctx)

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "send_message"})
        if blocked:
            # override tool name to slack
            blocked["tool"] = "slack"
            blocked["action"] = "send_message"
            self._log("send_message blocked requiresApproval", payload, blocked)
            return blocked
        result = {"ts": str(_now().timestamp()), "channel": payload.get("channel", "#incident-comms")}
        self._log("send_message", payload, result)
        return {
            "id": _gen_id("tool"),
            "incidentId": ctx.get("incidentId", "unknown"),
            "tool": "slack",
            "action": "send_message",
            "status": "success",
            "payload": payload,
            "result": result,
            "requiresApproval": False,
            "actionItemId": ctx.get("actionItemId"),
            "createdAt": _now().isoformat(),
        }

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.post(payload, ctx)


class MockPD(ToolAdapter):
    """Mock PagerDuty adapter."""

    tool_name = "pagerduty"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.trigger(payload, ctx)

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.trigger(payload, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "trigger_page"})
        if blocked:
            blocked["tool"] = "pagerduty"
            blocked["action"] = "trigger_page"
            self._log("trigger_page blocked requiresApproval", payload, blocked)
            return blocked
        result = {"incident_key": f"pd-{uuid.uuid4().hex[:6]}", "status": "triggered"}
        self._log("trigger_page", payload, result)
        return {
            "id": _gen_id("tool"),
            "incidentId": ctx.get("incidentId", "unknown"),
            "tool": "pagerduty",
            "action": "trigger_page",
            "status": "success",
            "payload": payload,
            "result": result,
            "requiresApproval": False,
            "actionItemId": ctx.get("actionItemId"),
            "createdAt": _now().isoformat(),
        }


class MockDatadog(ToolAdapter):
    tool_name = "datadog"

    async def create(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        blocked = self._require_approval_check({**ctx, "payload": payload, "action": "annotate"})
        if blocked:
            blocked["tool"] = "datadog"
            blocked["action"] = "annotate"
            self._log("annotate blocked requiresApproval", payload, blocked)
            return blocked
        result = {"annotation_id": _gen_id("dd"), "query": payload.get("query", "avg:payments.errors")}
        self._log("annotate", payload, result)
        return {
            "id": _gen_id("tool"),
            "incidentId": ctx.get("incidentId", "unknown"),
            "tool": "datadog",
            "action": "annotate",
            "status": "success",
            "payload": payload,
            "result": result,
            "requiresApproval": False,
            "actionItemId": ctx.get("actionItemId"),
            "createdAt": _now().isoformat(),
        }

    async def post(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)

    async def trigger(self, payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return await self.create(payload, ctx)


# Registry
ADAPTERS: Dict[str, ToolAdapter] = {
    "jira": MockJira(),
    "slack": MockSlack(),
    "pagerduty": MockPD(),
    "datadog": MockDatadog(),
    # github alias to jira mock for demo
    "github": MockJira(),
}


async def invoke_tool(
    tool: str,
    action: str,
    payload: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to correct adapter based on tool+action; handles requiresApproval."""
    adapter = ADAPTERS.get(tool)
    if not adapter:
        logger.warning(f"Unknown tool {tool}, using mock jira")
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
