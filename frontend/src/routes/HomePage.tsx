import { useMe } from "@/features/auth/useMe";

/** صفحة مؤقتة بعد اختيار المدرسة — لوحات الأعمال تأتي في مراحلها. */
export function HomePage() {
  const me = useMe();

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-2 text-xl font-bold" data-testid="active-school-name">
        {me.data?.active_school?.name}
      </h2>
      <p className="text-slate-600">
        تم الدخول بنجاح. لوحات العمل (الحضور، الطلاب، التقارير) تأتي في المراحل القادمة.
      </p>
    </section>
  );
}
