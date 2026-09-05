import type { SectionItem } from "@/features/students/api";
import { useId } from "react";

export function CounselorSectionPicker({
  sections,
  allSections,
  selectedIds,
  onAllSectionsChange,
  onSelectedIdsChange,
  disabled = false,
}: {
  sections: SectionItem[];
  allSections: boolean;
  selectedIds: number[];
  onAllSectionsChange: (value: boolean) => void;
  onSelectedIdsChange: (value: number[]) => void;
  disabled?: boolean;
}) {
  const modeName = useId();
  const grades = new Map<number, { name: string; sections: SectionItem[] }>();
  for (const section of sections) {
    const group = grades.get(section.grade.id) ?? {
      name: section.grade.name,
      sections: [],
    };
    group.sections.push(section);
    grades.set(section.grade.id, group);
  }

  function toggle(sectionId: number) {
    onSelectedIdsChange(
      selectedIds.includes(sectionId)
        ? selectedIds.filter((id) => id !== sectionId)
        : [...selectedIds, sectionId],
    );
  }

  return (
    <fieldset disabled={disabled} className="space-y-3" data-testid="counselor-section-picker">
      <legend className="text-sm font-black text-slate-900">الفصول المسؤول عنها</legend>
      <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm">
        <input
          type="radio"
          name={modeName}
          checked={allSections}
          onChange={() => onAllSectionsChange(true)}
          className="mt-0.5 size-4 accent-blue-600"
        />
        <span><strong className="block text-blue-900">جميع الفصول</strong><span className="text-xs text-blue-700">هو الاختيار الافتراضي عند عدم تحديد فصول بعينها.</span></span>
      </label>
      <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 p-3 text-sm">
        <input
          type="radio"
          name={modeName}
          checked={!allSections}
          onChange={() => onAllSectionsChange(false)}
          className="mt-0.5 size-4 accent-blue-600"
        />
        <span><strong className="block text-slate-900">فصول محددة</strong><span className="text-xs text-slate-500">اختر فصلًا واحدًا أو أكثر من القائمة.</span></span>
      </label>

      {!allSections && (
        <div className="max-h-64 space-y-3 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3">
          {[...grades.entries()].map(([gradeId, group]) => (
            <div key={gradeId}>
              <p className="mb-2 text-xs font-black text-slate-600">{group.name}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {group.sections.map((section) => (
                  <label key={section.id} className="flex cursor-pointer items-center gap-2 rounded-lg bg-white p-2 text-sm ring-1 ring-slate-200">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(section.id)}
                      onChange={() => toggle(section.id)}
                      className="size-4 accent-blue-600"
                    />
                    {section.grade.name} / {section.name}
                  </label>
                ))}
              </div>
            </div>
          ))}
          {sections.length === 0 && <p className="text-sm text-amber-800">لا توجد فصول نشطة في المدرسة.</p>}
        </div>
      )}
    </fieldset>
  );
}
