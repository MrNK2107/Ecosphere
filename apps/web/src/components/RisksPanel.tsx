import type { Snapshot, Gap, Conflict } from "../store/incidentStore";
import { Badge, EmptyState, type Tone } from "./ui";

const severityTone: Record<Gap["severity"], Tone> = {
  critical: "red",
  high: "orange",
  medium: "amber",
  low: "neutral",
};

const kindIcon: Record<Gap["kind"], string> = {
  ConflictingInfo: "⚡",
  MissingOwner: "👤",
  UnverifiedAssumption: "❓",
  StaleAction: "⏰",
  AssumptionCreep: "📈",
  DuplicateWork: "🪞",
  DecisionHygiene: "🧭",
};

const kindOrder: Gap["kind"][] = [
  "ConflictingInfo", "MissingOwner", "UnverifiedAssumption", "StaleAction",
  "AssumptionCreep", "DuplicateWork", "DecisionHygiene",
];

function humanizeKind(kind: string) {
  return kind.replace(/([A-Z])/g, " $1").trim();
}

function ConflictAlert({ c }: { c: Conflict }) {
  return (
    <div className="p-3 rounded-lg border border-red-200 bg-red-50">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">⚠️</span>
        <span className="text-[11px] font-bold text-red-700 uppercase tracking-wide">Conflict Detected</span>
        {c.verificationRequired && <Badge tone="red">Verification required</Badge>}
      </div>
      <p className="text-sm text-red-800">
        <span className="font-medium">A:</span> {c.claimA} <span className="mx-1 text-red-400">vs</span>
        <span className="font-medium">B:</span> {c.claimB}
      </p>
    </div>
  );
}

function GapCard({ gap }: { gap: Gap }) {
  return (
    <div className="p-3 rounded-lg border border-slate-200 hover:border-slate-300 hover:bg-slate-50/60 transition-colors">
      <div className="flex items-start gap-2.5">
        <span className="text-base leading-none mt-0.5">{kindIcon[gap.kind] ?? "⚠️"}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{humanizeKind(gap.kind)}</span>
            <Badge tone={severityTone[gap.severity] ?? "neutral"}>{gap.severity}</Badge>
          </div>
          <p className="text-sm text-slate-700 mt-1 break-words">{gap.message}</p>
        </div>
      </div>
    </div>
  );
}

export function RisksPanel({ snapshot }: { snapshot: Snapshot }) {
  const gaps = snapshot?.gaps ?? [];
  const openConflicts = (snapshot?.conflicts ?? []).filter((c) => c.status === "OPEN" || c.status === "UNDER_REVIEW");
  const grouped = gaps.reduce((acc, g) => {
    (acc[g.kind] ??= []).push(g);
    return acc;
  }, {} as Record<string, Gap[]>);

  const nothingToShow = gaps.length === 0 && openConflicts.length === 0;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Risks &amp; Conflicts</h3>
        <Badge tone={gaps.length + openConflicts.length > 0 ? "orange" : "green"}>
          {gaps.length + openConflicts.length} detected
        </Badge>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {nothingToShow ? (
          <EmptyState icon="🛡️">No open risks — nothing unverified, conflicting, or unowned</EmptyState>
        ) : (
          <>
            {openConflicts.length > 0 && (
              <div>
                <div className="text-[11px] font-medium text-red-500 uppercase mb-1.5">
                  Conflict Alerts ({openConflicts.length})
                </div>
                <div className="space-y-2">
                  {openConflicts.map((c) => <ConflictAlert key={c.id} c={c} />)}
                </div>
              </div>
            )}
            {kindOrder.map((kind) => {
              const kindGaps = grouped[kind];
              if (!kindGaps) return null;
              return (
                <div key={kind}>
                  <div className="text-[11px] font-medium text-slate-400 uppercase mb-1.5">
                    {humanizeKind(kind)} ({kindGaps.length})
                  </div>
                  <div className="space-y-2">
                    {kindGaps.map((g) => <GapCard key={g.id} gap={g} />)}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
