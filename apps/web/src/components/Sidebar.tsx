import type { Tab } from "../lib/nav";
import { NAV_ITEMS } from "../lib/nav";

export function Sidebar({
  activeTab, onTabChange, counts,
}: { activeTab: Tab; onTabChange: (t: Tab) => void; counts: Partial<Record<Tab, number>> }) {
  return (
    <div className="w-56 bg-white border-r border-slate-200 flex flex-col shrink-0">
      <div className="px-4 py-4 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm">E</div>
          <div>
            <h1 className="text-sm font-bold text-slate-900">EchoSphere</h1>
            <p className="text-[10px] text-slate-400">AI Incident Commander</p>
          </div>
        </div>
      </div>
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
              activeTab === t.key
                ? "bg-indigo-50 text-indigo-700 font-medium"
                : "text-slate-500 hover:bg-slate-50 hover:text-slate-700"
            }`}
          >
            <span className="text-base leading-none">{t.icon}</span>
            <span className="flex-1">{t.label}</span>
            {counts[t.key] != null && counts[t.key]! > 0 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                activeTab === t.key ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-500"
              }`}>
                {counts[t.key]}
              </span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
}
