import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { StudentPicker } from "@/features/devices/StudentPicker";
import { type ReasonType, REASON_LABELS, createExcuse } from "@/features/excuses/api";
import { useActiveSchoolType } from "@/features/settings/hooks";
import { localIsoDate } from "@/utils/dates";
import { studentLabel } from "@/utils/roles";

type Scope = "FULL_DAY" | "PERIODS";

/** إنشاء عذر معتمد مباشرة، وتُضاف تغطية الغياب عند تسجيل الحضور. */
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
  const schoolType = useActiveSchoolType();
  const [student, setStudent] = useState<{ id: number; name: string } | null>(
    fixedStudent ?? null,
  );
  const [reasonType, setReasonType] = useState<ReasonType>("MEDICAL_REPORT");
  const [notes, setNotes] = useState("");
  const [scope, setScope] = useState<Scope>(fixedPeriod ? "PERIODS" : "FULL_DAY");
  const [fromDate, setFromDate] = useState(fixedDate ?? today);
  const [toDate, setToDate] = useState(fixedDate ?? today);
  const [periodsText, setPeriodsText] = useState(fixedPeriod ? String(fixedPeriod) : "");
  const dayRange = scope === "FULL_DAY" ? datesBetween(fromDate, toDate) : null;
  const periodSequences = scope === "PERIODS" ? parsePeriodSequences(periodsText) : null;
  const validationError = scope === "FULL_DAY"
    ? dayRange?.error
    : !fromDate ? "حدد تاريخ العذر." : periodSequences?.error;

  const mutation = useMutation({
    mutationFn: () => {
      const targets: { attendance_date: string; period_sequence?: number | null }[] = [];
      if (scope === "FULL_DAY") {
        for (const date of dayRange?.dates ?? []) {
          targets.push({ attendance_date: date });
        }
      } else {
        for (const sequence of periodSequences?.sequences ?? []) {
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

  const targetsReady = student !== null && !validationError;

  return (
    <div
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="excuse-create"
    >
      <h2 className="font-bold">تسجيل عذر جديد</h2>
      <p className="text-sm text-slate-600">
        يعتمد العذر عند حفظه. إذا كان التاريخ مستقبلًا، تُصنّف حصص الغياب ضمنه بعذر تلقائيًا بعد تسجيلها.
      </p>

      {student === null ? (
        <StudentPicker
          onSelect={(id, name) => setStudent({ id, name })}
          onCancel={onCancel}
        />
      ) : (
        <div className="flex items-center gap-2 text-sm">
          <span>
            {studentLabel(schoolType, true)}: <strong data-testid="selected-student">{student.name}</strong>
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
      {validationError && <p role="alert" className="text-sm text-red-700">{validationError}</p>}

      <div className="flex gap-2">
        <Button
          onClick={() => mutation.mutate()}
          disabled={!targetsReady || mutation.isPending}
          data-testid="save-excuse"
        >
          {mutation.isPending ? "جارٍ الحفظ..." : "حفظ العذر واعتماده"}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          إلغاء
        </Button>
      </div>
    </div>
  );
}

function datesBetween(from: string, to: string): { dates: string[]; error?: string } {
  if (!from || !to) return { dates: [], error: "حدد تاريخ البداية والنهاية." };
  const start = new Date(`${from}T12:00:00`);
  const end = new Date(`${to}T12:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) ||
      localIsoDate(start) !== from || localIsoDate(end) !== to) {
    return { dates: [], error: "صيغة التاريخ غير صحيحة." };
  }
  if (end < start) return { dates: [], error: "تاريخ النهاية يجب ألا يسبق تاريخ البداية." };
  const dates: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    if (dates.length === 60) return { dates: [], error: "يمكن تسجيل 60 يومًا كحد أقصى في العذر الواحد." };
    dates.push(localIsoDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return { dates };
}

function parsePeriodSequences(value: string): { sequences: number[]; error?: string } {
  const parts = value.trim().split(/[,،\s]+/).filter(Boolean);
  if (parts.length === 0) return { sequences: [], error: "حدد رقم حصة واحدة على الأقل." };
  const sequences = parts.map(Number);
  if (sequences.some((number) => !Number.isInteger(number) || number < 1 || number > 30)) {
    return { sequences: [], error: "أدخل أرقام حصص صحيحة من 1 إلى 30." };
  }
  if (new Set(sequences).size !== sequences.length) {
    return { sequences: [], error: "أرقام الحصص مكررة." };
  }
  return { sequences };
}
