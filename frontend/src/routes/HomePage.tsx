import { TeacherHome } from "@/features/attendance/TeacherHome";
import { useMe } from "@/features/auth/useMe";
import { Navigate } from "react-router-dom";

const MONITORING_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL"];

/** الرئيسية بعد اختيار المدرسة — نقطة دخول عملية بحسب الدور، لا شاشة ترحيب خاملة. */
export function HomePage() {
  const me = useMe();
  const roles = me.data?.roles ?? [];
  const isTeacher = roles.includes("TEACHER");
  const isCounselor = roles.includes("COUNSELOR");
  const isGateGuard = roles.includes("GATE_GUARD");
  const canMonitor = roles.some((r) => MONITORING_ROLES.includes(r));
  const activeSchoolId = me.data?.active_school?.id;

  // المدير والوكيل يبدأان من مركز القيادة المباشر؛ لا تبقى لوحة الإدارة
  // صفحة جانبية منفصلة عن نقطة الدخول اليومية.
  if (canMonitor) {
    return <Navigate to="/dashboard" replace />;
  }

  // المرشد ذو الدور المفرد يبدأ من صندوق عمله الفعلي. العضوية متعددة الأدوار
  // التي تشمل «معلم» تبقى على شاشة التحضير لأنها المهمة الأسرع زمنيًا داخل الحصة.
  if (isCounselor && !isTeacher && !canMonitor) {
    return <Navigate to="/counselor" replace />;
  }

  if (isGateGuard && !isTeacher && !isCounselor && !canMonitor) {
    return <Navigate to="/gate" replace />;
  }

  return (
    <>{isTeacher && activeSchoolId && <TeacherHome activeSchoolId={activeSchoolId} />}</>
  );
}
