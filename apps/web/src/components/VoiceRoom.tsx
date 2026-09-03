import { useIncidentStore, type Snapshot } from "../store/incidentStore";

const roleColors: Record<string, string> = {
  SRE: "bg-cyan-950/40 text-cyan-300 border-cyan-800",
  Backend: "bg-emerald-950/40 text-emerald-300 border-emerald-800",
  Frontend: "bg-blue-950/40 text-blue-300 border-blue-800",
  Support: "bg-amber-950/40 text-amber-300 border-amber-800",
  Comms: "bg-fuchsia-950/40 text-fuchsia-300 border-fuchsia-800",
  Biz: "bg-sky-950/40 text-sky-300 border-sky-800",
};

export function VoiceRoom({ snapshot }: { snapshot: Snapshot }) {
  const { wsConnected, incidentId } = useIncidentStore();
  const participants = snapshot?.incident?.participants ?? [];

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-zinc-900 border-b border-zinc-800">
      {/* Connection status */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${wsConnected ? "bg-green-500" : "bg-red-500"}`} />
        <span className="text-xs text-zinc-400">{wsConnected ? "Connected" : "Disconnected"}</span>
      </div>

      {/* Incident ID */}
      {incidentId && (
        <span className="text-xs font-mono text-zinc-500 px-2 py-0.5 bg-zinc-800 rounded">
          {incidentId}
        </span>
      )}

      {/* Severity badge */}
      <span className={`text-xs font-bold px-2 py-0.5 rounded ${
        snapshot?.incident?.severity === "SEV1" ? "bg-red-900/50 text-red-300" :
        snapshot?.incident?.severity === "SEV2" ? "bg-orange-900/50 text-orange-300" :
        "bg-yellow-900/50 text-yellow-300"
      }`}>
        {snapshot?.incident?.severity ?? "SEV1"}
      </span>

      <div className="flex-1" />

      {/* Participants */}
      <div className="flex items-center gap-2">
        {participants.map((p) => (
          <div
            key={p.id}
            className={`flex items-center gap-1.5 px-2 py-1 rounded border text-xs ${
              roleColors[p.role] ?? "bg-zinc-900 text-zinc-300 border-zinc-800"
            }`}
          >
            <div className="w-5 h-5 rounded-full bg-zinc-700 flex items-center justify-center text-[10px] font-bold">
              {p.name[0]}
            </div>
            <span>{p.name}</span>
            <span className="text-[10px] opacity-60">({p.role})</span>
            {p.isBot && <span className="text-[10px]">🤖</span>}
          </div>
        ))}
        {participants.length === 0 && (
          <span className="text-xs text-zinc-600">No participants yet</span>
        )}
      </div>
    </div>
  );
}
