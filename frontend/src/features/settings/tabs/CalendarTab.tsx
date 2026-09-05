import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import {
  activateSemester,
  createSemester,
  createYear,
  yearAction,
  type AcademicYear,
} from "@/features/settings/api";
import { useInvalidateSchoolData, useYearsQuery } from "@/features/settings/hooks";

const YEAR_STATUS_LABELS: Record<string, string> = {
  UPCOMING: "قادم",
  ACTIVE: "نشط",
  CLOSED: "منتهي",
  ARCHIVED: "مؤرشف",
};

export function CalendarTab({ canWrite }: { canWrite: boolean }) {
  const years = useYearsQuery();
  const invalidate = useInvalidateSchoolData();
  const [error, setError] = useState<string | null>(null);

  const refresh = () => void invalidate("academic-years");

  const createYearMutation = useMutation({
    mutationFn: (data: { name: string; start_date: string; end_date: string }) =>
      createYear(data),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "تعذر إنشاء العام."),
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "activate" | "close" | "archive" }) =>
      yearAction(id, action),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "تعذر تنفيذ الإجراء."),
  });

  if (years.isPending) return <Spinner />;
  if (years.isError) return <ErrorState error={years.error} />;

  return (
    <div className="space-y-6">
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {canWrite && (
        <CreateYearForm
          pending={createYearMutation.isPending}
          onCreate={(data) => {
            setError(null);
            createYearMutation.mutate(data);
          }}
        />
      )}

      {years.data.length === 0 && (
        <p className="text-slate-500">لا توجد أعوام دراسية بعد.</p>
      )}

      {years.data.map((year) => (
        <YearCard
          key={year.id}
          year={year}
          canWrite={canWrite}
          onAction={(action) => {
            setError(null);
            actionMutation.mutate({ id: year.id, action });
          }}
          onChanged={refresh}
          onError={setError}
        />
      ))}
    </div>
  );
}

function CreateYearForm({
  pending,
  onCreate,
}: {
  pending: boolean;
  onCreate: (data: { name: string; start_date: string; end_date: string }) => void;
}) {
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim() || !start || !end) {
      setError("أكمل اسم العام وتاريخي البداية والنهاية.");
      return;
    }
    if (start >= end) {
      setError("تاريخ البداية يجب أن يسبق تاريخ النهاية.");
      return;
    }
    onCreate({ name: name.trim(), start_date: start, end_date: end });
    setName("");
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <TextField
        label="اسم العام (مثل 2026/2027)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <TextField
        label="بداية العام"
        type="date"
        value={start}
        onChange={(e) => setStart(e.target.value)}
      />
      <TextField
        label="نهاية العام"
        type="date"
        value={end}
        onChange={(e) => setEnd(e.target.value)}
      />
      <Button type="submit" disabled={pending}>
        إنشاء عام دراسي
      </Button>
      {error && (
        <p role="alert" className="w-full text-sm text-red-700">
          {error}
        </p>
      )}
    </form>
  );
}

function YearCard({
  year,
  canWrite,
  onAction,
  onChanged,
  onError,
}: {
  year: AcademicYear;
  canWrite: boolean;
  onAction: (action: "activate" | "close" | "archive") => void;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [showSemesterForm, setShowSemesterForm] = useState(false);

  const semesterMutation = useMutation({
    mutationFn: (data: { name: string; sequence: number; start_date: string; end_date: string }) =>
      createSemester(year.id, data),
    onSuccess: () => {
      setShowSemesterForm(false);
      onChanged();
    },
    onError: (e) => onError(e instanceof ApiError ? e.message : "تعذر إنشاء الفصل."),
  });

  const activateSemesterMutation = useMutation({
    mutationFn: (semesterId: number) => activateSemester(semesterId),
    onSuccess: onChanged,
    onError: (e) => onError(e instanceof ApiError ? e.message : "تعذر تفعيل الفصل."),
  });

  return (
    <section
      data-testid="academic-year-card"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-bold">{year.name}</h3>
          <p className="text-sm text-slate-500">
            {year.start_date} ← {year.end_date}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              year.status === "ACTIVE"
                ? "bg-emerald-100 text-emerald-800"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {YEAR_STATUS_LABELS[year.status]}
          </span>
          {canWrite && year.status === "UPCOMING" && (
            <Button variant="secondary" onClick={() => onAction("activate")}>
              تفعيل
            </Button>
          )}
          {canWrite && year.status === "ACTIVE" && (
            <Button variant="secondary" onClick={() => onAction("close")}>
              إغلاق
            </Button>
          )}
        </div>
      </div>

      <h4 className="mb-2 text-sm font-medium text-slate-600">الفصول الدراسية</h4>
      {year.semesters.length === 0 && (
        <p className="mb-2 text-sm text-slate-400">لا توجد فصول.</p>
      )}
      <ul className="mb-3 space-y-1">
        {year.semesters.map((semester) => (
          <li
            key={semester.id}
            className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm"
          >
            <span>
              {semester.name} ({semester.start_date} ← {semester.end_date})
            </span>
            <span className="flex items-center gap-2">
              <span className="text-xs text-slate-500">
                {YEAR_STATUS_LABELS[semester.status]}
              </span>
              {canWrite && semester.status === "UPCOMING" && (
                <button
                  type="button"
                  className="text-xs text-blue-700 underline"
                  onClick={() => activateSemesterMutation.mutate(semester.id)}
                >
                  تفعيل
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>

      {canWrite && !showSemesterForm && (
        <Button variant="secondary" onClick={() => setShowSemesterForm(true)}>
          إضافة فصل دراسي
        </Button>
      )}
      {canWrite && showSemesterForm && (
        <SemesterForm
          nextSequence={year.semesters.length + 1}
          pending={semesterMutation.isPending}
          onSubmit={(data) => semesterMutation.mutate(data)}
        />
      )}
    </section>
  );
}

function SemesterForm({
  nextSequence,
  pending,
  onSubmit,
}: {
  nextSequence: number;
  pending: boolean;
  onSubmit: (data: { name: string; sequence: number; start_date: string; end_date: string }) => void;
}) {
  const [name, setName] = useState(`الفصل الدراسي ${nextSequence}`);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  return (
    <form
      className="mt-2 flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim() && start && end) {
          onSubmit({ name: name.trim(), sequence: nextSequence, start_date: start, end_date: end });
        }
      }}
    >
      <TextField label="اسم الفصل" value={name} onChange={(e) => setName(e.target.value)} />
      <TextField label="البداية" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      <TextField label="النهاية" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
      <Button type="submit" disabled={pending}>
        حفظ الفصل
      </Button>
    </form>
  );
}
