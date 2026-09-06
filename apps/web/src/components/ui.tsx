import type { ReactNode } from "react";

export type Tone = "neutral" | "green" | "blue" | "amber" | "red" | "purple" | "indigo" | "orange";

const badgeTone: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-600",
  green: "bg-emerald-50 text-emerald-700",
  blue: "bg-blue-50 text-blue-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
  purple: "bg-violet-50 text-violet-700",
  indigo: "bg-indigo-50 text-indigo-700",
  orange: "bg-orange-50 text-orange-700",
};

const barTone: Record<Tone, string> = {
  neutral: "bg-slate-400",
  green: "bg-emerald-500",
  blue: "bg-blue-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  purple: "bg-violet-500",
  indigo: "bg-indigo-500",
  orange: "bg-orange-500",
};

const dotTone: Record<Tone, string> = {
  neutral: "bg-slate-400",
  green: "bg-emerald-500",
  blue: "bg-blue-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  purple: "bg-violet-500",
  indigo: "bg-indigo-500",
  orange: "bg-orange-500",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${badgeTone[tone]}`}>
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral", pulse = false }: { tone?: Tone; pulse?: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${dotTone[tone]} ${pulse ? "animate-pulse" : ""}`} />;
}

export function ProgressBar({ value, tone = "indigo" }: { value: number; tone?: Tone }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${barTone[tone]}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Card({
  title, right, children, className = "", padded = true,
}: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <div className={`bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col ${className}`}>
      {(title || right) && (
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
          {typeof title === "string" ? <h3 className="text-sm font-semibold text-slate-800">{title}</h3> : title}
          {right}
        </div>
      )}
      <div className={`flex-1 min-h-0 ${padded ? "p-4" : ""}`}>{children}</div>
    </div>
  );
}

export function StatTile({ label, value, sub, tone = "neutral" }: { label: string; value: ReactNode; sub?: string; tone?: Tone }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</span>
        <Dot tone={tone} />
      </div>
      <div className="mt-1.5 text-2xl font-bold text-slate-900">{value}</div>
      {sub && <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export function EmptyState({ icon = "—", children }: { icon?: string; children: ReactNode }) {
  return (
    <div className="text-center text-slate-400 text-xs py-8">
      <div className="text-xl mb-1 opacity-50">{icon}</div>
      {children}
    </div>
  );
}

export function Avatar({ name, size = 6 }: { name: string; size?: number }) {
  return (
    <div
      className="rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-semibold shrink-0"
      style={{ width: `${size * 4}px`, height: `${size * 4}px`, fontSize: `${size * 1.5}px` }}
    >
      {name?.[0]?.toUpperCase() ?? "?"}
    </div>
  );
}
