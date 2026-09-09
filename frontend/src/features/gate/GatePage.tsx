import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clock3,
  DoorOpen,
  Hash,
  RefreshCw,
  Search,
  ShieldCheck,
  UserRoundCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useDeferredValue, useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import {
  confirmGateRelease,
  getGateStudentLeaves,
  type GateStudentLeave,
} from "@/features/gate/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import { studentLabel, studentPluralLabel } from "@/utils/roles";

type GateTab = "pending" | "released";

function useOnlineStatus() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const onlineListener = () => setOnline(true);
    const offlineListener = () => setOnline(false);
    window.addEventListener("online", onlineListener);
    window.addEventListener("offline", offlineListener);
    return () => {
      window.removeEventListener("online", onlineListener);
      window.removeEventListener("offline", offlineListener);
    };
  }, []);
  return online;
}

function timeLabel(value: string) {
  const [hour = "0", minute = "0"] = value.split(":");
  const date = new Date(2000, 0, 1, Number(hour), Number(minute));
  return date.toLocaleTimeString("ar-SA", { hour: "numeric", minute: "2-digit" });
}

function releasedTimeLabel(value: string) {
  return new Date(value).toLocaleTimeString("ar-SA", { hour: "numeric", minute: "2-digit" });
}

export function GatePage() {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const online = useOnlineStatus();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<GateTab>("pending");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [selected, setSelected] = useState<GateStudentLeave | null>(null);

  const queryKey = schoolScopedKey(schoolId, "gate-student-leaves", deferredSearch);
  const leaves = useQuery({
    queryKey,
    queryFn: ({ signal }) => getGateStudentLeaves(deferredSearch, signal),
    enabled: schoolId > 0,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

  const release = useMutation({
    mutationFn: (leaveId: number) => confirmGateRelease(leaveId),
    onSuccess: async () => {
      setSelected(null);
      await queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "gate-student-leaves"),
      });
    },
  });

  const rows = (leaves.data?.results ?? []).filter((row) =>
    tab === "pending" ? row.gate_release === null : row.gate_release !== null,
  );
  const students = studentPluralLabel(schoolType);
  const student = studentLabel(schoolType, true);

  return (
    <div className="space-y-5" data-testid="gate-page">
      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-l from-slate-950 via-teal-950 to-emerald-900 p-5 text-white shadow-xl shadow-emerald-950/15 sm:p-7">
        <div aria-hidden className="absolute -left-12 -top-20 size-56 rounded-full bg-emerald-300/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div className="flex items-start gap-4">
            <span className="grid size-13 shrink-0 place-items-center rounded-2xl bg-white/10 text-emerald-200 ring-1 ring-white/15">
              <DoorOpen aria-hidden size={27} />
            </span>
            <div>
              <p className="text-xs font-bold text-emerald-200">محطة حارس البوابة</p>
              <h1 className="mt-1 text-2xl font-black sm:text-3xl">خروج {students}</h1>
              <p className="mt-2 text-sm leading-6 text-emerald-50/80">تحقق من البيانات ثم سجّل الخروج الفعلي من المدرسة.</p>
            </div>
          </div>
          <span className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-2 text-xs font-black ring-1 ${online ? "bg-emerald-400/15 text-emerald-100 ring-emerald-300/25" : "bg-red-400/15 text-red-100 ring-red-300/25"}`}>
            {online ? <Wifi aria-hidden size={15} /> : <WifiOff aria-hidden size={15} />}
            {online ? "متصل — القائمة محدثة" : "غير متصل — التأكيد متوقف"}
          </span>
        </div>
      </header>

      {!online && (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
          <WifiOff aria-hidden size={20} className="mt-0.5 shrink-0" />
          <div><p className="font-black">تعذر الاتصال بالخادم</p><p className="mt-1">لا تعتمد البيانات الظاهرة، ولن يُسمح بتسجيل أي خروج حتى يعود الاتصال.</p></div>
        </div>
      )}

      <section className="grid grid-cols-2 gap-3" aria-label="ملخص البوابة اليوم">
        <SummaryButton active={tab === "pending"} label="بانتظار الخروج" value={leaves.data?.summary.pending ?? 0} onClick={() => setTab("pending")} />
        <SummaryButton active={tab === "released"} label="خرج اليوم" value={leaves.data?.summary.released ?? 0} onClick={() => setTab("released")} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4">
        <div className="flex gap-2">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">بحث عن {student}</span>
            <Search aria-hidden size={18} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input aria-label={`بحث عن ${student}`} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`اسم ${student} أو الرقم الطلابي`} className="h-12 w-full rounded-xl border border-slate-300 bg-slate-50 pr-10 pl-3 text-base outline-none focus:border-emerald-500 focus:bg-white focus:ring-3 focus:ring-emerald-100" />
          </label>
          <button type="button" aria-label="تحديث القائمة" title="تحديث القائمة" disabled={leaves.isFetching || !online} onClick={() => void leaves.refetch()} className="grid size-12 shrink-0 place-items-center rounded-xl border border-slate-300 bg-white text-slate-600 disabled:opacity-50">
            <RefreshCw aria-hidden size={19} className={leaves.isFetching ? "animate-spin" : ""} />
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">تتحدث القائمة تلقائيًا كل 15 ثانية وتصل إلى جميع حراس المدرسة.</p>
      </section>

      {leaves.isPending ? (
        <div className="grid min-h-48 place-items-center"><Spinner label="جارٍ تحميل استئذانات اليوم..." /></div>
      ) : leaves.isError ? (
        <ErrorState error={leaves.error} />
      ) : rows.length === 0 ? (
        <section className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-100 text-slate-500"><CheckCircle2 aria-hidden size={27} /></span>
          <h2 className="mt-4 text-lg font-black text-slate-900">{tab === "pending" ? "لا توجد حالات بانتظار الخروج" : `لم يخرج أي ${studentLabel(schoolType)} بعد`}</h2>
          <p className="mt-2 text-sm text-slate-500">{search ? "جرّب مسح البحث لعرض بقية القائمة." : "ستظهر الاستئذانات المعتمدة هنا تلقائيًا."}</p>
        </section>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {rows.map((row) => (
            <GateLeaveCard key={row.id} leave={row} online={online} schoolType={schoolType} onRelease={() => { release.reset(); setSelected(row); }} />
          ))}
        </ul>
      )}

      {selected && (
        <Modal title={`تأكيد خروج ${selected.student.full_name}`} description={`تحقق من ${student} وبيانات المستلم قبل السماح بالخروج.`} onClose={() => { if (!release.isPending) setSelected(null); }}>
          <div className="space-y-3">
            <StudentIdentity leave={selected} />
            <RecipientDetails leave={selected} />
            <div className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm leading-6 text-amber-900"><ShieldCheck aria-hidden size={18} className="mt-1 shrink-0" />سيُسجّل اسمك ووقت الخروج من الخادم، ولا يمكن إلغاء الاستئذان بعد التأكيد.</div>
            {release.isError && <ErrorState error={release.error} />}
          </div>
          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => setSelected(null)} disabled={release.isPending}>تراجع</Button>
            <Button className="min-h-12 bg-emerald-600 text-base hover:bg-emerald-700" disabled={!online || release.isPending} onClick={() => release.mutate(selected.id)}>
              <UserRoundCheck aria-hidden size={20} />{release.isPending ? "جارٍ تسجيل الخروج..." : "تم التحقق والسماح بالخروج"}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function SummaryButton({ active, label, value, onClick }: { active: boolean; label: string; value: number; onClick: () => void }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`rounded-2xl border p-4 text-start shadow-sm transition ${active ? "border-emerald-300 bg-emerald-50 ring-2 ring-emerald-100" : "border-slate-200 bg-white hover:border-slate-300"}`}><span className="text-xs font-bold text-slate-600">{label}</span><strong className={`mt-1 block text-3xl font-black ${active ? "text-emerald-800" : "text-slate-900"}`}>{value}</strong></button>;
}

function GateLeaveCard({ leave, online, schoolType, onRelease }: { leave: GateStudentLeave; online: boolean; schoolType: "BOYS" | "GIRLS"; onRelease: () => void }) {
  const released = leave.gate_release !== null;
  return (
    <li className={`overflow-hidden rounded-3xl border bg-white shadow-sm ${released ? "border-emerald-200" : "border-slate-200"}`} data-testid={`gate-leave-${leave.id}`}>
      <div className="p-5">
        <div className="flex items-start justify-between gap-3"><StudentIdentity leave={leave} /><span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-black ${released ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{released ? "خرج" : "بانتظار الخروج"}</span></div>
        <div className="mt-4 grid grid-cols-2 gap-2 rounded-2xl bg-slate-50 p-3 text-sm"><span className="flex items-center gap-2 text-slate-600"><Clock3 aria-hidden size={17} />الوقت المصرح</span><strong className="text-end text-slate-900">{timeLabel(leave.leave_time)}</strong><span className="text-slate-500">اعتمده</span><span className="text-end font-bold text-slate-700">{leave.recorded_by_name ?? "إدارة المدرسة"}</span></div>
        <RecipientDetails leave={leave} compact />
      </div>
      {released ? (
        <div className="border-t border-emerald-100 bg-emerald-50 px-5 py-4 text-sm text-emerald-900"><p className="flex items-center gap-2 font-black"><CheckCircle2 aria-hidden size={18} />سُجّل الخروج {releasedTimeLabel(leave.gate_release!.released_at)}</p><p className="mt-1 text-xs">بواسطة {leave.gate_release!.released_by_name ?? "حارس البوابة"}</p></div>
      ) : (
        <div className="border-t border-slate-100 p-4"><Button className="min-h-13 w-full bg-emerald-600 text-base hover:bg-emerald-700" disabled={!online} onClick={onRelease}><UserRoundCheck aria-hidden size={21} />تحقق واسمح بخروج {studentLabel(schoolType, true)}</Button></div>
      )}
    </li>
  );
}

function StudentIdentity({ leave }: { leave: GateStudentLeave }) {
  return <div className="min-w-0"><h2 className="text-lg font-black text-slate-950">{leave.student.full_name}</h2><p className="mt-1 text-sm font-medium text-slate-600">{leave.grade_name || "الصف غير محدد"} · فصل {leave.section_name || "—"}</p><p dir="ltr" className="mt-2 inline-flex items-center gap-1 rounded-lg bg-blue-50 px-2 py-1 font-mono text-xs font-bold text-blue-800"><Hash aria-hidden size={14} />{leave.student.student_number || "لا يوجد رقم طلابي"}</p></div>;
}

function RecipientDetails({ leave, compact = false }: { leave: GateStudentLeave; compact?: boolean }) {
  const hasDetails = Boolean(leave.recipient_name || leave.recipient_relationship || leave.recipient_id_last4);
  return <div className={`${compact ? "mt-3" : ""} rounded-2xl border ${hasDetails ? "border-blue-100 bg-blue-50/70" : "border-slate-200 bg-slate-50"} p-3`}><p className="flex items-center gap-2 text-xs font-black text-slate-700"><UserRoundCheck aria-hidden size={16} />بيانات المستلم</p>{hasDetails ? <div className="mt-2 grid gap-1 text-sm text-slate-800"><p><span className="text-slate-500">الاسم:</span> {leave.recipient_name || "غير محدد"}</p><p><span className="text-slate-500">الصفة:</span> {leave.recipient_relationship || "غير محددة"}</p><p><span className="text-slate-500">آخر الهوية:</span> <strong dir="ltr" className="font-mono tracking-widest">•••• {leave.recipient_id_last4 || "غير مسجل"}</strong></p></div> : <p className="mt-2 text-xs text-slate-500">لم تُسجّل بيانات مستلم لهذا الاستئذان.</p>}</div>;
}
