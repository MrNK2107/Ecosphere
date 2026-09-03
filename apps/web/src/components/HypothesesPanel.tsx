import { useIncidentStore, type Snapshot, type Hypothesis } from "../store/incidentStore";

const statusColor: Record<string, string> = {
  Active: "bg-yellow-900/50 text-yellow-300",
  Disproven: "bg-red-900/50 text-red-300",
  Confirmed: "bg-green-900/50 text-green-300",
};

function HypCard({ hyp }: { hyp: Hypothesis }) {
  return (
    <div className="p-2 rounded border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/50">
      <div className="flex items-start gap-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${statusColor[hyp.status] ?? ""}`}>
          {hyp.status}
        </span>
        <span className="text-xs text-zinc-200 flex-1">{hyp.statement}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div className="h-full bg-yellow-500 rounded-full" style={{ width: `${hyp.confidence * 100}%` }} />
        </div>
        <span className="text-[10px] text-zinc-500">{Math.round(hyp.confidence * 100)}%</span>
      </div>
    </div>
  );
}

export function HypothesesPanel({ snapshot }: { snapshot: Snapshot }) {
  const hyps = snapshot?.hypotheses ?? [];
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Hypotheses</h3>
        <span className="text-[10px] text-zinc-600">{hyps.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {hyps.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">No hypotheses</div>
        ) : (
          hyps.map((h) => <HypCard key={h.id} hyp={h} />)
        )}
      </div>
    </div>
  );
}
