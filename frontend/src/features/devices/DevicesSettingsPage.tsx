import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Cable, Fingerprint, Link2, Router, ShieldCheck, UsersRound, Wifi, WifiOff } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import type { BridgeCredential, IdentityRow } from "@/features/devices/api";
import {
  createBridge,
  createDevice,
  getBridges,
  getDevicesFull,
  getIdentities,
  mapIdentity,
  rotateBridge,
  testDeviceConnection,
  unmapIdentity,
} from "@/features/devices/api";
import { StudentPicker } from "@/features/devices/StudentPicker";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import type { SchoolType } from "@/types/auth";
import { studentLabel, studentPluralLabel } from "@/utils/roles";

const DEVICE_STATUS_LABELS: Record<string, string> = {
  ONLINE: "متصل",
  OFFLINE: "غير متصل",
  DEGRADED: "متقطع",
  DISABLED: "موقوف",
  UNKNOWN: "غير معروف",
};

/** إعدادات أجهزة الحضور (مدير فقط): الجسور، الأجهزة، مطابقة مستخدمي الأجهزة. */
export function DevicesSettingsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [credential, setCredential] = useState<BridgeCredential | null>(null);
  const [bridgeName, setBridgeName] = useState("");
  const [deviceForm, setDeviceForm] = useState({ name: "", vendor: "", local_ip: "" });
  const [identityTab, setIdentityTab] = useState<"UNMATCHED" | "MATCHED" | "CONFLICT">(
    "UNMATCHED",
  );
  const [actionError, setActionError] = useState<unknown>(null);

  const bridgesQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "devices", "bridges"),
    queryFn: ({ signal }) => getBridges(signal),
    enabled: schoolId > 0,
  });
  const devicesQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "devices", "list"),
    queryFn: ({ signal }) => getDevicesFull(signal),
    enabled: schoolId > 0,
    refetchInterval: 30_000, // حالة الأجهزة تتغير مع النبضات
  });
  const identitiesQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "devices", "identities", identityTab),
    queryFn: ({ signal }) => getIdentities(identityTab, signal),
    enabled: schoolId > 0,
  });

  const refresh = () =>
    queryClient.invalidateQueries({
      predicate: (q) => JSON.stringify(q.queryKey).includes('"devices"'),
    });

  const run = async (action: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await action();
      await refresh();
    } catch (error) {
      setActionError(error);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={Fingerprint}
        eyebrow="التكاملات التشغيلية"
        title="أجهزة الحضور"
        description={`إدارة جسور الاتصال والأجهزة ومطابقة معرفات ${studentPluralLabel(schoolType)} من مساحة واحدة آمنة. الاتصال يبدأ من داخل شبكة المدرسة ولا تُخزن بيانات بيومترية في المنصة.`}
        tone="operational"
        badge={devicesQuery.data ? `${devicesQuery.data.filter((device) => device.status === "ONLINE").length} متصل من ${devicesQuery.data.length}` : "جارٍ التحقق"}
        meta={<><span className="inline-flex items-center gap-1"><ShieldCheck aria-hidden size={14} /> اتصال خارجي آمن</span><span aria-hidden>•</span><span>لا حاجة لفتح منافذ واردة</span></>}
      />
      {actionError != null && <ErrorState error={actionError} />}

      {credential && (
        <section
          className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-900 shadow-sm"
          data-testid="bridge-credential-box"
        >
          <p className="font-bold">رمز اعتماد الجسر — يظهر مرة واحدة فقط:</p>
          <code className="mt-2 block break-all rounded bg-white p-2 text-xs" dir="ltr">
            {credential.credential}
          </code>
          <p className="mt-2 text-sm">
            انسخه الآن وأدخله أثناء تثبيت الجسر ({credential.bridge.installation_name}).
            لن يعرض مجددًا — التجديد يولّد رمزًا جديدًا ويبطل القديم.
          </p>
          <Button variant="secondary" className="mt-2" onClick={() => setCredential(null)}>
            أغلقت النسخ — إخفاء
          </Button>
        </section>
      )}

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700"><Router aria-hidden size={20} /></span><div><h2 className="font-black text-slate-950">جسور الاتصال</h2><p className="text-xs text-slate-500">الخادم الوسيط داخل شبكة المدرسة</p></div></div>{bridgesQuery.data && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">{bridgesQuery.data.length} جسر</span>}</div>
        <form
          className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl border border-blue-100 bg-blue-50/60 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!bridgeName.trim()) return;
            void run(async () => {
              setCredential(await createBridge(bridgeName.trim()));
              setBridgeName("");
            });
          }}
        >
          <label className="min-w-56 flex-1"><span className="mb-1 block text-xs font-bold text-slate-600">اسم الجسر الجديد</span><input value={bridgeName} onChange={(e) => setBridgeName(e.target.value)} placeholder="مثال: خادم الاستقبال" aria-label="اسم الجسر" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm" /></label>
          <Button type="submit" data-testid="add-bridge" disabled={!bridgeName.trim()}><Link2 aria-hidden size={16} /> إضافة جسر</Button>
        </form>
        {bridgesQuery.isPending && <Spinner />}
        {bridgesQuery.isError && <ErrorState error={bridgesQuery.error} />}
        {bridgesQuery.isSuccess && (
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto rounded-2xl border border-slate-100 px-3" data-testid="bridges-list">
            {bridgesQuery.data.length === 0 && (
              <li className="py-2 text-slate-500">لا توجد جسور بعد.</li>
            )}
            {bridgesQuery.data.map((bridge) => (
              <li
                key={bridge.id}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
                data-testid={`bridge-${bridge.id}`}
              >
                <span className="font-medium">{bridge.installation_name}</span>
                <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold ${bridge.is_online ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                  {bridge.is_online ? <Wifi aria-hidden size={13} /> : <WifiOff aria-hidden size={13} />}{bridge.is_online ? "متصل" : "غير متصل"}
                </span>
                <Button
                  variant="secondary"
                  onClick={() => {
                    if (
                      window.confirm(
                        "تجديد الرمز يبطل رمز الجسر الحالي فورًا — تابع فقط إذا كنت ستعيد إعداد الجسر.",
                      )
                    ) {
                      void run(async () => setCredential(await rotateBridge(bridge.id)));
                    }
                  }}
                  data-testid={`rotate-bridge-${bridge.id}`}
                >
                  تدوير الاعتماد
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-violet-50 text-violet-700"><Cable aria-hidden size={20} /></span><div><h2 className="font-black text-slate-950">الأجهزة المسجلة</h2><p className="text-xs text-slate-500">حالة الاتصال والفحص الفني لكل جهاز</p></div></div>{devicesQuery.data && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">{devicesQuery.data.length} جهاز</span>}</div>
        <form
          className="mb-4 grid gap-2 rounded-2xl border border-violet-100 bg-violet-50/50 p-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (!deviceForm.name.trim()) return;
            void run(async () => {
              await createDevice({ name: deviceForm.name.trim(), vendor: deviceForm.vendor.trim(), local_ip: deviceForm.local_ip.trim() || undefined });
              setDeviceForm({ name: "", vendor: "", local_ip: "" });
            });
          }}
        >
          <label><span className="mb-1 block text-xs font-bold text-slate-600">اسم الجهاز</span><input value={deviceForm.name} onChange={(e) => setDeviceForm({ ...deviceForm, name: e.target.value })} placeholder="البوابة الرئيسية" aria-label="اسم الجهاز" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm" /></label>
          <label><span className="mb-1 block text-xs font-bold text-slate-600">الشركة أو النوع</span><input value={deviceForm.vendor} onChange={(e) => setDeviceForm({ ...deviceForm, vendor: e.target.value })} placeholder="SIMULATOR للتجربة" aria-label="الشركة" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm" /></label>
          <label><span className="mb-1 block text-xs font-bold text-slate-600">عنوان الشبكة (اختياري)</span><input value={deviceForm.local_ip} onChange={(e) => setDeviceForm({ ...deviceForm, local_ip: e.target.value })} placeholder="192.168.1.50" aria-label="IP المحلي" dir="ltr" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm" /></label>
          <Button type="submit" data-testid="add-device" disabled={!deviceForm.name.trim()}><Cable aria-hidden size={16} /> إضافة جهاز</Button>
        </form>
        {devicesQuery.isPending && <Spinner />}
        {devicesQuery.isError && <ErrorState error={devicesQuery.error} />}
        {devicesQuery.isSuccess && (
          <ul className="max-h-[30rem] divide-y divide-slate-100 overflow-y-auto rounded-2xl border border-slate-100 px-3" data-testid="devices-list">
            {devicesQuery.data.length === 0 && (
              <li className="py-2 text-slate-500">لا توجد أجهزة بعد.</li>
            )}
            {devicesQuery.data.map((device) => (
              <li
                key={device.id}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
                data-testid={`device-${device.id}`}
              >
                <div>
                  <p className="font-medium">{device.name}</p>
                  <p className="text-xs text-slate-500" dir="ltr">
                    {device.vendor || "—"} · {device.local_ip || "—"}
                  </p>
                </div>
                <span className="text-sm" data-testid={`device-status-${device.id}`}>
                  {DEVICE_STATUS_LABELS[device.status] ?? device.status}
                  {device.unmatched_events > 0 &&
                    ` · ${device.unmatched_events} حدثًا غير مطابق`}
                </span>
                <div className="flex items-center gap-2">
                  {device.test_result && (
                    <span className="text-xs text-slate-500" data-testid="test-result">
                      {device.test_result.ok ? "✅" : "❌"} {device.test_result.detail}
                    </span>
                  )}
                  <Button
                    variant="secondary"
                    onClick={() => void run(() => testDeviceConnection(device.id))}
                    data-testid={`test-device-${device.id}`}
                  >
                    اختبار الاتصال
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-4 flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><UsersRound aria-hidden size={20} /></span><div><h2 className="font-black text-slate-950">مطابقة مستخدمي الأجهزة</h2><p className="text-xs text-slate-500">اربط معرف الجهاز بسجل {studentLabel(schoolType, true)} الصحيح</p></div></div>
        <div className="mb-3 flex gap-1" role="tablist">
          {(
            [
              ["UNMATCHED", "غير مطابق"],
              ["MATCHED", "تمت المطابقة"],
              ["CONFLICT", "متعارض"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={identityTab === key}
              onClick={() => setIdentityTab(key)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                identityTab === key
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {identitiesQuery.isPending && <Spinner />}
        {identitiesQuery.isError && <ErrorState error={identitiesQuery.error} />}
        {identitiesQuery.isSuccess && (
          <ul className="divide-y divide-slate-100" data-testid="identities-list">
            {identitiesQuery.data.length === 0 && (
              <li className="py-2 text-slate-500">لا توجد سجلات في هذا التبويب.</li>
            )}
            {identitiesQuery.data.map((identity) => (
              <IdentityRowView
                key={identity.id}
                identity={identity}
                schoolType={schoolType}
                onMap={(studentId) => run(() => mapIdentity(identity.id, studentId))}
                onUnmap={() => run(() => unmapIdentity(identity.id))}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function IdentityRowView({
  identity,
  schoolType,
  onMap,
  onUnmap,
}: {
  identity: IdentityRow;
  schoolType: SchoolType;
  onMap: (studentId: number) => Promise<void> | void;
  onUnmap: () => Promise<void> | void;
}) {
  const [picking, setPicking] = useState(false);
  return (
    <li
      className="flex flex-wrap items-center justify-between gap-2 py-2"
      data-testid={`identity-${identity.id}`}
    >
      <div>
        <p className="font-medium" dir="ltr">
          {identity.external_user_id}
        </p>
        <p className="text-xs text-slate-500">
          {identity.device_name}
          {identity.display_name && ` · ${identity.display_name}`}
        </p>
      </div>
      {identity.status === "MATCHED" ? (
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-700">{identity.student_name}</span>
          <Button variant="secondary" onClick={() => void onUnmap()}>
            إلغاء الربط
          </Button>
        </div>
      ) : picking ? (
        <StudentPicker
          onSelect={(studentId) => {
            setPicking(false);
            void onMap(studentId);
          }}
          onCancel={() => setPicking(false)}
        />
      ) : (
        <Button onClick={() => setPicking(true)} data-testid={`map-identity-${identity.id}`}>
          ربط {schoolType === "GIRLS" ? "بطالبة" : "بطالب"}
        </Button>
      )}
    </li>
  );
}
