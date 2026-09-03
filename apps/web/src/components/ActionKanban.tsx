import { useIncidentStore, type Snapshot, type ActionItem } from "../store/incidentStore";

const statusColumns: { key: string; label: string; color: string }[] = [
  { key: "Open", label: "Open", color: "border-zinc-700" },
  { key: "InProgress", label: "In Progress", color: "border-blue-700" },
  { key: "Done", label: "Done", color: "border-green-700" },
];

const priorityColor: Record<string, string> = {
  Open: "border-l-zinc-500",
  InProgress: "border-l-blue-500",
  Blocked: "border-l-red-500",
  Done: "border-l-green-500",
  Overdue: "border-l-orange-500",
};

function ActionCard({ action }: { action: ActionItem }) {
  const { approveAction, updateActionStatus } = useIncidentStore();

  const isOverdue = action.status === "Overdue" ||
    (action.dueAt && new Date(action.dueAt) < new Date() && action.status !== "Done");

  return (
    <div className={`p-2 rounded border border-zinc-800 bg-zinc-900/50 border-l-2 ${
      priorityColor[action.status] ?? "border-l-zinc-500"
    } ${isOverdue ? "animate-pulse" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-zinc-200 flex-1 font-medium">{action.title}</span>
        {action.requiresConfirmation && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-900/50 text-orange-300 shrink-0">
            ⚠️ Confirm
          </span>
        )}
      </div>

      <div className="mt-1.5 flex items-center gap-2 text-[10px] text-zinc-500">
        {action.ownerName ? (
          <span>👤 {action.ownerName}</span>
        ) : (
          <span className="text-orange-400">⚠️ Unassigned</span>
        )}
        {action.toolKey && (
          <span className="px-1 py-0.5 bg-zinc-800 rounded">🔧 {action.toolKey}</span>
        )}
        {action.dueAt && (
          <span className={isOverdue ? "text-red-400" : ""}>
            ⏰ {new Date(action.dueAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      <div className="mt-2 flex items-center gap-1">
        {action.requiresConfirmation && (
          <button
            onClick={() => approveAction(action.id)}
            className="text-[10px] px-2 py-1 rounded bg-green-900/50 text-green-300 hover:bg-green-800/50"
          >
            ✓ Approve
          </button>
        )}
        {action.status === "Open" && (
          <button
            onClick={() => updateActionStatus(action.id, "InProgress")}
            className="text-[10px] px-2 py-1 rounded bg-blue-900/50 text-blue-300 hover:bg-blue-800/50"
          >
            → Start
          </button>
        )}
        {action.status === "InProgress" && (
          <button
            onClick={() => updateActionStatus(action.id, "Done")}
            className="text-[10px] px-2 py-1 rounded bg-green-900/50 text-green-300 hover:bg-green-800/50"
          >
            ✓ Done
          </button>
        )}
        {action.status === "Done" && (
          <span className="text-[10px] text-green-600">✓ Completed</span>
        )}
      </div>
    </div>
  );
}

export function ActionKanban({ snapshot }: { snapshot: Snapshot }) {
  const actions = snapshot?.actions ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Actions</h3>
        <span className="text-[10px] text-zinc-600">{actions.length} total</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <div className="grid grid-cols-3 gap-2 h-full">
          {statusColumns.map((col) => {
            const colActions = actions.filter((a) => a.status === col.key);
            return (
              <div key={col.key} className="flex flex-col">
                <div className={`text-xs font-medium text-zinc-400 px-2 py-1 border-b ${col.color} mb-1`}>
                  {col.label} ({colActions.length})
                </div>
                <div className="flex-1 space-y-1.5 overflow-y-auto">
                  {colActions.map((a) => <ActionCard key={a.id} action={a} />)}
                  {colActions.length === 0 && (
                    <div className="text-[10px] text-zinc-700 text-center py-2">No items</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
