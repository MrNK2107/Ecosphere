import type { Snapshot, ToolEvent } from "../store/incidentStore";
import { Badge, Dot, EmptyState, type Tone } from "./ui";

const statusTone: Record<string, Tone> = {
  pending: "amber",
  success: "green",
  failed: "red",
  requiresApproval: "orange",
  rejected: "red",
};

function ToolEventRow({ te }: { te: ToolEvent }) {
  const result = te.result as Record<string, unknown> | undefined;
  const resultKey = result?.key != null ? String(result.key) : null;
  return (
    <div className="flex items-center gap-3 py-2 px-3 hover:bg-slate-50 text-xs border-b border-slate-100 last:border-0">
      <Dot tone={statusTone[te.status] ?? "neutral"} />
      <span className="font-mono text-slate-500 w-20 shrink-0">{te.tool}</span>
      <span className="text-slate-700 flex-1 truncate">{te.action}</span>
      {te.requiresApproval && <Badge tone="orange">approval</Badge>}
      {resultKey && <span className="text-[11px] font-mono text-blue-600">{resultKey}</span>}
    </div>
  );
}

export function ToolEvents({ snapshot }: { snapshot: Snapshot }) {
  const events = snapshot?.toolEvents ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Integrations</h3>
        <span className="text-[11px] text-slate-400">{events.length} events</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <EmptyState icon="🔧">No integration activity yet</EmptyState>
        ) : (
          events.map((te) => <ToolEventRow key={te.id} te={te} />)
        )}
      </div>
    </div>
  );
}
