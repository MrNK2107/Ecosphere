import { useState } from "react";
import { useIncidentStore, type Snapshot } from "../store/incidentStore";
import { Avatar, Badge, Dot, type Tone } from "./ui";
import { useElapsed } from "../lib/utils";
import { useVoiceRoom } from "../lib/voice";
import { VoiceSession } from "./VoiceSession";

const severityTone: Record<string, Tone> = {
  SEV1: "red", SEV2: "orange", SEV3: "amber", SEV4: "neutral",
};

export function Header({ snapshot }: { snapshot: Snapshot | null }) {
  const { wsConnected, incidentId, connect } = useIncidentStore();
  const [inputId, setInputId] = useState(incidentId ?? "payment-001");
  const duration = useElapsed(snapshot?.incident?.createdAt);
  const participants = snapshot?.incident?.participants ?? [];
  const voice = useVoiceRoom(incidentId);

  return (
    <div className="relative px-5 py-3 bg-white border-b border-slate-200 flex items-center gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-slate-900 truncate">
            {snapshot?.incident?.title ?? "Waiting for incident…"}
          </h2>
          {snapshot?.incident && (
            <Badge tone={severityTone[snapshot.incident.severity] ?? "neutral"}>
              {snapshot.incident.severity.replace("SEV", "SEV-")}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <Dot tone={wsConnected ? "green" : "red"} pulse={wsConnected} />
          <span className="text-[11px] text-slate-400">{wsConnected ? "Live" : "Disconnected"}</span>
          {snapshot?.incident && <span className="text-[11px] text-slate-300">· {duration} elapsed</span>}
        </div>
      </div>

      <div className="flex-1" />

      <div className="flex items-center -space-x-2">
        {participants.slice(0, 5).map((p) => (
          <div key={p.id} title={`${p.name} (${p.role})`} className="ring-2 ring-white rounded-full">
            <Avatar name={p.name} size={7} />
          </div>
        ))}
        {participants.length > 0 && (
          <span className="ml-3 text-[11px] text-slate-400">{participants.length} participant{participants.length === 1 ? "" : "s"}</span>
        )}
      </div>

      <div className="flex items-center gap-1.5 border-l border-slate-200 pl-4">
        <input
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && inputId.trim() && connect(inputId.trim())}
          className="text-xs px-2 py-1.5 bg-slate-50 border border-slate-200 rounded-md w-32 focus:outline-none focus:border-indigo-400 text-slate-600"
          placeholder="incident id"
        />
        <button
          onClick={() => inputId.trim() && connect(inputId.trim())}
          className="text-[11px] px-2.5 py-1.5 rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 font-medium"
        >
          Connect
        </button>
      </div>

      {incidentId && (
        <div className="flex items-center gap-2 border-l border-slate-200 pl-4">
          <button
            onClick={() => (voice.state === "connected" ? voice.leave() : voice.join())}
            disabled={voice.state === "connecting" || voice.state === "leaving"}
            className={`text-[11px] px-2.5 py-1.5 rounded-md font-medium disabled:opacity-50 ${
              voice.state === "connected"
                ? "bg-red-50 text-red-700 hover:bg-red-100"
                : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
            }`}
          >
            {voice.state === "idle" && "🎙️ Join Voice"}
            {voice.state === "connecting" && "Connecting…"}
            {voice.state === "connected" && "🎙️ Leave Voice"}
            {voice.state === "leaving" && "Leaving…"}
          </button>
        </div>
      )}

      {voice.state === "connected" && voice.session && <VoiceSession {...voice.session} />}
    </div>
  );
}
