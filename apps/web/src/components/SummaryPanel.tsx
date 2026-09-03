import { useState } from "react";
import { useIncidentStore, type Snapshot } from "../store/incidentStore";
import { speakSummary, stopSpeaking } from "../lib/tts";
import { exportToPDF } from "../lib/pdf";

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
      <div className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2">
        <h3 className="text-sm font-semibold text-zinc-300">Summary</h3>
        <div className="flex-1" />
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="text-[10px] px-2 py-1 rounded bg-blue-900/50 text-blue-300 hover:bg-blue-800/50 disabled:opacity-50"
        >
          {loading ? "Generating..." : "Generate"}
        </button>
        <button
          onClick={handleTTS}
          className={`text-[10px] px-2 py-1 rounded ${
            speaking ? "bg-red-900/50 text-red-300" : "bg-green-900/50 text-green-300"
          } hover:opacity-80`}
        >
          {speaking ? "⏹ Stop" : "🔊 Speak"}
        </button>
        <button
          onClick={handlePDF}
          className="text-[10px] px-2 py-1 rounded bg-purple-900/50 text-purple-300 hover:bg-purple-800/50"
        >
          📄 PDF
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {displayMarkdown ? (
          <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
            {displayMarkdown}
          </pre>
        ) : (
          <div className="text-center text-zinc-600 text-xs py-8">
            Click "Generate" to create a summary
          </div>
        )}
      </div>
    </div>
  );
}
