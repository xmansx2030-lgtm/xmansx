import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import type {
  AttendanceSessionData,
  MarkInput,
  MarkStatus,
  RosterStudent,
} from "@/features/attendance/api";
import { editSession, startSession, submitSession } from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";

/** حالة الطالب محليًا — «حاضر» هو الافتراضي ولا يرسل للخادم (استثناءات فقط). */
type LocalStatus = "PRESENT" | MarkStatus;

interface LocalMark {
  status: LocalStatus;
  arrival_time: string;
}

const STATUS_LABELS: Record<LocalStatus, string> = {
  PRESENT: "حاضر",
  ABSENT: "غائب",
  LATE: "متأخر",
};

function nowTime(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function marksFromSession(session: AttendanceSessionData): Record<number, LocalMark> {
  const map: Record<number, LocalMark> = {};
  for (const mark of session.marks) {
    map[mark.student_id] = {
      status: mark.status,
      arrival_time: mark.arrival_time ?? nowTime(),
    };
  }
  return map;
}

function buildPayload(marks: Record<number, LocalMark>, roster: RosterStudent[]): MarkInput[] {
  const rosterIds = new Set(roster.map((s) => s.student_id));
  return Object.entries(marks)
    .filter(([id, mark]) => mark.status !== "PRESENT" && rosterIds.has(Number(id)))
    .map(([id, mark]) => ({
      student_id: Number(id),
      status: mark.status as MarkStatus,
      arrival_time: mark.status === "LATE" ? mark.arrival_time : null,
    }));
}

export function AttendanceSessionPage() {
  const { sectionId } = useParams();
  const me = useMe();
  const activeSchoolId = me.data?.active_school?.id ?? 0;

  const startQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "session-start", sectionId),
    queryFn: () => startSession(Number(sectionId)),
    enabled: activeSchoolId > 0,
    staleTime: Infinity,
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

  // مزامنة أثناء العرض (نمط adjusting state during render) — مرة واحدة لكل جلسة
  const [loadedSessionId, setLoadedSessionId] = useState<number | null>(null);
  if (startQuery.data && startQuery.data.id !== loadedSessionId) {
    setLoadedSessionId(startQuery.data.id);
    setSession(startQuery.data);
    setMarks(marksFromSession(startQuery.data));
  }

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

  if (startQuery.isPending || me.isPending) {
    return <Spinner label="جارٍ فتح جلسة التحضير..." />;
  }
  if (startQuery.isError) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <ErrorState error={startQuery.error} />
        <p className="mt-3">
          <Link to="/" className="text-blue-700 underline">
            العودة للرئيسية
          </Link>
        </p>
      </section>
    );
  }
  if (!session) return null;

  const marking = session.status === "IN_PROGRESS" || editing;

  const setStatus = (studentId: number, status: LocalStatus) => {
    setMarks((prev) => ({
      ...prev,
      [studentId]: {
        status,
        arrival_time: prev[studentId]?.arrival_time ?? nowTime(),
      },
    }));
  };

  const setArrival = (studentId: number, value: string) => {
    setMarks((prev) => ({
      ...prev,
      [studentId]: { status: prev[studentId]?.status ?? "LATE", arrival_time: value },
    }));
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
    } catch (error) {
      if (error instanceof ApiError && error.code === "ATTENDANCE_ROSTER_CHANGED") {
        // الخادم حدّث بصمة القائمة — نعيد فتح الجلسة لقائمة محدثة ونبقي العلامات الصالحة
        setRosterNotice(true);
        const refreshed = await startQuery.refetch();
        if (refreshed.data) {
          setSession(refreshed.data);
          setMarks((prev) => {
            const validIds = new Set(refreshed.data.roster.map((s) => s.student_id));
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
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-slate-800" data-testid="session-section-name">
              {session.section.name} — {session.section.grade_name}
            </h2>
            <p className="text-sm text-slate-500">
              {session.period.name} ·{" "}
              <span dir="ltr">
                {session.period.start_time} – {session.period.end_time}
              </span>{" "}
              · {session.attendance_date}
            </p>
          </div>
          <div className="flex gap-2 text-sm" data-testid="live-summary">
            <span className="rounded-full bg-green-100 px-3 py-1 text-green-800">
              حاضر {summary.present}
            </span>
            <span className="rounded-full bg-red-100 px-3 py-1 text-red-800">
              غائب {summary.absent}
            </span>
            <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-800">
              متأخر {summary.late}
            </span>
          </div>
        </div>

        {session.status === "SUBMITTED" && !editing && (
          <div
            className="mt-3 rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900"
            data-testid="submitted-banner"
          >
            تم إرسال التحضير بواسطة {session.submitted_by ?? "—"}
            {session.submitted_at &&
              ` في ${new Date(session.submitted_at).toLocaleString("ar-SA")}`}
            {session.can_edit && (
              <Button
                variant="secondary"
                className="ms-3"
                onClick={() => setEditing(true)}
                data-testid="edit-button"
              >
                تعديل
              </Button>
            )}
          </div>
        )}
      </section>

      {rosterNotice && (
        <p
          className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
          role="alert"
          data-testid="roster-changed-notice"
        >
          تغيرت قائمة الفصل منذ فتح الجلسة — حُدِّثت القائمة، راجع العلامات ثم أعد الإرسال.
        </p>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <ul className="divide-y divide-slate-100" data-testid="roster-list">
          {roster.map((student) => {
            const mark = marks[student.student_id];
            const status = mark?.status ?? "PRESENT";
            return (
              <li
                key={student.student_id}
                className="flex flex-wrap items-center justify-between gap-2 p-3"
                data-testid={`roster-student-${student.student_id}`}
              >
                <div>
                  <p className="font-medium text-slate-800">{student.full_name}</p>
                  <p className="text-xs text-slate-400" dir="ltr">
                    {student.national_id_masked}
                  </p>
                </div>
                {marking ? (
                  <div className="flex items-center gap-1">
                    {(["PRESENT", "ABSENT", "LATE"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setStatus(student.student_id, option)}
                        aria-pressed={status === option}
                        className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                          status === option
                            ? option === "PRESENT"
                              ? "bg-green-600 text-white"
                              : option === "ABSENT"
                                ? "bg-red-600 text-white"
                                : "bg-amber-500 text-white"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        }`}
                      >
                        {STATUS_LABELS[option]}
                      </button>
                    ))}
                    {status === "LATE" && (
                      <input
                        type="time"
                        value={mark?.arrival_time ?? nowTime()}
                        onChange={(e) => setArrival(student.student_id, e.target.value)}
                        aria-label={`وقت وصول ${student.full_name}`}
                        className="ms-1 rounded-lg border border-slate-300 px-2 py-1 text-sm"
                      />
                    )}
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
                    {STATUS_LABELS[status]}
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
      </section>

      {marking && (
        <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
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
        </section>
      )}
    </div>
  );
}
