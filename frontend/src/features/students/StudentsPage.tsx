import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Filter, Pencil, Plus, Upload, UsersRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  bulkSetStatus,
  getGrades,
  getSections,
  getStudents,
  type StudentRow,
} from "@/features/students/api";
import { ManualStudentForm } from "@/features/students/ManualStudentForm";
import { StudentEditForm } from "@/features/students/StudentEditForm";
import { roleLabel, studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "منتظم",
  INACTIVE: "غير نشط",
  TRANSFERRED: "منقول",
  GRADUATED: "متخرج",
  ARCHIVED: "مؤرشف",
};

const READ_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];

export function StudentsPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const student = studentLabel(schoolType, true);
  const studentsLabel = studentPluralLabel(schoolType);
  const canImport = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const canRead = me.data?.roles.some((r) => READ_ROLES.includes(r)) ?? true;

  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [nationalId, setNationalId] = useState("");
  const [gradeFilter, setGradeFilter] = useState<number | "">("");
  const [sectionFilter, setSectionFilter] = useState<number | "">("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [editingStudent, setEditingStudent] = useState<StudentRow | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const graduateMutation = useMutation({
    mutationFn: (ids: number[]) => bulkSetStatus(ids, "GRADUATED"),
    onSuccess: () => {
      setBulkError(null);
      setSelected(new Set());
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "students"),
      });
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "inactive-students"),
      });
    },
    onError: (e) =>
      setBulkError(e instanceof ApiError ? e.message : "تعذر تنفيذ التخريج."),
  });

  const grades = useQuery({
    queryKey: schoolScopedKey(schoolId, "grades"),
    queryFn: ({ signal }) => getGrades(signal),
    enabled: schoolId > 0,
  });
  const sections = useQuery({
    queryKey: schoolScopedKey(schoolId, "sections"),
    queryFn: ({ signal }) => getSections(signal),
    enabled: schoolId > 0,
  });
  const students = useQuery({
    queryKey: schoolScopedKey(schoolId, "students", {
      page, search, nationalId, gradeFilter, sectionFilter,
    }),
    queryFn: ({ signal }) =>
      getStudents(
        {
          page,
          search,
          national_id: nationalId,
          grade: gradeFilter,
          section: sectionFilter,
          status: "ACTIVE", // صفحة النشطين — الخارجون في صفحتهم المستقلة
        },
        signal,
      ),
    enabled: schoolId > 0,
    placeholderData: (previous) => previous,
  });

  const totalPages = students.data ? Math.max(1, Math.ceil(students.data.count / 25)) : 1;
  const visibleSections = (sections.data ?? []).filter(
    (s) => !gradeFilter || s.grade.id === gradeFilter,
  );

  if (me.isSuccess && !canRead) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="mb-2 text-lg font-bold">لا تملك صلاحية عرض قائمة {studentsLabel}</h2>
        <p className="text-slate-600">وصول {roleLabel("TEACHER", schoolType)} {schoolType === "GIRLS" ? "لطالبات فصلها" : "لطلاب فصله"} يأتي مع شاشة التحضير.</p>
      </section>
    );
  }

  return (
    <div className="ds-page">
      <PageHeader
        icon={UsersRound}
        eyebrow={schoolType === "GIRLS" ? "سجل الطالبات" : "السجل الطلابي"}
        title={`${studentsLabel} ${schoolType === "GIRLS" ? "النشطات" : "النشطون"}`}
        description={`الوصول السريع إلى ملف ${student} و${schoolType === "GIRLS" ? "مواظبتها وإجراءاتها" : "مواظبته وإجراءاته"}، مع أدوات استيراد وإدارة آمنة لفريق المدرسة.`}
        tone="operational"
        badge={`${students.data?.count ?? 0} ${studentCountLabel(schoolType)}`}
        actions={<div className="flex flex-wrap items-center gap-2"><Link to="/students/inactive" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 py-2 text-sm font-bold text-white ring-1 ring-white/15 hover:bg-white/15"><Archive aria-hidden size={17} /> {schoolType === "GIRLS" ? "غير النشطات" : "غير النشطين"}</Link>
          {canImport && (
            <><Link to="/students/import"><Button variant="headerGhost"><Upload aria-hidden size={17} /> استيراد</Button></Link><Button variant="header" onClick={() => setManualOpen(true)}><Plus aria-hidden size={17} /> إدخال يدوي</Button></>
          )}</div>}
      />

      {notice && <p role="status" className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-800">{notice}</p>}

      {canImport && (
        <div className="mb-4 flex flex-col items-stretch gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm sm:flex-row sm:flex-wrap sm:items-center">
          <span className="text-sm text-slate-600">تخريج دفعة — {schoolType === "GIRLS" ? "المحددات" : "المحددون"}: {selected.size}</span>
          <Button
            variant="secondary"
            className="md:hidden"
            disabled={(students.data?.results.length ?? 0) === 0}
            onClick={() => {
              const visibleIds = students.data?.results.map((row) => row.id) ?? [];
              const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
              setSelected(allVisibleSelected ? new Set() : new Set(visibleIds));
            }}
          >
            {students.data?.results.length && students.data.results.every((row) => selected.has(row.id))
              ? "إلغاء تحديد المعروض"
              : "تحديد المعروض"}
          </Button>
          <Button
            variant="secondary"
            disabled={selected.size === 0 || graduateMutation.isPending}
            onClick={() => graduateMutation.mutate([...selected])}
          >
            تعيين {schoolType === "GIRLS" ? "المحددات كخريجات" : "المحددين كخريجين"}
          </Button>
          {bulkError && (
            <span role="alert" className="text-sm text-red-700">
              {bulkError}
            </span>
          )}
        </div>
      )}

      {/* الفلاتر */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2"><Filter aria-hidden size={18} className="text-slate-500" /><h2 className="font-black text-slate-900">البحث والتصفية</h2></div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="search-name" className="text-sm font-medium text-slate-700">
            بحث بالاسم
          </label>
          <input
            id="search-name"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder={`اسم ${student}`}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="search-nid" className="text-sm font-medium text-slate-700">
            بحث برقم الهوية (مطابقة تامة)
          </label>
          <input
            id="search-nid"
            dir="ltr"
            value={nationalId}
            onChange={(e) => {
              setNationalId(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="1XXXXXXXXX"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-grade" className="text-sm font-medium text-slate-700">
            الصف
          </label>
          <select
            id="filter-grade"
            value={gradeFilter}
            onChange={(e) => {
              setGradeFilter(e.target.value ? Number(e.target.value) : "");
              setSectionFilter("");
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">الكل</option>
            {(grades.data ?? []).map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-section" className="text-sm font-medium text-slate-700">
            الفصل
          </label>
          <select
            id="filter-section"
            value={sectionFilter}
            onChange={(e) => {
              setSectionFilter(e.target.value ? Number(e.target.value) : "");
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">الكل</option>
            {visibleSections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.grade.name} / {s.name}
              </option>
            ))}
          </select>
        </div>
        </div>
      </section>

      {students.isPending && <Spinner />}
      {students.isError && <ErrorState error={students.error} />}

      {students.data && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="md:overflow-x-auto">
            <table className="block w-full text-sm md:table md:min-w-150">
              <thead className="hidden md:table-header-group">
                <tr className="border-b border-slate-200 text-slate-500">
                  {canImport && (
                    <th className="p-3">
                      <input
                        type="checkbox"
                        aria-label="تحديد الكل"
                        checked={
                          students.data.results.length > 0 &&
                          students.data.results.every((r) => selected.has(r.id))
                        }
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? new Set(students.data!.results.map((r) => r.id))
                              : new Set(),
                          )
                        }
                        className="size-4"
                      />
                    </th>
                  )}
                  <th className="p-3 text-start">الاسم</th>
                  <th className="p-3 text-start">رقم الهوية</th>
                  <th className="p-3 text-start">الصف</th>
                  <th className="p-3 text-start">الفصل</th>
                  <th className="p-3 text-start">الحالة</th>
                  {canImport && <th className="p-3 text-start">الإجراءات</th>}
                </tr>
              </thead>
              <tbody className="grid gap-3 p-3 md:table-row-group md:p-0" data-testid="students-table-body">
                {students.data.results.map((student) => (
                  <tr key={student.id} className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 md:table-row md:border-x-0 md:border-t-0 md:p-0">
                    {canImport && (
                      <td className="col-span-2 flex items-center gap-2 p-0 md:table-cell md:p-3">
                        <input
                          type="checkbox"
                          aria-label={`تحديد ${student.full_name}`}
                          checked={selected.has(student.id)}
                          onChange={(e) => {
                            const next = new Set(selected);
                            if (e.target.checked) next.add(student.id);
                            else next.delete(student.id);
                            setSelected(next);
                          }}
                          className="size-4"
                        />
                        <span className="text-xs font-bold text-slate-500 md:hidden">تحديد السجل</span>
                      </td>
                    )}
                    <td className="col-span-2 p-0 font-medium md:table-cell md:p-3">
                      <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الاسم</span>
                      <Link to={`/students/${student.id}/attendance`} className="text-blue-700 hover:underline">
                        {student.full_name}
                      </Link>
                    </td>
                    <td className="p-0 md:table-cell md:p-3" dir="ltr">
                      <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden" dir="rtl">رقم الهوية</span>
                      {student.national_id_masked}
                    </td>
                    <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الصف</span>{student.grade?.name ?? "—"}</td>
                    <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الفصل</span>{student.section?.name ?? "—"}</td>
                    <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الحالة</span>{STATUS_LABELS[student.status] ?? student.status}</td>
                    {canImport && (
                      <td className="col-span-2 p-0 md:table-cell md:p-3">
                        <Button className="w-full md:w-auto" variant="secondary" onClick={() => setEditingStudent(student)}>
                          <Pencil aria-hidden size={15} /> تعديل البيانات
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
                {students.data.results.length === 0 && (
                  <tr className="block">
                    <td colSpan={canImport ? 7 : 5} className="block p-6 text-center text-slate-400">
                      <EmptyState title={`لا يوجد ${studentsLabel} ${schoolType === "GIRLS" ? "مطابقات" : "مطابقون"}`} description="جرّب مسح بعض معايير البحث أو تغيير الصف والفصل." compact />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 border-t border-slate-100 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <span className="text-slate-500">
              الإجمالي: {students.data.count} {studentCountLabel(schoolType)} — صفحة {page} من {totalPages}
            </span>
            <div className="grid grid-cols-2 gap-2 sm:flex">
              <Button
                variant="secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                السابق
              </Button>
              <Button
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                التالي
              </Button>
            </div>
          </div>
        </div>
      )}

      {manualOpen && (
        <Modal title={`إضافة ${studentLabel(schoolType)} يدويًا`} description={`أدخل بيانات ${student} وحدد فصله في العام الدراسي الحالي.`} onClose={() => setManualOpen(false)}>
          <ManualStudentForm
            sections={sections.data ?? []}
            onCancel={() => setManualOpen(false)}
            onCreated={(student) => {
              setManualOpen(false);
              setNotice(`تمت إضافة ${studentLabel(schoolType, true)} ${student.full_name} بنجاح.`);
              setPage(1);
              void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "students") });
            }}
          />
        </Modal>
      )}

      {editingStudent && (
        <Modal title={`تعديل بيانات ${editingStudent.full_name}`} description="صحح البيانات أو رقم الهوية/الإقامة مع حفظ سجل التغيير." onClose={() => setEditingStudent(null)}>
          <StudentEditForm
            student={editingStudent}
            sections={sections.data ?? []}
            onCancel={() => setEditingStudent(null)}
            onUpdated={(updated) => {
              setEditingStudent(null);
              setNotice(`تم تحديث بيانات ${studentLabel(schoolType, true)} ${updated.full_name} بنجاح.`);
              void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "students") });
            }}
          />
        </Modal>
      )}
    </div>
  );
}
