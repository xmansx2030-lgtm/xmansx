import { useMemo } from "react";

import type { SectionItem } from "@/features/students/api";

export function VicePrincipalScopePicker({
  sections,
  selectedGradeIds,
  selectedSectionIds,
  onSelectedGradeIdsChange,
  onSelectedSectionIdsChange,
  disabled = false,
}: {
  sections: SectionItem[];
  selectedGradeIds: number[];
  selectedSectionIds: number[];
  onSelectedGradeIdsChange: (value: number[]) => void;
  onSelectedSectionIdsChange: (value: number[]) => void;
  disabled?: boolean;
}) {
  const grades = useMemo(() => {
    const grouped = new Map<number, { name: string; sections: SectionItem[] }>();
    for (const section of sections) {
      const current = grouped.get(section.grade.id) ?? {
        name: section.grade.name,
        sections: [],
      };
      current.sections.push(section);
      grouped.set(section.grade.id, current);
    }
    return [...grouped.entries()];
  }, [sections]);

  function toggleGrade(gradeId: number) {
    if (selectedGradeIds.includes(gradeId)) {
      onSelectedGradeIdsChange(selectedGradeIds.filter((id) => id !== gradeId));
      return;
    }
    onSelectedGradeIdsChange([...selectedGradeIds, gradeId]);
    const childIds = new Set(
      sections.filter((item) => item.grade.id === gradeId).map((item) => item.id),
    );
    onSelectedSectionIdsChange(selectedSectionIds.filter((id) => !childIds.has(id)));
  }

  function toggleSection(sectionId: number) {
    onSelectedSectionIdsChange(
      selectedSectionIds.includes(sectionId)
        ? selectedSectionIds.filter((id) => id !== sectionId)
        : [...selectedSectionIds, sectionId],
    );
  }

  return (
    <fieldset disabled={disabled} className="space-y-3" data-testid="vice-principal-scope-picker">
      <legend className="text-sm font-black text-slate-900">نطاق الطلاب المسؤول عنهم</legend>
      <p className="text-xs leading-5 text-slate-600">
        اختر صفًا كاملًا أو فصولًا محددة. إحالات المعلمين ستصل تلقائيًا إلى هذا الوكيل،
        ولن يراها المرشد حتى يحولها الوكيل إليه.
      </p>
      <div className="max-h-80 space-y-3 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-3">
        {grades.map(([gradeId, group]) => {
          const wholeGrade = selectedGradeIds.includes(gradeId);
          return (
            <section key={gradeId} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <label className={`flex cursor-pointer items-center gap-3 p-3 text-sm font-black ${wholeGrade ? "bg-violet-50 text-violet-900" : "text-slate-900"}`}>
                <input
                  type="checkbox"
                  checked={wholeGrade}
                  onChange={() => toggleGrade(gradeId)}
                  className="size-4 accent-violet-600"
                />
                جميع طلاب {group.name}
              </label>
              <div className="grid gap-2 border-t border-slate-100 p-3 sm:grid-cols-2">
                {group.sections.map((section) => (
                  <label key={section.id} className={`flex items-center gap-2 rounded-lg p-2 text-sm ring-1 ${wholeGrade ? "cursor-not-allowed bg-slate-50 text-slate-400 ring-slate-100" : "cursor-pointer bg-white text-slate-700 ring-slate-200"}`}>
                    <input
                      type="checkbox"
                      checked={wholeGrade || selectedSectionIds.includes(section.id)}
                      disabled={wholeGrade}
                      onChange={() => toggleSection(section.id)}
                      className="size-4 accent-violet-600"
                    />
                    {group.name} / {section.name}
                  </label>
                ))}
              </div>
            </section>
          );
        })}
        {grades.length === 0 && (
          <p className="p-3 text-center text-sm text-amber-800">لا توجد صفوف وفصول نشطة.</p>
        )}
      </div>
      {selectedGradeIds.length === 0 && selectedSectionIds.length === 0 && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-bold text-amber-900">
          لم يُحدد نطاق بعد؛ لن تُوجّه إحالات جديدة إلى هذا الوكيل حتى تحفظ نطاقًا.
        </p>
      )}
    </fieldset>
  );
}
