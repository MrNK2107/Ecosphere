import { useEffect, useMemo } from "react";
import AgoraRTC, {
  AgoraRTCProvider,
  useJoin,
  useLocalMicrophoneTrack,
  usePublish,
  useRemoteUsers,
  useRemoteAudioTracks,
  useAutoPlayAudioTrack,
} from "agora-rtc-react";
import { ConversationalAIProvider, useTranscript, useAgentState } from "agora-agent-client-toolkit-react";
import { API } from "../store/incidentStore";
import { showToast } from "./Toast";
import type { VoiceSessionData } from "../lib/voice";

// Must match the SDK's numeric-UID requirement for App Credentials mode
// (apps/api/main.py's agora_agent_join — confirmed live 2026-09-06).
const AGENT_RTC_UID = "911911";

const rtcClient = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });

export function VoiceSession({ appId, channel, token, uid, rtmClient }: VoiceSessionData) {
  const config = useMemo(() => ({ channel, rtmEngine: rtmClient }), [channel, rtmClient]);

  return (
    <AgoraRTCProvider client={rtcClient}>
      <ConversationalAIProvider config={config}>
        <VoiceSessionInner appId={appId} channel={channel} token={token} uid={uid} />
      </ConversationalAIProvider>
    </AgoraRTCProvider>
  );
}

function VoiceSessionInner({ appId, channel, token, uid }: { appId: string; channel: string; token: string; uid: number }) {
  useJoin({ appid: appId, channel, token, uid });
  const { localMicrophoneTrack } = useLocalMicrophoneTrack();
  usePublish([localMicrophoneTrack]);

  const remoteUsers = useRemoteUsers();
  const { audioTracks } = useRemoteAudioTracks(remoteUsers);
  useAutoPlayAudioTrack(audioTracks[0] ?? null);

  const transcript = useTranscript();
  const { agentState } = useAgentState();

  useEffect(() => {
    fetch(`${API}/incidents/${encodeURIComponent(channel)}/agora-agent/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, agentRtcUid: AGENT_RTC_UID }),
    })
      .then(async (res) => {
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `Agent join failed (${res.status})`);
        showToast("success", "Voice room connected — EchoSphere is listening.");
      })
      .catch((e) => showToast("error", `Agent join failed: ${e.message}`));
    // Runs once when the session mounts (i.e. once per "Join Voice" click).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="absolute right-4 top-14 z-40 w-80 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-100 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700">Live Voice</span>
        <span className="text-[10px] text-slate-400 capitalize">{agentState ?? "connecting…"}</span>
      </div>
      <div className="max-h-72 overflow-y-auto p-3 space-y-2">
        {transcript.length === 0 && <p className="text-xs text-slate-400">Listening — say something…</p>}
        {transcript.map((t) => (
          <div key={`${t.uid}-${t.turn_id}`} className="text-xs leading-snug">
            <span className="font-medium text-slate-600">{t.uid === AGENT_RTC_UID ? "EchoSphere" : "You"}: </span>
            <span className="text-slate-500">{t.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
