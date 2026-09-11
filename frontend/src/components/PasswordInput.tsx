import { useId, useState, type InputHTMLAttributes } from "react";

import { FieldShell } from "@/components/FormField";

interface PasswordInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  description?: string;
}

/** حقل كلمة مرور مع إظهار/إخفاء — بلا أي ميزات إضافية (لا استرجاع/OTP في هذه المرحلة). */
export function PasswordInput({ label, error, description, className = "", id: idProp, required, ...props }: PasswordInputProps) {
  const generatedId = useId();
  const id = idProp ?? generatedId;
  const describedBy = error ? `${id}-error` : description ? `${id}-description` : undefined;
  const [visible, setVisible] = useState(false);

  return (
    <FieldShell id={id} label={label} required={required} description={description} error={error} className={className}>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`min-h-11 w-full rounded-xl border bg-white px-3.5 py-2.5 pe-20 text-sm outline-none transition-all focus:ring-2 ${
            error
              ? "border-red-400 focus:border-red-500 focus:ring-red-100"
              : "border-slate-300 focus:border-blue-500 focus:ring-blue-100"
          }`}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute end-1.5 top-1/2 min-h-9 -translate-y-1/2 rounded-lg px-2.5 py-1 text-xs font-bold text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          aria-label={visible ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
        >
          {visible ? "إخفاء" : "إظهار"}
        </button>
      </div>
    </FieldShell>
  );
}
