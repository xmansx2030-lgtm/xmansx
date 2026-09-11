import type { ReactNode } from "react";

export function Tooltip({ content, children, side = "bottom" }: { content: string; children: ReactNode; side?: "top" | "bottom" }) {
  return (
    <span className="group/tooltip relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={`pointer-events-none absolute start-1/2 z-50 hidden -translate-x-1/2 whitespace-nowrap rounded-lg bg-slate-950 px-2.5 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100 sm:block ${side === "top" ? "bottom-full mb-2" : "top-full mt-2"}`}
      >
        {content}
      </span>
    </span>
  );
}
