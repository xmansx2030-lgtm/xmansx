import type { HTMLAttributes } from "react";

export function Skeleton({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={`ds-skeleton ${className}`} {...props} />;
}

export function PageSkeleton({ label = "جارٍ تحميل الصفحة" }: { label?: string }) {
  return (
    <div className="ds-page" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div className="ds-surface overflow-hidden p-5 sm:p-7">
        <div className="flex items-start gap-4">
          <Skeleton className="size-12 shrink-0 rounded-2xl" />
          <div className="flex-1 space-y-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-8 w-2/3 max-w-md" />
            <Skeleton className="h-4 w-full max-w-2xl" />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-28" />)}
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}
