import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: LucideIcon;
  action?: ReactNode;
  testId?: string;
  compact?: boolean;
}

export function EmptyState({ title, description, icon: Icon = Inbox, action, testId, compact = false }: EmptyStateProps) {
  return (
    <div className={`rounded-2xl border border-dashed border-teal-200 bg-gradient-to-br from-[#f7fbfa] to-[#f1f7f5] text-center ${compact ? "p-5" : "p-6 sm:p-8"}`} data-testid={testId}>
      <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-white text-teal-700 shadow-sm ring-1 ring-teal-100">
        <Icon aria-hidden size={21} strokeWidth={1.8} />
      </span>
      <h3 className="mt-4 font-black text-slate-900">{title}</h3>
      <p className="mx-auto mt-1 max-w-xl text-sm leading-6 text-slate-600">{description}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
