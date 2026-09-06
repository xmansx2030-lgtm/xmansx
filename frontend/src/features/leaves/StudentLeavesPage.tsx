import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  CheckCircle2,
  Clock3,
  DoorOpen,
  FileText,
  Search,
  ShieldCheck,
  UserRoundCheck,
  XCircle,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  cancelStudentLeave,
  createStudentLeave,
  getStudentLeaves,
  type StudentLeaveRow,
  type StudentLeaveStatus,
} from "@/features/leaves/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import { getStudents, type StudentRow } from "@/features/students/api";
import { localIsoDate } from "@/utils/dates";
import { roleLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

function currentTime() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

function dateLabel(value: string) {
  if (!value) return "جميع التواريخ";
  return new Intl.DateTimeFormat("ar-SA", { dateStyle: "medium" }).format(
    new Date(`${value}T12:00:00`),
  );
}

function weekdayLabel(value: string) {
  if (!value) return "جميع الأيام";
  return new Intl.DateTimeFormat("ar-SA", { weekday: "long" }).format(
    new Date(`${value}T12:00:00`),
  );
}

export function StudentLeavesPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const student = studentLabel(schoolType, true);
  const students = studentPluralLabel(schoolType);
  const queryClient = useQueryClient();
  const today = localIsoDate(new Date());
  const canManage = me.data?.roles.some(
    (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL",
  ) ?? false;
  const [date, setDate] = useState(today);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StudentLeaveStatus | "">("");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [created, setCreated] = useState<StudentLeaveRow | null>(null);

  const leaves = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-leaves", { date, search, status, page }),
    queryFn: ({ signal }) => getStudentLeaves({ date, search, status, page }, signal),
    enabled: schoolId > 0 && canManage,
    placeholderData: (previous) => previous,
  });

  const refresh = () => Promise.all([
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "student-leaves"),
    }),
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "dashboard"),
    }),
  ]);

  if (me.isSuccess && !canManage) return null;

  const totalPages = Math.max(1, Math.ceil((leaves.data?.count ?? 0) / 25));
  const summary = leaves.data?.summary ?? { total: 0, active: 0, cancelled: 0 };

  return (
    <div className="space-y-5" data-testid="student-leaves-page">
      <PageHeader
        icon={DoorOpen}
        eyebrow={`شؤون ${students}`}
        title={`استئذانات ${students}`}
        description={`تسجيل خروج ${student} بدقة وحفظ السبب والوقت والتاريخ داخل ${schoolType === "GIRLS" ? "سجلها" : "سجله"} الموحد.`}
        tone="executive"
        badge={me.data?.roles.includes("VICE_PRINCIPAL") ? `مساحة ${roleLabel("VICE_PRINCIPAL", me.data.active_school?.school_type)}` : "إشراف الإدارة"}
        actions={(
          <Button variant="header" onClick={() => { setCreated(null); setFormOpen(true); }}>
            <UserRoundCheck aria-hidden size={17} /> تسجيل استئذان
          </Button>
        )}
      >
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-300">
          <span className="inline-flex items-center gap-1.5"><ShieldCheck aria-hidden size={14} /> كل عملية مرتبطة بالموظف المنفذ</span>
          <span className="inline-flex items-center gap-1.5"><FileText aria-hidden size={14} /> محفوظة تلقائيًا في ملف {student}</span>
        </div>
      </PageHeader>

      {created && (
        <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          <span className="inline-flex items-center gap-2 font-bold"><CheckCircle2 aria-hidden size={19} /> تم تسجيل استئذان {created.student.full_name} وحفظه في ملفه.</span>
          <Link className="font-bold text-emerald-800 underline" to={`/students/${created.student.id}/attendance`}>فتح ملف {student}</Link>
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-3" aria-label="ملخص الاستئذانات">
        <SummaryCard label="إجمالي اليوم" value={summary.total} icon={CalendarDays} tone="blue" />
        <SummaryCard label="استئذانات سارية" value={summary.active} icon={DoorOpen} tone="emerald" />
        <SummaryCard label="استئذانات ملغاة" value={summary.cancelled} icon={XCircle} tone="slate" />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5" aria-label="البحث والتصفية">
        <div className="grid gap-3 md:grid-cols-[13rem_minmax(0,1fr)_12rem]">
          <label className="text-sm font-bold text-slate-700">التاريخ
            <input type="date" value={date} onChange={(event) => { setDate(event.target.value); setPage(1); }} className="mt-1 h-11 w-full rounded-xl border border-slate-300 px-3" />
          </label>
          <label className="text-sm font-bold text-slate-700">بحث عن {studentLabel(schoolType)}
            <span className="relative mt-1 block">
              <Search aria-hidden size={17} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="الاسم أو الرقم الطلابي" className="h-11 w-full rounded-xl border border-slate-300 pr-10 pl-3" />
            </span>
          </label>
          <label className="text-sm font-bold text-slate-700">الحالة
            <select value={status} onChange={(event) => { setStatus(event.target.value as StudentLeaveStatus | ""); setPage(1); }} className="mt-1 h-11 w-full rounded-xl border border-slate-300 px-3">
              <option value="">جميع الحالات</option>
              <option value="ACTIVE">ساري</option>
              <option value="CANCELLED">ملغى</option>
            </select>
          </label>
        </div>
      </section>

      {leaves.isPending && <div className="grid min-h-48 place-items-center"><Spinner /></div>}
      {leaves.isError && <ErrorState error={leaves.error} />}
      {leaves.data && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="سجل الاستئذانات">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div><h2 className="font-black text-slate-900">سجل {dateLabel(date)}</h2><p className="mt-1 text-xs text-slate-500">{weekdayLabel(date)} · {leaves.data.count} سجل</p></div>
            {leaves.isFetching && <span className="text-xs text-blue-700">جارٍ التحديث...</span>}
          </div>
          {leaves.data.results.length === 0 ? (
            <div className="px-5 py-14 text-center"><DoorOpen aria-hidden size={30} className="mx-auto text-slate-300" /><h3 className="mt-3 font-black text-slate-800">لا توجد استئذانات مطابقة</h3><p className="mt-1 text-sm text-slate-500">يمكن تسجيل أول استئذان من الزر أعلى الصفحة.</p></div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {leaves.data.results.map((leave) => <LeaveRow key={leave.id} leave={leave} onChanged={refresh} />)}
            </ul>
          )}
          {leaves.data.results.length > 0 && (
            <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 p-3 px-5 text-xs text-slate-500">
              <span>صفحة {page} من {totalPages}</span>
              <div className="flex gap-2"><Button variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>السابق</Button><Button variant="secondary" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>التالي</Button></div>
            </div>
          )}
        </section>
      )}

      {formOpen && (
        <LeaveForm
          today={today}
          schoolType={schoolType}
          onClose={() => setFormOpen(false)}
          onCreated={(leave) => { setCreated(leave); setFormOpen(false); setDate(leave.leave_date); void refresh(); }}
        />
      )}
    </div>
  );
}

function LeaveForm({ today, schoolType, onClose, onCreated }: { today: string; schoolType: "BOYS" | "GIRLS"; onClose: () => void; onCreated: (leave: StudentLeaveRow) => void }) {
  const [student, setStudent] = useState<StudentRow | null>(null);
  const [leaveDate, setLeaveDate] = useState(today);
  const [leaveTime, setLeaveTime] = useState(currentTime);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => createStudentLeave({ student_id: student!.id, leave_date: leaveDate, leave_time: leaveTime, reason: reason.trim() }),
    onSuccess: onCreated,
    onError: (value) => setError(value instanceof ApiError ? value.message : "تعذر تسجيل الاستئذان."),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!student) { setError(`اختر ${studentLabel(schoolType, true)} أولًا.`); return; }
    if (!leaveDate || !leaveTime || reason.trim().length < 3) { setError("أكمل التاريخ والوقت وسبب الاستئذان."); return; }
    setError(null);
    create.mutate();
  }

  return (
    <Modal title={`تسجيل استئذان ${studentLabel(schoolType)}`} description={`ستُحفظ البيانات فورًا داخل ملف ${studentLabel(schoolType, true)}.`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <StudentSearch schoolType={schoolType} selected={student} onSelect={setStudent} onClear={() => setStudent(null)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-bold text-slate-700">تاريخ الاستئذان *
            <input aria-label="تاريخ الاستئذان" type="date" max={today} value={leaveDate} onChange={(event) => setLeaveDate(event.target.value)} className="mt-1 h-11 w-full rounded-xl border border-slate-300 px-3" />
            <span className="mt-1 block text-xs font-medium text-blue-700">اليوم: {weekdayLabel(leaveDate)}</span>
          </label>
          <label className="text-sm font-bold text-slate-700">وقت خروج {studentLabel(schoolType, true)} *
            <input aria-label={`وقت خروج ${studentLabel(schoolType, true)}`} type="time" value={leaveTime} onChange={(event) => setLeaveTime(event.target.value)} className="mt-1 h-11 w-full rounded-xl border border-slate-300 px-3" />
          </label>
        </div>
        <label className="block text-sm font-bold text-slate-700">سبب الاستئذان *
          <textarea aria-label="سبب الاستئذان" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} rows={4} placeholder={`اكتب السبب بوضوح ليظهر في سجل ${studentLabel(schoolType, true)}...`} className="mt-1 w-full rounded-xl border border-slate-300 p-3 font-normal leading-6" />
          <span className="mt-1 block text-end text-xs font-medium text-slate-400">{reason.length}/500</span>
        </label>
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-slate-100 pt-4"><Button variant="secondary" onClick={onClose} disabled={create.isPending}>إلغاء</Button><Button type="submit" disabled={create.isPending}><DoorOpen aria-hidden size={17} />{create.isPending ? "جارٍ التسجيل..." : "اعتماد الاستئذان"}</Button></div>
      </form>
    </Modal>
  );
}

function StudentSearch({ schoolType, selected, onSelect, onClear }: { schoolType: "BOYS" | "GIRLS"; selected: StudentRow | null; onSelect: (student: StudentRow) => void; onClear: () => void }) {
  const schoolId = useActiveSchoolId();
  const [term, setTerm] = useState("");
  const students = useQuery({
    queryKey: schoolScopedKey(schoolId, "leave-student-search", term),
    queryFn: ({ signal }) => getStudents({ search: term, status: "ACTIVE" }, signal),
    enabled: !selected && term.trim().length >= 2,
  });
  if (selected) return <div className="flex items-center justify-between gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4"><div><p className="text-xs font-bold text-blue-700">{studentLabel(schoolType, true)} {schoolType === "GIRLS" ? "المختارة" : "المختار"}</p><p className="mt-1 font-black text-slate-900">{selected.full_name}</p><p className="mt-1 text-xs text-slate-500">{selected.grade?.name ?? "—"} / {selected.section?.name ?? "—"}</p></div><Button variant="secondary" onClick={onClear}>تغيير {studentLabel(schoolType, true)}</Button></div>;
  return <div><label className="text-sm font-bold text-slate-700">{studentLabel(schoolType, true)} *<span className="relative mt-1 block"><Search aria-hidden size={17} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" /><input aria-label={`بحث عن ${studentLabel(schoolType, true)}`} value={term} onChange={(event) => setTerm(event.target.value)} autoFocus placeholder={`اكتب حرفين على الأقل من اسم ${studentLabel(schoolType, true)}`} className="h-11 w-full rounded-xl border border-slate-300 pr-10 pl-3 font-normal" /></span></label>{students.isFetching && <p className="mt-2 text-xs text-slate-500">جارٍ البحث...</p>}{students.data && <ul className="mt-2 max-h-52 divide-y overflow-y-auto rounded-xl border border-slate-200">{students.data.results.map((row) => <li key={row.id}><button type="button" data-testid={`leave-pick-student-${row.id}`} onClick={() => onSelect(row)} className="flex w-full items-center justify-between gap-3 p-3 text-start hover:bg-blue-50"><span><strong className="block text-sm text-slate-900">{row.full_name}</strong><span className="mt-1 block text-xs text-slate-500">{row.grade?.name ?? "—"} / {row.section?.name ?? "—"}</span></span><span dir="ltr" className="text-xs text-slate-400">{row.student_number ?? row.national_id_masked}</span></button></li>)}{students.data.results.length === 0 && <li className="p-4 text-center text-sm text-slate-500">لا توجد {studentLabel(schoolType)} مطابقة.</li>}</ul>}</div>;
}

function LeaveRow({ leave, onChanged }: { leave: StudentLeaveRow; onChanged: () => Promise<unknown> }) {
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const cancel = useMutation({ mutationFn: () => cancelStudentLeave(leave.id, reason.trim()), onSuccess: async () => { setCancelOpen(false); setReason(""); await onChanged(); } });
  return <li className={`p-4 sm:p-5 ${leave.status === "CANCELLED" ? "bg-slate-50/70" : ""}`} data-testid={`student-leave-${leave.id}`}><div className="grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1.5fr)_auto]"><div><div className="flex flex-wrap items-center gap-2"><Link to={`/students/${leave.student.id}/attendance`} className="font-black text-slate-900 hover:text-blue-700">{leave.student.full_name}</Link><span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${leave.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>{leave.status_label}</span></div><p className="mt-2 text-xs text-slate-500">{leave.grade_name || "—"} / {leave.section_name || "—"}{leave.student.student_number ? ` · ${leave.student.student_number}` : ""}</p></div><div><p className="text-sm leading-6 text-slate-800">{leave.reason}</p><p className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500"><span className="inline-flex items-center gap-1"><CalendarDays aria-hidden size={14} />{leave.weekday_label}، {dateLabel(leave.leave_date)}</span><span className="inline-flex items-center gap-1 font-bold text-blue-800"><Clock3 aria-hidden size={14} />{leave.leave_time}</span><span>سجله: {leave.recorded_by_name ?? "—"}</span></p>{leave.cancellation_reason && <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">سبب الإلغاء: {leave.cancellation_reason}</p>}</div><div className="flex items-start justify-end">{leave.status === "ACTIVE" && <Button variant="secondary" className="border-red-200 text-red-700" onClick={() => setCancelOpen(true)}>إلغاء الاستئذان</Button>}</div></div>{cancelOpen && <Modal title={`إلغاء استئذان ${leave.student.full_name}`} description="سيبقى السجل محفوظًا مع سبب الإلغاء." onClose={() => setCancelOpen(false)}><label className="text-sm font-bold text-slate-700">سبب الإلغاء *<textarea aria-label="سبب إلغاء الاستئذان" value={reason} onChange={(event) => setReason(event.target.value)} rows={3} maxLength={300} className="mt-2 w-full rounded-xl border border-slate-300 p-3 font-normal" /></label>{cancel.isError && <ErrorState error={cancel.error} />}<div className="mt-5 flex justify-end gap-2"><Button variant="secondary" onClick={() => setCancelOpen(false)}>تراجع</Button><Button variant="danger" disabled={reason.trim().length < 3 || cancel.isPending} onClick={() => cancel.mutate()}>{cancel.isPending ? "جارٍ الإلغاء..." : "تأكيد الإلغاء"}</Button></div></Modal>}</li>;
}

function SummaryCard({ label, value, icon: Icon, tone }: { label: string; value: number; icon: typeof DoorOpen; tone: "blue" | "emerald" | "slate" }) {
  const colors = { blue: "bg-blue-50 text-blue-700", emerald: "bg-emerald-50 text-emerald-700", slate: "bg-slate-100 text-slate-600" }[tone];
  return <article className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><span className={`grid size-11 place-items-center rounded-xl ${colors}`}><Icon aria-hidden size={21} /></span><div><p className="text-xs font-bold text-slate-500">{label}</p><strong className="mt-1 block text-2xl font-black text-slate-900">{value}</strong></div></article>;
}
