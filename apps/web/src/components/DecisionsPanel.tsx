import type { Snapshot, Decision } from "../store/incidentStore";
import { Badge, EmptyState, type Tone } from "./ui";

const statusTone: Record<Decision["status"], Tone> = {
  Proposed: "blue",
  Approved: "green",
  Reverted: "red",
};

function DecisionCard({ dec }: { dec: Decision }) {
  return (
    <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 transition-colors">
      <div className="flex items-start gap-2">
        <Badge tone={statusTone[dec.status] ?? "neutral"}>{dec.status}</Badge>
        <span className="text-sm text-slate-700 flex-1">{dec.statement}</span>
      </div>
      {dec.decidedBy && <div className="mt-1.5 text-[11px] text-slate-400">Decided by {dec.decidedBy}</div>}
    </div>
  );
}

export function DecisionsPanel({ snapshot }: { snapshot: Snapshot }) {
  const decs = snapshot?.decisions ?? [];
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Decisions</h3>
        <span className="text-[11px] text-slate-400">{decs.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {decs.length === 0 ? (
          <EmptyState icon="⚖️">No decisions yet</EmptyState>
        ) : (
          decs.map((d) => <DecisionCard key={d.id} dec={d} />)
        )}
      </div>
    </div>
  );
}
