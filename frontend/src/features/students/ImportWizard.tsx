import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  CATEGORY_LABELS,
  commitImportJob,
  getImportJob,
  getImportPreview,
  MAPPING_LABELS,
  processImportJob,
  uploadImportFile,
  type ImportJob,
  type MappingField,
} from "@/features/students/api";

const STEPS = ["رفع الملف", "مطابقة الأعمدة", "المعاينة", "التأكيد", "النتيجة"] as const;

/** معالج استيراد نور — الخطوات: رفع → مطابقة → معاينة → تأكيد → نتيجة.
 *  المفاتيح كلها tenant-aware؛ تبديل المدرسة يفرغ الـ cache (سياسة المرحلة 2)
 *  فيسقط سياق الـ Wizard القديم تلقائيًا. */
export function ImportWizard() {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [job, setJob] = useState<ImportJob | null>(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  function fail(e: unknown, fallback: string) {
    setError(e instanceof ApiError || e instanceof Error ? e.message : fallback);
  }

  // Polling أثناء المعالجة في الـ Worker
  const jobQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "import-job", job?.id ?? 0),
    queryFn: ({ signal }) => getImportJob(job!.id, signal),
    enabled: job !== null && (job.status === "PROCESSING" || step === 2),
    refetchInterval: (query) =>
      query.state.data?.status === "PROCESSING" ? 1500 : false,
  });
  const liveJob = jobQuery.data ?? job;

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadImportFile(file),
    onSuccess: (created) => {
      setJob(created);
      setStep(1);
      setError(null);
    },
    onError: (e) => fail(e, "تعذر رفع الملف."),
  });

  const processMutation = useMutation({
    mutationFn: (mapping: Partial<Record<MappingField, number>>) =>
      processImportJob(job!.id, mapping),
    onSuccess: (updated) => {
      setJob(updated);
      setStep(2);
      setError(null);
    },
    onError: (e) => fail(e, "تعذرت معالجة الملف."),
  });

  const commitMutation = useMutation({
    mutationFn: () => commitImportJob(job!.id),
    onSuccess: (completed) => {
      setJob(completed);
      queryClient.setQueryData(
        schoolScopedKey(schoolId, "import-job", completed.id),
        completed,
      );
      setStep(4);
      setError(null);
      // بيانات الطلاب تغيرت — إبطال قوائمها
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "students"),
      });
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "grades") });
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "sections"),
      });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "IMPORT_PREVIEW_STALE") {
        setStep(2); // المعاينة أعيد بناؤها — يعيد المراجعة
        void jobQuery.refetch();
      }
      fail(e, "تعذر اعتماد الاستيراد.");
    },
  });

  return (
    <div className="mx-auto max-w-4xl">
      <h2 className="mb-2 text-2xl font-bold">استيراد الطلاب من نور</h2>

      {/* مؤشر الخطوات */}
      <ol className="mb-6 flex flex-wrap gap-2 text-sm" aria-label="خطوات الاستيراد">
        {STEPS.map((label, index) => (
          <li
            key={label}
            aria-current={index === step ? "step" : undefined}
            className={`rounded-full px-3 py-1 ${
              index === step
                ? "bg-blue-600 text-white"
                : index < step
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {index + 1}. {label}
          </li>
        ))}
      </ol>

      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {step === 0 && (
        <UploadStep pending={uploadMutation.isPending} onUpload={uploadMutation.mutate} />
      )}
      {step === 1 && job && (
        <MappingStep
          job={job}
          pending={processMutation.isPending}
          onConfirm={(mapping) => processMutation.mutate(mapping)}
        />
      )}
      {step === 2 && liveJob && (
        <PreviewStep
          job={liveJob}
          onNext={() => setStep(3)}
          onBack={() => setStep(1)}
        />
      )}
      {step === 3 && liveJob && (
        <ConfirmStep
          job={liveJob}
          pending={commitMutation.isPending}
          onCommit={() => commitMutation.mutate()}
          onBack={() => setStep(2)}
        />
      )}
      {step === 4 && liveJob && <ResultStep job={liveJob} />}
    </div>
  );
}

function UploadStep({
  pending,
  onUpload,
}: {
  pending: boolean;
  onUpload: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files[0];
          if (file) setSelected(file);
        }}
        className={`mb-4 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          dragOver ? "border-blue-500 bg-blue-50" : "border-slate-300"
        }`}
      >
        <p className="mb-1 font-medium text-slate-700">
          اسحب ملف نور هنا أو اضغط للاختيار
        </p>
        <p className="text-sm text-slate-500">ملف Excel بامتداد ‎.xlsx — بحد أقصى 10MB</p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          data-testid="import-file-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) setSelected(file);
          }}
        />
      </div>

      {selected && (
        <p className="mb-4 text-sm text-slate-600">
          الملف: <span className="font-medium">{selected.name}</span> (
          {(selected.size / 1024).toFixed(0)} KB)
        </p>
      )}

      <Button disabled={!selected || pending} onClick={() => selected && onUpload(selected)}>
        {pending ? "جارٍ الرفع..." : "رفع الملف"}
      </Button>
    </section>
  );
}

function MappingStep({
  job,
  pending,
  onConfirm,
}: {
  job: ImportJob;
  pending: boolean;
  onConfirm: (mapping: Partial<Record<MappingField, number>>) => void;
}) {
  const [mapping, setMapping] = useState<Partial<Record<MappingField, number | "">>>(() => {
    const initial: Partial<Record<MappingField, number | "">> = {};
    const suggested = job.suggested_mapping ?? {};
    (Object.keys(MAPPING_LABELS) as MappingField[]).forEach((field) => {
      const value = suggested[field];
      initial[field] = value === null || value === undefined ? "" : value;
    });
    return initial;
  });

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-1 font-bold">مطابقة الأعمدة</h3>
      <p className="mb-4 text-sm text-slate-500">
        تحقق من ربط أعمدة الملف بحقول النظام — الحقول: اسم الطالب والصف والفصل مطلوبة،
        ورقم الهوية مطلوب للمطابقة الموثوقة.
      </p>

      <div className="mb-4 space-y-3">
        {(Object.keys(MAPPING_LABELS) as MappingField[]).map((field) => (
          <div key={field} className="flex flex-wrap items-center gap-3">
            <span className="w-36 text-sm font-medium text-slate-700">
              {MAPPING_LABELS[field]}
            </span>
            <select
              aria-label={`عمود ${MAPPING_LABELS[field]}`}
              value={mapping[field] ?? ""}
              onChange={(e) =>
                setMapping((prev) => ({
                  ...prev,
                  [field]: e.target.value === "" ? "" : Number(e.target.value),
                }))
              }
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            >
              <option value="">— غير مرتبط —</option>
              {job.headers.map((header, index) => (
                <option key={index} value={index}>
                  {header || `عمود ${index + 1}`}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <Button
        disabled={pending}
        onClick={() => {
          const clean: Partial<Record<MappingField, number>> = {};
          (Object.entries(mapping) as [MappingField, number | ""][]).forEach(([k, v]) => {
            if (v !== "") clean[k] = v;
          });
          onConfirm(clean);
        }}
      >
        {pending ? "جارٍ البدء..." : "بدء التحليل"}
      </Button>
    </section>
  );
}

function PreviewStep({
  job,
  onNext,
  onBack,
}: {
  job: ImportJob;
  onNext: () => void;
  onBack: () => void;
}) {
  const schoolId = useActiveSchoolId();
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);

  const rowsQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "import-preview", job.id, category, page),
    queryFn: () => getImportPreview(job.id, category, page),
    enabled: job.status === "READY_FOR_REVIEW",
    placeholderData: (previous) => previous,
  });

  if (job.status === "PROCESSING") {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <Spinner label="جارٍ تحليل الملف والتحقق من البيانات..." />
      </section>
    );
  }
  if (job.status === "FAILED") {
    return (
      <section className="rounded-xl border border-red-200 bg-red-50 p-6 text-center shadow-sm">
        <p className="font-medium text-red-700" role="alert">
          فشل تحليل الملف. تأكد أنه ملف نور سليم ثم أعد المحاولة.
        </p>
      </section>
    );
  }

  const summary = job.summary;
  const counts: Record<string, number> = {
    "": job.total_rows,
    NEW: summary.new ?? 0,
    EXISTING_UNCHANGED: summary.unchanged ?? 0,
    EXISTING_UPDATED: summary.updated ?? 0,
    SECTION_CHANGED: summary.section_changed ?? 0,
    GRADE_CHANGED: summary.grade_changed ?? 0,
    ERROR: summary.errors ?? 0,
    DUPLICATE_IN_FILE: summary.duplicates ?? 0,
  };
  const hasBlockingIssues = (summary.errors ?? 0) + (summary.duplicates ?? 0) > 0;
  const totalPages = rowsQuery.data
    ? Math.max(1, Math.ceil(rowsQuery.data.count / 25))
    : 1;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-3 font-bold">المعاينة والتحقق</h3>

      {(summary.missing_from_file ?? 0) > 0 && (
        <p className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          {summary.missing_from_file} طالبًا موجودون في النظام وغير موجودين في الملف الجديد —
          لن يتم حذفهم أو تغييرهم.
        </p>
      )}

      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="فئات المعاينة">
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={category === key}
            onClick={() => {
              setCategory(key);
              setPage(1);
            }}
            className={`rounded-full px-3 py-1 text-sm ${
              category === key
                ? "bg-blue-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {label} ({counts[key] ?? 0})
          </button>
        ))}
      </div>

      {rowsQuery.isPending && <Spinner />}
      {rowsQuery.data && (
        <div className="mb-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="p-2 text-start">الصف بالملف</th>
                <th className="p-2 text-start">الاسم</th>
                <th className="p-2 text-start">الهوية</th>
                <th className="p-2 text-start">الصف/الفصل</th>
                <th className="p-2 text-start">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {rowsQuery.data.results.map((row) => (
                <tr key={row.row_number} className="border-b border-slate-100">
                  <td className="p-2">{row.row_number}</td>
                  <td className="p-2">
                    {row.data.full_name || "—"}
                    {row.data.changes?.full_name && (
                      <span className="block text-xs text-amber-700">
                        كان: {row.data.changes.full_name.from}
                      </span>
                    )}
                  </td>
                  <td className="p-2" dir="ltr">
                    {row.data.national_id_masked || "—"}
                  </td>
                  <td className="p-2">
                    {row.data.grade_name} / {row.data.section_name}
                  </td>
                  <td className="p-2">
                    {row.error_message ? (
                      <span className="text-red-700">❌ {row.error_message}</span>
                    ) : (
                      (CATEGORY_LABELS[row.status] ?? row.status)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="mt-2 flex gap-2">
              <Button
                variant="secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                السابق
              </Button>
              <span className="self-center text-sm text-slate-500">
                {page} / {totalPages}
              </span>
              <Button
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                التالي
              </Button>
            </div>
          )}
        </div>
      )}

      {hasBlockingIssues && (
        <p className="mb-3 text-sm text-amber-700">
          الصفوف ذات الأخطاء والتكرارات ستتخطى ولن تستورد.
        </p>
      )}

      <div className="flex gap-2">
        <Button variant="secondary" onClick={onBack}>
          تعديل المطابقة
        </Button>
        <Button onClick={onNext} disabled={job.status !== "READY_FOR_REVIEW"}>
          متابعة إلى التأكيد
        </Button>
      </div>
    </section>
  );
}

function ConfirmStep({
  job,
  pending,
  onCommit,
  onBack,
}: {
  job: ImportJob;
  pending: boolean;
  onCommit: () => void;
  onBack: () => void;
}) {
  const summary = job.summary;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-3 font-bold">ملخص التغييرات</h3>
      <ul className="mb-4 space-y-1 text-sm" data-testid="confirm-summary">
        <li>سيتم إنشاء {summary.new ?? 0} طالبًا جديدًا.</li>
        <li>سيتم تحديث بيانات {summary.updated ?? 0} طالبًا.</li>
        <li>
          سيتم نقل {(summary.section_changed ?? 0) + (summary.grade_changed ?? 0)} طالبًا إلى
          فصول/صفوف جديدة.
        </li>
        <li>{summary.unchanged ?? 0} طالبًا بلا تغيير.</li>
        {(summary.will_create_grades?.length ?? 0) > 0 && (
          <li>سيتم إنشاء الصفوف: {summary.will_create_grades!.join("، ")}</li>
        )}
        {(summary.will_create_sections?.length ?? 0) > 0 && (
          <li>سيتم إنشاء الفصول: {summary.will_create_sections!.join("، ")}</li>
        )}
        {(summary.missing_from_file ?? 0) > 0 && (
          <li className="text-amber-700">
            {summary.missing_from_file} طالبًا غير موجودين في الملف — لن يمسوا.
          </li>
        )}
      </ul>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={onBack} disabled={pending}>
          رجوع
        </Button>
        <Button onClick={onCommit} disabled={pending}>
          {pending ? "جارٍ الاستيراد..." : "اعتماد الاستيراد"}
        </Button>
      </div>
    </section>
  );
}

function ResultStep({ job }: { job: ImportJob }) {
  const summary = job.summary;
  return (
    <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
      <h3 className="mb-3 font-bold text-emerald-800">تم استيراد البيانات بنجاح</h3>
      <ul className="mb-4 space-y-1 text-sm text-emerald-900" data-testid="import-result">
        <li>طلاب جدد: {summary.created ?? 0}</li>
        <li>طلاب محدثون: {summary.updated ?? 0}</li>
        <li>تغييرات فصول: {summary.enrollment_changes ?? 0}</li>
        <li>بدون تغيير: {summary.unchanged ?? 0}</li>
      </ul>
      <Link to="/students">
        <Button>عرض الطلاب</Button>
      </Link>
    </section>
  );
}
