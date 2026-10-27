import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type PageHeaderTone = "executive" | "teacher" | "counselor" | "operational";

const toneClasses: Record<PageHeaderTone, { shell: string; glow: string; accent: string }> = {
  executive: {
    shell: "from-[#102d2a] via-[#123c38] to-[#15584f]",
    glow: "bg-teal-300/20",
    accent: "text-teal-100",
  },
  teacher: {
    shell: "from-[#123b37] via-[#15554e] to-[#1c6659]",
    glow: "bg-emerald-300/20",
    accent: "text-emerald-100",
  },
  counselor: {
    shell: "from-[#153a38] via-[#164b48] to-[#176257]",
    glow: "bg-cyan-300/20",
    accent: "text-cyan-100",
  },
  operational: {
    shell: "from-[#102d2a] via-[#123c38] to-[#15584f]",
    glow: "bg-teal-300/20",
    accent: "text-teal-100",
  },
};

interface PageHeaderProps {
  icon: LucideIcon;
  eyebrow: string;
  title: ReactNode;
  description: ReactNode;
  tone?: PageHeaderTone;
  badge?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  testId?: string;
}

/** رأس موحد لكل مساحات العمل؛ يوضح الدور والمهمة قبل الأرقام والإجراءات. */
export function PageHeader({
  icon: Icon,
  eyebrow,
  title,
  description,
  tone = "operational",
  badge,
  meta,
  actions,
  children,
  testId,
}: PageHeaderProps) {
  const colors = toneClasses[tone];
  return (
    <header
      className={`relative isolate overflow-hidden rounded-[1.35rem] border border-white/10 bg-gradient-to-l ${colors.shell} px-4 py-5 text-white shadow-[0_16px_38px_-24px_rgba(7,27,25,.5)] sm:px-7 sm:py-7`}
      data-testid={testId}
    >
      <div aria-hidden className={`absolute -start-20 -top-24 -z-10 size-64 rounded-full ${colors.glow} blur-3xl`} />
      <div aria-hidden className="absolute -bottom-28 end-1/3 -z-10 size-52 rounded-full bg-white/5 blur-3xl" />
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
        <div className="flex min-w-0 items-start gap-4">
          <span className={`grid size-11 shrink-0 place-items-center rounded-2xl bg-white/10 ${colors.accent} ring-1 ring-white/15 sm:size-12`}>
            <Icon aria-hidden size={24} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className={`text-xs font-bold ${colors.accent}`}>{eyebrow}</p>
              {badge && <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-bold text-slate-100 ring-1 ring-white/10">{badge}</span>}
            </div>
            <h1 className="mt-2 text-[1.55rem] font-bold leading-[1.4] tracking-tight text-white sm:text-3xl">{title}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/75">{description}</p>
            {meta && <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">{meta}</div>}
          </div>
        </div>
        {actions && <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto lg:shrink-0">{actions}</div>}
      </div>
      {children && <div className="mt-5 border-t border-white/10 pt-4">{children}</div>}
    </header>
  );
}
