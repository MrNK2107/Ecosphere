import { useIncidentStore, type Snapshot, type Gap } from "../store/incidentStore";

const severityColor: Record<string, string> = {
  critical: "bg-red-900/50 text-red-300 border-red-800",
  high: "bg-orange-900/50 text-orange-300 border-orange-800",
  medium: "bg-yellow-900/50 text-yellow-300 border-yellow-800",
  low: "bg-zinc-800 text-zinc-400 border-zinc-700",
};

const kindIcon: Record<string, string> = {
  ConflictingInfo: "⚡",
  MissingOwner: "👤",
  UnverifiedAssumption: "❓",
  StaleAction: "⏰",
};

function GapCard({ gap }: { gap: Gap }) {
  return (
    <div className={`p-2 rounded border ${severityColor[gap.severity] ?? severityColor.medium}`}>
      <div className="flex items-start gap-2">
        <span className="text-sm">{kindIcon[gap.kind] ?? "⚠️"}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium uppercase">{gap.kind.replace(/([A-Z])/g, " $1").trim()}</span>
            <span className="text-[10px] opacity-60">• {gap.severity}</span>
          </div>
          <p className="text-xs mt-0.5 break-words">{gap.message}</p>
        </div>
      </div>
    </div>
  );
}

export function GapsPanel({ snapshot }: { snapshot: Snapshot }) {
  const gaps = snapshot?.gaps ?? [];

  // Group by kind
  const grouped = gaps.reduce((acc, g) => {
    (acc[g.kind] ??= []).push(g);
    return acc;
  }, {} as Record<string, Gap[]>);

  const kindOrder = ["ConflictingInfo", "MissingOwner", "UnverifiedAssumption", "StaleAction"];

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Gaps & Risks</h3>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          gaps.length > 0 ? "bg-orange-900/50 text-orange-300" : "bg-green-900/50 text-green-300"
        }`}>
          {gaps.length} detected
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {gaps.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">No gaps detected ✓</div>
        ) : (
          kindOrder.map((kind) => {
            const kindGaps = grouped[kind];
            if (!kindGaps) return null;
            return (
              <div key={kind}>
                <div className="text-[10px] text-zinc-500 uppercase mb-1">
                  {kind.replace(/([A-Z])/g, " $1").trim()} ({kindGaps.length})
                </div>
                {kindGaps.map((g) => <GapCard key={g.id} gap={g} />)}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
