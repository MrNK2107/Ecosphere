import type { Snapshot, Fact } from "../store/incidentStore";
import { Badge, ProgressBar, EmptyState, type Tone } from "./ui";

const statusTone: Record<Fact["status"], Tone> = {
  Confirmed: "green",
  Corroborated: "blue",
  Reported: "amber",
  Contradicted: "red",
};

function FactCard({ fact }: { fact: Fact }) {
  return (
    <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 transition-colors">
      <div className="flex items-start gap-2">
        <Badge tone={statusTone[fact.status] ?? "neutral"}>{fact.status}</Badge>
        <span className="text-sm text-slate-700 flex-1">{fact.statement}</span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <ProgressBar value={fact.confidence} tone="blue" />
        <span className="text-[11px] text-slate-400 tabular-nums">{Math.round(fact.confidence * 100)}%</span>
      </div>
      {fact.sourceSegmentIds.length > 0 && (
        <div className="mt-1 text-[10px] text-slate-400">source: {fact.sourceSegmentIds.length} transcript segment(s)</div>
      )}
    </div>
  );
}

export function FactsPanel({ snapshot }: { snapshot: Snapshot }) {
  const facts = snapshot?.facts ?? [];
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Facts</h3>
        <span className="text-[11px] text-slate-400">{facts.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {facts.length === 0 ? (
          <EmptyState icon="✅">No facts extracted yet</EmptyState>
        ) : (
          facts.map((f) => <FactCard key={f.id} fact={f} />)
        )}
      </div>
    </div>
  );
}
