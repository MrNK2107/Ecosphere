/**
 * Frontend tool helpers — Agent E.
 * Wraps /incidents/{id}/actions/{actionId}/approve and status update,
 * plus generic tool event posting.
 */
export type ToolName = "jira" | "slack" | "pagerduty" | "datadog" | "github";
export type ActionStatus = "Open" | "InProgress" | "Blocked" | "Done" | "Overdue";

const API = (import.meta as unknown as { env: Record<string,string> }).env?.VITE_API_URL ?? "";

function apiBase(): string {
  // vite proxy: /api -> localhost:8000; prefer relative /api so vite proxies in dev
  if (API) return API.replace(/\/$/, "");
  // use proxy path if running via vite dev
  if (typeof window !== "undefined" && window.location.port === "5173") return "/api";
  return "http://localhost:8000";
}

export async function approveAction(incidentId: string, actionId: string): Promise<unknown> {
  const base = apiBase();
  // try new path then legacy
  let r = await fetch(`${base}/incidents/${incidentId}/actions/${actionId}/approve`, { method: "POST" });
  if (!r.ok) {
    r = await fetch(`${base}/incidents/${incidentId}/approve/${actionId}`, { method: "POST" });
  }
  if (!r.ok) throw new Error(`approve failed ${r.status}`);
  return r.json();
}

export async function updateActionStatus(incidentId: string, actionId: string, status: ActionStatus): Promise<unknown> {
  const base = apiBase();
  const r = await fetch(`${base}/incidents/${incidentId}/actions/${actionId}/update-status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!r.ok) throw new Error(`update-status failed ${r.status}`);
  return r.json();
}

export async function moveAction(incidentId: string, actionId: string, to: ActionStatus): Promise<unknown> {
  return updateActionStatus(incidentId, actionId, to);
}

export async function fetchSnapshot(incidentId: string): Promise<unknown> {
  const base = apiBase();
  const r = await fetch(`${base}/incidents/${incidentId}/snapshot`);
  if (!r.ok) throw new Error(`snapshot ${r.status}`);
  return r.json();
}

export async function triggerTool(
  incidentId: string,
  tool: ToolName,
  action: string,
  payload: Record<string, unknown>,
  actionItemId?: string
): Promise<unknown> {
  // Frontend does not call tool directly; it approves actionItem which triggers backend.
  // Keep for future direct tool invocation via /incidents/{id}/tools
  const base = apiBase();
  const r = await fetch(`${base}/incidents/${incidentId}/tools`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool, action, payload, actionItemId }),
  });
  if (!r.ok) throw new Error(`tool trigger ${r.status}`);
  return r.json();
}
