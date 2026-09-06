import type { Snapshot, Hypothesis } from "../store/incidentStore";
import { Badge, ProgressBar, EmptyState, type Tone } from "./ui";

const statusTone: Record<string, Tone> = {
  Active: "amber",
  Disproven: "red",
  Confirmed: "green",
};

function HypCard({ hyp }: { hyp: Hypothesis }) {
  return (
    <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 transition-colors">
      <div className="flex items-start gap-2">
        <Badge tone={statusTone[hyp.status] ?? "neutral"}>{hyp.status}</Badge>
        <span className="text-sm text-slate-700 flex-1">{hyp.statement}</span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <ProgressBar value={hyp.confidence} tone="amber" />
        <span className="text-[11px] text-slate-400 tabular-nums">{Math.round(hyp.confidence * 100)}%</span>
      </div>
    </div>
  );
}

export function HypothesesPanel({ snapshot }: { snapshot: Snapshot }) {
  const hyps = snapshot?.hypotheses ?? [];
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Hypotheses</h3>
        <span className="text-[11px] text-slate-400">{hyps.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {hyps.length === 0 ? (
          <EmptyState icon="❓">No hypotheses yet</EmptyState>
        ) : (
          hyps.map((h) => <HypCard key={h.id} hyp={h} />)
        )}
      </div>
    </div>
  );
}
