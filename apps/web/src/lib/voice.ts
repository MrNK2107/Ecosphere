import { useCallback, useState } from "react";
import AgoraRTM, { RTMClient } from "agora-rtm";
import { API } from "../store/incidentStore";
import { showToast } from "../components/Toast";

export type VoiceState = "idle" | "connecting" | "connected" | "leaving";

export interface VoiceSessionData {
  appId: string;
  channel: string;
  token: string;
  uid: number;
  rtmClient: RTMClient;
}

// Human uid range deliberately excludes the fixed agent RTC uid (911911, see
// apps/api/main.py's agora_agent_join) so the two can never collide.
function randomHumanUid() {
  return Math.floor(Math.random() * 700000) + 100000;
}

export function useVoiceRoom(incidentId: string | null) {
  const [state, setState] = useState<VoiceState>("idle");
  const [session, setSession] = useState<VoiceSessionData | null>(null);

  const join = useCallback(async () => {
    if (!incidentId || state !== "idle") return;
    setState("connecting");
    try {
      const uid = randomHumanUid();
      // Combined RTC+RTM token (agora_agent.generate_convo_ai_token) — one token joins the
      // voice channel and logs into the RTM channel of the same name, where the Conversational
      // AI agent publishes transcript/state events.
      const res = await fetch(`${API}/agora/rtc-token?channel=${encodeURIComponent(incidentId)}&uid=${uid}`);
      if (!res.ok) throw new Error(`Token request failed (${res.status})`);
      const { token, appId } = await res.json();

      // RTM login identity must match the token subject (String(uid)) — mismatches surface as
      // generic startup failures per the agora skill's documented gotcha.
      const rtmClient = new AgoraRTM.RTM(appId, String(uid));
      await rtmClient.login({ token });

      setSession({ appId, channel: incidentId, token, uid, rtmClient });
      setState("connected");
    } catch (e) {
      showToast("error", `Voice connect failed: ${(e as Error).message}`);
      setState("idle");
    }
  }, [incidentId, state]);

  const leave = useCallback(async () => {
    if (!incidentId || state === "idle" || !session) return;
    setState("leaving");
    try {
      await session.rtmClient.logout();
    } catch { /* best-effort */ }
    try {
      await fetch(`${API}/incidents/${encodeURIComponent(incidentId)}/agora-agent/leave`, { method: "POST" });
    } catch { /* best-effort */ }
    setSession(null);
    setState("idle");
  }, [incidentId, state, session]);

  return { state, session, join, leave };
}
