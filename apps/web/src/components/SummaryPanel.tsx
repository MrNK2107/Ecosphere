import { useState } from "react";
import { useIncidentStore, type Snapshot } from "../store/incidentStore";
import { speakSummary, stopSpeaking } from "../lib/tts";
import { exportToPDF } from "../lib/pdf";
import { EmptyState } from "./ui";

export function SummaryPanel({ snapshot }: { snapshot: Snapshot }) {
  const { generateSummary, speaking, setSpeaking } = useIncidentStore();
  const [markdown, setMarkdown] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    const md = await generateSummary();
    setMarkdown(md);
    setLoading(false);
  };

  const handleTTS = async () => {
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
      return;
    }
    const text = markdown || snapshot?.incident?.summaryMarkdown || "";
    if (!text) return;
    setSpeaking(true);
    try {
      await speakSummary(snapshot.incident.id);
    } finally {
      setSpeaking(false);
    }
  };

  const handlePDF = async () => {
    const text = markdown || snapshot?.incident?.summaryMarkdown || "";
    if (!text) return;
    await exportToPDF(text, snapshot.incident.id);
  };

  const displayMarkdown = markdown || snapshot?.incident?.summaryMarkdown || "";

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2 shrink-0">
        <h3 className="text-sm font-semibold text-slate-800">Postmortem Report</h3>
        <div className="flex-1" />
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="text-[11px] px-2.5 py-1.5 rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 font-medium"
        >
          {loading ? "Generating…" : "Generate"}
        </button>
        <button
          onClick={handleTTS}
          className={`text-[11px] px-2.5 py-1.5 rounded-md font-medium ${
            speaking ? "bg-red-50 text-red-700 hover:bg-red-100" : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
          }`}
        >
          {speaking ? "⏹ Stop" : "🔊 Speak"}
        </button>
        <button
          onClick={handlePDF}
          className="text-[11px] px-2.5 py-1.5 rounded-md bg-violet-50 text-violet-700 hover:bg-violet-100 font-medium"
        >
          📄 Export PDF
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">
        {displayMarkdown ? (
          <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{displayMarkdown}</pre>
        ) : (
          <EmptyState icon="📝">Click "Generate" to draft a report from the incident so far</EmptyState>
        )}
      </div>
    </div>
  );
}
