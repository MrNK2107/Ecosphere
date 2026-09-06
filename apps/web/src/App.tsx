import { useState, useEffect } from "react";
import { useIncidentStore, type Snapshot } from "./store/incidentStore";
import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { Overview } from "./components/Overview";
import { Transcript } from "./components/Transcript";
import { FactsPanel } from "./components/FactsPanel";
import { HypothesesPanel } from "./components/HypothesesPanel";
import { DecisionsPanel } from "./components/DecisionsPanel";
import { ActionKanban } from "./components/ActionKanban";
import { RisksPanel } from "./components/RisksPanel";
import { Timeline } from "./components/Timeline";
import { ToolEvents } from "./components/ToolEvents";
import { SummaryPanel } from "./components/SummaryPanel";
import type { Tab } from "./lib/nav";

export default function App() {
  const { snapshot, connect, disconnect } = useIncidentStore();
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  useEffect(() => {
    connect("payment-001");
    return () => disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const counts: Partial<Record<Tab, number>> = {
    conversation: snapshot?.transcript?.length ?? 0,
    decisions: snapshot?.decisions?.length ?? 0,
    actions: snapshot?.actions?.filter((a) => a.status !== "Done").length ?? 0,
    risks: (snapshot?.gaps?.length ?? 0) + (snapshot?.conflicts?.filter((c) => c.status === "OPEN" || c.status === "UNDER_REVIEW").length ?? 0),
    integrations: snapshot?.toolEvents?.length ?? 0,
  };

  return (
    <div className="h-screen flex bg-slate-50 text-slate-900">
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} counts={counts} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header snapshot={snapshot} />
        <div className="flex-1 overflow-hidden">
          {!snapshot ? (
            <div className="h-full flex items-center justify-center text-slate-400">
              <div className="text-center">
                <p className="text-base mb-1">Connecting to incident…</p>
                <p className="text-xs text-slate-300">Enter an incident ID above, or wait for the connection.</p>
              </div>
            </div>
          ) : (
            <MainPanel tab={activeTab} snapshot={snapshot} />
          )}
        </div>
      </div>
    </div>
  );
}

function MainPanel({ tab, snapshot }: { tab: Tab; snapshot: Snapshot }) {
  switch (tab) {
    case "overview":
      return <Overview snapshot={snapshot} />;
    case "conversation":
      return <Transcript snapshot={snapshot} />;
    case "evidence":
      return (
        <div className="h-full grid grid-cols-1 md:grid-cols-2 divide-x divide-slate-100">
          <FactsPanel snapshot={snapshot} />
          <HypothesesPanel snapshot={snapshot} />
        </div>
      );
    case "decisions":
      return <DecisionsPanel snapshot={snapshot} />;
    case "actions":
      return <ActionKanban snapshot={snapshot} />;
    case "risks":
      return <RisksPanel snapshot={snapshot} />;
    case "timeline":
      return <Timeline snapshot={snapshot} />;
    case "reports":
      return <SummaryPanel snapshot={snapshot} />;
    case "integrations":
      return <ToolEvents snapshot={snapshot} />;
    default:
      return null;
  }
}
