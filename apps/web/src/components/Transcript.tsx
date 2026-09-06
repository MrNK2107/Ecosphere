import { useRef, useEffect } from "react";
import type { Snapshot, TranscriptSegment } from "../store/incidentStore";
import { Avatar, EmptyState } from "./ui";

const roleColor: Record<string, string> = {
  SRE: "text-cyan-600",
  Backend: "text-emerald-600",
  Frontend: "text-blue-600",
  Support: "text-amber-600",
  Comms: "text-fuchsia-600",
  Biz: "text-sky-600",
};

function TranscriptLine({ seg }: { seg: TranscriptSegment }) {
  const time = seg.startMs != null ? new Date(seg.startMs).toISOString().substr(14, 5) : "";
  const name = seg.speakerName ?? seg.speakerId ?? "?";
  return (
    <div className="flex gap-3 py-2.5 px-1 group">
      <Avatar name={name} size={7} />
      <div className="flex-1 min-w-0 bg-slate-50 rounded-xl rounded-tl-sm px-3 py-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${roleColor[seg.role ?? ""] ?? "text-slate-600"}`}>{name}</span>
          {seg.role && <span className="text-[10px] text-slate-400">{seg.role}</span>}
          <span className="text-[10px] text-slate-300 ml-auto font-mono">{time}</span>
        </div>
        <p className="text-sm text-slate-800 mt-0.5 break-words leading-snug">{seg.text}</p>
      </div>
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
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Live Conversation</h3>
        <span className="text-[11px] text-slate-400">{segments.length} segments</span>
      </div>
      <div className="flex-1 overflow-y-auto px-3">
        {segments.length === 0 ? (
          <EmptyState icon="💬">No transcript yet — waiting for voice input</EmptyState>
        ) : (
          segments.map((seg) => <TranscriptLine key={seg.id} seg={seg} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
