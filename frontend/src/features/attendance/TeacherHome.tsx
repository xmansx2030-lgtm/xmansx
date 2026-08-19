import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { getAttendanceSections, getCurrentPeriod } from "@/features/attendance/api";
import { QrScanner } from "@/features/attendance/QrScanner";
import { schoolScopedKey } from "@/features/auth/useMe";

interface TeacherHomeProps {
  activeSchoolId: number;
}

/** شاشة المعلم: الحصة الحالية + فصول المدرسة + مسح QR — Mobile-first. */
export function TeacherHome({ activeSchoolId }: TeacherHomeProps) {
  const navigate = useNavigate();
  const [scanning, setScanning] = useState(false);

  const periodQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "current-period"),
    queryFn: ({ signal }) => getCurrentPeriod(signal),
    refetchInterval: 60_000, // الحصة تتغير مع الوقت
  });

  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
  });

  const period = periodQuery.data?.period;

  return (
    <div className="space-y-4">
      <section
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
        data-testid="current-period-card"
      >
        {periodQuery.isPending && <Spinner label="جارٍ تحديد الحصة الحالية..." />}
        {periodQuery.isError && <ErrorState error={periodQuery.error} />}
        {periodQuery.isSuccess && period && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm text-slate-500">الحصة الحالية</p>
              <p className="text-lg font-bold text-slate-800" data-testid="current-period-name">
                {period.name}
              </p>
            </div>
            <p className="text-sm text-slate-600" dir="ltr">
              {period.start_time} – {period.end_time}
            </p>
          </div>
        )}
        {periodQuery.isSuccess && !period && (
          <p className="text-slate-600" data-testid="no-current-period">
            لا توجد حصة حالية الآن — التحضير متاح أثناء الحصص فقط.
          </p>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">التحضير</h2>
          <Button variant="secondary" onClick={() => setScanning((v) => !v)}>
            {scanning ? "إغلاق الماسح" : "مسح رمز QR"}
          </Button>
        </div>

        {scanning && (
          <div className="mb-4">
            <QrScanner
              onToken={(token) => navigate(`/qr/${encodeURIComponent(token)}`)}
              onClose={() => setScanning(false)}
            />
          </div>
        )}

        <p className="mb-3 text-sm text-slate-500">أو اختر الفصل يدويًا:</p>
        {sectionsQuery.isPending && <Spinner label="جارٍ تحميل الفصول..." />}
        {sectionsQuery.isError && <ErrorState error={sectionsQuery.error} />}
        {sectionsQuery.isSuccess && sectionsQuery.data.length === 0 && (
          <p className="text-slate-600" data-testid="no-sections">
            لا توجد فصول نشطة في هذه المدرسة.
          </p>
        )}
        {sectionsQuery.isSuccess && (
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3" data-testid="sections-list">
            {sectionsQuery.data.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-start transition-colors hover:border-blue-400 hover:bg-blue-50"
                  onClick={() => navigate(`/attendance/section/${section.id}`)}
                  data-testid={`section-${section.id}`}
                >
                  <span className="block font-medium text-slate-800">{section.name}</span>
                  <span className="block text-xs text-slate-500">
                    {section.grade_name} · {section.students_count} طالبًا
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
