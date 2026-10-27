import type { HTMLAttributes, ReactNode } from "react";

type BadgeTone = "neutral" | "brand" | "info" | "success" | "warning" | "danger" | "violet";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  brand: "bg-brand-50 text-brand-800 ring-brand-200",
  info: "bg-blue-50 text-blue-800 ring-blue-200",
  success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  warning: "bg-amber-50 text-amber-900 ring-amber-200",
  danger: "bg-red-50 text-red-800 ring-red-200",
  violet: "bg-violet-50 text-violet-800 ring-violet-200",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  children: ReactNode;
  dot?: boolean;
}

export function Badge({ tone = "neutral", dot = false, className = "", children, ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex min-h-6 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold leading-none ring-1 ring-inset ${tones[tone]} ${className}`}
      {...props}
    >
      {dot && <span aria-hidden className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}
