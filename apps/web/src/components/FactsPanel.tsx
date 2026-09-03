import { useIncidentStore, type Snapshot, type Fact } from "../store/incidentStore";

const statusColor: Record<string, string> = {
  Confirmed: "bg-green-900/50 text-green-300",
  Corroborated: "bg-blue-900/50 text-blue-300",
  Reported: "bg-yellow-900/50 text-yellow-300",
  Contradicted: "bg-red-900/50 text-red-300",
};

function FactCard({ fact }: { fact: Fact }) {
  return (
    <div className="p-2 rounded border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/50">
      <div className="flex items-start gap-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${statusColor[fact.status] ?? ""}`}>
          {fact.status}
        </span>
        <span className="text-xs text-zinc-200 flex-1">{fact.statement}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 rounded-full"
            style={{ width: `${fact.confidence * 100}%` }}
          />
        </div>
        <span className="text-[10px] text-zinc-500">{Math.round(fact.confidence * 100)}%</span>
      </div>
      {fact.sourceSegmentIds.length > 0 && (
        <div className="mt-1 text-[10px] text-zinc-600">
          src: {fact.sourceSegmentIds.join(", ")}
        </div>
      )}
    </div>
  );
}

export function FactsPanel({ snapshot }: { snapshot: Snapshot }) {
  const facts = snapshot?.facts ?? [];
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Facts</h3>
        <span className="text-[10px] text-zinc-600">{facts.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {facts.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">No facts extracted yet</div>
        ) : (
          facts.map((f) => <FactCard key={f.id} fact={f} />)
        )}
      </div>
    </div>
  );
}
