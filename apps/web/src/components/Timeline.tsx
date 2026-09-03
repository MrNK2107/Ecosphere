import { useIncidentStore, type Snapshot, type TimelineEvent } from "../store/incidentStore";

const typeColor: Record<string, string> = {
  transcript: "bg-zinc-600",
  fact_created: "bg-green-500",
  fact_updated: "bg-green-400",
  hypothesis_created: "bg-yellow-500",
  hypothesis_updated: "bg-yellow-400",
  decision: "bg-blue-500",
  action_created: "bg-purple-500",
  action_updated: "bg-purple-400",
  gap_detected: "bg-red-500",
  gap_resolved: "bg-green-500",
  tool: "bg-cyan-500",
  summary: "bg-indigo-500",
  system: "bg-zinc-500",
};

const typeLabel: Record<string, string> = {
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
  system: "⚙️",
};

function TimelineItem({ event, isLast }: { event: TimelineEvent; isLast: boolean }) {
  const payloadStr = event.payload
    ? JSON.stringify(event.payload).slice(0, 100)
    : "";
  const time = event.createdAt
    ? new Date(event.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "";

  return (
    <div className="flex gap-2 relative">
      {/* Vertical line */}
      {!isLast && (
        <div className="absolute left-2.5 top-6 bottom-0 w-px bg-zinc-800" />
      )}
      {/* Dot */}
      <div className={`w-5 h-5 rounded-full ${typeColor[event.type] ?? "bg-zinc-600"} flex items-center justify-center text-[10px] shrink-0 z-10`}>
        {typeLabel[event.type] ?? "•"}
      </div>
      {/* Content */}
      <div className="flex-1 pb-3 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium text-zinc-400">
            {event.type.replace(/_/g, " ")}
          </span>
          <span className="text-[10px] text-zinc-600 font-mono">seq={event.seq}</span>
          <span className="text-[10px] text-zinc-600">{time}</span>
        </div>
        <p className="text-xs text-zinc-500 mt-0.5 truncate">{payloadStr}</p>
      </div>
    </div>
  );
}

export function Timeline({ snapshot }: { snapshot: Snapshot }) {
  const events = snapshot?.timeline ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Timeline</h3>
        <span className="text-[10px] text-zinc-600">{events.length} events</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {events.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">No events yet</div>
        ) : (
          events.map((ev, i) => (
            <TimelineItem key={ev.id} event={ev} isLast={i === events.length - 1} />
          ))
        )}
      </div>
    </div>
  );
}
