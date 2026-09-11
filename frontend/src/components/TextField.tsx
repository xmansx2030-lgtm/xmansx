import { useId, type InputHTMLAttributes } from "react";

import { FieldShell } from "@/components/FormField";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  description?: string;
}

export function TextField({ label, error, description, className = "", id: idProp, required, ...props }: TextFieldProps) {
  const generatedId = useId();
  const id = idProp ?? generatedId;
  const describedBy = error ? `${id}-error` : description ? `${id}-description` : undefined;

  return (
    <FieldShell id={id} label={label} required={required} description={description} error={error} className={className}>
      <input
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`min-h-11 rounded-xl border bg-white px-3.5 py-2.5 text-sm outline-none transition-all focus:ring-2 ${
          error
            ? "border-red-400 focus:border-red-500 focus:ring-red-100"
            : "border-slate-300 focus:border-blue-500 focus:ring-blue-100"
        }`}
        {...props}
      />
    </FieldShell>
  );
}
