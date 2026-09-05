import { useIncidentStore, type Snapshot, type ToolEvent } from "../store/incidentStore";

const statusDot: Record<string, string> = {
  pending: "bg-yellow-500",
  success: "bg-green-500",
  failed: "bg-red-500",
  requiresApproval: "bg-orange-500",
  rejected: "bg-red-400",
};

function ToolEventRow({ te }: { te: ToolEvent }) {
  const result = te.result as Record<string, unknown> | undefined;
  const resultKey = result?.key != null ? String(result.key) : null;
  return (
    <div className="flex items-center gap-2 py-1 px-2 hover:bg-zinc-800/50 text-xs">
      <div className={`w-2 h-2 rounded-full ${statusDot[te.status] ?? "bg-zinc-600"}`} />
      <span className="font-mono text-zinc-400 w-16 shrink-0">{te.tool}</span>
      <span className="text-zinc-300 flex-1 truncate">{te.action}</span>
      {te.requiresApproval && (
        <span className="text-[10px] px-1 py-0.5 bg-orange-900/50 text-orange-300">⚠️</span>
      )}
      {resultKey && (
        <span className="text-[10px] font-mono text-blue-400">{resultKey}</span>
      )}
    </div>
  );
}

export function ToolEvents({ snapshot }: { snapshot: Snapshot }) {
  const events = snapshot?.toolEvents ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Tool Events</h3>
        <span className="text-[10px] text-zinc-600">{events.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">No tool events</div>
        ) : (
          events.map((te) => <ToolEventRow key={te.id} te={te} />)
        )}
      </div>
    </div>
  );
}
