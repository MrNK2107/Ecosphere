import { useIncidentStore, type Snapshot, type ActionItem } from "../store/incidentStore";
import { Badge, EmptyState, type Tone } from "./ui";

const statusColumns: { key: ActionItem["status"]; label: string; tone: Tone }[] = [
  { key: "Open", label: "Open", tone: "neutral" },
  { key: "InProgress", label: "In Progress", tone: "blue" },
  { key: "Blocked", label: "Blocked", tone: "red" },
  { key: "Overdue", label: "Overdue", tone: "orange" },
  { key: "Done", label: "Done", tone: "green" },
];

const borderTone: Record<ActionItem["status"], string> = {
  Open: "border-l-slate-300",
  InProgress: "border-l-blue-400",
  Blocked: "border-l-red-400",
  Done: "border-l-emerald-400",
  Overdue: "border-l-orange-400",
};

function ActionCard({ action }: { action: ActionItem }) {
  const { approveAction, updateActionStatus } = useIncidentStore();
  const isOverdue = action.status === "Overdue" ||
    (!!action.dueAt && new Date(action.dueAt) < new Date() && action.status !== "Done");

  return (
    <div className={`p-2.5 rounded-lg border border-slate-200 bg-white border-l-[3px] ${borderTone[action.status] ?? "border-l-slate-300"}`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-slate-800 flex-1 font-medium leading-snug">{action.title}</span>
        {action.requiresConfirmation && <Badge tone="orange">Confirm</Badge>}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-400">
        {action.ownerName ? <span>👤 {action.ownerName}</span> : <span className="text-orange-500">⚠ Unassigned</span>}
        {action.toolKey && <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-500">🔧 {action.toolKey}</span>}
        {action.dueAt && (
          <span className={isOverdue ? "text-red-500 font-medium" : ""}>
            ⏰ {new Date(action.dueAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      <div className="mt-2 flex items-center gap-1.5">
        {action.requiresConfirmation && (
          <button
            onClick={() => approveAction(action.id)}
            className="text-[11px] px-2 py-1 rounded-md bg-emerald-50 text-emerald-700 hover:bg-emerald-100 font-medium"
          >
            ✓ Approve
          </button>
        )}
        {action.status === "Open" && (
          <button
            onClick={() => updateActionStatus(action.id, "InProgress")}
            className="text-[11px] px-2 py-1 rounded-md bg-blue-50 text-blue-700 hover:bg-blue-100 font-medium"
          >
            Start →
          </button>
        )}
        {(action.status === "InProgress" || action.status === "Overdue" || action.status === "Blocked") && (
          <button
            onClick={() => updateActionStatus(action.id, "Done")}
            className="text-[11px] px-2 py-1 rounded-md bg-emerald-50 text-emerald-700 hover:bg-emerald-100 font-medium"
          >
            ✓ Done
          </button>
        )}
        {action.status === "Done" && <span className="text-[11px] text-emerald-600">✓ Completed</span>}
      </div>
    </div>
  );
}

export function ActionKanban({ snapshot }: { snapshot: Snapshot }) {
  const actions = snapshot?.actions ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Action Items</h3>
        <span className="text-[11px] text-slate-400">{actions.length} total</span>
      </div>
      <div className="flex-1 overflow-x-auto p-3">
        {actions.length === 0 ? (
          <EmptyState icon="📋">No action items yet</EmptyState>
        ) : (
          <div className="grid grid-flow-col auto-cols-[220px] gap-3 h-full">
            {statusColumns.map((col) => {
              const colActions = actions.filter((a) => a.status === col.key);
              return (
                <div key={col.key} className="flex flex-col min-h-0">
                  <div className="flex items-center gap-1.5 px-1 pb-2 border-b border-slate-200 mb-2 shrink-0">
                    <Badge tone={col.tone}>{col.label}</Badge>
                    <span className="text-[11px] text-slate-400">{colActions.length}</span>
                  </div>
                  <div className="flex-1 space-y-2 overflow-y-auto">
                    {colActions.map((a) => <ActionCard key={a.id} action={a} />)}
                    {colActions.length === 0 && (
                      <div className="text-[11px] text-slate-300 text-center py-3">No items</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
