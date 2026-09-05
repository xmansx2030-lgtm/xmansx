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
    <div className={`rounded-2xl border border-dashed border-slate-300 bg-gradient-to-b from-white to-slate-50 text-center ${compact ? "p-5" : "p-8"}`} data-testid={testId}>
      <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500 ring-1 ring-slate-200">
        <Icon aria-hidden size={22} />
      </span>
      <h3 className="mt-4 font-black text-slate-900">{title}</h3>
      <p className="mx-auto mt-1 max-w-xl text-sm leading-6 text-slate-500">{description}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
