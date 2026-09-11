import type { ReactNode } from "react";

export function TableShell({ title, description, actions, children, className = "" }: { title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`ds-surface overflow-hidden ${className}`}>
      {(title || description || actions) && (
        <header className="flex flex-col justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
          <div className="min-w-0">
            {title && <h2 className="ds-section-title">{title}</h2>}
            {description && <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="overflow-x-auto overscroll-x-contain" tabIndex={0} role="region" aria-label={typeof title === "string" ? title : "جدول بيانات"}>
        {children}
      </div>
    </section>
  );
}
