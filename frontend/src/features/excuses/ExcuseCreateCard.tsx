import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { StudentPicker } from "@/features/devices/StudentPicker";
import { type ReasonType, REASON_LABELS, createExcuse } from "@/features/excuses/api";
import { localIsoDate } from "@/utils/dates";

type Scope = "FULL_DAY" | "PERIODS";

/** إنشاء عذر: طالب ← نوع ← يوم/أيام أو حصص ← حفظ Pending (المعاينة في التفاصيل). */
export function ExcuseCreateCard({
  onCreated,
  onCancel,
  fixedStudent,
  fixedDate,
  fixedPeriod,
}: {
  onCreated: (excuseId: number) => void;
  onCancel: () => void;
  fixedStudent?: { id: number; name: string };
  fixedDate?: string;
  fixedPeriod?: number;
}) {
  const today = localIsoDate();
  const [student, setStudent] = useState<{ id: number; name: string } | null>(
    fixedStudent ?? null,
  );
  const [reasonType, setReasonType] = useState<ReasonType>("MEDICAL_REPORT");
  const [notes, setNotes] = useState("");
  const [scope, setScope] = useState<Scope>(fixedPeriod ? "PERIODS" : "FULL_DAY");
  const [fromDate, setFromDate] = useState(fixedDate ?? today);
  const [toDate, setToDate] = useState(fixedDate ?? today);
  const [periodsText, setPeriodsText] = useState(fixedPeriod ? String(fixedPeriod) : "");

  const mutation = useMutation({
    mutationFn: () => {
      const targets: { attendance_date: string; period_sequence?: number | null }[] = [];
      if (scope === "FULL_DAY") {
        for (const date of datesBetween(fromDate, toDate)) {
          targets.push({ attendance_date: date });
        }
      } else {
        const sequences = periodsText
          .split(/[,،\s]+/)
          .map((part) => Number(part.trim()))
          .filter((value) => Number.isInteger(value) && value > 0);
        for (const sequence of sequences) {
          targets.push({ attendance_date: fromDate, period_sequence: sequence });
        }
      }
      return createExcuse({
        student_id: student!.id,
        reason_type: reasonType,
        notes,
        targets,
      });
    },
    onSuccess: (excuse) => onCreated(excuse.id),
  });

  const targetsReady =
    student !== null && (scope === "FULL_DAY" || periodsText.trim().length > 0);

  return (
    <div
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="excuse-create"
    >
      <h2 className="font-bold">تسجيل عذر جديد</h2>

      {student === null ? (
        <StudentPicker
          onSelect={(id, name) => setStudent({ id, name })}
          onCancel={onCancel}
        />
      ) : (
        <div className="flex items-center gap-2 text-sm">
          <span>
            الطالب: <strong data-testid="selected-student">{student.name}</strong>
          </span>
          {!fixedStudent && (
            <Button variant="secondary" onClick={() => setStudent(null)}>
              تغيير
            </Button>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          نوع العذر
          <select
            data-testid="excuse-reason"
            value={reasonType}
            onChange={(event) => setReasonType(event.target.value as ReasonType)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            {Object.entries(REASON_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          النطاق
          <select
            data-testid="excuse-scope"
            value={scope}
            onChange={(event) => setScope(event.target.value as Scope)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="FULL_DAY">يوم كامل / عدة أيام</option>
            <option value="PERIODS">حصص محددة</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {scope === "FULL_DAY" ? "من تاريخ" : "التاريخ"}
          <input
            type="date"
            data-testid="excuse-from"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        {scope === "FULL_DAY" ? (
          <label className="flex flex-col gap-1 text-sm">
            إلى تاريخ
            <input
              type="date"
              data-testid="excuse-to"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
        ) : (
          <label className="flex flex-col gap-1 text-sm">
            أرقام الحصص (مفصولة بفاصلة)
            <input
              data-testid="excuse-periods"
              value={periodsText}
              onChange={(event) => setPeriodsText(event.target.value)}
              placeholder="مثال: 2، 3"
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
        )}
      </div>

      <label className="flex flex-col gap-1 text-sm">
        ملاحظات (اختيارية)
        <textarea
          data-testid="excuse-notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
          className="rounded-lg border border-slate-300 px-3 py-2"
        />
      </label>

      {mutation.isError && (
        <p role="alert" className="text-sm text-red-700">
          {(mutation.error as { message?: string }).message ?? "تعذر حفظ العذر."}
        </p>
      )}

      <div className="flex gap-2">
        <Button
          onClick={() => mutation.mutate()}
          disabled={!targetsReady || mutation.isPending}
          data-testid="save-excuse"
        >
          {mutation.isPending ? "جارٍ الحفظ..." : "حفظ ومتابعة للمعاينة"}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          إلغاء
        </Button>
      </div>
    </div>
  );
}

function datesBetween(from: string, to: string): string[] {
  const start = new Date(`${from}T12:00:00`);
  const end = new Date(`${to}T12:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return [from];
  }
  const dates: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end && dates.length < 60) {
    dates.push(localIsoDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}
