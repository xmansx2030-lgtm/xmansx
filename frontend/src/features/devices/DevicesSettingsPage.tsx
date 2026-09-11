import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cable,
  Fingerprint,
  Link2,
  Pencil,
  Router,
  Save,
  ShieldCheck,
  UsersRound,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import type {
  BridgeCredential,
  DeviceFull,
  DeviceMutationPayload,
  IdentityRow,
} from "@/features/devices/api";
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
  updateDevice,
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

interface DeviceFormState {
  name: string;
  vendor: "ZKTECO" | "SIMULATOR";
  model: string;
  serial_number: string;
  connection_type: "TCP" | "UDP";
  local_ip: string;
  local_port: string;
  connection_secret: string;
}

const NEW_DEVICE_FORM: DeviceFormState = {
  name: "",
  vendor: "ZKTECO",
  model: "MB2000",
  serial_number: "",
  connection_type: "TCP",
  local_ip: "",
  local_port: "4370",
  connection_secret: "0",
};

function editFormFor(device: DeviceFull): DeviceFormState {
  return {
    name: device.name,
    vendor: device.vendor.toUpperCase() === "SIMULATOR" ? "SIMULATOR" : "ZKTECO",
    model: device.model || (device.vendor.toUpperCase() === "SIMULATOR" ? "" : "MB2000"),
    serial_number: device.serial_number,
    connection_type: device.connection_type.toUpperCase() === "UDP" ? "UDP" : "TCP",
    local_ip: device.local_ip,
    local_port: String(device.local_port ?? 4370),
    connection_secret: "",
  };
}

function devicePayload(
  form: DeviceFormState,
  includeEmptySecret: boolean,
): DeviceMutationPayload {
  const port = form.local_port.trim() ? Number(form.local_port) : null;
  const payload: DeviceMutationPayload = {
    name: form.name.trim(),
    vendor: form.vendor,
    model: form.model.trim(),
    serial_number: form.serial_number.trim(),
    connection_type: form.connection_type,
    local_ip: form.local_ip.trim(),
    local_port: Number.isFinite(port) ? port : null,
  };
  if (includeEmptySecret || form.connection_secret.trim()) {
    payload.connection_secret = form.connection_secret.trim();
  }
  return payload;
}

function isLanReady(device: DeviceFull) {
  return (
    device.vendor.toUpperCase() === "ZKTECO" &&
    device.model.toUpperCase() === "MB2000" &&
    Boolean(device.local_ip) &&
    Boolean(device.local_port)
  );
}

/** إعدادات أجهزة الحضور (مدير فقط): الجسور، الأجهزة، مطابقة مستخدمي الأجهزة. */
export function DevicesSettingsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [credential, setCredential] = useState<BridgeCredential | null>(null);
  const [bridgeName, setBridgeName] = useState("");
  const [deviceForm, setDeviceForm] = useState<DeviceFormState>({ ...NEW_DEVICE_FORM });
  const [editingDeviceId, setEditingDeviceId] = useState<number | null>(null);
  const [editDeviceForm, setEditDeviceForm] = useState<DeviceFormState | null>(null);
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
    <div className="ds-page">
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
        <div className="mb-4 rounded-2xl border border-violet-100 bg-violet-50/50 p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-bold text-slate-900">إعداد ZKTeco MB2000 عبر LAN</p>
              <p className="mt-1 text-xs leading-5 text-slate-600">
                استخدم IP ثابتًا داخل شبكة المدرسة، والمنفذ 4370، وComm Key مطابقًا
                تمامًا لقيمة PC Connection في الجهاز.
              </p>
            </div>
            <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-violet-700 ring-1 ring-violet-200">
              لا تُرسل قوالب الوجه أو البصمة
            </span>
          </div>
          <form
          className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (
              !deviceForm.name.trim() ||
              (deviceForm.vendor === "ZKTECO" && !deviceForm.local_ip.trim())
            ) return;
            void run(async () => {
              await createDevice(devicePayload(deviceForm, true));
              setDeviceForm({ ...NEW_DEVICE_FORM });
            });
          }}
        >
          <DeviceLanFields form={deviceForm} onChange={setDeviceForm} />
          <div className="flex items-end xl:col-span-4">
            <Button
              type="submit"
              data-testid="add-device"
              disabled={
                !deviceForm.name.trim() ||
                (deviceForm.vendor === "ZKTECO" && !deviceForm.local_ip.trim())
              }
            >
              <Cable aria-hidden size={16} /> حفظ وإضافة الجهاز
            </Button>
          </div>
        </form>
        </div>
        {devicesQuery.isPending && <Spinner />}
        {devicesQuery.isError && <ErrorState error={devicesQuery.error} />}
        {devicesQuery.isSuccess && (
          <ul className="max-h-[40rem] space-y-3 overflow-y-auto" data-testid="devices-list">
            {devicesQuery.data.length === 0 && (
              <li className="py-2 text-slate-500">لا توجد أجهزة بعد.</li>
            )}
            {devicesQuery.data.map((device) => (
              <li
                key={device.id}
                className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4"
                data-testid={`device-${device.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-bold text-slate-950">{device.name}</p>
                      {isLanReady(device) ? (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
                          إعداد LAN مكتمل
                        </span>
                      ) : device.vendor.toUpperCase() === "ZKTECO" ? (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-700">
                          إعداد LAN ناقص
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs text-slate-500" dir="ltr">
                      {device.vendor || "—"} · {device.model || "—"} · {device.local_ip || "—"}:{device.local_port ?? "—"} · {device.connection_type}
                    </p>
                    {device.serial_number && (
                      <p className="mt-1 text-xs text-slate-500" dir="ltr">
                        S/N: {device.serial_number}
                      </p>
                    )}
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-bold ${device.status === "ONLINE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-700"}`}
                    data-testid={`device-status-${device.id}`}
                  >
                    {DEVICE_STATUS_LABELS[device.status] ?? device.status}
                    {device.unmatched_events > 0 && ` · ${device.unmatched_events} حدثًا غير مطابق`}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-3">
                  <div>
                    {device.test_result ? (
                      <span
                        className={`text-xs font-medium ${device.test_result.ok ? "text-emerald-700" : "text-red-700"}`}
                        data-testid="test-result"
                      >
                        {device.test_result.ok ? "نجح الفحص: " : "فشل الفحص: "}
                        {device.test_result.detail}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-500">لم يُنفذ اختبار اتصال بعد.</span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setEditingDeviceId(device.id);
                        setEditDeviceForm(editFormFor(device));
                      }}
                      data-testid={`edit-device-${device.id}`}
                    >
                      <Pencil aria-hidden size={15} /> تعديل الشبكة
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => void run(() => testDeviceConnection(device.id))}
                      data-testid={`test-device-${device.id}`}
                    >
                      اختبار الاتصال
                    </Button>
                  </div>
                </div>
                {editingDeviceId === device.id && editDeviceForm && (
                  <form
                    className="mt-4 grid gap-3 rounded-xl border border-blue-200 bg-white p-4 md:grid-cols-2 xl:grid-cols-4"
                    data-testid={`edit-device-form-${device.id}`}
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (
                        !editDeviceForm.name.trim() ||
                        (editDeviceForm.vendor === "ZKTECO" && !editDeviceForm.local_ip.trim())
                      ) return;
                      void run(async () => {
                        await updateDevice(device.id, devicePayload(editDeviceForm, false));
                        setEditingDeviceId(null);
                        setEditDeviceForm(null);
                      });
                    }}
                  >
                    <DeviceLanFields
                      form={editDeviceForm}
                      onChange={setEditDeviceForm}
                      editing
                    />
                    <div className="flex flex-wrap items-end gap-2 xl:col-span-4">
                      <Button type="submit" data-testid={`save-device-${device.id}`}>
                        <Save aria-hidden size={15} /> حفظ إعداد LAN
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setEditingDeviceId(null);
                          setEditDeviceForm(null);
                        }}
                      >
                        <X aria-hidden size={15} /> إلغاء
                      </Button>
                    </div>
                  </form>
                )}
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

function DeviceLanFields({
  form,
  onChange,
  editing = false,
}: {
  form: DeviceFormState;
  onChange: (next: DeviceFormState) => void;
  editing?: boolean;
}) {
  const inputClass =
    "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100";
  const set = (field: keyof DeviceFormState, value: string) =>
    onChange({ ...form, [field]: value });

  return (
    <>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">اسم الجهاز</span>
        <input
          value={form.name}
          onChange={(event) => set("name", event.target.value)}
          placeholder="البوابة الرئيسية"
          aria-label={editing ? "تعديل اسم الجهاز" : "اسم الجهاز"}
          className={inputClass}
          required
        />
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">الشركة</span>
        <select
          value={form.vendor}
          onChange={(event) => {
            const vendor = event.target.value as DeviceFormState["vendor"];
            onChange({
              ...form,
              vendor,
              model: vendor === "ZKTECO" ? form.model || "MB2000" : "",
              local_port: vendor === "ZKTECO" ? form.local_port || "4370" : form.local_port,
            });
          }}
          aria-label={editing ? "تعديل الشركة" : "الشركة"}
          className={inputClass}
        >
          <option value="ZKTECO">ZKTeco</option>
          <option value="SIMULATOR">Simulator (تطوير)</option>
        </select>
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">الموديل</span>
        <input
          value={form.model}
          onChange={(event) => set("model", event.target.value)}
          placeholder="MB2000"
          aria-label={editing ? "تعديل الموديل" : "الموديل"}
          className={inputClass}
        />
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">الرقم التسلسلي</span>
        <input
          value={form.serial_number}
          onChange={(event) => set("serial_number", event.target.value)}
          placeholder="اختياري"
          aria-label={editing ? "تعديل الرقم التسلسلي" : "الرقم التسلسلي"}
          className={inputClass}
          dir="ltr"
        />
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">IP المحلي الثابت</span>
        <input
          value={form.local_ip}
          onChange={(event) => set("local_ip", event.target.value)}
          placeholder="192.168.1.50"
          aria-label={editing ? "تعديل IP المحلي" : "IP المحلي"}
          className={inputClass}
          inputMode="decimal"
          dir="ltr"
          required={form.vendor === "ZKTECO"}
        />
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">المنفذ</span>
        <input
          value={form.local_port}
          onChange={(event) => set("local_port", event.target.value)}
          placeholder="4370"
          aria-label={editing ? "تعديل المنفذ" : "المنفذ"}
          className={inputClass}
          inputMode="numeric"
          dir="ltr"
          required={form.vendor === "ZKTECO"}
        />
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">البروتوكول</span>
        <select
          value={form.connection_type}
          onChange={(event) =>
            set("connection_type", event.target.value as DeviceFormState["connection_type"])
          }
          aria-label={editing ? "تعديل البروتوكول" : "البروتوكول"}
          className={inputClass}
        >
          <option value="TCP">TCP (موصى به)</option>
          <option value="UDP">UDP</option>
        </select>
      </label>
      <label>
        <span className="mb-1 block text-xs font-bold text-slate-600">
          Comm Key {editing && <span className="font-normal">(اتركه فارغًا للإبقاء عليه)</span>}
        </span>
        <input
          type="password"
          value={form.connection_secret}
          onChange={(event) => set("connection_secret", event.target.value)}
          placeholder={editing ? "بدون تغيير" : "0"}
          aria-label={editing ? "تعديل Comm Key" : "Comm Key"}
          className={inputClass}
          inputMode="numeric"
          dir="ltr"
          autoComplete="new-password"
        />
      </label>
    </>
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
