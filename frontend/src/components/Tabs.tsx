import type { KeyboardEvent, ReactNode } from "react";

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  badge?: ReactNode;
  disabled?: boolean;
}

interface TabsProps<T extends string> {
  value: T;
  items: readonly TabItem<T>[];
  onChange: (value: T) => void;
  label: string;
  className?: string;
}

export function Tabs<T extends string>({ value, items, onChange, label, className = "" }: TabsProps<T>) {
  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const enabled = items.map((item, itemIndex) => ({ item, itemIndex })).filter(({ item }) => !item.disabled);
    const current = enabled.findIndex(({ itemIndex }) => itemIndex === index);
    let next: number;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = enabled.length - 1;
    else if (event.key === "ArrowLeft") next = (current + 1) % enabled.length;
    else if (event.key === "ArrowRight") next = (current - 1 + enabled.length) % enabled.length;
    else return;

    event.preventDefault();
    const target = enabled[next];
    if (!target) return;
    onChange(target.item.value);
    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("[role='tab']")[target.itemIndex]?.focus();
  };

  return (
    <div className={`flex gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1 shadow-sm ${className}`} role="tablist" aria-label={label}>
      {items.map((item, index) => {
        const selected = value === item.value;
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            onKeyDown={(event) => move(event, index)}
            onClick={() => onChange(item.value)}
            className={`min-h-11 shrink-0 rounded-xl px-4 text-sm font-bold transition ${selected ? "bg-slate-950 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"}`}
          >
            {item.label}
            {item.badge && <span className="ms-2 rounded-full bg-current/10 px-2 py-0.5 text-[11px]">{item.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
