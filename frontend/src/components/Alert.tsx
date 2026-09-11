import { AlertCircle, CheckCircle2, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type AlertTone = "info" | "success" | "warning" | "danger";

const styles: Record<AlertTone, { shell: string; icon: string; Icon: LucideIcon }> = {
  info: { shell: "border-blue-200 bg-blue-50/80 text-blue-950", icon: "bg-white text-blue-700", Icon: Info },
  success: { shell: "border-emerald-200 bg-emerald-50/80 text-emerald-950", icon: "bg-white text-emerald-700", Icon: CheckCircle2 },
  warning: { shell: "border-amber-200 bg-amber-50/80 text-amber-950", icon: "bg-white text-amber-700", Icon: TriangleAlert },
  danger: { shell: "border-red-200 bg-red-50/80 text-red-950", icon: "bg-white text-red-700", Icon: AlertCircle },
};

interface AlertProps {
  tone?: AlertTone;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  live?: boolean;
  className?: string;
}

export function Alert({ tone = "info", title, children, actions, live = false, className = "" }: AlertProps) {
  const style = styles[tone];
  const Icon = style.Icon;
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      aria-live={live ? "polite" : undefined}
      className={`flex items-start gap-3 rounded-2xl border p-4 text-sm ${style.shell} ${className}`}
    >
      <span className={`grid size-10 shrink-0 place-items-center rounded-xl shadow-sm ring-1 ring-black/5 ${style.icon}`}>
        <Icon aria-hidden size={19} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-bold">{title}</p>
        {children && <div className="mt-1 leading-6 opacity-85">{children}</div>}
        {actions && <div className="mt-3 flex flex-wrap gap-2">{actions}</div>}
      </div>
    </div>
  );
}
