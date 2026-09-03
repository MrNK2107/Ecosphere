import { useIncidentStore, type Snapshot, type Decision } from "../store/incidentStore";

const statusColor: Record<string, string> = {
  Proposed: "bg-blue-900/50 text-blue-300",
  Approved: "bg-green-900/50 text-green-300",
  Reverted: "bg-red-900/50 text-red-300",
};

function DecisionCard({ dec }: { dec: Decision }) {
  return (
    <div className="p-2 rounded border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/50">
      <div className="flex items-start gap-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${statusColor[dec.status] ?? ""}`}>
          {dec.status}
        </span>
        <span className="text-xs text-zinc-200 flex-1">{dec.statement}</span>
      </div>
      {dec.decidedBy && (
        <div className="mt-1 text-[10px] text-zinc-500">by {dec.decidedBy}</div>
      )}
    </div>
  );
}

export function DecisionsPanel({ snapshot }: { snapshot: Snapshot }) {
  const decs = snapshot?.decisions ?? [];
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Decisions</h3>
        <span className="text-[10px] text-zinc-600">{decs.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {decs.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">No decisions yet</div>
        ) : (
          decs.map((d) => <DecisionCard key={d.id} dec={d} />)
        )}
      </div>
    </div>
  );
}
