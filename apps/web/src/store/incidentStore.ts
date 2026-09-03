import { create } from "zustand";

// ── Types (mirror @agora/shared) ──────────────────────────────────────────
export type Incident = {
  id: string; title: string; severity: "SEV1" | "SEV2" | "SEV3" | "SEV4";
  status: string; description?: string;
  participants: { id: string; name: string; role: string; avatarUrl?: string }[];
  summaryMarkdown?: string; createdAt: string; updatedAt: string;
};
export type TranscriptSegment = {
  id: string; incidentId: string; speakerId: string | null; speakerName?: string;
  role?: string; text: string; isFinal: boolean; startMs: number; endMs: number;
  confidence: number; createdAt: string;
};
export type Fact = {
  id: string; incidentId: string; statement: string;
  status: "Confirmed" | "Corroborated" | "Reported" | "Contradicted";
  confidence: number; sourceSegmentIds: string[]; createdAt: string; updatedAt: string;
};
export type Hypothesis = {
  id: string; incidentId: string; statement: string; status: string;
  confidence: number; sourceSegmentIds: string[];
};
export type Decision = {
  id: string; incidentId: string; statement: string;
  status: "Proposed" | "Approved" | "Reverted"; decidedBy?: string;
};
export type ActionItem = {
  id: string; incidentId: string; title: string; description?: string;
  ownerId?: string | null; ownerName?: string | null;
  status: "Open" | "InProgress" | "Blocked" | "Done" | "Overdue";
  requiresConfirmation: boolean; dueAt?: string | null; toolKey?: string;
};
export type Gap = {
  id: string; kind: "MissingOwner" | "ConflictingInfo" | "UnverifiedAssumption" | "StaleAction";
  severity: "low" | "medium" | "high" | "critical"; message: string; relatedIds: string[];
};
export type TimelineEvent = {
  id: string; incidentId: string; type: string; seq: number;
  createdAt: string; payload: Record<string, unknown>; refId?: string;
};
export type ToolEvent = {
  id: string; incidentId: string; tool: string; action: string; status: string;
  payload: Record<string, unknown>; result?: Record<string, unknown>;
  requiresApproval: boolean; createdAt: string;
};
export type Snapshot = {
  incident: Incident; facts: Fact[]; hypotheses: Hypothesis[];
  decisions: Decision[]; actions: ActionItem[]; gaps: Gap[];
  timeline: TimelineEvent[]; transcript: TranscriptSegment[];
  toolEvents: ToolEvent[];
};

// ── Store ─────────────────────────────────────────────────────────────────
interface IncidentState {
  snapshot: Snapshot | null;
  incidentId: string | null;
  ws: WebSocket | null;
  wsConnected: boolean;
  error: string | null;
  speaking: boolean;

  connect: (incidentId: string) => void;
  disconnect: () => void;
  setSnapshot: (snap: Snapshot) => void;
  approveAction: (actionId: string) => Promise<void>;
  updateActionStatus: (actionId: string, status: ActionItem["status"]) => Promise<void>;
  generateSummary: () => Promise<string>;
  setSpeaking: (v: boolean) => void;
}

const API = (() => {
  const env = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL;
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location.port === "5173") return "/api";
  return "http://localhost:8000";
})();

export const useIncidentStore = create<IncidentState>((set, get) => ({
  snapshot: null,
  incidentId: null,
  ws: null,
  wsConnected: false,
  error: null,
  speaking: false,

  connect: (incidentId: string) => {
    const { ws: oldWs } = get();
    if (oldWs) oldWs.close();

    const wsUrl = API.replace(/^http/, "ws") + `/ws/incidents/${incidentId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      set({ wsConnected: true, incidentId, error: null });
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "snapshot" && msg.snapshot) {
          set({ snapshot: msg.snapshot });
        }
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      set({ wsConnected: false, ws: null });
      // Auto-reconnect after 3s
      setTimeout(() => {
        const state = get();
        if (state.incidentId && !state.ws) {
          state.connect(state.incidentId);
        }
      }, 3000);
    };

    ws.onerror = () => {
      set({ error: "WebSocket connection error" });
    };

    set({ ws, incidentId });
  },

  disconnect: () => {
    const { ws } = get();
    if (ws) ws.close();
    set({ ws: null, wsConnected: false, incidentId: null, snapshot: null });
  },

  setSnapshot: (snap) => set({ snapshot: snap }),

  approveAction: async (actionId: string) => {
    const { incidentId } = get();
    if (!incidentId) return;
    try {
      let r = await fetch(`${API}/incidents/${incidentId}/actions/${actionId}/approve`, { method: "POST" });
      if (!r.ok) {
        r = await fetch(`${API}/incidents/${incidentId}/approve/${actionId}`, { method: "POST" });
      }
      if (!r.ok) throw new Error(`approve failed ${r.status}`);
    } catch (e) {
      set({ error: String(e) });
    }
  },

  updateActionStatus: async (actionId: string, status: ActionItem["status"]) => {
    const { incidentId } = get();
    if (!incidentId) return;
    try {
      const r = await fetch(`${API}/incidents/${incidentId}/actions/${actionId}/update-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!r.ok) throw new Error(`update-status failed ${r.status}`);
    } catch (e) {
      set({ error: String(e) });
    }
  },

  generateSummary: async () => {
    const { incidentId } = get();
    if (!incidentId) return "";
    try {
      const r = await fetch(`${API}/incidents/${incidentId}/summary`, { method: "POST" });
      if (!r.ok) throw new Error(`summary failed ${r.status}`);
      const j = await r.json();
      return j.markdown || "";
    } catch (e) {
      set({ error: String(e) });
      return "";
    }
  },

  setSpeaking: (v) => set({ speaking: v }),
}));
