import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ClipboardCheck, Search, ShieldCheck, UserRoundPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import type {
  AttendanceSessionData,
  AttendanceStartSource,
  MarkInput,
  RosterStudent,
  SessionMarkStatus,
} from "@/features/attendance/api";
import {
  editSession,
  getAttendancePreview,
  getSession,
  startSession,
  submitSession,
} from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { ReferralCreateCard } from "@/features/referrals/ReferralCreateCard";
import { studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

/** حالة الطالب محليًا — «حاضر» هو الافتراضي ولا يرسل للخادم (استثناءات فقط). */
type LocalStatus = "PRESENT" | SessionMarkStatus;
type TeacherAttendanceStatus = "PRESENT" | "ABSENT";

interface LocalMark {
  status: LocalStatus;
  arrival_time: string;
}

const STATUS_LABELS: Record<LocalStatus, string> = {
  PRESENT: "حاضر",
  ABSENT: "غائب",
  LATE: "متأخر",
};

const FEMININE_STATUS_LABELS: Record<LocalStatus, string> = {
  PRESENT: "حاضرة",
  ABSENT: "غائبة",
  LATE: "متأخرة",
};

function marksFromSession(session: AttendanceSessionData): Record<number, LocalMark> {
  const map: Record<number, LocalMark> = {};
  for (const mark of session.marks) {
    map[mark.student_id] = {
      status: mark.status,
      arrival_time: mark.arrival_time ?? "",
    };
  }
  return map;
}

function buildPayload(marks: Record<number, LocalMark>, roster: RosterStudent[]): MarkInput[] {
  const rosterIds = new Set(roster.map((s) => s.student_id));
  return Object.entries(marks)
    .filter(([id, mark]) => mark.status === "ABSENT" && rosterIds.has(Number(id)))
    .map(([id]) => ({
      student_id: Number(id),
      status: "ABSENT" as const,
    }));
}

export function AttendanceSessionPage() {
  const { sectionId } = useParams();
  const location = useLocation();
  const me = useMe();
  const queryClient = useQueryClient();
  const activeSchoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const studentsLabel = studentPluralLabel(schoolType);
  const statusLabels = schoolType === "GIRLS" ? FEMININE_STATUS_LABELS : STATUS_LABELS;

  const navigationSource = (location.state as { attendanceSource?: AttendanceStartSource } | null)
    ?.attendanceSource;
  const startSource: AttendanceStartSource =
    navigationSource === "SECTION_LIST" || navigationSource === "QR"
      ? navigationSource
      : "DIRECT_LINK";

  const previewQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "session-preview", sectionId),
    queryFn: ({ signal }) => getAttendancePreview(Number(sectionId), signal),
    enabled: activeSchoolId > 0,
    staleTime: 15_000,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const [session, setSession] = useState<AttendanceSessionData | null>(null);
  const [marks, setMarks] = useState<Record<number, LocalMark>>({});
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [rosterNotice, setRosterNotice] = useState(false);
  const [rosterSearch, setRosterSearch] = useState("");
  const [exceptionsOnly, setExceptionsOnly] = useState(false);
  // م13 — تحويل طالب من قائمة الفصل إلى المرشد
  const [referralTarget, setReferralTarget] = useState<{
    id: number;
    name: string;
  } | null>(null);
  const [referralDone, setReferralDone] = useState<string | null>(null);

  // مزامنة أثناء العرض (نمط adjusting state during render) — مرة واحدة لكل جلسة
  const [loadedSessionId, setLoadedSessionId] = useState<number | null>(null);
  if (previewQuery.data?.session && previewQuery.data.session.id !== loadedSessionId) {
    setLoadedSessionId(previewQuery.data.session.id);
    setSession(previewQuery.data.session);
    setMarks(marksFromSession(previewQuery.data.session));
  }

  const startMutation = useMutation({
    mutationFn: () => startSession(Number(sectionId), startSource),
    onSuccess: async (started) => {
      setLoadedSessionId(started.id);
      setSession(started);
      setMarks(marksFromSession(started));
      await queryClient.invalidateQueries({
        queryKey: schoolScopedKey(activeSchoolId, "dashboard"),
      });
    },
  });

  const roster = useMemo(() => session?.roster ?? [], [session]);
  const summary = useMemo(() => {
    let absent = 0;
    let late = 0;
    for (const student of roster) {
      const status = marks[student.student_id]?.status ?? "PRESENT";
      if (status === "ABSENT") absent += 1;
      if (status === "LATE") late += 1;
    }
    return { absent, late, present: roster.length - absent - late };
  }, [roster, marks]);
  const displayedRoster = useMemo(() => {
    const term = rosterSearch.trim().toLocaleLowerCase("ar");
    return roster.filter((student) => {
      const status = marks[student.student_id]?.status ?? "PRESENT";
      const matchesSearch =
        term.length === 0 ||
        student.full_name.toLocaleLowerCase("ar").includes(term) ||
        student.national_id_masked.includes(term);
      return matchesSearch && (!exceptionsOnly || status === "ABSENT");
    });
  }, [exceptionsOnly, marks, roster, rosterSearch]);

  if (previewQuery.isPending || me.isPending) {
    return <Spinner label="جارٍ عرض بيانات الفصل..." />;
  }
  if (previewQuery.isError) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <ErrorState error={previewQuery.error} />
        <p className="mt-3">
          <Link to="/" className="text-blue-700 underline">
            العودة للرئيسية
          </Link>
        </p>
      </section>
    );
  }
  if (!session && previewQuery.data) {
    const preview = previewQuery.data;
    const sectionTitle = `${preview.section.grade_name} / ${preview.section.name}`;
    return (
      <div className="space-y-4">
        <PageHeader
          icon={ClipboardCheck}
          eyebrow="معاينة الفصل"
          title={<span data-testid="preview-section-name">{sectionTitle}</span>}
          description="راجع بيانات الفصل والحصة قبل إنشاء جلسة التحضير. لن يظهر الفصل قيد التحضير إلا بعد التأكيد أدناه."
          tone="teacher"
          badge="لم يبدأ"
          meta={<><span>{preview.period.name}</span><span className="text-white/30">•</span><span dir="ltr">{preview.period.start_time} – {preview.period.end_time}</span><span className="text-white/30">•</span><span>{preview.attendance_date}</span></>}
          actions={(
            <Link
              to="/"
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15"
            >
              <ArrowRight aria-hidden size={17} />
              اختيار فصل آخر
            </Link>
          )}
        />

        <section
          className="rounded-3xl border border-teal-200 bg-white p-5 shadow-lg shadow-teal-950/5 sm:p-7"
          data-testid="attendance-start-confirmation"
        >
          <div className="flex items-start gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-teal-50 text-teal-700">
              <ShieldCheck aria-hidden size={24} />
            </span>
            <div>
              <h1 className="text-xl font-black text-slate-900">تأكيد الفصل قبل البدء</h1>
              <p className="mt-2 text-sm leading-7 text-slate-600">
                ستبدأ تحضير <strong className="text-slate-950">{sectionTitle}</strong> في {preview.period.name}،
                وعدد {studentsLabel} المسجلين {preview.section.students_count}.
              </p>
              <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900">
                لن تُنشأ جلسة ولن يظهر «قيد التحضير» للوكيل قبل ضغط زر البدء.
              </p>
            </div>
          </div>

          {startMutation.isError && <div className="mt-4"><ErrorState error={startMutation.error} /></div>}
          <div className="mt-6 flex flex-wrap items-center justify-end gap-2">
            <Link
              to="/"
              className="inline-flex min-h-10 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
            >
              إلغاء واختيار فصل آخر
            </Link>
            <Button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              data-testid="start-attendance"
            >
              {startMutation.isPending
                ? "جارٍ بدء التحضير..."
                : `بدء تحضير ${sectionTitle}`}
            </Button>
          </div>
        </section>
      </div>
    );
  }
  if (!session) return null;

  const marking = session.status === "IN_PROGRESS" || editing;

  const setStatus = (studentId: number, status: TeacherAttendanceStatus) => {
    setMarks((prev) => ({
      ...prev,
      [studentId]: {
        status,
        arrival_time: "",
      },
    }));
  };

  const beginEditing = () => {
    // أي LATE تاريخية تظهر عند القراءة فقط؛ عند بدء التصحيح تعامل كحضور
    // ما لم يختر المصحح «غائب» صراحةً.
    setMarks((prev) =>
      Object.fromEntries(
        Object.entries(prev).map(([studentId, mark]) => [
          studentId,
          mark.status === "LATE" ? { status: "PRESENT", arrival_time: "" } : mark,
        ]),
      ),
    );
    setEditing(true);
  };

  const handleSubmit = async () => {
    setPending(true);
    setActionError(null);
    setRosterNotice(false);
    try {
      const payload = buildPayload(marks, roster);
      const updated = editing
        ? await editSession(session.id, payload, reason)
        : await submitSession(session.id, payload);
      setSession(updated);
      setMarks(marksFromSession(updated));
      setEditing(false);
      setReason("");
      // إن كانت لوحة الإدارة مفتوحة في نفس التطبيق فتُحدّث فورًا؛ أما الأجهزة
      // الأخرى فتلتقط النتيجة عبر الاستعلام الحي القصير.
      await queryClient.invalidateQueries({
        queryKey: schoolScopedKey(activeSchoolId, "dashboard"),
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "ATTENDANCE_ROSTER_CHANGED") {
        // الخادم حدّث بصمة القائمة — نعيد فتح الجلسة لقائمة محدثة ونبقي العلامات الصالحة
        setRosterNotice(true);
        const refreshed = await getSession(session.id);
        if (refreshed) {
          setSession(refreshed);
          setMarks((prev) => {
            const validIds = new Set(refreshed.roster.map((s) => s.student_id));
            return Object.fromEntries(
              Object.entries(prev).filter(([id]) => validIds.has(Number(id))),
            );
          });
        }
      } else {
        setActionError(error);
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        icon={ClipboardCheck}
        eyebrow="جلسة التحضير"
        title={<span data-testid="session-section-name">{session.section.name} — {session.section.grade_name}</span>}
        description={`التحضير بخيارين فقط: ${schoolType === "GIRLS" ? "حاضرة أو غائبة" : "حاضر أو غائب"}. جميع ${studentsLabel} ${schoolType === "GIRLS" ? "حاضرات" : "حاضرون"} افتراضيًا حتى تحدد الغياب.`}
        tone="teacher"
        badge={session.status === "SUBMITTED" && !editing ? "تم الاعتماد" : editing ? "تعديل معتمد" : "قيد التحضير"}
        meta={<><span>{session.period.name}</span><span className="text-white/30">•</span><span dir="ltr">{session.period.start_time} – {session.period.end_time}</span><span className="text-white/30">•</span><span>{session.attendance_date}</span></>}
        actions={(
          <Link
            to={me.data?.roles.includes("TEACHER") ? "/" : "/attendance/monitoring"}
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            <ArrowRight aria-hidden size={17} />
            العودة للمتابعة
          </Link>
        )}
      >
        <div className="flex flex-wrap gap-2 text-sm" data-testid="live-summary">
          <span className="rounded-full bg-emerald-400/15 px-3 py-1 font-bold text-emerald-100 ring-1 ring-emerald-300/20">{statusLabels.PRESENT} {summary.present}</span>
          <span className="rounded-full bg-red-400/15 px-3 py-1 font-bold text-red-100 ring-1 ring-red-300/20">{statusLabels.ABSENT} {summary.absent}</span>
          {summary.late > 0 && (
            <span className="rounded-full bg-amber-400/15 px-3 py-1 font-bold text-amber-100 ring-1 ring-amber-300/20">تأخر تاريخي {summary.late}</span>
          )}
        </div>
      </PageHeader>

      {session.status === "SUBMITTED" && !editing && (
          <div
            className="rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900"
            data-testid="submitted-banner"
          >
            تم إرسال التحضير بواسطة {session.submitted_by ?? "—"}
            {session.submitted_at &&
              ` في ${new Date(session.submitted_at).toLocaleString("ar-SA")}`}
            {session.can_edit && (
              <Button
                variant="secondary"
                className="ms-3"
                onClick={beginEditing}
                data-testid="edit-button"
              >
                تعديل
              </Button>
            )}
          </div>
        )}

      {rosterNotice && (
        <p
          className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
          role="alert"
          data-testid="roster-changed-notice"
        >
          تغيرت قائمة الفصل منذ فتح الجلسة — حُدِّثت القائمة، راجع العلامات ثم أعد الإرسال.
        </p>
      )}

      {referralTarget && (
        <ReferralCreateCard
          // ‏key بالطالب: بدونه يعيد React استخدام النموذج نفسه عند اختيار طالب
          // آخر فتذهب الملاحظة (أو حالة التكرار) إلى ملف الطالب السابق
          key={referralTarget.id}
          student={{ id: referralTarget.id, name: referralTarget.name }}
          onCreated={() => {
            setReferralTarget(null);
            setReferralDone("تم إرسال الإحالة إلى المرشد.");
          }}
          onContributed={() => {
            setReferralTarget(null);
            setReferralDone("أضيفت ملاحظتك إلى ملف المتابعة المفتوح.");
          }}
          onCancel={() => setReferralTarget(null)}
        />
      )}
      {referralDone && (
        <p
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"
          data-testid="referral-done"
        >
          {referralDone}
        </p>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 bg-gradient-to-l from-slate-50 to-white p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-bold text-slate-900">قائمة {studentsLabel}</h2>
              <p className="mt-1 text-xs text-slate-500">
                يظهر {displayedRoster.length} من أصل {roster.length} {studentCountLabel(schoolType)}
              </p>
            </div>
            <button
              type="button"
              aria-pressed={exceptionsOnly}
              data-testid="exceptions-only"
              onClick={() => setExceptionsOnly((value) => !value)}
              className={`min-h-10 rounded-xl px-3 text-sm font-bold transition ${
                exceptionsOnly
                  ? "bg-slate-900 text-white shadow-sm"
                  : "border border-slate-200 bg-white text-slate-700 hover:border-slate-300"
              }`}
            >
              الغائبون فقط ({summary.absent})
            </button>
          </div>
          <label className="relative mt-4 block">
            <span className="sr-only">البحث في قائمة {studentsLabel}</span>
            <Search
              aria-hidden
              size={18}
              className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              type="search"
              value={rosterSearch}
              onChange={(event) => setRosterSearch(event.target.value)}
              placeholder={`ابحث باسم ${studentLabel(schoolType, true)} أو رقم الهوية المخفي`}
              className="min-h-11 w-full rounded-xl border border-slate-200 bg-white px-4 pe-10 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10"
              data-testid="roster-search"
            />
          </label>
        </div>

        <ul className="divide-y divide-slate-100" data-testid="roster-list">
          {displayedRoster.map((student) => {
            const mark = marks[student.student_id];
            const status = mark?.status ?? "PRESENT";
            return (
              <li
                key={student.student_id}
                className={`flex flex-wrap items-center justify-between gap-3 p-4 transition-colors sm:p-5 ${
                  status === "ABSENT"
                    ? "bg-red-50/50"
                    : status === "LATE"
                      ? "bg-amber-50/60"
                      : "hover:bg-slate-50/70"
                }`}
                data-testid={`roster-student-${student.student_id}`}
              >
                <div>
                  <p className="font-medium text-slate-800">{student.full_name}</p>
                  <p className="text-xs text-slate-400" dir="ltr">
                    {student.national_id_masked}
                  </p>
                  {/* م13: التحويل للمرشد من مكان ملاحظة المعلم للطالب فعليًا */}
                  <button
                    type="button"
                    className="mt-2 inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-blue-50 px-2.5 text-xs font-bold text-blue-700 transition hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                    onClick={() =>
                      setReferralTarget({
                        id: student.student_id,
                        name: student.full_name,
                      })
                    }
                    data-testid={`refer-student-${student.student_id}`}
                  >
                    <UserRoundPlus aria-hidden size={14} />
                    تحويل للمرشد
                  </button>
                </div>
                {marking ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {(["PRESENT", "ABSENT"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setStatus(student.student_id, option)}
                        aria-pressed={status === option}
                        className={`min-h-10 rounded-xl px-3 py-1.5 text-sm font-bold transition-all ${
                          status === option
                            ? option === "PRESENT"
                              ? "bg-green-600 text-white"
                              : "bg-red-600 text-white"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        }`}
                      >
                        {statusLabels[option]}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span
                    className={`rounded-full px-3 py-1 text-sm ${
                      status === "PRESENT"
                        ? "bg-green-100 text-green-800"
                        : status === "ABSENT"
                          ? "bg-red-100 text-red-800"
                          : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {statusLabels[status]}
                    {status === "LATE" &&
                      session.marks.find((m) => m.student_id === student.student_id)
                        ?.late_minutes != null &&
                      ` (${session.marks.find((m) => m.student_id === student.student_id)?.late_minutes} د)`}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
        {displayedRoster.length === 0 && (
          <div className="px-5 py-10 text-center" data-testid="no-roster-results">
            <p className="font-bold text-slate-700">لا يوجد {studentLabel(schoolType)} {schoolType === "GIRLS" ? "مطابقة" : "مطابق"}</p>
            <p className="mt-1 text-sm text-slate-500">
              غيّر البحث أو اعرض جميع {studentsLabel} للمتابعة.
            </p>
            <button
              type="button"
              onClick={() => {
                setRosterSearch("");
                setExceptionsOnly(false);
              }}
              className="mt-3 text-sm font-bold text-blue-700 hover:text-blue-800"
            >
              عرض جميع {studentsLabel}
            </button>
          </div>
        )}
      </section>

      {marking && (
        <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-lg shadow-slate-900/5 sm:p-5">
          {editing && (
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">سبب التعديل (اختياري)</span>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
                className="w-full rounded-lg border border-slate-300 px-3 py-2"
                data-testid="edit-reason"
              />
            </label>
          )}
          {actionError != null && <ErrorState error={actionError} />}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-500">
              سيُرسل غياب {summary.absent}، والبقية {schoolType === "GIRLS" ? "حاضرات" : "حاضرون"} تلقائيًا.
            </p>
            <div className="flex gap-2">
              <Button
                onClick={() => void handleSubmit()}
                disabled={pending}
                data-testid="submit-attendance"
              >
                {pending ? "جارٍ الإرسال..." : editing ? "حفظ التعديل" : "إرسال التحضير"}
              </Button>
              {editing && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setEditing(false);
                    setMarks(marksFromSession(session));
                    setActionError(null);
                  }}
                >
                  إلغاء
                </Button>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
