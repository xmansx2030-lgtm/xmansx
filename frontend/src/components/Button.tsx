import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "header" | "headerGhost";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-blue-600 text-white shadow-sm shadow-teal-900/15 hover:-translate-y-0.5 hover:bg-blue-700 hover:shadow-md focus-visible:outline-blue-600 active:translate-y-0",
  secondary:
    "bg-white text-slate-700 border border-slate-300 shadow-sm hover:-translate-y-0.5 hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-slate-400 active:translate-y-0",
  danger:
    "bg-red-600 text-white shadow-sm shadow-red-900/10 hover:-translate-y-0.5 hover:bg-red-700 hover:shadow-md focus-visible:outline-red-600 active:translate-y-0",
  header:
    "border border-white bg-white text-slate-950 shadow-sm hover:-translate-y-0.5 hover:bg-slate-50 hover:shadow-md focus-visible:outline-white active:translate-y-0",
  headerGhost:
    "bg-white/10 text-white ring-1 ring-white/15 hover:-translate-y-0.5 hover:bg-white/15 focus-visible:outline-white active:translate-y-0",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      type={props.type ?? "button"}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-bold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${className}`}
      {...props}
    />
  );
}
