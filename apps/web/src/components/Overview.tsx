import type { Snapshot } from "../store/incidentStore";
import { Badge, Card, EmptyState, ProgressBar, StatTile, type Tone } from "./ui";
import { TimelineItem } from "./Timeline";
import { useElapsed } from "../lib/utils";

const actionStatusTone: Record<string, Tone> = {
  Open: "neutral", InProgress: "blue", Blocked: "red", Overdue: "orange", Done: "green",
};

export function Overview({ snapshot }: { snapshot: Snapshot }) {
  const duration = useElapsed(snapshot?.incident?.createdAt);
  const actions = snapshot?.actions ?? [];
  const openActions = actions.filter((a) => a.status !== "Done");
  const gaps = snapshot?.gaps ?? [];
  const openConflicts = (snapshot?.conflicts ?? []).filter((c) => c.status === "OPEN" || c.status === "UNDER_REVIEW");
  const events = [...(snapshot?.timeline ?? [])].slice(-5).reverse();

  const topHypothesis = [...(snapshot?.hypotheses ?? [])].sort((a, b) => b.confidence - a.confidence)[0];
  const latestDecision = [...(snapshot?.decisions ?? [])].reverse().find((d) => d.status === "Approved")
    ?? [...(snapshot?.decisions ?? [])].reverse()[0];

  return (
    <div className="h-full overflow-y-auto p-5 space-y-4">
      {openConflicts.length > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm">⚠️</span>
            <span className="text-[11px] font-bold text-red-700 uppercase tracking-wide">
              {openConflicts.length} Conflict{openConflicts.length === 1 ? "" : "s"} Detected — Verification Required
            </span>
          </div>
          <p className="text-sm text-red-800 truncate">
            <span className="font-medium">A:</span> {openConflicts[0].claimA}
            <span className="mx-1.5 text-red-400">vs</span>
            <span className="font-medium">B:</span> {openConflicts[0].claimB}
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Severity" value={snapshot.incident.severity.replace("SEV", "SEV-")} tone="red" />
        <StatTile label="Duration" value={duration} sub="Since incident opened" tone="blue" />
        <StatTile label="Open Actions" value={openActions.length} sub={`${actions.length} total`} tone="orange" />
        <StatTile label="Participants" value={snapshot.incident.participants.length} tone="indigo" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Live Timeline" className="lg:col-span-2 max-h-[420px]" padded>
          <div className="overflow-y-auto max-h-[350px] pr-1">
            {events.length === 0 ? (
              <EmptyState icon="📜">No events yet</EmptyState>
            ) : (
              events.map((ev, i) => <TimelineItem key={ev.id} event={ev} isLast={i === events.length - 1} />)
            )}
          </div>
        </Card>

        <Card title="AI Incident Commander" padded>
          <div className="space-y-3">
            <div>
              <div className="text-[11px] font-medium text-slate-400 uppercase mb-1">Likely Cause</div>
              <p className="text-sm text-slate-700">{topHypothesis ? topHypothesis.statement : "Still investigating — no hypothesis yet"}</p>
            </div>
            <div>
              <div className="text-[11px] font-medium text-slate-400 uppercase mb-1">Current Mitigation</div>
              <p className="text-sm text-slate-700">{latestDecision ? latestDecision.statement : "No decision recorded yet"}</p>
            </div>
            <div>
              <div className="text-[11px] font-medium text-slate-400 uppercase mb-1">Impact</div>
              <p className="text-sm text-slate-700">{snapshot.incident.description || "No impact statement yet"}</p>
            </div>
            {topHypothesis && (
              <div className="pt-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] font-medium text-slate-400 uppercase">Confidence</span>
                  <span className="text-[11px] font-semibold text-indigo-600">{Math.round(topHypothesis.confidence * 100)}%</span>
                </div>
                <ProgressBar value={topHypothesis.confidence} tone="indigo" />
              </div>
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Open Action Items" right={<Badge tone="orange">{openActions.length}</Badge>}>
          {openActions.length === 0 ? (
            <EmptyState icon="📋">Nothing open — everything's done</EmptyState>
          ) : (
            <div className="space-y-2">
              {openActions.slice(0, 5).map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-2 py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-sm text-slate-700 truncate">{a.title}</span>
                  <Badge tone={actionStatusTone[a.status]}>{a.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Risk Indicators" right={<Badge tone={gaps.length > 0 ? "orange" : "green"}>{gaps.length + openConflicts.length}</Badge>}>
          {gaps.length === 0 ? (
            <EmptyState icon="🛡️">No open risks</EmptyState>
          ) : (
            <div className="space-y-2">
              {gaps.slice(0, 5).map((g) => (
                <div key={g.id} className="flex items-start gap-2 py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-sm text-slate-700 flex-1">{g.message}</span>
                  <Badge tone={g.severity === "critical" ? "red" : g.severity === "high" ? "orange" : "amber"}>{g.severity}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
