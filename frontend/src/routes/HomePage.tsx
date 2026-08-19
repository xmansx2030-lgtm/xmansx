import { MonitoringSummaryCard } from "@/features/attendance/MonitoringSummaryCard";
import { TeacherHome } from "@/features/attendance/TeacherHome";
import { useMe } from "@/features/auth/useMe";

const MONITORING_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL"];

/** الرئيسية بعد اختيار المدرسة — للمعلم شاشة التحضير، وللوكيل/المدير بطاقة المتابعة. */
export function HomePage() {
  const me = useMe();
  const roles = me.data?.roles ?? [];
  const isTeacher = roles.includes("TEACHER");
  const canMonitor = roles.some((r) => MONITORING_ROLES.includes(r));
  const activeSchoolId = me.data?.active_school?.id;

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-2 text-xl font-bold" data-testid="active-school-name">
          {me.data?.active_school?.name}
        </h2>
        {!isTeacher && !canMonitor && (
          <p className="text-slate-600">
            تم الدخول بنجاح. لوحات العمل (التقارير، المتابعة) تأتي في المراحل القادمة.
          </p>
        )}
      </section>
      {canMonitor && activeSchoolId && (
        <MonitoringSummaryCard activeSchoolId={activeSchoolId} />
      )}
      {isTeacher && activeSchoolId && <TeacherHome activeSchoolId={activeSchoolId} />}
    </div>
  );
}
