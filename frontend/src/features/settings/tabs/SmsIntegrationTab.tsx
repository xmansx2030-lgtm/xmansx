import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  getSmsIntegration, PROVIDER_LABELS, saveSmsIntegration,
  type SmsIntegration, type SmsProvider,
} from "@/features/sms/api";

export function SmsIntegrationTab() {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const query = useQuery({
    queryKey: schoolScopedKey(schoolId, "sms", "integration"),
    queryFn: ({ signal }) => getSmsIntegration(signal),
    enabled: schoolId > 0,
  });

  if (query.isPending) return <Spinner label="جارٍ تحميل إعدادات الرسائل..." />;
  if (query.isError) return <ErrorState error={query.error} />;
  return (
    <div className="space-y-5">
      <Alert title="إرسال الغياب حسب التحاضير المعتمدة" tone="info">
        يمكن مراجعة إرسال الرسالة لمن سُجل غيابه في جميع التحاضير المعتمدة لفصله حتى الآن، دون انتظار عدد محدد من الحصص أو اكتمال تحضير الفصول الأخرى. يُستبعد الغياب المعذور والطلاب بلا رقم ولي أمر صالح.
      </Alert>
      <SmsIntegrationForm key={schoolId} initial={query.data} schoolId={schoolId} />
    </div>
  );
}

function SmsIntegrationForm({ initial, schoolId }: { initial: SmsIntegration; schoolId: number }) {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<SmsProvider>(initial.provider ?? "DREAMS");
  const [username, setUsername] = useState(initial.username);
  const [senderName, setSenderName] = useState(initial.sender_name);
  const [apiKey, setApiKey] = useState("");
  const [active, setActive] = useState(initial.is_active);
  const [saved, setSaved] = useState(false);
  const mutation = useMutation({
    mutationFn: () => saveSmsIntegration({
      provider, username: username.trim(), api_key: apiKey.trim(),
      sender_name: senderName.trim(), is_active: active,
    }),
    onSuccess: (data) => {
      queryClient.setQueryData(schoolScopedKey(schoolId, "sms", "integration"), data);
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "sms", "preview") });
      setApiKey("");
      setSaved(true);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    mutation.mutate();
  }

  return (
    <div className="max-w-4xl space-y-5">
      <Alert title="ربط مستقل لهذه المدرسة" tone="info">
        تحفظ بيانات هذا الحساب لهذه المدرسة فقط. لا تستخدم مفتاح مدرسة أخرى، ولا يظهر المفتاح بعد حفظه.
      </Alert>
      <form onSubmit={submit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900">مزود الرسائل النصية</h3>
          <p className="mt-1 text-sm text-slate-600">اختر المنصة التي تملك المدرسة حسابًا واسم مرسل معتمدًا فيها.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-bold text-slate-700">
            المنصة
            <select
              value={provider}
              onChange={(event) => {
                setProvider(event.target.value as SmsProvider);
                setApiKey("");
                setActive(false);
                setSaved(false);
              }}
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-slate-900"
            >
              {(Object.entries(PROVIDER_LABELS) as [SmsProvider, string][]).map(([value, label]) =>
                <option key={value} value={value}>{label}</option>,
              )}
            </select>
          </label>
          <label className="block text-sm font-bold text-slate-700">
            اسم المستخدم لدى المزود
            <input required maxLength={150} autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2.5" dir="ltr" />
          </label>
          <label className="block text-sm font-bold text-slate-700">
            اسم المرسل المعتمد
            <input required maxLength={provider === "MSEGAT" ? 11 : 30} value={senderName} onChange={(e) => setSenderName(e.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2.5" dir="ltr" />
          </label>
          <label className="block text-sm font-bold text-slate-700">
            {provider === "DREAMS" ? "مفتاح API السري من دريمز" : "مفتاح API من مسجات"}
            <input
              type="password" autoComplete="new-password" maxLength={500}
              value={apiKey} onChange={(e) => setApiKey(e.target.value)}
              placeholder={initial.has_secret && initial.provider === provider ? "اتركه فارغًا للاحتفاظ بالمفتاح المحفوظ" : "أدخل مفتاح هذه المدرسة"}
              className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2.5" dir="ltr"
            />
          </label>
        </div>
        {provider === "DREAMS" && (
          <p className="text-xs leading-6 text-slate-600">استخدم مفتاح API السري الخاص بخدمة الرسائل، وليس كلمة مرور الدخول أو مفتاح OAuth قبل التحقق من نوع واجهة الربط.</p>
        )}
        <label className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm font-bold text-slate-800">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="size-5" />
          تفعيل إرسال رسائل الغياب من هذا الحساب
        </label>
        <p className="text-xs leading-6 text-slate-500">قد يحتاج المزود إلى السماح بعنوان خادم المنصة ضمن قائمة عناوين IP الخاصة بالحساب. لا تغيّر العناوين المستخدمة في مشاريع أخرى.</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={mutation.isPending}>حفظ ربط المدرسة</Button>
          <Link to="/attendance/absence-messages" className="text-sm font-bold text-blue-700 underline">الانتقال إلى رسائل الغياب</Link>
        </div>
        {mutation.isError && <p role="alert" className="text-sm text-red-700">{mutation.error.message}</p>}
        {saved && <p role="status" className="text-sm font-bold text-emerald-700">حُفظ الربط لهذه المدرسة. لم تُرسل أي رسالة عند الحفظ.</p>}
      </form>
    </div>
  );
}
