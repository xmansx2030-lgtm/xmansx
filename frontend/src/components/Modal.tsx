import { X } from "lucide-react";
import { useId, type ReactNode } from "react";

import { IconButton } from "@/components/IconButton";
import { useDialogA11y } from "@/hooks/useDialogA11y";

export function Modal({
  title,
  description,
  children,
  onClose,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const dialogRef = useDialogA11y<HTMLElement>(true, onClose);
  const titleId = useId();
  const descriptionId = useId();

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/55 p-2 backdrop-blur-sm sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className="ds-surface-elevated my-auto flex max-h-[calc(100dvh-1rem)] w-full max-w-2xl flex-col overflow-hidden sm:max-h-[calc(100dvh-2rem)]"
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-4 py-4 sm:px-6">
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-black text-slate-900">{title}</h2>
            {description && <p id={descriptionId} className="mt-1 text-sm leading-6 text-slate-500">{description}</p>}
          </div>
          <IconButton type="button" label="إغلاق" variant="ghost" onClick={onClose}>
            <X aria-hidden size={19} />
          </IconButton>
        </header>
        <div className="min-h-0 overflow-y-auto p-4 sm:p-6">{children}</div>
      </section>
    </div>
  );
}
