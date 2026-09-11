import { useId, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldShellProps {
  id: string;
  label: string;
  required?: boolean;
  description?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}

export function FieldShell({ id, label, required, description, error, children, className = "" }: FieldShellProps) {
  return (
    <div className={`flex flex-col min-w-0 gap-1.5 ${className}`}>
      <label
        htmlFor={id}
        className={`text-sm font-bold text-slate-700 ${required ? "after:ms-1 after:text-red-600 after:content-['*']" : ""}`}
      >
        {label}
      </label>
      {children}
      {description && !error && <p id={`${id}-description`} className="text-xs leading-5 text-slate-500">{description}</p>}
      {error && <p id={`${id}-error`} role="alert" className="text-xs font-medium leading-5 text-red-700">{error}</p>}
    </div>
  );
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  description?: string;
  error?: string;
  children: ReactNode;
}

export function SelectField({ label, description, error, children, className = "", id: idProp, required, ...props }: SelectFieldProps) {
  const generatedId = useId();
  const id = idProp ?? generatedId;
  const describedBy = error ? `${id}-error` : description ? `${id}-description` : undefined;
  return (
    <FieldShell id={id} label={label} description={description} error={error} required={required} className={className}>
      <select id={id} required={required} aria-invalid={error ? true : undefined} aria-describedby={describedBy} className="w-full min-w-0 border px-3.5 py-2.5 text-sm" {...props}>
        {children}
      </select>
    </FieldShell>
  );
}

interface TextareaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  description?: string;
  error?: string;
}

export function TextareaField({ label, description, error, className = "", id: idProp, required, ...props }: TextareaFieldProps) {
  const generatedId = useId();
  const id = idProp ?? generatedId;
  const describedBy = error ? `${id}-error` : description ? `${id}-description` : undefined;
  return (
    <FieldShell id={id} label={label} description={description} error={error} required={required} className={className}>
      <textarea id={id} required={required} aria-invalid={error ? true : undefined} aria-describedby={describedBy} className="min-h-28 w-full min-w-0 resize-y border px-3.5 py-2.5 text-sm leading-6" {...props} />
    </FieldShell>
  );
}
