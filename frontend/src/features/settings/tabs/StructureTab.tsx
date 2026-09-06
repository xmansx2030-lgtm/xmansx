import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  createGrade,
  createSection,
  getGrades,
  getSections,
} from "@/features/students/api";

export function StructureTab({ canWrite }: { canWrite: boolean }) {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [grade, setGrade] = useState({ name: "", code: "", sequence: 1 });
  const [section, setSection] = useState({ grade_id: "", name: "", code: "" });
  const gradesKey = schoolScopedKey(schoolId, "grades");
  const sectionsKey = schoolScopedKey(schoolId, "sections");
  const grades = useQuery({ queryKey: gradesKey, queryFn: ({ signal }) => getGrades(signal) });
  const sections = useQuery({ queryKey: sectionsKey, queryFn: ({ signal }) => getSections(signal) });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: gradesKey }),
      queryClient.invalidateQueries({ queryKey: sectionsKey }),
    ]);
  };
  const gradeMutation = useMutation({
    mutationFn: () => createGrade({ ...grade, name: grade.name.trim(), code: grade.code.trim() }),
    onSuccess: async (created) => {
      setGrade((current) => ({
        name: "",
        code: "",
        sequence: Number.isFinite(created.sequence) ? created.sequence + 1 : current.sequence + 1,
      }));
      setSection((value) => ({ ...value, grade_id: String(created.id) }));
      await refresh();
    },
  });
  const sectionMutation = useMutation({
    mutationFn: () => createSection({ ...section, grade_id: Number(section.grade_id), name: section.name.trim(), code: section.code.trim() }),
    onSuccess: async () => {
      setSection((value) => ({ ...value, name: "", code: "" }));
      await refresh();
    },
  });

  if (grades.isPending || sections.isPending) return <Spinner />;
  if (grades.isError) return <ErrorState error={grades.error} />;
  if (sections.isError) return <ErrorState error={sections.error} />;

  return (
    <div className="space-y-5">
      <p className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
        أنشئ الصف أولًا ثم أضف فصوله. ستظهر هذه الخيارات مباشرة في إضافة الطلاب والاستيراد والتحضير.
      </p>
      {canWrite && (
        <div className="grid gap-4 lg:grid-cols-2">
          <form className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" onSubmit={(event) => { event.preventDefault(); gradeMutation.mutate(); }}>
            <h3 className="font-bold">إضافة صف</h3>
            <input aria-label="اسم الصف" required placeholder="مثال: الأول الثانوي" value={grade.name} onChange={(event) => setGrade({ ...grade, name: event.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2" />
            <div className="grid grid-cols-2 gap-2">
              <input aria-label="رمز الصف" required placeholder="مثال: SEC-1" value={grade.code} onChange={(event) => setGrade({ ...grade, code: event.target.value })} className="rounded-lg border border-slate-300 px-3 py-2" />
              <input aria-label="ترتيب الصف" required type="number" min="0" value={grade.sequence} onChange={(event) => setGrade({ ...grade, sequence: Number(event.target.value) })} className="rounded-lg border border-slate-300 px-3 py-2" />
            </div>
            <Button type="submit" disabled={gradeMutation.isPending}>حفظ الصف</Button>
            {gradeMutation.isError && <ErrorState error={gradeMutation.error} />}
          </form>
          <form className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" onSubmit={(event) => { event.preventDefault(); sectionMutation.mutate(); }}>
            <h3 className="font-bold">إضافة فصل</h3>
            <select aria-label="الصف التابع له الفصل" required value={section.grade_id} onChange={(event) => setSection({ ...section, grade_id: event.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2">
              <option value="">اختر الصف</option>
              {grades.data.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <input aria-label="اسم الفصل" required placeholder="مثال: 1 أو أ" value={section.name} onChange={(event) => setSection({ ...section, name: event.target.value })} className="rounded-lg border border-slate-300 px-3 py-2" />
              <input aria-label="رمز الفصل" required placeholder="مثال: A" value={section.code} onChange={(event) => setSection({ ...section, code: event.target.value })} className="rounded-lg border border-slate-300 px-3 py-2" />
            </div>
            <Button type="submit" disabled={sectionMutation.isPending || grades.data.length === 0}>حفظ الفصل</Button>
            {sectionMutation.isError && <ErrorState error={sectionMutation.error} />}
          </form>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {grades.data.map((item) => (
          <section key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="font-bold text-slate-900">{item.name}</h3>
            <p className="text-xs text-slate-500">الرمز: {item.code} · الترتيب: {item.sequence}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {sections.data.filter((row) => row.grade.id === item.id).map((row) => <span key={row.id} className="rounded-full bg-slate-100 px-3 py-1 text-sm">فصل {row.name}</span>)}
              {!sections.data.some((row) => row.grade.id === item.id) && <span className="text-sm text-slate-500">لا توجد فصول بعد.</span>}
            </div>
          </section>
        ))}
        {grades.data.length === 0 && <p className="text-slate-500">لا توجد صفوف بعد.</p>}
      </div>
    </div>
  );
}
