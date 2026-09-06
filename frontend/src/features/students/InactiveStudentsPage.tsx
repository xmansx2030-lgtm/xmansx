import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  bulkSetStatus,
  createPurge,
  getInactiveStudents,
  getPurgeJob,
  LIFECYCLE_STATUS_LABELS,
  purgePreview,
  type PurgeJob,
  type PurgePreview,
} from "@/features/students/api";
import { studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

const FILTERS = [
  { key: "", label: "الكل" },
  { key: "GRADUATED", label: "الخريجون" },
  { key: "TRANSFERRED", label: "المنتقلون" },
  { key: "WITHDRAWN", label: "المنسحبون" },
  { key: "INACTIVE", label: "غير النشطين" },
  { key: "missing", label: "غير الموجودين في آخر ملف نور" },
] as const;

/** الطلاب غير النشطين: تصنيف، تحديد جماعي، حذف نهائي (مدير فقط). */
export function InactiveStudentsPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const student = studentLabel(schoolType, true);
  const studentsLabel = studentPluralLabel(schoolType);
  const queryClient = useQueryClient();
  const isManager = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const [searchParams, setSearchParams] = useSearchParams();

  const [filter, setFilter] = useState<string>(() =>
    searchParams.get("filter") === "missing" ? "missing" : "",
  );
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<PurgePreview | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const students = useQuery({
    queryKey: schoolScopedKey(schoolId, "inactive-students", { filter, page, search }),
    queryFn: ({ signal }) =>
      getInactiveStudents(
        {
          page,
          status: filter && filter !== "missing" ? filter : undefined,
          missing_last_import: filter === "missing",
          search,
        },
        signal,
      ),
    enabled: schoolId > 0,
    placeholderData: (previous) => previous,
  });

  const purgeJob = useQuery({
    queryKey: schoolScopedKey(schoolId, "purge-job", activeJobId ?? 0),
    queryFn: ({ signal }) => getPurgeJob(activeJobId!, signal),
    enabled: activeJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "RUNNING" ? 1200 : false;
    },
  });

  function fail(e: unknown, fallback: string) {
    setError(e instanceof ApiError ? e.message : fallback);
  }

  const refresh = () => {
    setSelected(new Set());
    void queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "inactive-students"),
    });
    void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "students") });
  };

  const statusMutation = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: string }) =>
      bulkSetStatus(ids, status),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => fail(e, "تعذر تغيير الحالة."),
  });

  const previewMutation = useMutation({
    mutationFn: (ids: number[]) => purgePreview(ids),
    onSuccess: (data) => {
      setError(null);
      setPreview(data);
      setConfirmText("");
    },
    onError: (e) => fail(e, "تعذرت معاينة الحذف."),
  });

  const purgeMutation = useMutation({
    mutationFn: (token: string) => createPurge(token, filter || "MANUAL_SELECTION"),
    onSuccess: (job: PurgeJob) => {
      setError(null);
      setPreview(null);
      setActiveJobId(job.id);
      refresh();
    },
    onError: (e) => {
      setPreview(null);
      fail(e, "تعذر بدء الحذف.");
    },
  });

  const rows = students.data?.results ?? [];
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const selectedRows = rows.filter((row) => selected.has(row.id));
  const selectedArePurgeable =
    selected.size > 0 &&
    selectedRows.length === selected.size &&
    selectedRows.every((row) => row.status !== "ACTIVE");
  const expectedConfirm = preview ? `حذف ${preview.summary.students} ${studentCountLabel(schoolType)}` : "";
  const jobData = purgeJob.data;
  const jobDone =
    jobData && ["COMPLETED", "PARTIALLY_FAILED", "FAILED"].includes(jobData.status);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={Archive}
        eyebrow="السجل الأكاديمي"
        title={filter === "missing" ? `مراجعة ${studentsLabel} ${schoolType === "GIRLS" ? "غير الموجودات" : "غير الموجودين"} في آخر ملف نور` : `${studentsLabel} ${schoolType === "GIRLS" ? "غير النشطات" : "غير النشطين"}`}
        description={isManager
          ? "راجع حالات الخريجين والمنقولين والمنسحبين، واتخذ الإجراءات الجماعية بعد التحقق."
          : `اطّلع على حالات ${studentsLabel} خارج القيد النشط وسجل انتقالهم أو تخرجهم دون تعديل البيانات.`}
        tone="operational"
        badge={isManager ? "إدارة السجل" : "عرض فقط"}
        meta={<span>{students.data ? `${students.data.count} سجلًا` : "جارٍ تحميل السجلات"}</span>}
        actions={(
          <Link
            to="/students"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            <ArrowRight aria-hidden size={17} />
            {studentsLabel} {schoolType === "GIRLS" ? "النشطات" : "النشطون"}
          </Link>
        )}
        testId="inactive-students-header"
      />

      <div>
        <label htmlFor="inactive-search" className="me-2 text-sm font-medium text-slate-700">
          بحث بالاسم
        </label>
        <input
          id="inactive-search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
            setSelected(new Set());
          }}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="فلاتر الحالة">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => {
              setFilter(f.key);
              setSearchParams(f.key ? { filter: f.key } : {});
              setPage(1);
              setSelected(new Set());
            }}
            className={`rounded-full px-3 py-1 text-sm ${
              filter === f.key
                ? "bg-blue-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filter === "missing" && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-bold">هذه القائمة تحتاج قرارًا إداريًا، ولا تعني الحذف تلقائيًا.</p>
          <p className="mt-1">
            حدّد من غادر المدرسة وصنّفه كمنتقل أو متخرج أولًا. بعد إغلاق قيده سيصبح
            زر الحذف النهائي متاحًا، مع معاينة مستقلة لكل السجلات التي ستُحذف.
          </p>
        </div>
      )}

      {error && (
        <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {/* شريط تقدم الحذف الجاري */}
      {activeJobId !== null && jobData && (
        <section
          className={`mb-4 rounded-xl border p-4 shadow-sm ${
            jobDone
              ? jobData.status === "COMPLETED"
                ? "border-emerald-200 bg-emerald-50"
                : "border-amber-300 bg-amber-50"
              : "border-blue-200 bg-blue-50"
          }`}
          data-testid="purge-progress"
        >
          <p className="mb-1 font-bold">
            {jobData.status === "RUNNING" || jobData.status === "PENDING"
              ? `جارٍ حذف بيانات ${studentsLabel}...`
              : jobData.status === "COMPLETED"
                ? "اكتمل الحذف النهائي"
                : jobData.status === "PARTIALLY_FAILED"
                  ? "اكتمل الحذف جزئيًا — ملفات بحاجة لتنظيف لاحق"
                  : "فشل الحذف"}
          </p>
          <p className="text-sm text-slate-700">
            {jobData.processed_students} / {jobData.total_students}
            {jobDone && <> — سجلات محذوفة: {jobData.db_records_deleted}</>}
          </p>
          {jobDone && (
            <Button variant="secondary" className="mt-2" onClick={() => setActiveJobId(null)}>
              إغلاق
            </Button>
          )}
        </section>
      )}

      {/* إجراءات جماعية للمدير */}
      {isManager && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <span className="text-sm text-slate-600">المحددون: {selected.size}</span>
          {filter === "missing" && (
            <>
              <Button
                variant="secondary"
                disabled={selected.size === 0 || statusMutation.isPending}
                onClick={() =>
                  statusMutation.mutate({ ids: [...selected], status: "TRANSFERRED" })
                }
              >
                تعيين كمنتقلين
              </Button>
              <Button
                variant="secondary"
                disabled={selected.size === 0 || statusMutation.isPending}
                onClick={() =>
                  statusMutation.mutate({ ids: [...selected], status: "GRADUATED" })
                }
              >
                تعيين كخريجين
              </Button>
              <Button
                variant="danger"
                disabled={!selectedArePurgeable || previewMutation.isPending}
                onClick={() => previewMutation.mutate([...selected])}
                title={
                  selected.size > 0 && !selectedArePurgeable
                    ? `صنّف ${studentsLabel} ${schoolType === "GIRLS" ? "كمنتقلات أو خريجات" : "كمنتقلين أو متخرجين"} أولًا`
                    : undefined
                }
              >
                حذف المحددين نهائيًا
              </Button>
              {selected.size > 0 && !selectedArePurgeable && (
                <span className="text-xs text-amber-800">
                  الحذف النهائي يتاح بعد تصنيف {student} وإغلاق قيده النشط.
                </span>
              )}
            </>
          )}
          {filter !== "missing" && (
            <Button
              variant="danger"
              disabled={selected.size === 0 || previewMutation.isPending}
              onClick={() => previewMutation.mutate([...selected])}
            >
              حذف المحددين نهائيًا
            </Button>
          )}
          {(filter === "GRADUATED" || filter === "TRANSFERRED") && rows.length > 0 && (
            <Button
              variant="danger"
              disabled={previewMutation.isPending}
              onClick={() => previewMutation.mutate(rows.map((r) => r.id))}
            >
              {filter === "GRADUATED"
                ? `حذف جميع الخريجين المعروضين (${rows.length})`
                : `حذف جميع المنتقلين المعروضين (${rows.length})`}
            </Button>
          )}
        </div>
      )}

      {students.isPending && <Spinner />}
      {students.isError && <ErrorState error={students.error} />}

      {students.data && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-150 text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  {isManager && (
                    <th className="p-3">
                      <input
                        type="checkbox"
                        aria-label="تحديد الكل"
                        checked={allSelected}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked ? new Set(rows.map((r) => r.id)) : new Set(),
                          )
                        }
                        className="size-4"
                      />
                    </th>
                  )}
                  <th className="p-3 text-start">الاسم</th>
                  <th className="p-3 text-start">آخر صف/فصل</th>
                  <th className="p-3 text-start">الحالة</th>
                  <th className="p-3 text-start">تاريخ الخروج</th>
                </tr>
              </thead>
              <tbody data-testid="inactive-table-body">
                {rows.map((student) => (
                  <tr key={student.id} className="border-b border-slate-100">
                    {isManager && (
                      <td className="p-3">
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
                      </td>
                    )}
                    <td className="p-3 font-medium">{student.full_name}</td>
                    <td className="p-3">
                      {student.grade ? `${student.grade.name} / ${student.section?.name}` : "—"}
                    </td>
                    <td className="p-3">
                      {LIFECYCLE_STATUS_LABELS[student.status] ?? student.status}
                    </td>
                    <td className="p-3">{student.exit_date ?? "—"}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={isManager ? 5 : 4} className="p-6 text-center text-slate-400">
                      لا يوجد {studentsLabel} {schoolType === "GIRLS" ? "مطابقات" : "مطابقون"}.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 p-3 text-sm text-slate-500">
            الإجمالي: {students.data.count}
          </div>
        </div>
      )}

      {/* حوار تأكيد الحذف النهائي */}
      {preview && (
        <div
          className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="تأكيد الحذف النهائي"
        >
          {/* الملخص ينمو بنمو خطوات الحذف — بلا تمرير داخلي يخرج زر التأكيد من الشاشة */}
          <div className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-bold text-red-700">حذف نهائي</h3>
            <p className="mb-3 text-sm text-slate-700">
              سيتم حذف بيانات {preview.summary.students} {studentCountLabel(schoolType)} نهائيًا.
            </p>
            <ul className="mb-3 space-y-1 text-sm text-slate-600" data-testid="purge-summary">
              {Object.entries(preview.summary)
                .filter(([key]) => !["students", "database_records"].includes(key))
                .map(([key, value]) => (
                  <li key={key}>
                    {key}: {value}
                  </li>
                ))}
              <li>إجمالي سجلات قاعدة البيانات: {preview.summary.database_records}</li>
            </ul>
            <p className="mb-3 rounded-lg bg-red-50 p-2 text-sm font-medium text-red-700">
              لن يمكن استعادة هذه البيانات من المنصة بعد إتمام العملية.
            </p>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              اكتب: {expectedConfirm}
            </label>
            <input
              dir="rtl"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className="mb-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              data-testid="purge-confirm-input"
            />
            <div className="flex gap-2">
              <Button
                variant="danger"
                disabled={confirmText.trim() !== expectedConfirm || purgeMutation.isPending}
                onClick={() => purgeMutation.mutate(preview.confirmation_token)}
              >
                {purgeMutation.isPending ? "جارٍ البدء..." : "حذف نهائي"}
              </Button>
              <Button variant="secondary" onClick={() => setPreview(null)}>
                إلغاء
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
