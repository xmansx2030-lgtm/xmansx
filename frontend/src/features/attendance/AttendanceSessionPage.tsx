import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ClipboardCheck, Search, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useBlocker, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

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
  getAdministrativePreview,
  getAttendancePreview,
  getSession,
  startSession,
  startAdministrativeSession,
  submitSession,
  submitAdministrativeSession,
} from "@/features/attendance/api";
import { sectionLabel } from "@/features/attendance/sectionLabel";
import { readDraft, removeDraft, writeDraft } from "@/features/attendance/drafts";
import { PendingAttendance } from "@/features/attendance/PendingAttendance";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

/** حالة الطالب محليًا — «حاضر» هو الافتراضي ولا يرسل للخادم (استثناءات فقط). */
type LocalStatus = "PRESENT" | SessionMarkStatus;
type TeacherAttendanceStatus = "PRESENT" | "ABSENT";

interface LocalMark {
  status: LocalStatus;
}

const STATUS_LABELS: Record<LocalStatus, string> = {
  PRESENT: "حاضر",
  ABSENT: "غائب",
};

const FEMININE_STATUS_LABELS: Record<LocalStatus, string> = {
  PRESENT: "حاضرة",
  ABSENT: "غائبة",
};

function marksFromSession(session: AttendanceSessionData): Record<number, LocalMark> {
  const map: Record<number, LocalMark> = {};
  for (const mark of session.marks) {
    map[mark.student_id] = {
      status: mark.status,
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
  const location = useLocation();
  const me = useMe();
  const context = new URLSearchParams(location.search);
  context.delete("session"); // Binding an opened session must not remount and discard live state.
  return <AttendanceSessionForm key={`${me.data?.id ?? 0}:${me.data?.active_school?.id ?? 0}:${location.pathname}?${context}`} />;
}

function AttendanceSessionForm() {
  const { sectionId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const me = useMe();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const activeSchoolId = me.data?.active_school?.id ?? 0;
  const draftScope = { userId: me.data?.id ?? 0, schoolId: activeSchoolId };
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const studentsLabel = studentPluralLabel(schoolType);
  const statusLabels = schoolType === "GIRLS" ? FEMININE_STATUS_LABELS : STATUS_LABELS;
  const canPrepareAdministratively = me.data?.roles.some((role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL") ?? false;
  const requestedAdministrativeContext = searchParams.has("period") || searchParams.has("date");
  const administrative = canPrepareAdministratively && (requestedAdministrativeContext || !me.data?.roles.includes("TEACHER"));
  const target = { date: searchParams.get("date") ?? "", period_sequence: Number(searchParams.get("period")) };
  const validTarget = /^\d{4}-\d{2}-\d{2}$/.test(target.date) && Number.isInteger(target.period_sequence) && target.period_sequence > 0;
  const selectedSessionId = searchParams.has("session") ? Number(searchParams.get("session")) : null;
  const validSessionId = selectedSessionId === null || (Number.isSafeInteger(selectedSessionId) && selectedSessionId > 0);
  const invalidatePreparation = async () => {
    // Corrections also change student profiles, reports and excuse coverage.
    await queryClient.invalidateQueries({ queryKey: schoolScopedKey(activeSchoolId) });
  };

  const navigationSource = (location.state as { attendanceSource?: AttendanceStartSource } | null)
    ?.attendanceSource;
  const startSource: AttendanceStartSource =
    navigationSource === "SECTION_LIST" || navigationSource === "QR"
      ? navigationSource
      : "DIRECT_LINK";

  const previewQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "session-preview", sectionId, administrative ? target.date : "current", administrative ? target.period_sequence : "current", selectedSessionId),
    queryFn: async ({ signal }) => {
      if (!administrative && selectedSessionId !== null) {
        const resumed = await getSession(selectedSessionId, signal);
        if (resumed.section.id !== Number(sectionId)) throw new ApiError(404, { code: "ATTENDANCE_SESSION_SECTION_MISMATCH", message: "جلسة التحضير لا تتبع الفصل المحدد.", details: {} }, null);
        return { attendance_date: resumed.attendance_date, section: resumed.section, period: resumed.period, session: resumed };
      }
      return administrative ? getAdministrativePreview(Number(sectionId), target, signal) : getAttendancePreview(Number(sectionId), signal);
    },
    enabled: activeSchoolId > 0 && validSessionId && (!administrative || validTarget) && (!requestedAdministrativeContext || canPrepareAdministratively),
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
  const [draftStatus, setDraftStatus] = useState<"none" | "saved" | "unavailable">("none");
  const [draftRestored, setDraftRestored] = useState(false);
  const [periodChanged, setPeriodChanged] = useState(false);
  const reasonRequired = canPrepareAdministratively && (editing || administrative);
  const backTo = administrative ? `/attendance/monitoring?date=${target.date}&period=${target.period_sequence}&status=${session?.status === "SUBMITTED" ? "ALL" : "INCOMPLETE"}` : "/workspace";

  // مزامنة أثناء العرض (نمط adjusting state during render) — مرة واحدة لكل جلسة
  const [loadedSessionId, setLoadedSessionId] = useState<number | null>(null);
  if (previewQuery.data?.session && !periodChanged && (
    loadedSessionId === null ||
    (selectedSessionId !== null && previewQuery.data.session.id !== loadedSessionId) ||
    (session?.status === "IN_PROGRESS" && previewQuery.data.session.status === "SUBMITTED")
  )) {
    setLoadedSessionId(previewQuery.data.session.id);
    setSession(previewQuery.data.session);
    const restored = readDraft(draftScope, previewQuery.data.session);
    setMarks(restored === null ? marksFromSession(previewQuery.data.session) : Object.fromEntries(restored.map((id) => [id, { status: "ABSENT" as const }])));
    setDraftRestored(restored !== null);
    setDraftStatus(restored === null ? "none" : "saved");
    if (previewQuery.data.session.status === "SUBMITTED") removeDraft(draftScope, previewQuery.data.session.id);
  }

  // Keep reloads bound to the opened session, including sessions resumed from preview.
  useEffect(() => {
    if (administrative || !session || selectedSessionId !== null) return;
    const params = new URLSearchParams(location.search);
    params.set("session", String(session.id));
    navigate(`${location.pathname}?${params}`, { replace: true, state: location.state });
  }, [administrative, session, selectedSessionId, location.pathname, location.search, location.state, navigate]);

  // Saved drafts can safely survive navigation. Warn only if device storage failed
  // or an approval request is still in flight, whose result must remain visible.
  const unsafeToLeave = pending || draftStatus === "unavailable";
  const blocker = useBlocker(unsafeToLeave);
  useEffect(() => {
    if (!unsafeToLeave && blocker.state === "blocked") blocker.reset();
  }, [unsafeToLeave, blocker]);
  useEffect(() => {
    if (!unsafeToLeave) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsafeToLeave]);

  const startMutation = useMutation({
    mutationFn: () => administrative ? startAdministrativeSession(Number(sectionId), target) : startSession(Number(sectionId), startSource, previewQuery.data!),
    onSuccess: async (started) => {
      setLoadedSessionId(started.id);
      setSession(started);
      const restored = readDraft(draftScope, started);
      setMarks(restored === null ? marksFromSession(started) : Object.fromEntries(restored.map((id) => [id, { status: "ABSENT" as const }])));
      setDraftRestored(restored !== null);
      setDraftStatus(restored === null ? "none" : "saved");
      await invalidatePreparation();
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.code === "ATTENDANCE_PERIOD_CHANGED") {
        setPeriodChanged(true);
        await previewQuery.refetch();
      }
    },
  });

  const roster = useMemo(() => session?.roster ?? [], [session]);
  const summary = useMemo(() => {
    let absent = 0;
    for (const student of roster) {
      const status = marks[student.student_id]?.status ?? "PRESENT";
      if (status === "ABSENT") absent += 1;
    }
    return { absent, present: roster.length - absent };
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

  if (requestedAdministrativeContext && !canPrepareAdministratively && me.isSuccess) {
    return <section className="rounded-2xl border border-slate-200 bg-white p-6"><p className="font-bold text-slate-800">التحضير لحصة محددة متاح للمدير والوكيل. اختر الفصل من مساحة المعلم لتحضير الحصة الحالية.</p><Link to="/workspace" className="mt-4 inline-block text-teal-700 underline">مساحة المعلم</Link></section>;
  }
  if (administrative && !validTarget) {
    return <section className="rounded-2xl border border-slate-200 bg-white p-6"><p className="font-bold text-slate-800">اختر الحصة والفصل من متابعة تحضير اليوم.</p><Link to="/attendance/monitoring" className="mt-4 inline-block text-teal-700 underline">فتح متابعة التحضير</Link></section>;
  }
  if (!validSessionId) return <ErrorState error={new ApiError(400, { code: "INVALID_ATTENDANCE_SESSION", message: "رابط جلسة التحضير غير صالح.", details: {} }, null)} />;
  const needsSelectedSession = !administrative && selectedSessionId !== null && session?.id !== selectedSessionId;
  if ((previewQuery.isPending && (!session || needsSelectedSession)) || me.isPending) {
    return <Spinner label="جارٍ عرض بيانات الفصل..." />;
  }
  if (previewQuery.isError && (!session || needsSelectedSession)) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {!administrative && <PendingAttendance sectionId={Number(sectionId)} />}
        <ErrorState error={previewQuery.error} />
        <p className="mt-3">
          <Link to={backTo} className="text-blue-700 underline">
            العودة للرئيسية
          </Link>
        </p>
      </section>
    );
  }
  if (!session && previewQuery.data) {
    const preview = previewQuery.data;
    const sectionTitle = sectionLabel(preview.section.grade_name, preview.section.name, preview.section.department);
    return (
      <div className="space-y-4">
        {!administrative && <PendingAttendance sectionId={Number(sectionId)} />}
        <PageHeader
          icon={ClipboardCheck}
          eyebrow="معاينة الفصل"
          title={<span data-testid="preview-section-name">{sectionTitle}</span>}
          description="راجع بيانات الفصل والحصة قبل إنشاء جلسة التحضير. لن يظهر الفصل قيد التحضير إلا بعد التأكيد أدناه."
          tone={administrative ? "executive" : "teacher"}
          badge="لم يبدأ"
          meta={<><span>{preview.period.name}</span><span className="text-white/30">•</span><span dir="ltr">{preview.period.start_time} – {preview.period.end_time}</span><span className="text-white/30">•</span><span>{preview.attendance_date}</span></>}
          actions={(
            <Link
              to={backTo}
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15 sm:w-auto"
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
          <div className="flex flex-col items-start gap-4 sm:flex-row">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-teal-50 text-teal-700">
              <ShieldCheck aria-hidden size={24} />
            </span>
            <div className="min-w-0">
              <h1 className="text-xl font-black text-slate-900">تأكيد الفصل قبل البدء</h1>
              <p className="mt-2 text-sm leading-7 text-slate-600">
                ستبدأ تحضير <strong className="text-slate-950">{sectionTitle}</strong> في {preview.period.name}،
                وعدد {studentsLabel} المسجلين {preview.section.students_count}.
              </p>
              <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900">
                {administrative ? "سيُحفظ اعتماد التحضير باسمك مع سبب التدخل الإداري. راجع الفصل والحصة قبل البدء." : "لن تُنشأ جلسة ولن يظهر «قيد التحضير» للوكيل قبل ضغط زر البدء."}
              </p>
            </div>
          </div>

          {periodChanged && <p role="alert" data-testid="period-changed-notice" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm font-bold text-amber-900">تغيرت الحصة منذ المعاينة. راجع الحصة المعروضة أعلاه ثم أكد البدء مجددًا.</p>}
          {startMutation.isError && !periodChanged && <div className="mt-4"><ErrorState error={startMutation.error} /></div>}
          <div className="mt-6 grid gap-2 sm:flex sm:flex-wrap sm:items-center sm:justify-end">
            <Link
              to={backTo}
              className="inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2 text-center text-sm font-bold text-slate-700 hover:bg-slate-50 sm:w-auto"
            >
              إلغاء واختيار فصل آخر
            </Link>
            <Button
              className="w-full justify-center sm:w-auto"
              onClick={() => { setPeriodChanged(false); startMutation.mutate(); }}
              disabled={startMutation.isPending || previewQuery.isFetching}
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
    const next = { ...marks, [studentId]: { status } };
    setMarks(next);
    if (session.status === "IN_PROGRESS") {
      setDraftStatus(writeDraft(draftScope, session, buildPayload(next, roster).map((mark) => mark.student_id)) ? "saved" : "unavailable");
    }
  };

  const beginEditing = () => {
    setActionError(null);
    setEditing(true);
  };

  const handleSubmit = async () => {
    if (reasonRequired && !reason.trim()) return;
    setPending(true);
    setActionError(null);
    setRosterNotice(false);
    try {
      const payload = buildPayload(marks, roster);
      const updated = editing
        ? await editSession(session.id, payload, reason.trim(), session.updated_at)
        : administrative ? await submitAdministrativeSession(session.id, payload, reason.trim()) : await submitSession(session.id, payload);
      if (updated.id !== session.id || updated.status !== "SUBMITTED" || !updated.submitted_at) {
        throw new ApiError(409, { code: "ATTENDANCE_CONFIRMATION_REQUIRED", message: "لم يؤكد الخادم اعتماد هذه الجلسة. احتُفظ باختياراتك؛ أعد المحاولة أو حدّث الصفحة للتحقق.", details: {} }, null);
      }
      removeDraft(draftScope, session.id);
      setDraftStatus("none");
      setDraftRestored(false);
      setSession(updated);
      setMarks(marksFromSession(updated));
      setEditing(false);
      setReason("");
      // إن كانت لوحة الإدارة مفتوحة في نفس التطبيق فتُحدّث فورًا؛ أما الأجهزة
      // الأخرى فتلتقط النتيجة عبر الاستعلام الحي القصير.
      await invalidatePreparation();
    } catch (error) {
      try {
        if (error instanceof ApiError && error.code === "ATTENDANCE_ROSTER_CHANGED") {
          // الخادم حدّث بصمة القائمة — نعيد فتح الجلسة لقائمة محدثة ونبقي العلامات الصالحة
          setRosterNotice(true);
          const refreshed = await getSession(session.id);
          if (refreshed) {
            setSession(refreshed);
            const validIds = new Set(refreshed.roster.map((s) => s.student_id));
            const next = Object.fromEntries(Object.entries(marks).filter(([id]) => validIds.has(Number(id))));
            if (refreshed.status === "IN_PROGRESS") {
              setMarks(next);
              setDraftStatus(writeDraft(draftScope, refreshed, buildPayload(next, refreshed.roster).map((mark) => mark.student_id)) ? "saved" : "unavailable");
            } else {
              setMarks(marksFromSession(refreshed));
              setEditing(false);
              removeDraft(draftScope, session.id);
              setDraftStatus("none");
              setDraftRestored(false);
            }
          }
        } else if (error instanceof ApiError && (error.code === "ATTENDANCE_SESSION_ALREADY_SUBMITTED" || error.code === "ATTENDANCE_SESSION_CHANGED")) {
          const refreshed = await getSession(session.id);
          setSession(refreshed);
          setMarks(marksFromSession(refreshed));
          setEditing(false);
          removeDraft(draftScope, session.id);
          setDraftStatus("none");
          setDraftRestored(false);
          setActionError(error);
          await invalidatePreparation();
        } else {
          setActionError(error);
        }
      } catch (refreshError) {
        // A failed conflict refresh must retain choices and leave an actionable error.
        setActionError(refreshError);
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        icon={ClipboardCheck}
        eyebrow={administrative ? "تحضير إداري" : "جلسة التحضير"}
        title={<span data-testid="session-section-name">{sectionLabel(session.section.grade_name, session.section.name, session.section.department)}</span>}
        description={`التحضير بخيارين فقط: ${schoolType === "GIRLS" ? "حاضرة أو غائبة" : "حاضر أو غائب"}. جميع ${studentsLabel} ${schoolType === "GIRLS" ? "حاضرات" : "حاضرون"} افتراضيًا حتى تحدد الغياب.`}
        tone={administrative ? "executive" : "teacher"}
        badge={session.status === "SUBMITTED" && !editing ? "تم الاعتماد" : editing ? "تعديل معتمد" : "قيد التحضير"}
        meta={<><span>{session.period.name}</span><span className="text-white/30">•</span><span dir="ltr">{session.period.start_time} – {session.period.end_time}</span><span className="text-white/30">•</span><span>{session.attendance_date}</span></>}
        actions={(
          <Link
            to={backTo}
            className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white sm:w-auto"
          >
            <ArrowRight aria-hidden size={17} />
            العودة للمتابعة
          </Link>
        )}
      >
        <div className="flex flex-wrap gap-2 text-sm" data-testid="live-summary">
          <span className="rounded-full bg-emerald-400/15 px-3 py-1 font-bold text-emerald-100 ring-1 ring-emerald-300/20">{statusLabels.PRESENT} {summary.present}</span>
          <span className="rounded-full bg-red-400/15 px-3 py-1 font-bold text-red-100 ring-1 ring-red-300/20">{statusLabels.ABSENT} {summary.absent}</span>
        </div>
      </PageHeader>

      {blocker.state === "blocked" && <section role="alert" className="space-y-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
        <p>{pending ? "جارٍ إرسال التحضير. انتظر نتيجة الاعتماد قبل مغادرة الصفحة." : "تعذر حفظ المسودة على جهازك. المغادرة ستفقد اختيارات الغياب غير المرسلة."}</p>
        <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => blocker.reset()}>البقاء في التحضير</Button>{!pending && <Button variant="danger" onClick={() => blocker.proceed()}>مغادرة دون حفظ</Button>}</div>
      </section>}
      {session.status === "IN_PROGRESS" && draftStatus !== "none" && <p role="status" data-testid="draft-status" className={`rounded-xl border p-3 text-sm ${draftStatus === "saved" ? "border-teal-200 bg-teal-50 text-teal-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
        {draftStatus === "saved" ? `${draftRestored ? "استُعيدت اختيارات الغياب من المسودة. " : ""}المسودة محفوظة على هذا الجهاز فقط؛ لا يُعتمد التحضير حتى تضغط إرسال التحضير.` : "تعذر حفظ المسودة على هذا الجهاز. أبقِ الصفحة مفتوحة وأرسل التحضير لحفظه واعتماده."}
      </p>}

      {session.status === "SUBMITTED" && !editing && (
          <div
            className="flex flex-col items-stretch gap-3 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900 sm:flex-row sm:items-center sm:justify-between"
            data-testid="submitted-banner"
          >
            <span>
              تم إرسال التحضير بواسطة {session.submitted_by ?? "—"}
              {session.submitted_at &&
                ` في ${new Date(session.submitted_at).toLocaleString("ar-SA")}`}
            </span>
            {session.can_edit && (
              <Button
                variant="secondary"
                className="w-full justify-center sm:w-auto"
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
      {actionError != null && !marking && <ErrorState error={actionError} />}

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
                  className={`flex flex-col items-stretch justify-between gap-3 p-4 transition-colors sm:flex-row sm:items-center sm:p-5 ${status === "ABSENT" ? "bg-red-50/50" : "hover:bg-slate-50/70"}`}
                data-testid={`roster-student-${student.student_id}`}
              >
                <div className="min-w-0">
                  <p className="break-words font-medium text-slate-800">{student.full_name}</p>
                  <p className="text-xs text-slate-400" dir="ltr">
                    {student.national_id_masked}
                  </p>
                </div>
                {marking ? (
                  <div className="grid w-full grid-cols-2 items-center gap-1.5 sm:flex sm:w-auto sm:flex-wrap">
                    {(["PRESENT", "ABSENT"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setStatus(student.student_id, option)}
                        disabled={pending}
                        aria-pressed={status === option}
                        className={`min-h-10 w-full rounded-xl px-3 py-1.5 text-sm font-bold transition-all sm:w-auto ${
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
                    className={`self-start rounded-full px-3 py-1 text-sm ${
                      status === "PRESENT"
                        ? "bg-green-100 text-green-800"
                        : "bg-red-100 text-red-800"
                    }`}
                  >
                    {statusLabels[status]}
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
          {(editing || administrative) && (
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">{editing ? reasonRequired ? "سبب التصحيح الإداري (مطلوب)" : "سبب التعديل (اختياري)" : "سبب التحضير الإداري (مطلوب)"}</span>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
                required={reasonRequired}
                className="w-full rounded-lg border border-slate-300 px-3 py-2"
                placeholder={administrative && !editing ? "مثال: استكمال تحضير الفصل لعدم اعتماد المعلم" : undefined}
                data-testid={editing ? "edit-reason" : "administrative-reason"}
              />
            </label>
          )}
          {actionError != null && <ErrorState error={actionError} />}
          <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
            <p className="text-sm text-slate-500">
              سيُرسل غياب {summary.absent}، والبقية {schoolType === "GIRLS" ? "حاضرات" : "حاضرون"} تلقائيًا.
            </p>
            <div className="grid gap-2 sm:flex">
              <Button
                className="w-full justify-center sm:w-auto"
                onClick={() => void handleSubmit()}
                disabled={pending || (reasonRequired && !reason.trim())}
                data-testid="submit-attendance"
              >
                {pending ? "جارٍ الإرسال..." : editing ? "حفظ التعديل" : administrative ? "اعتماد التحضير" : "إرسال التحضير"}
              </Button>
              {editing && (
                <Button
                  variant="secondary"
                  className="w-full justify-center sm:w-auto"
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
