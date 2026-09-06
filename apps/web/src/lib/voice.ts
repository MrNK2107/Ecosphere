import { useCallback, useRef, useState } from "react";
import AgoraRTC, { type IAgoraRTCClient, type IMicrophoneAudioTrack } from "agora-rtc-sdk-ng";
import { API } from "../store/incidentStore";
import { showToast } from "../components/Toast";

export type VoiceState = "idle" | "connecting" | "connected" | "leaving";

// Non-numeric agent UIDs crash the agent-kit SDK's ConvoAI token auto-generation
// (confirmed live 2026-09-06 — see apps/api/main.py's agora_agent_join).
const AGENT_RTC_UID = "911911";

export function useVoiceRoom(incidentId: string | null) {
  const [state, setState] = useState<VoiceState>("idle");
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const clientRef = useRef<IAgoraRTCClient | null>(null);
  const micTrackRef = useRef<IMicrophoneAudioTrack | null>(null);

  const join = useCallback(async () => {
    if (!incidentId || state !== "idle") return;
    setState("connecting");
    try {
      const uid = Math.floor(Math.random() * 900000) + 100000;
      const tokenRes = await fetch(
        `${API}/agora/rtc-token?channel=${encodeURIComponent(incidentId)}&uid=${uid}&role=publisher`
      );
      if (!tokenRes.ok) throw new Error(`Token request failed (${tokenRes.status})`);
      const { token, appId } = await tokenRes.json();

      const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      client.on("user-published", async (user, mediaType) => {
        await client.subscribe(user, mediaType);
        if (mediaType === "audio") {
          user.audioTrack?.play();
          setAgentSpeaking(true);
        }
      });
      client.on("user-unpublished", (_user, mediaType) => {
        if (mediaType === "audio") setAgentSpeaking(false);
      });
      clientRef.current = client;

      await client.join(appId, incidentId, token, uid);
      const micTrack = await AgoraRTC.createMicrophoneAudioTrack();
      micTrackRef.current = micTrack;
      await client.publish([micTrack]);

      const agentRes = await fetch(`${API}/incidents/${encodeURIComponent(incidentId)}/agora-agent/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: incidentId, agentRtcUid: AGENT_RTC_UID }),
      });
      const agentBody = await agentRes.json();
      if (!agentRes.ok) throw new Error(agentBody.detail || `Agent join failed (${agentRes.status})`);

      setState("connected");
      showToast("success", "Voice room connected — EchoSphere is listening.");
    } catch (e) {
      showToast("error", `Voice connect failed: ${(e as Error).message}`);
      await teardown();
      setState("idle");
    }
  }, [incidentId, state]);

  const teardown = useCallback(async () => {
    micTrackRef.current?.close();
    micTrackRef.current = null;
    if (clientRef.current) {
      try { await clientRef.current.leave(); } catch { /* already left */ }
      clientRef.current = null;
    }
  }, []);

  const leave = useCallback(async () => {
    if (!incidentId || state === "idle") return;
    setState("leaving");
    await teardown();
    try {
      await fetch(`${API}/incidents/${encodeURIComponent(incidentId)}/agora-agent/leave`, { method: "POST" });
    } catch { /* best-effort */ }
    setAgentSpeaking(false);
    setState("idle");
  }, [incidentId, state, teardown]);

  return { state, agentSpeaking, join, leave };
}
