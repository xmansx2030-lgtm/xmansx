interface SpinnerProps {
  label?: string;
}

export function Spinner({ label = "جارٍ التحميل..." }: SpinnerProps) {
  return (
    <span role="status" aria-live="polite" className="inline-flex min-h-11 items-center gap-2.5 text-sm font-medium text-slate-600">
      <span
        aria-hidden
        className="size-[18px] animate-spin rounded-full border-2 border-teal-100 border-t-teal-700"
      />
      {label}
    </span>
  );
}
