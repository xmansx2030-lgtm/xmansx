import type { LucideIcon } from "lucide-react";

type MetricTone = "neutral" | "teal" | "blue" | "amber" | "red" | "violet";

const tones: Record<MetricTone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  teal: "bg-teal-50 text-teal-700",
  blue: "bg-blue-50 text-blue-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
  violet: "bg-violet-50 text-violet-700",
};

interface MetricCardProps {
  label: string;
  value: number | string;
  hint?: string;
  icon?: LucideIcon;
  tone?: MetricTone;
  testId?: string;
  valueFirst?: boolean;
}

export function MetricCard({ label, value, hint, icon: Icon, tone = "neutral", testId, valueFirst = false }: MetricCardProps) {
  return (
    <article className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md" data-testid={testId}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {valueFirst ? <><p className="text-2xl font-black tabular-nums text-slate-900 sm:text-3xl">{value}</p><p className="mt-1 text-xs font-bold leading-5 text-slate-500">{label}</p></> : <><p className="text-xs font-bold leading-5 text-slate-500">{label}</p><p className="mt-1 text-2xl font-black tabular-nums text-slate-900 sm:text-3xl">{value}</p></>}
        </div>
        {Icon && <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${tones[tone]}`}><Icon aria-hidden size={19} /></span>}
      </div>
      {hint && <p className="mt-2 text-xs leading-5 text-slate-500">{hint}</p>}
    </article>
  );
}
