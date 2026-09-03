import { useState, useCallback, useEffect } from "react";
import { useIncidentStore, type Snapshot } from "./store/incidentStore";
import { VoiceRoom } from "./components/VoiceRoom";
import { Transcript } from "./components/Transcript";
import { FactsPanel } from "./components/FactsPanel";
import { HypothesesPanel } from "./components/HypothesesPanel";
import { DecisionsPanel } from "./components/DecisionsPanel";
import { ActionKanban } from "./components/ActionKanban";
import { GapsPanel } from "./components/GapsPanel";
import { Timeline } from "./components/Timeline";
import { ToolEvents } from "./components/ToolEvents";
import { SummaryPanel } from "./components/SummaryPanel";

type Tab = "transcript" | "facts" | "hypotheses" | "decisions" | "gaps" | "timeline" | "tools" | "summary";

const tabs: { key: Tab; label: string; icon: string }[] = [
  { key: "transcript", label: "Transcript", icon: "💬" },
  { key: "facts", label: "Facts", icon: "✅" },
  { key: "hypotheses", label: "Hypotheses", icon: "❓" },
  { key: "decisions", label: "Decisions", icon: "⚖️" },
  { key: "gaps", label: "Gaps", icon: "⚠️" },
  { key: "timeline", label: "Timeline", icon: "📜" },
  { key: "tools", label: "Tools", icon: "🔧" },
  { key: "summary", label: "Summary", icon: "📝" },
];

function Sidebar({ activeTab, onTabChange, counts }: {
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
  counts: Record<string, number>;
}) {
  return (
    <div className="w-48 bg-zinc-950 border-r border-zinc-800 flex flex-col">
      <div className="p-3 border-b border-zinc-800">
        <h1 className="text-sm font-bold text-zinc-200">🔴 Agora</h1>
        <p className="text-[10px] text-zinc-600">Incident Commander</p>
      </div>
      <nav className="flex-1 p-2 space-y-0.5">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left transition-colors ${
              activeTab === t.key
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-300"
            }`}
          >
            <span>{t.icon}</span>
            <span className="flex-1">{t.label}</span>
            {counts[t.key] != null && counts[t.key] > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">
                {counts[t.key]}
              </span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
}

function MainPanel({ tab, snapshot }: { tab: Tab; snapshot: Snapshot | null }) {
  if (!snapshot) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-600">
        <div className="text-center">
          <p className="text-lg mb-2">Connecting to incident...</p>
          <p className="text-xs text-zinc-700">
            Enter an incident ID to start, or wait for WebSocket connection.
          </p>
        </div>
      </div>
    );
  }

  switch (tab) {
    case "transcript": return <Transcript snapshot={snapshot} />;
    case "facts": return <FactsPanel snapshot={snapshot} />;
    case "hypotheses": return <HypothesesPanel snapshot={snapshot} />;
    case "decisions": return <DecisionsPanel snapshot={snapshot} />;
    case "gaps": return <GapsPanel snapshot={snapshot} />;
    case "timeline": return <Timeline snapshot={snapshot} />;
    case "tools": return <ToolEvents snapshot={snapshot} />;
    case "summary": return <SummaryPanel snapshot={snapshot} />;
    default: return null;
  }
}

export default function App() {
  const { snapshot, connect, disconnect, incidentId } = useIncidentStore();
  const [activeTab, setActiveTab] = useState<Tab>("transcript");
  const [inputId, setInputId] = useState("payment-001");

  // Auto-connect on mount
  useEffect(() => {
    connect(inputId);
    return () => disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleConnect = useCallback(() => {
    if (inputId.trim()) {
      connect(inputId.trim());
    }
  }, [inputId, connect]);

  const counts: Record<string, number> = {
    transcript: snapshot?.transcript?.length ?? 0,
    facts: snapshot?.facts?.length ?? 0,
    hypotheses: snapshot?.hypotheses?.length ?? 0,
    decisions: snapshot?.decisions?.length ?? 0,
    gaps: snapshot?.gaps?.length ?? 0,
    timeline: snapshot?.timeline?.length ?? 0,
    tools: snapshot?.toolEvents?.length ?? 0,
  };

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      {/* Top bar: Voice Room */}
      <VoiceRoom snapshot={snapshot!} />

      {/* Incident selector bar */}
      <div className="flex items-center gap-2 px-4 py-1.5 bg-zinc-900/50 border-b border-zinc-800">
        <span className="text-[10px] text-zinc-500">Incident:</span>
        <input
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleConnect()}
          className="text-xs px-2 py-1 bg-zinc-800 border border-zinc-700 rounded w-48 focus:outline-none focus:border-zinc-500"
          placeholder="e.g. payment-001"
        />
        <button
          onClick={handleConnect}
          className="text-[10px] px-2 py-1 rounded bg-blue-900/50 text-blue-300 hover:bg-blue-800/50"
        >
          Connect
        </button>
        {snapshot?.incident && (
          <span className="text-[10px] text-zinc-500 ml-2">
            {snapshot.incident.title}
          </span>
        )}
      </div>

      {/* Main content: Sidebar + Panel */}
      <div className="flex-1 flex overflow-hidden">
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} counts={counts} />
        <div className="flex-1 flex flex-col overflow-hidden">
          <MainPanel tab={activeTab} snapshot={snapshot} />
        </div>
      </div>
    </div>
  );
}
