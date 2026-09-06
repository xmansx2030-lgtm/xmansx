import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest } from "@/api/client";
import { Button } from "@/components/Button";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { studentLabel } from "@/utils/roles";

interface SearchResult {
  results: { id: number; full_name: string; national_id_masked: string }[];
}

/** بحث طالب مصغر (بالاسم — النشطون فقط) لاختياره في المطابقة/الوصول اليدوي. */
export function StudentPicker({
  onSelect,
  onCancel,
}: {
  onSelect: (studentId: number, name: string) => void;
  onCancel?: () => void;
}) {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [term, setTerm] = useState("");

  const searchQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-picker", term),
    queryFn: ({ signal }) =>
      apiRequest<SearchResult>(
        `/students/search/?search=${encodeURIComponent(term)}&page_size=25`,
        { signal },
      ),
    enabled: schoolId > 0 && term.trim().length >= 2,
  });

  return (
    <div className="flex flex-col gap-1" data-testid="student-picker">
      <div className="flex items-center gap-2">
        <input
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder={`ابحث باسم ${studentLabel(schoolType, true)}`}
          aria-label={`بحث عن ${studentLabel(schoolType)}`}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            إلغاء
          </Button>
        )}
      </div>
      {searchQuery.isSuccess && term.trim().length >= 2 && (
        <ul className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white text-sm">
          {searchQuery.data.results.length === 0 && (
            <li className="p-2 text-slate-500">لا نتائج.</li>
          )}
          {searchQuery.data.results.map((student) => (
            <li key={student.id}>
              <button
                type="button"
                className="w-full p-2 text-start hover:bg-blue-50"
                onClick={() => onSelect(student.id, student.full_name)}
                data-testid={`pick-student-${student.id}`}
              >
                {student.full_name}{" "}
                <span className="text-xs text-slate-400" dir="ltr">
                  {student.national_id_masked}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
