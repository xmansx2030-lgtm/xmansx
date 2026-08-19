import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
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
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-bold text-slate-800">أجهزة الحضور</h2>
        <p className="text-sm text-slate-500">
          الجسر يعمل داخل شبكة المدرسة ويتصل للخارج فقط — لا حاجة لفتح أي منفذ، ولا
          تخزن المنصة أي بيانات بيومترية.
        </p>
        {actionError != null && <ErrorState error={actionError} />}
      </section>

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

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-2 font-bold text-slate-800">الجسور</h3>
        {bridgesQuery.isPending && <Spinner />}
        {bridgesQuery.isError && <ErrorState error={bridgesQuery.error} />}
        {bridgesQuery.isSuccess && (
          <ul className="divide-y divide-slate-100" data-testid="bridges-list">
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
                <span className="text-sm text-slate-600">
                  {bridge.is_online ? "🟢 متصل" : "⚪ غير متصل"}
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
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!bridgeName.trim()) return;
            void run(async () => {
              setCredential(await createBridge(bridgeName.trim()));
              setBridgeName("");
            });
          }}
        >
          <input
            value={bridgeName}
            onChange={(e) => setBridgeName(e.target.value)}
            placeholder="اسم الجسر (مثال: خادم الاستقبال)"
            aria-label="اسم الجسر"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          />
          <Button type="submit" data-testid="add-bridge">
            إضافة جسر
          </Button>
        </form>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-2 font-bold text-slate-800">الأجهزة</h3>
        {devicesQuery.isPending && <Spinner />}
        {devicesQuery.isError && <ErrorState error={devicesQuery.error} />}
        {devicesQuery.isSuccess && (
          <ul className="divide-y divide-slate-100" data-testid="devices-list">
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
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!deviceForm.name.trim()) return;
            void run(async () => {
              await createDevice({
                name: deviceForm.name.trim(),
                vendor: deviceForm.vendor.trim(),
                local_ip: deviceForm.local_ip.trim() || undefined,
              });
              setDeviceForm({ name: "", vendor: "", local_ip: "" });
            });
          }}
        >
          <input
            value={deviceForm.name}
            onChange={(e) => setDeviceForm({ ...deviceForm, name: e.target.value })}
            placeholder="اسم الجهاز"
            aria-label="اسم الجهاز"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          />
          <input
            value={deviceForm.vendor}
            onChange={(e) => setDeviceForm({ ...deviceForm, vendor: e.target.value })}
            placeholder="الشركة (SIMULATOR للتجربة)"
            aria-label="الشركة"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          />
          <input
            value={deviceForm.local_ip}
            onChange={(e) => setDeviceForm({ ...deviceForm, local_ip: e.target.value })}
            placeholder="IP المحلي (اختياري)"
            aria-label="IP المحلي"
            dir="ltr"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          />
          <Button type="submit" data-testid="add-device">
            إضافة جهاز
          </Button>
        </form>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-2 font-bold text-slate-800">مطابقة مستخدمي الأجهزة</h3>
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
  onMap,
  onUnmap,
}: {
  identity: IdentityRow;
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
          ربط بطالب
        </Button>
      )}
    </li>
  );
}
