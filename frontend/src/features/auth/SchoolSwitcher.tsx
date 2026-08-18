import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useMe, useSwitchSchool } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

/** «المدرسة الحالية ▼» — يعرض فقط مدارس العضويات الفعالة، والتبديل يفرغ الـ cache كاملًا. */
export function SchoolSwitcher() {
  const navigate = useNavigate();
  const me = useMe();
  const switchSchool = useSwitchSchool();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const switchMutation = useMutation({
    mutationFn: (schoolId: number) => switchSchool(schoolId),
    onSuccess: () => {
      setOpen(false);
      navigate("/", { replace: true });
    },
  });

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (!me.isSuccess || me.data.active_school === null) return null;

  const others = me.data.memberships.filter(
    (m) => m.school.id !== me.data.active_school?.id,
  );

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        {me.data.active_school.name}
        {others.length > 0 && <span aria-hidden>▼</span>}
      </button>

      {open && others.length > 0 && (
        <ul
          role="listbox"
          className="absolute start-0 z-10 mt-1 w-64 rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
        >
          {others.map((membership) => (
            <li key={membership.id}>
              <button
                type="button"
                disabled={switchMutation.isPending}
                onClick={() => switchMutation.mutate(membership.school.id)}
                className="flex w-full flex-col items-start px-4 py-2 text-start hover:bg-slate-50 disabled:opacity-50"
              >
                <span className="text-sm font-medium text-slate-800">
                  {membership.school.name}
                </span>
                <span className="text-xs text-slate-500">{roleLabels(membership.roles)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
