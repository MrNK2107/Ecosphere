import { useRef, useEffect } from "react";
import { useIncidentStore, type Snapshot, type TranscriptSegment } from "../store/incidentStore";

const roleBadge: Record<string, string> = {
  SRE: "text-cyan-400",
  Backend: "text-emerald-400",
  Frontend: "text-blue-400",
  Support: "text-amber-400",
  Comms: "text-fuchsia-400",
  Biz: "text-sky-400",
};

function TranscriptLine({ seg }: { seg: TranscriptSegment }) {
  const time = seg.startMs != null
    ? new Date(seg.startMs).toISOString().substr(14, 5)
    : "";
  return (
    <div className="flex gap-2 py-1 px-2 hover:bg-zinc-800/50 group">
      <span className="text-[10px] text-zinc-600 w-12 shrink-0 mt-0.5 font-mono">
        {time}
      </span>
      <div className="flex-1 min-w-0">
        <span className={`text-xs font-medium ${roleBadge[seg.role ?? ""] ?? "text-zinc-400"}`}>
          {seg.speakerName ?? seg.speakerId ?? "?"}
        </span>
        {seg.role && (
          <span className="text-[10px] text-zinc-600 ml-1">({seg.role})</span>
        )}
        <span className="text-sm text-zinc-200 ml-2 break-words">{seg.text}</span>
      </div>
      <span className="text-[10px] text-zinc-700 opacity-0 group-hover:opacity-100 shrink-0">
        {Math.round(seg.confidence * 100)}%
      </span>
    </div>
  );
}

export function Transcript({ snapshot }: { snapshot: Snapshot }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const segments = snapshot?.transcript ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [segments.length]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Transcript</h3>
        <span className="text-[10px] text-zinc-600">{segments.length} segments</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {segments.length === 0 ? (
          <div className="p-4 text-center text-zinc-600 text-sm">
            No transcript yet. Waiting for voice input...
          </div>
        ) : (
          segments.map((seg) => <TranscriptLine key={seg.id} seg={seg} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
