import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { patchSettings } from "@/features/settings/api";
import { useSettingsQuery } from "@/features/settings/hooks";
import {
  getSmsIntegration, PROVIDER_LABELS, saveSmsIntegration,
  type SmsIntegration, type SmsProvider,
} from "@/features/sms/api";

export function SmsIntegrationTab() {
  const me = useMe();
  const settings = useSettingsQuery();
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
      {settings.isPending && <Spinner label="جارٍ تحميل معيار إرسال الغياب..." />}
      {settings.isError && <ErrorState error={settings.error} />}
      {settings.data && <SmsAbsencePolicyForm key={schoolId} schoolId={schoolId} initial={settings.data.absence_sms_min_approved_periods} />}
      <SmsIntegrationForm key={schoolId} initial={query.data} schoolId={schoolId} />
    </div>
  );
}

function SmsAbsencePolicyForm({ schoolId, initial }: { schoolId: number; initial: number }) {
  const queryClient = useQueryClient();
  const [minimum, setMinimum] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const mutation = useMutation({
    mutationFn: () => patchSettings({ absence_sms_min_approved_periods: minimum }),
    onSuccess: (data) => {
      queryClient.setQueryData(schoolScopedKey(schoolId, "settings"), data);
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "sms", "preview") });
      setSaved(minimum);
    },
  });

  return (
    <form onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <h3 className="text-lg font-bold text-slate-900">معيار إرسال غياب اليوم</h3>
      <p className="mt-1 text-sm leading-6 text-slate-600">تحدد كل مدرسة عدد حصص التحضير المعتمدة قبل إتاحة رسائل الغياب. يظهر الطلاب في قائمة المراجعة فور اعتماد أي حصة، ثم يتاح الإرسال بعد بلوغ هذا العدد إذا بقي غياب غير معذور.</p>
      <label className="mt-4 block max-w-md text-sm font-bold text-slate-700">
        عدد التحاضير المعتمدة المطلوب
        <select value={minimum === 0 ? "all" : "fixed"} onChange={(event) => setMinimum(event.target.value === "all" ? 0 : 2)} className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5">
          <option value="all">جميع حصص التحضير في جدول اليوم</option>
          <option value="fixed">عدد تحدده المدرسة</option>
        </select>
      </label>
      {minimum > 0 && <label className="mt-4 block text-sm font-bold text-slate-700">
        عدد الحصص
        <input type="number" min={1} max={20} step={1} required value={minimum} onChange={(event) => setMinimum(Number(event.target.value))} className="mt-2 block w-28 rounded-xl border border-slate-300 px-3 py-2.5" />
      </label>}
      <p className="mt-3 text-xs leading-6 text-slate-500">مثال: عند اختيار حصتين، يمكن مراجعة الإرسال بعد اعتماد حصتين من فصل الطالب، حتى لو كان الجدول يتضمن حصصًا أخرى. نص الرسالة يذكر الغياب المسجل في التحاضير المعتمدة.</p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button type="submit" loading={mutation.isPending} disabled={minimum === saved || !Number.isInteger(minimum) || minimum < 0 || minimum > 20}>حفظ معيار المدرسة</Button>
        {minimum === saved && <span className="text-xs text-slate-500">المعيار المحفوظ لهذه المدرسة</span>}
      </div>
      {mutation.isError && <p role="alert" className="mt-3 text-sm text-red-700">{mutation.error.message}</p>}
    </form>
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
