import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, FileSpreadsheet, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
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
import { studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

const STEPS = ["رفع الملف", "مطابقة الأعمدة", "المعاينة", "التأكيد", "النتيجة"] as const;

/** معالج استيراد نور — الخطوات: رفع → مطابقة → معاينة → تأكيد → نتيجة.
 *  المفاتيح كلها tenant-aware؛ تبديل المدرسة يفرغ الـ cache (سياسة المرحلة 2)
 *  فيسقط سياق الـ Wizard القديم تلقائيًا. */
export function ImportWizard() {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const studentsLabel = studentPluralLabel(schoolType);
  const queryClient = useQueryClient();
  const [job, setJob] = useState<ImportJob | null>(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [handledAsyncError, setHandledAsyncError] = useState("");

  function fail(e: unknown, fallback: string) {
    setError(e instanceof ApiError || e instanceof Error ? e.message : fallback);
  }

  // Polling أثناء المعالجة في الـ Worker
  const jobQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "import-job", job?.id ?? 0),
    queryFn: ({ signal }) => getImportJob(job!.id, signal),
    enabled:
      job !== null &&
      (job.status === "PROCESSING" || job.status === "IMPORTING" || step === 2 || step === 3),
    refetchInterval: (query) =>
      query.state.data?.status === "PROCESSING" || query.state.data?.status === "IMPORTING"
        ? 1500
        : false,
  });
  const liveJob = jobQuery.data ?? job;

  useEffect(() => {
    if (!jobQuery.data) return;
    const updated = jobQuery.data;
    setJob(updated);
    if (updated.status === "COMPLETED") {
      setStep(4);
      setError(null);
      setHandledAsyncError("");
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "students"),
      });
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "grades") });
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "sections"),
      });
      return;
    }
    if (!updated.error_code || updated.error_code === handledAsyncError) return;
    setHandledAsyncError(updated.error_code);
    setError(updated.error_message || "تعذر اعتماد الاستيراد.");
    if (updated.status === "READY_FOR_REVIEW") {
      setStep(2);
    } else if (updated.status === "FAILED") {
      setJob(null);
      setStep(0);
    }
  }, [handledAsyncError, jobQuery.data, queryClient, schoolId]);

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
    onSuccess: (updated) => {
      setJob(updated);
      queryClient.setQueryData(
        schoolScopedKey(schoolId, "import-job", updated.id),
        updated,
      );
      setStep(updated.status === "COMPLETED" ? 4 : 3);
      setError(null);
      if (updated.status === "IMPORTING") {
        void jobQuery.refetch();
      }
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
    <div className="ds-page mx-auto max-w-5xl">
      <PageHeader
        icon={FileSpreadsheet}
        eyebrow="تحديث جماعي موثوق"
        title={<>استيراد {studentsLabel} من نور</>}
        description="ارفع ملف نور، راجع مطابقة الأعمدة والتغييرات المقترحة، ثم اعتمدها بعد التحقق النهائي."
        tone="operational"
        actions={<Link to="/students"><Button variant="headerGhost"><ArrowRight aria-hidden size={16} /> العودة إلى {studentsLabel}</Button></Link>}
      />

      {/* مؤشر الخطوات */}
      <ol className="grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 bg-white p-3 text-xs shadow-sm sm:grid-cols-5" aria-label="خطوات الاستيراد">
        {STEPS.map((label, index) => (
          <li
            key={label}
            aria-current={index === step ? "step" : undefined}
            className={`flex items-center gap-2 rounded-xl px-3 py-2.5 font-bold ${
              index === step
                ? "bg-blue-600 text-white shadow-sm"
                : index < step
                  ? "bg-emerald-50 text-emerald-800"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            <span className={`grid size-5 shrink-0 place-items-center rounded-full text-[10px] ${index === step ? "bg-white/20" : "bg-white"}`}>{index < step ? <Check aria-hidden size={12} /> : index + 1}</span><span>الخطوة: {label}</span>
          </li>
        ))}
      </ol>

      {error && <Alert tone="danger" title="تعذر إكمال خطوة الاستيراد">{error}</Alert>}

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
          pending={commitMutation.isPending || liveJob.status === "IMPORTING"}
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
  const schoolType = useActiveSchoolType();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
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
        className={`mb-4 flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition-all ${
          dragOver ? "border-blue-500 bg-blue-50 shadow-inner" : "border-slate-300 bg-slate-50/60 hover:border-blue-400 hover:bg-blue-50/50"
        }`}
      >
        <span className="mb-4 grid size-14 place-items-center rounded-2xl bg-blue-100 text-blue-700"><UploadCloud aria-hidden size={27} /></span>
        <p className="mb-1 font-medium text-slate-700">
          اسحب ملف نور هنا أو اضغط للاختيار
        </p>
        <p className="max-w-xl text-sm leading-6 text-slate-500">
          ارفع تقرير {studentPluralLabel(schoolType)} بصيغته المصدرة من نور؛ سيتعرف النظام تلقائيًا على صف
          العناوين وترتيب الأعمدة حتى عند وجود بيانات المدرسة قبله. ملف ‎.xlsx بحد أقصى 10MB.
        </p>
        <input
          ref={inputRef}
          type="file"
          aria-label="اختيار ملف استيراد الطلاب"
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
  const schoolType = useActiveSchoolType();
  const student = studentLabel(schoolType, true);
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
        تحقق من ربط أعمدة الملف بحقول النظام — الحقول: اسم {student} والصف والفصل مطلوبة،
        ورقم الهوية مطلوب للمطابقة الموثوقة.
      </p>

      {job.import_format === "NOOR_OFFICIAL_MULTI_SHEET" ? (
        <div
          className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950"
          role="status"
        >
          <p className="font-bold">تم التعرف على تقرير نور الرسمي بنجاح</p>
          <p className="mt-1 leading-6">
            جُمعت {job.source_sheet_count ?? 1} ورقة، واكتُشف {job.detected_rows ?? 0} {studentCountLabel(schoolType)}.
            سيُستخرج الصف والفصل من رأس كل صفحة تلقائيًا، وتظهر السجلات التي تحتاج
            مراجعة في خطوة المعاينة.
          </p>
        </div>
      ) : job.header_row != null && job.header_row > 1 ? (
        <div
          className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"
          role="status"
        >
          تم التعرف تلقائيًا على عناوين تقرير نور في الصف {job.header_row}. راجع
          المطابقة ثم ابدأ التحليل.
        </div>
      ) : null}

      <div className="mb-4 space-y-3">
        {(Object.keys(MAPPING_LABELS) as MappingField[]).map((field) => (
          <div key={field} className="flex flex-wrap items-center gap-3">
            <span className="w-36 text-sm font-medium text-slate-700">
              {field === "full_name" ? `اسم ${student}` : field === "student_number" ? `رقم ${student}` : MAPPING_LABELS[field]}
            </span>
            <select
              aria-label={`عمود ${field === "full_name" ? `اسم ${student}` : field === "student_number" ? `رقم ${student}` : MAPPING_LABELS[field]}`}
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
  const schoolType = useActiveSchoolType();
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
          {summary.missing_from_file} {studentCountLabel(schoolType)} {schoolType === "GIRLS" ? "موجودات" : "موجودون"} في النظام وغير {schoolType === "GIRLS" ? "موجودات" : "موجودين"} في الملف الجديد —
          لن يتغيروا تلقائيًا، وستتمكن من مراجعتهم وتصنيفهم بعد اعتماد الاستيراد.
        </p>
      )}

      {summary.student_capacity?.over_limit && (
        <p className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-800">
          يتجاوز الاستيراد حد الباقة: {summary.student_capacity.projected} / {summary.student_capacity.limit} {studentCountLabel(schoolType)}.
          يمكنك مراجعة المعاينة، لكن الاعتماد يتطلب ترقية الباقة.
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
            {key === "NEW" && schoolType === "GIRLS" ? "طالبات جديدات" : label} ({counts[key] ?? 0})
          </button>
        ))}
      </div>

      {rowsQuery.isPending && <Spinner />}
      {rowsQuery.data && (
        <div className="mb-4 overflow-x-auto">
            <table className="w-full min-w-140 text-sm">
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
  const schoolType = useActiveSchoolType();
  const countLabel = studentCountLabel(schoolType);
  if (job.status === "IMPORTING") {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <Spinner label="جارٍ تثبيت بيانات الاستيراد..." />
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-3 font-bold">ملخص التغييرات</h3>
      <ul className="mb-4 space-y-1 text-sm" data-testid="confirm-summary">
        <li>سيتم إنشاء {summary.new ?? 0} {countLabel} {schoolType === "GIRLS" ? "جديدة" : "جديدًا"}.</li>
        <li>سيتم تحديث بيانات {summary.updated ?? 0} {countLabel}.</li>
        <li>
          سيتم نقل {(summary.section_changed ?? 0) + (summary.grade_changed ?? 0)} {countLabel} إلى
          فصول/صفوف جديدة.
        </li>
        <li>{summary.unchanged ?? 0} {countLabel} بلا تغيير.</li>
        {(summary.will_create_grades?.length ?? 0) > 0 && (
          <li>سيتم إنشاء الصفوف: {summary.will_create_grades!.join("، ")}</li>
        )}
        {(summary.will_create_sections?.length ?? 0) > 0 && (
          <li>سيتم إنشاء الفصول: {summary.will_create_sections!.join("، ")}</li>
        )}
        {(summary.missing_from_file ?? 0) > 0 && (
          <li className="text-amber-700">
            {summary.missing_from_file} {countLabel} غير {schoolType === "GIRLS" ? "موجودات" : "موجودين"} في الملف — لن {schoolType === "GIRLS" ? "يتغيرن" : "يتغيروا"} تلقائيًا،
            وستظهر مراجعتهم بعد الاعتماد.
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
  const schoolType = useActiveSchoolType();
  const studentsLabel = studentPluralLabel(schoolType);
  const missingCount = summary.missing_from_file ?? 0;
  return (
    <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
      <h3 className="mb-3 font-bold text-emerald-800">تم استيراد البيانات بنجاح</h3>
      <ul className="mb-4 space-y-1 text-sm text-emerald-900" data-testid="import-result">
        <li>{schoolType === "GIRLS" ? "طالبات جديدات" : "طلاب جدد"}: {summary.created ?? 0}</li>
        <li>{schoolType === "GIRLS" ? "طالبات محدثات" : "طلاب محدثون"}: {summary.updated ?? 0}</li>
        <li>تغييرات فصول: {summary.enrollment_changes ?? 0}</li>
        <li>بدون تغيير: {summary.unchanged ?? 0}</li>
      </ul>
      {missingCount > 0 && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
          <p className="font-bold">يلزم إجراء على {missingCount} {studentCountLabel(schoolType)} غير {schoolType === "GIRLS" ? "موجودات" : "موجودين"} في الملف</p>
          <p className="mt-1 text-sm">
            راجعهم ثم صنّف من غادر المدرسة كمنتقل أو متخرج. بعد التصنيف يمكنك حذفه
            نهائيًا إذا لم تعد بحاجة إلى سجلاته.
          </p>
          <Link to="/students/inactive?filter=missing" className="mt-3 inline-block">
            <Button variant="secondary">مراجعة {studentsLabel} غير {schoolType === "GIRLS" ? "الموجودات" : "الموجودين"}</Button>
          </Link>
        </div>
      )}
      <Link to="/students">
        <Button>عرض جميع {studentsLabel}</Button>
      </Link>
    </section>
  );
}
