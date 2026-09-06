export type Tab = "overview" | "conversation" | "evidence" | "decisions" | "actions" | "risks" | "timeline" | "reports" | "integrations";

export const NAV_ITEMS: { key: Tab; label: string; icon: string }[] = [
  { key: "overview", label: "Overview", icon: "🏠" },
  { key: "conversation", label: "Live Conversation", icon: "💬" },
  { key: "evidence", label: "Facts & Hypotheses", icon: "🔍" },
  { key: "decisions", label: "Decisions", icon: "⚖️" },
  { key: "actions", label: "Action Items", icon: "📋" },
  { key: "risks", label: "Risks", icon: "⚠️" },
  { key: "timeline", label: "Timeline", icon: "📜" },
  { key: "reports", label: "Reports", icon: "📝" },
  { key: "integrations", label: "Integrations", icon: "🔧" },
];
