interface SpinnerProps {
  label?: string;
}

export function Spinner({ label = "جارٍ التحميل..." }: SpinnerProps) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-slate-500">
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600"
      />
      {label}
    </span>
  );
}
