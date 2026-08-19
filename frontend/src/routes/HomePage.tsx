import { TeacherHome } from "@/features/attendance/TeacherHome";
import { useMe } from "@/features/auth/useMe";

/** الرئيسية بعد اختيار المدرسة — للمعلم: شاشة التحضير؛ لغيره: بطاقة ترحيب. */
export function HomePage() {
  const me = useMe();
  const isTeacher = me.data?.roles.includes("TEACHER") ?? false;
  const activeSchoolId = me.data?.active_school?.id;

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-2 text-xl font-bold" data-testid="active-school-name">
          {me.data?.active_school?.name}
        </h2>
        {!isTeacher && (
          <p className="text-slate-600">
            تم الدخول بنجاح. لوحات العمل (التقارير، المتابعة) تأتي في المراحل القادمة.
          </p>
        )}
      </section>
      {isTeacher && activeSchoolId && <TeacherHome activeSchoolId={activeSchoolId} />}
    </div>
  );
}
