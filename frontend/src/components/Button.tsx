import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "header" | "headerGhost";
type Size = "sm" | "md" | "lg" | "icon";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-blue-600 text-white shadow-sm shadow-teal-900/15 hover:-translate-y-0.5 hover:bg-blue-700 hover:shadow-md focus-visible:outline-blue-600 active:translate-y-0",
  secondary:
    "bg-white text-slate-700 border border-slate-300 shadow-sm hover:-translate-y-0.5 hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-slate-400 active:translate-y-0",
  ghost:
    "bg-transparent text-slate-700 hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-slate-400 active:bg-slate-200/70",
  danger:
    "bg-red-600 text-white shadow-sm shadow-red-900/10 hover:-translate-y-0.5 hover:bg-red-700 hover:shadow-md focus-visible:outline-red-600 active:translate-y-0",
  header:
    "border border-white bg-white text-slate-950 shadow-sm hover:-translate-y-0.5 hover:bg-slate-50 hover:shadow-md focus-visible:outline-white active:translate-y-0",
  headerGhost:
    "bg-white/10 text-white ring-1 ring-white/15 hover:-translate-y-0.5 hover:bg-white/15 focus-visible:outline-white active:translate-y-0",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  loadingLabel?: string;
  fullWidth?: boolean;
}

const sizeClasses: Record<Size, string> = {
  sm: "min-h-9 rounded-lg px-3 py-1.5 text-xs",
  md: "min-h-11 rounded-xl px-4 py-2 text-sm",
  lg: "min-h-12 rounded-xl px-5 py-2.5 text-base",
  icon: "size-11 shrink-0 rounded-xl p-0",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  loadingLabel = "جارٍ التنفيذ...",
  fullWidth = false,
  className = "",
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      type={props.type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 font-bold transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-55 ${sizeClasses[size]} ${variantClasses[variant]} ${fullWidth ? "w-full" : ""} ${className}`}
      {...props}
    >
      {loading && <LoaderCircle aria-hidden className="animate-spin" size={size === "sm" ? 14 : 17} />}
      {loading ? loadingLabel : children}
    </button>
  );
}
