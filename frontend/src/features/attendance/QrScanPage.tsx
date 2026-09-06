import {
  BadgeCheck,
  Building2,
  CheckCircle2,
  LockKeyhole,
  LogIn,
  QrCode,
  ShieldCheck,
  UserRoundX,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { resolveQr } from "@/features/attendance/api";
import { safeReturnTo, withReturnTo } from "@/features/auth/returnTo";
import { useMe } from "@/features/auth/useMe";
import { roleLabel } from "@/utils/roles";

interface AccessCardProps {
  icon: ReactNode;
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}

function AccessCard({ icon, eyebrow, title, description, action }: AccessCardProps) {
  return (
    <main className="auth-shell relative flex min-h-dvh items-center justify-center overflow-hidden p-4 sm:p-8">
      <div className="pointer-events-none absolute -right-28 -top-28 size-80 rounded-full bg-teal-300/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -left-24 size-96 rounded-full bg-sky-300/10 blur-3xl" />

      <section
        className="auth-card relative w-full max-w-xl overflow-hidden rounded-[2rem] border border-white/70 p-6 shadow-2xl shadow-slate-950/15 sm:p-9"
        data-testid="qr-access-gate"
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-l from-teal-500 via-emerald-400 to-sky-500" />

        <div className="mb-7 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-2xl bg-slate-950 text-teal-300 shadow-lg shadow-slate-950/15">
              <QrCode aria-hidden size={23} />
            </span>
            <div>
              <p className="font-black text-slate-900">منصة المواظبة</p>
              <p className="text-xs text-slate-500">بوابة رمز الفصل الآمنة</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800">
            <ShieldCheck aria-hidden size={15} /> محمي
          </span>
        </div>

        <div className="mb-6 grid size-16 place-items-center rounded-2xl bg-teal-50 text-teal-800 ring-8 ring-teal-50/45">
          {icon}
        </div>
        <p className="mb-2 text-sm font-bold text-teal-700">{eyebrow}</p>
        <h1 className="text-2xl font-black leading-tight text-slate-950 sm:text-3xl">{title}</h1>
        <p className="mt-3 text-sm leading-7 text-slate-600 sm:text-base">{description}</p>

        <div className="my-7 grid gap-2.5 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-700">
          <p className="flex items-center gap-2">
            <CheckCircle2 aria-hidden size={17} className="text-emerald-600" />
            لا يعرض الرمز أسماء الطلاب أو بيانات الفصل للعامة.
          </p>
          <p className="flex items-center gap-2">
            <CheckCircle2 aria-hidden size={17} className="text-emerald-600" />
            امتلاك الرمز وحده لا يمنح أي صلاحية.
          </p>
          <p className="flex items-center gap-2">
            <CheckCircle2 aria-hidden size={17} className="text-emerald-600" />
            يتم التحقق من الحساب والدور والمدرسة قبل فتح التحضير.
          </p>
        </div>

        {action}
        <p className="mt-6 text-center text-xs leading-6 text-slate-400">
          إذا وصل إليك هذا الرمز بالخطأ، يمكنك إغلاق الصفحة بأمان.
        </p>
      </section>
    </main>
  );
}

/**
 * بوابة QR عامة وآمنة: لا تحاول حل الرمز إلا بعد إثبات أن الجلسة لمعلم
 * في مدرسة نشطة. يبقى الخادم هو جهة الإنفاذ النهائية ولا يثق بهذه الواجهة.
 */
export function QrScanPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const me = useMe();
  const [error, setError] = useState<unknown>(null);
  const requestedToken = useRef<string | null>(null);
  const returnTo = safeReturnTo(`/qr/${token}`);
  const isTeacher = me.isSuccess && me.data.roles.includes("TEACHER");
  const canResolve = Boolean(
    token &&
      me.isSuccess &&
      me.data.active_school &&
      isTeacher &&
      !me.data.must_change_password,
  );

  useEffect(() => {
    if (!canResolve || requestedToken.current === token) return;
    requestedToken.current = token;
    setError(null);
    resolveQr(token)
      .then((section) => {
        navigate(`/attendance/section/${section.id}`, { replace: true });
      })
      .catch((err: unknown) => setError(err));
  }, [canResolve, token, navigate]);

  if (me.isPending) {
    return (
      <AccessCard
        icon={<LockKeyhole aria-hidden size={30} />}
        eyebrow="تحقق آمن"
        title="جارٍ التحقق من صلاحية الوصول"
        description="لن يتم عرض أي بيانات قبل اكتمال التحقق من الحساب والدور والمدرسة."
        action={
          <div className="flex justify-center">
            <Spinner label="جارٍ التحقق..." />
          </div>
        }
      />
    );
  }

  if (me.isError) {
    const unauthenticated =
      me.error instanceof ApiError &&
      (me.error.status === 401 ||
        me.error.status === 403 ||
        me.error.code === "AUTHENTICATION_REQUIRED");
    if (unauthenticated) {
      return (
        <AccessCard
          icon={<LockKeyhole aria-hidden size={30} />}
          eyebrow="وصول داخلي مقيد"
          title="هذا الرمز مخصص للهيئة التعليمية المصرح لها"
          description="لم يتم عرض أي بيانات مدرسية. سجّل الدخول بحساب الموظف المعتمد، وسيُعاد التحقق من الرمز تلقائيًا."
          action={
            <Link
              to={withReturnTo("/login", returnTo)}
              className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 py-3 text-sm font-black text-white shadow-lg shadow-teal-900/15 transition hover:-translate-y-0.5 hover:bg-teal-800"
            >
              <LogIn aria-hidden size={18} /> دخول الموظفين المصرح لهم
            </Link>
          }
        />
      );
    }
    return (
      <AccessCard
        icon={<ShieldCheck aria-hidden size={30} />}
        eyebrow="تعذر التحقق"
        title="لم نتمكن من التحقق من الصلاحية الآن"
        description="لم يتم عرض أي بيانات. تحقق من اتصالك ثم أعد فتح الرمز."
        action={
          <div className="rounded-xl border border-red-100 bg-red-50 p-3">
            <ErrorState error={me.error} />
          </div>
        }
      />
    );
  }

  if (me.data.must_change_password) {
    return <Navigate to="/change-password" replace />;
  }

  if (me.data.active_school === null) {
    const canChooseSchool = me.data.memberships.length > 0 || me.data.invitations.length > 0;
    return (
      <AccessCard
        icon={
          canChooseSchool ? (
            <Building2 aria-hidden size={30} />
          ) : (
            <UserRoundX aria-hidden size={30} />
          )
        }
        eyebrow="الوصول محمي"
        title={canChooseSchool ? "اختر مدرستك أولًا" : "هذا الحساب غير مرتبط بمدرسة"}
        description={
          canChooseSchool
            ? "اختر المدرسة التي تعمل بها، ثم سيُعاد فحص صلاحيتك للرمز دون كشف بياناته."
            : "لم يتم عرض أي بيانات، ولا يمكن استخدام رمز الفصل دون عضوية مدرسية فعالة."
        }
        action={
          canChooseSchool ? (
            <Link
              to={withReturnTo("/select-school", returnTo)}
              className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 py-3 text-sm font-black text-white shadow-lg shadow-teal-900/15 transition hover:-translate-y-0.5 hover:bg-teal-800"
            >
              <Building2 aria-hidden size={18} /> اختيار المدرسة
            </Link>
          ) : undefined
        }
      />
    );
  }

  if (!isTeacher) {
    return (
      <AccessCard
        icon={<UserRoundX aria-hidden size={30} />}
        eyebrow="صلاحية غير متاحة"
        title="هذا الحساب غير مخول بفتح التحضير"
        description={`رموز الفصول مخصصة ${me.data.active_school.school_type === "GIRLS" ? "للمعلمة" : "للمعلم"} فقط. لم يتم إرسال الرمز للتحقق، ولم يتم عرض أي بيانات طلابية أو مدرسية.`}
        action={
          <Link
            to="/"
            className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-black text-slate-800 transition hover:bg-slate-50"
          >
            العودة إلى المنصة
          </Link>
        }
      />
    );
  }

  return (
    <AccessCard
      icon={
        error == null ? (
          <BadgeCheck aria-hidden size={30} />
        ) : (
          <ShieldCheck aria-hidden size={30} />
        )
      }
      eyebrow={error == null ? "حساب مصرح" : "تعذر فتح الرمز"}
      title={error == null ? "جارٍ فتح الفصل بأمان" : "لم يتم فتح بيانات الفصل"}
      description={
        error == null
          ? `تم التحقق من صفة ${roleLabel("TEACHER", me.data.active_school.school_type)}، ويجري الآن التحقق من الرمز داخل المدرسة النشطة.`
          : "بقيت بيانات الطلاب محمية. قد يكون الرمز قديمًا أو تابعًا لمدرسة أخرى."
      }
      action={
        error == null ? (
          <div className="flex justify-center">
            <Spinner label="جارٍ فتح التحضير..." />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-xl border border-red-100 bg-red-50 p-3">
              <ErrorState error={error} />
            </div>
            <Link
              to="/"
              className="inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-black text-slate-800 transition hover:bg-slate-50"
            >
              العودة للرئيسية واختيار الفصل يدويًا
            </Link>
          </div>
        )
      }
    />
  );
}
