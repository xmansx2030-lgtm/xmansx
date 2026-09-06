import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, FileSpreadsheet, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import {
  commitStaffImportJob,
  getStaffImportJob,
  getStaffImportPreview,
  processStaffImportJob,
  STAFF_CATEGORY_LABELS,
  STAFF_MAPPING_LABELS,
  uploadStaffImportFile,
  type StaffImportJob,
} from "@/features/staff/api";
import type { SchoolType } from "@/types/auth";

const STEPS = ["رفع الملف", "مطابقة الأعمدة", "المعاينة", "التأكيد", "النتيجة"] as const;

function mappingLabel(field: string, fallback: string, schoolType: SchoolType): string {
  return field === "full_name" && schoolType === "GIRLS" ? "اسم المعلمة" : fallback;
}

function categoryLabel(key: string, fallback: string, schoolType: SchoolType): string {
  if (schoolType !== "GIRLS") return fallback;
  if (key === "NEW") return "معلمات جديدات";
  if (key === "ADD_TEACHER_ROLE") return "إضافة دور معلمة";
  return fallback;
}

/** معالج استيراد المعلمين — النتيجة تعرض بيانات الحسابات الجديدة مرة واحدة فقط. */
export function StaffImportWizard() {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [job, setJob] = useState<StaffImportJob | null>(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [committedJob, setCommittedJob] = useState<StaffImportJob | null>(null);

  function fail(e: unknown, fallback: string) {
    setError(e instanceof ApiError || e instanceof Error ? e.message : fallback);
  }

  const jobQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "staff-import-job", job?.id ?? 0),
    queryFn: ({ signal }) => getStaffImportJob(job!.id, signal),
    enabled: job !== null && (job.status === "PROCESSING" || step === 2),
    refetchInterval: (query) =>
      query.state.data?.status === "PROCESSING" ? 1500 : false,
  });
  const liveJob = committedJob ?? jobQuery.data ?? job;

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadStaffImportFile(file),
    onSuccess: (created) => {
      setJob(created);
      setStep(1);
      setError(null);
    },
    onError: (e) => fail(e, "تعذر رفع الملف."),
  });

  const processMutation = useMutation({
    mutationFn: (mapping: Partial<Record<string, number>>) =>
      processStaffImportJob(job!.id, mapping),
    onSuccess: (updated) => {
      setJob(updated);
      setStep(2);
      setError(null);
    },
    onError: (e) => fail(e, "تعذرت معالجة الملف."),
  });

  const commitMutation = useMutation({
    mutationFn: () => commitStaffImportJob(job!.id),
    onSuccess: (completed) => {
      setCommittedJob(completed);
      setStep(4);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "staff") });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "STAFF_IMPORT_PREVIEW_STALE") {
        setStep(2);
        void jobQuery.refetch();
      }
      fail(e, "تعذر اعتماد الاستيراد.");
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-l from-slate-950 via-slate-900 to-emerald-950 p-5 text-white shadow-xl shadow-slate-900/10 sm:p-7">
        <div aria-hidden className="absolute -left-10 -top-16 size-48 rounded-full bg-emerald-400/15 blur-3xl" />
        <div className="relative">
          <Link to="/staff" className="mb-5 inline-flex items-center gap-1.5 text-xs font-bold text-slate-300 hover:text-white"><ArrowRight aria-hidden size={15} /> العودة إلى الموظفين</Link>
          <div className="flex items-start gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/10 text-emerald-200 ring-1 ring-white/15"><FileSpreadsheet aria-hidden size={24} /></span>
            <div><p className="text-xs font-bold text-emerald-200">إضافة جماعية</p><h1 className="mt-1 text-2xl font-black sm:text-3xl">استيراد الموظفين</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">ارفع ملف Excel، راجع المطابقة والنتائج، ثم اعتمد الإضافة بعد التحقق.</p></div>
          </div>
        </div>
      </header>

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

      {error && (
        <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
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
        <PreviewStep job={liveJob} onNext={() => setStep(3)} onBack={() => setStep(1)} />
      )}
      {step === 3 && liveJob && (
        <ConfirmStep
          job={liveJob}
          pending={commitMutation.isPending}
          onCommit={() => commitMutation.mutate()}
          onBack={() => setStep(2)}
        />
      )}
      {step === 4 && committedJob && <ResultStep job={committedJob} />}
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
  const schoolType = useActiveSchoolType();
  const [selected, setSelected] = useState<File | null>(null);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
      <div className="mb-5"><h2 className="text-lg font-black text-slate-900">اختر ملف الموظفين</h2><p className="mt-1 text-sm text-slate-500">يدعم ملفات XLSX البسيطة وتقارير {schoolType === "GIRLS" ? "معلمات" : "معلمي"} المدرسة المصدّرة من وزارة التعليم، مع اكتشاف صف الترويسات تلقائيًا.</p></div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) setSelected(file);
        }}
        className="mb-4 flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50/60 p-6 text-center transition hover:border-blue-400 hover:bg-blue-50/40 focus-visible:outline-2 focus-visible:outline-blue-500"
      >
        <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-white text-blue-700 shadow-sm ring-1 ring-slate-200"><UploadCloud aria-hidden size={23} /></span>
        <p className="mb-1 font-bold text-slate-800">
          اسحب ملف {schoolType === "GIRLS" ? "المعلمات" : "المعلمين"} هنا أو اضغط للاختيار
        </p>
        <p className="text-sm text-slate-500">الأعمدة الأساسية: اسم {schoolType === "GIRLS" ? "المعلمة" : "المعلم"} ورقم الجوال</p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          data-testid="staff-file-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) setSelected(file);
          }}
        />
      </div>
      {selected && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"><FileSpreadsheet aria-hidden size={19} /><div className="min-w-0"><p className="font-bold">الملف جاهز للرفع</p><p className="truncate text-xs text-emerald-700">{selected.name}</p></div></div>
      )}
      <Button className="w-full sm:w-auto" disabled={!selected || pending} onClick={() => selected && onUpload(selected)}>
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
  job: StaffImportJob;
  pending: boolean;
  onConfirm: (mapping: Partial<Record<string, number>>) => void;
}) {
  const schoolType = useActiveSchoolType();
  const [mapping, setMapping] = useState<Partial<Record<string, number | "">>>(() => {
    const initial: Partial<Record<string, number | "">> = {};
    const suggested = job.suggested_mapping ?? {};
    Object.keys(STAFF_MAPPING_LABELS).forEach((field) => {
      const value = suggested[field];
      initial[field] = value === null || value === undefined ? "" : value;
    });
    return initial;
  });

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 font-bold">مطابقة الأعمدة</h3>
      {job.header_row != null && job.header_row > 1 && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900" role="status">
          تم التعرف تلقائيًا على ترويسات تقرير الموظفين في الصف {job.header_row}. راجع المطابقة ثم ابدأ التحليل.
        </div>
      )}
      <div className="mb-4 space-y-3">
        {Object.entries(STAFF_MAPPING_LABELS).map(([field, label]) => (
          <div key={field} className="flex flex-wrap items-center gap-3">
            <span className="w-36 text-sm font-medium text-slate-700">{mappingLabel(field, label, schoolType)}</span>
            <select
              aria-label={`عمود ${mappingLabel(field, label, schoolType)}`}
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
          const clean: Partial<Record<string, number>> = {};
          Object.entries(mapping).forEach(([k, v]) => {
            if (v !== "" && v !== undefined) clean[k] = v as number;
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
  job: StaffImportJob;
  onNext: () => void;
  onBack: () => void;
}) {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);

  const rowsQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "staff-import-preview", job.id, category, page),
    queryFn: () => getStaffImportPreview(job.id, category, page),
    enabled: job.status === "READY_FOR_REVIEW",
    placeholderData: (previous) => previous,
  });

  if (job.status === "PROCESSING") {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <Spinner label="جارٍ تحليل الملف..." />
      </section>
    );
  }
  if (job.status === "FAILED") {
    return (
      <section className="rounded-xl border border-red-200 bg-red-50 p-6 text-center shadow-sm">
        <p className="font-medium text-red-700" role="alert">
          فشل تحليل الملف. تأكد من صيغته ثم أعد المحاولة.
        </p>
      </section>
    );
  }

  const summary = job.summary;
  const counts: Record<string, number> = {
    "": job.total_rows,
    NEW: summary.new ?? 0,
    EXISTING_USER_INVITE: summary.invite ?? 0,
    ADD_TEACHER_ROLE: summary.add_role ?? 0,
    PROFILE_UPDATE: summary.profile_update ?? 0,
    EXISTING_UNCHANGED: summary.unchanged ?? 0,
    INVITATION_PENDING: summary.invitation_pending ?? 0,
    NEEDS_MANUAL_ACTION: summary.manual ?? 0,
    ERROR: summary.errors ?? 0,
    DUPLICATE_IN_FILE: summary.duplicates ?? 0,
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-3 font-bold">المعاينة والتحقق</h3>
      <div className="mb-4 flex flex-wrap gap-2" role="tablist">
        {Object.entries(STAFF_CATEGORY_LABELS).map(([key, label]) => (
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
            {categoryLabel(key, label, schoolType)} ({counts[key] ?? 0})
          </button>
        ))}
      </div>

      {rowsQuery.isPending && <Spinner />}
      {rowsQuery.data && (
        <div className="mb-4 overflow-x-auto">
          <table className="w-full min-w-135 text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="p-2 text-start">الصف</th>
                <th className="p-2 text-start">الاسم</th>
                <th className="p-2 text-start">الجوال</th>
                <th className="p-2 text-start">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {rowsQuery.data.results.map((row) => (
                <tr key={row.row_number} className="border-b border-slate-100">
                  <td className="p-2">{row.row_number}</td>
                  <td className="p-2">{row.data.full_name || "—"}</td>
                  <td className="p-2" dir="ltr">
                    {row.data.mobile_masked || "—"}
                  </td>
                  <td className="p-2">
                    {row.error_message ? (
                      <span className="text-red-700">❌ {row.error_message}</span>
                    ) : (
                      categoryLabel(
                        row.status,
                        STAFF_CATEGORY_LABELS[row.status] ?? row.status,
                        schoolType,
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
  job: StaffImportJob;
  pending: boolean;
  onCommit: () => void;
  onBack: () => void;
}) {
  const schoolType = useActiveSchoolType();
  const summary = job.summary;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-3 font-bold">ملخص التغييرات</h3>
      <ul className="mb-4 space-y-1 text-sm" data-testid="staff-confirm-summary">
        <li>حسابات {schoolType === "GIRLS" ? "معلمات جديدة" : "معلمين جدد"}: {summary.new ?? 0} (كلمة الدخول الأولى هي رقم الجوال)</li>
        <li>حسابات موجودة ستدعى للانضمام: {summary.invite ?? 0}</li>
        <li>أعضاء سيضاف لهم دور {schoolType === "GIRLS" ? "معلمة" : "معلم"}: {summary.add_role ?? 0}</li>
        <li>تحديث بيانات: {summary.profile_update ?? 0}</li>
        <li>بلا تغيير: {summary.unchanged ?? 0}</li>
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

function ResultStep({ job }: { job: StaffImportJob }) {
  const schoolType = useActiveSchoolType();
  const summary = job.summary;
  const credentials = job.new_credentials ?? [];
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
        <h3 className="mb-3 font-bold text-emerald-800">تم الاستيراد بنجاح</h3>
        <ul className="space-y-1 text-sm text-emerald-900" data-testid="staff-import-result">
          <li>حسابات جديدة: {summary.created ?? 0}</li>
          <li>دعوات أرسلت: {summary.invited ?? 0}</li>
          <li>أدوار {schoolType === "GIRLS" ? "معلمة" : "معلم"} أضيفت: {summary.roles_added ?? 0}</li>
          <li>بيانات محدثة: {summary.profiles_updated ?? 0}</li>
        </ul>
      </section>

      {credentials.length > 0 && (
        <section
          className="rounded-xl border border-amber-300 bg-amber-50 p-6 shadow-sm"
          data-testid="new-credentials"
        >
          <h3 className="mb-1 font-bold text-amber-900">حسابات جديدة — بيانات الدخول</h3>
          <p className="mb-3 text-sm font-medium leading-6 text-amber-800">
            تظهر هذه التفاصيل مرة واحدة فقط. كلمة المرور الأولية لكل {schoolType === "GIRLS" ? "معلمة" : "معلم"} هي رقم الجوال بصيغة 05XXXXXXXX، ويجب تغييرها فور أول دخول قبل استخدام المنصة.
          </p>
          <ul className="space-y-2">
            {credentials.map((c, index) => (
              <li
                key={index}
                className="rounded-lg border border-amber-200 bg-white p-3 text-sm"
              >
                <p className="font-bold">{c.name}</p>
                <p className="text-slate-600">
                  الجوال: <span dir="ltr">{c.mobile_masked}</span>
                </p>
                <p className="text-slate-600">
                  كلمة المرور الأولية (رقم الجوال):{" "}
                  <code
                    dir="ltr"
                    className="rounded bg-slate-100 px-2 py-0.5 font-mono"
                    data-testid={`temp-password-${index}`}
                  >
                    {c.temporary_password}
                  </code>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Link to="/staff">
        <Button>عرض الموظفين</Button>
      </Link>
    </div>
  );
}
