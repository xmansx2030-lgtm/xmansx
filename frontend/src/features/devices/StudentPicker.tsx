import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, apiRequest } from "@/api/client";
import { Button } from "@/components/Button";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { studentLabel } from "@/utils/roles";

interface SearchResult {
  results: { id: number; full_name: string; national_id_masked?: string }[];
}

/** بحث طالب مصغر (بالاسم — النشطون فقط) لاختياره في المطابقة/الوصول اليدوي. */
export function StudentPicker({
  onSelect,
  onCancel,
  searchEndpoint = "/students/search/",
  showMaskedIdentifier = true,
}: {
  onSelect: (studentId: number, name: string) => void;
  onCancel?: () => void;
  searchEndpoint?: string;
  showMaskedIdentifier?: boolean;
}) {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [term, setTerm] = useState("");

  const searchQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-picker", searchEndpoint, term),
    queryFn: ({ signal }) =>
      apiRequest<SearchResult>(
        `${searchEndpoint}?search=${encodeURIComponent(term)}&page_size=25`,
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
          className="min-h-11 w-full rounded-xl border border-slate-300 bg-slate-50 px-3 text-sm outline-none transition focus:border-teal-500 focus:bg-white focus:ring-3 focus:ring-teal-100"
        />
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            إلغاء
          </Button>
        )}
      </div>
      {searchQuery.isFetching && term.trim().length >= 2 && (
        <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500" role="status">
          جارٍ البحث...
        </p>
      )}
      {searchQuery.isError && term.trim().length >= 2 && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" role="alert">
          <span>{searchQuery.error instanceof ApiError ? searchQuery.error.message : "تعذر البحث عن الطلاب."}</span>
          <button type="button" className="min-h-11 shrink-0 rounded-lg px-3 font-bold hover:bg-red-100" onClick={() => void searchQuery.refetch()}>
            إعادة المحاولة
          </button>
        </div>
      )}
      {searchQuery.isSuccess && term.trim().length >= 2 && (
        <ul className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white text-sm">
          {searchQuery.data.results.length === 0 && (
            <li className="p-3 text-slate-500">لا توجد نتائج مطابقة.</li>
          )}
          {searchQuery.data.results.map((student) => (
            <li key={student.id}>
              <button
                type="button"
                className="min-h-11 w-full p-2 text-start hover:bg-blue-50"
                onClick={() => onSelect(student.id, student.full_name)}
                data-testid={`pick-student-${student.id}`}
              >
                {student.full_name}{" "}
                {showMaskedIdentifier && student.national_id_masked && (
                  <span className="text-xs text-slate-400" dir="ltr">
                    {student.national_id_masked}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
