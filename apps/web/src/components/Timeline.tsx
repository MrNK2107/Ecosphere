import type { Snapshot, TimelineEvent } from "../store/incidentStore";
import { EmptyState } from "./ui";

const typeDot: Record<string, string> = {
  transcript: "bg-slate-400",
  fact_created: "bg-emerald-500",
  fact_updated: "bg-emerald-400",
  hypothesis_created: "bg-amber-500",
  hypothesis_updated: "bg-amber-400",
  decision: "bg-blue-500",
  action_created: "bg-violet-500",
  action_updated: "bg-violet-400",
  gap_detected: "bg-red-500",
  gap_resolved: "bg-emerald-500",
  tool: "bg-cyan-500",
  summary: "bg-indigo-500",
  spoken_summary: "bg-indigo-400",
  system: "bg-slate-400",
};

const typeIcon: Record<string, string> = {
  transcript: "💬",
  fact_created: "✅",
  fact_updated: "🔄",
  hypothesis_created: "❓",
  hypothesis_updated: "🔄",
  decision: "⚖️",
  action_created: "📋",
  action_updated: "🔄",
  gap_detected: "⚠️",
  gap_resolved: "✓",
  tool: "🔧",
  summary: "📝",
  spoken_summary: "🔊",
  system: "⚙️",
};

function formatEventText(event: TimelineEvent): string {
  const p = event.payload ?? {};
  const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : JSON.stringify(v));
  switch (event.type) {
    case "transcript":
      return `${str(p.speakerName) || "Someone"}: ${str(p.text)}`;
    case "fact_created":
    case "fact_updated":
    case "hypothesis_created":
    case "hypothesis_updated":
      return `${str(p.statement)}${p.status ? ` (${str(p.status)})` : ""}`;
    case "decision":
      return `${str(p.statement)}${p.status ? ` (${str(p.status)})` : ""}`;
    case "action_created":
      return str(p.title);
    case "action_updated":
      return `${str(p.title)}${p.status ? ` → ${str(p.status)}` : ""}`;
    case "gap_detected":
      return str(p.message);
    case "gap_resolved":
      return str(p.message) || "Gap resolved";
    case "tool":
      return `${str(p.tool)} ${str(p.action)}${p.status ? ` — ${str(p.status)}` : ""}`;
    case "spoken_summary":
      return str(p.script);
    case "summary":
      return str(p.markdown);
    case "system":
      return str(p.message);
    default:
      return event.payload ? JSON.stringify(event.payload).slice(0, 100) : "";
  }
}

export function TimelineItem({ event, isLast }: { event: TimelineEvent; isLast: boolean }) {
  const payloadStr = formatEventText(event).slice(0, 140);
  const time = event.createdAt
    ? new Date(event.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "";

  return (
    <div className="flex gap-3 relative">
      {!isLast && <div className="absolute left-[13px] top-7 bottom-0 w-px bg-slate-200" />}
      <div className={`w-[26px] h-[26px] rounded-full ${typeDot[event.type] ?? "bg-slate-400"} flex items-center justify-center text-[11px] shrink-0 z-10 ring-4 ring-white`}>
        {typeIcon[event.type] ?? "•"}
      </div>
      <div className="flex-1 pb-4 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[12px] font-medium text-slate-700 capitalize">{event.type.replace(/_/g, " ")}</span>
          <span className="text-[11px] text-slate-300">{time}</span>
        </div>
        {payloadStr && <p className="text-xs text-slate-400 mt-0.5 truncate">{payloadStr}</p>}
      </div>
    </div>
  );
}

export function Timeline({ snapshot }: { snapshot: Snapshot }) {
  const events = snapshot?.timeline ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Timeline</h3>
        <span className="text-[11px] text-slate-400">{events.length} events</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {events.length === 0 ? (
          <EmptyState icon="📜">No events yet</EmptyState>
        ) : (
          events.map((ev, i) => <TimelineItem key={ev.id} event={ev} isLast={i === events.length - 1} />)
        )}
      </div>
    </div>
  );
}
