import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { useLogout } from "@/features/auth/useMe";
import {
  addSchoolManager,
  createPlan,
  createPlatformSchool,
  disablePlan,
  getPlans,
  getPlatformOverview,
  getPlatformSchools,
  getPlanChangePreview,
  getSchoolDetail,
  getSubscriptionEvents,
  getSubscriptionHistory,
  runSubscriptionAction,
  runSchoolManagerAction,
  updatePlatformSchool,
  updatePlan,
  updateSchoolManager,
  type ManagerCredentialResponse,
  type Plan,
  type PlanInput,
  type SchoolDetail,
  type SchoolManagerAccount,
  type SchoolRow,
  type Usage,
} from "@/features/platform/api";

const LIMIT_KEYS = ["MAX_STUDENTS", "MAX_STAFF", "MAX_DEVICES", "MAX_STORAGE_GB"] as const;
const LIMIT_FORM_KEYS = {
  MAX_STUDENTS: "max_students",
  MAX_STAFF: "max_staff",
  MAX_DEVICES: "max_devices",
  MAX_STORAGE_GB: "max_storage_gb",
} as const;
const FEATURE_KEYS = [
  "ATTENDANCE",
  "BIOMETRIC_DEVICES",
  "ROSTER_SYNC",
  "EXCUSES",
  "WARNINGS",
  "DOCUMENTS",
  "REFERRALS",
  "COUNSELING",
  "EXECUTIVE_DASHBOARD",
] as const;

const STATUS_LABELS: Record<string, string> = {
  NO_SUBSCRIPTION: "بدون اشتراك",
  TRIAL: "تجريبي",
  ACTIVE: "نشط",
  GRACE_PERIOD: "مهلة سماح",
  EXPIRED: "منتهي",
  SUSPENDED: "موقوف",
  CANCELLED: "ملغي",
};
const ENTITLEMENT_LABELS: Record<string, string> = {
  MAX_STUDENTS: "الحد الأقصى للطلاب",
  MAX_STAFF: "الحد الأقصى للموظفين",
  MAX_DEVICES: "الحد الأقصى للأجهزة",
  MAX_STORAGE_GB: "التخزين (GB)",
  ATTENDANCE: "التحضير",
  BIOMETRIC_DEVICES: "أجهزة البصمة",
  ROSTER_SYNC: "مزامنة القوائم",
  EXCUSES: "الأعذار",
  WARNINGS: "الإنذارات",
  DOCUMENTS: "المستندات",
  REFERRALS: "الإحالات",
  COUNSELING: "الإرشاد الطلابي",
  EXECUTIVE_DASHBOARD: "لوحة المؤشرات التنفيذية",
};

const statusLabel = (status: string | null | undefined) =>
  STATUS_LABELS[status ?? "NO_SUBSCRIPTION"] ?? status ?? STATUS_LABELS.NO_SUBSCRIPTION;

function statusClass(status: string | null | undefined) {
  if (status === "ACTIVE" || status === "TRIAL") return "bg-emerald-50 text-emerald-700";
  if (status === "GRACE_PERIOD") return "bg-amber-50 text-amber-700";
  if (status === "SUSPENDED" || status === "CANCELLED") return "bg-red-50 text-red-700";
  return "bg-slate-100 text-slate-700";
}

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : "تعذر تنفيذ الطلب.";
  return <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p>;
}

function UsageGrid({ usage }: { usage: Usage }) {
  const rows = [
    ["الطلاب", usage.students],
    ["الموظفون", usage.staff],
    ["الأجهزة", usage.devices],
    ["التخزين", { ...usage.storage, used: usage.storage.used_gb, limit: usage.storage.limit_gb }],
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-3">
      {rows.map(([label, row]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-xs text-slate-500">{label}</p>
          <p className="mt-1 text-lg font-bold text-slate-900">
            {row.used} / {row.limit ?? "بلا حد"}
          </p>
          {row.over_limit && <p className="mt-1 text-xs font-semibold text-red-700">تجاوز الحد</p>}
          {!row.over_limit && row.near_limit && <p className="mt-1 text-xs font-semibold text-amber-700">قريب من الحد</p>}
        </div>
      ))}
    </div>
  );
}

const formatDate = (value: string | null | undefined) =>
  value ? new Intl.DateTimeFormat("ar-SA", { dateStyle: "medium" }).format(new Date(value)) : "—";

function CredentialNotice({
  mobile,
  password,
  onClose,
}: {
  mobile: string;
  password: string | null;
  onClose: () => void;
}) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" role="status">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-bold">بيانات الدخول</p>
          <p className="mt-1">رقم الجوال: <b dir="ltr">{mobile}</b></p>
          {password ? (
            <>
              <p>كلمة المرور المؤقتة: <b dir="ltr">{password}</b></p>
              <p className="mt-1 text-xs">تظهر مرة واحدة، وسيُطلب من المدير تغييرها بعد الدخول.</p>
            </>
          ) : (
            <p className="mt-1 text-xs">الحساب موجود مسبقًا ويستخدم كلمة مروره الحالية.</p>
          )}
        </div>
        <button type="button" className="text-xs font-bold text-amber-900" onClick={onClose}>إخفاء</button>
      </div>
      {password && (
        <Button
          type="button"
          variant="secondary"
          className="mt-2 px-3 py-1.5"
          onClick={() => void navigator.clipboard.writeText(`رقم الجوال: ${mobile}\nكلمة المرور المؤقتة: ${password}`)}
        >
          نسخ بيانات الدخول
        </Button>
      )}
    </div>
  );
}

function ManagerAccountCard({
  schoolId,
  manager,
}: {
  schoolId: number;
  manager: SchoolManagerAccount;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(manager.name);
  const [mobile, setMobile] = useState(manager.mobile);
  const [confirmation, setConfirmation] = useState<"reset-password" | "suspend" | null>(null);
  const [credentials, setCredentials] = useState<ManagerCredentialResponse | null>(null);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "school", schoolId] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => updateSchoolManager(schoolId, manager.membership_id, { name, mobile }),
    onSuccess: refresh,
  });
  const accountAction = useMutation({
    mutationFn: (action: "reset-password" | "suspend" | "reactivate") =>
      runSchoolManagerAction(schoolId, manager.membership_id, action),
    onSuccess: async (result) => {
      if ("temporary_password" in result) setCredentials(result);
      setConfirmation(null);
      await refresh();
    },
  });
  const active = manager.membership_status === "ACTIVE";

  return (
    <article className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold text-slate-900">{manager.name}</p>
          <p className="text-xs text-slate-500">
            {active ? "عضوية فعالة" : "عضوية موقوفة"} · آخر دخول {formatDate(manager.last_login)}
          </p>
        </div>
        <span className={`rounded px-2 py-1 text-xs ${manager.must_change_password ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
          {manager.must_change_password ? "بانتظار تغيير كلمة المرور" : "بيانات الدخول مفعلة"}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs font-semibold text-slate-600">
          اسم المدير
          <input aria-label={`اسم المدير ${manager.membership_id}`} className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="text-xs font-semibold text-slate-600">
          رقم الجوال للدخول
          <input aria-label={`جوال المدير ${manager.membership_id}`} dir="ltr" className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-left" value={mobile} onChange={(event) => setMobile(event.target.value)} />
        </label>
      </div>
      {manager.shared_with_other_schools && <p className="mt-2 text-xs text-blue-700">هذا الحساب مرتبط بمدارس أخرى؛ تعديل الجوال يغيّر معرف دخوله إليها أيضًا.</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" className="px-3 py-1.5" disabled={save.isPending} onClick={() => save.mutate()}>حفظ بيانات الحساب</Button>
        <Button type="button" variant="secondary" className="px-3 py-1.5" disabled={accountAction.isPending} onClick={() => setConfirmation("reset-password")}>إعادة ضبط كلمة المرور</Button>
        {active ? (
          <Button type="button" variant="danger" className="px-3 py-1.5" disabled={accountAction.isPending} onClick={() => setConfirmation("suspend")}>إيقاف المدير</Button>
        ) : (
          <Button type="button" variant="secondary" className="px-3 py-1.5" disabled={accountAction.isPending} onClick={() => accountAction.mutate("reactivate")}>إعادة تفعيل المدير</Button>
        )}
      </div>
      {confirmation && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          <p>{confirmation === "reset-password" ? "سيتم إبطال كلمة المرور الحالية وإصدار كلمة مؤقتة جديدة." : "سيتوقف وصول هذا المدير إلى المدرسة. لا يمكن إيقاف المدير الوحيد."}</p>
          <div className="mt-2 flex gap-2">
            <Button type="button" variant="danger" className="px-3 py-1.5" onClick={() => accountAction.mutate(confirmation)}>تأكيد</Button>
            <Button type="button" variant="secondary" className="px-3 py-1.5" onClick={() => setConfirmation(null)}>تراجع</Button>
          </div>
        </div>
      )}
      <div className="mt-2"><ErrorLine error={save.error ?? accountAction.error} /></div>
      {credentials && <div className="mt-3"><CredentialNotice mobile={credentials.manager.mobile} password={credentials.temporary_password} onClose={() => setCredentials(null)} /></div>}
    </article>
  );
}

function SchoolAccountManagement({ detail }: { detail: SchoolDetail }) {
  const queryClient = useQueryClient();
  const [schoolName, setSchoolName] = useState(detail.name);
  const [schoolStatus, setSchoolStatus] = useState(detail.school_status);
  const [newManager, setNewManager] = useState({ name: "", mobile: "" });
  const [credentials, setCredentials] = useState<ManagerCredentialResponse | null>(null);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "school", detail.id] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
    ]);
  };
  const saveSchool = useMutation({
    mutationFn: () => updatePlatformSchool(detail.id, { name: schoolName, school_status: schoolStatus }),
    onSuccess: refresh,
  });
  const addManager = useMutation({
    mutationFn: () => addSchoolManager(detail.id, newManager),
    onSuccess: async (result) => {
      setCredentials(result);
      setNewManager({ name: "", mobile: "" });
      await refresh();
    },
  });

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <h3 className="font-bold text-slate-900">بيانات المدرسة والدخول</h3>
        <p className="text-xs text-slate-500">المعرف: {detail.slug} · أضيفت {formatDate(detail.created_at)}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_150px]">
        <label className="text-xs font-semibold text-slate-600">
          اسم المدرسة
          <input aria-label="اسم المدرسة المسجلة" className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm" value={schoolName} onChange={(event) => setSchoolName(event.target.value)} />
        </label>
        <label className="text-xs font-semibold text-slate-600">
          حالة المدرسة
          <select aria-label="حالة المدرسة التشغيلية" className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm" value={schoolStatus} onChange={(event) => setSchoolStatus(event.target.value)}>
            <option value="ACTIVE">نشطة</option>
            <option value="SUSPENDED">موقوفة</option>
            <option value="ARCHIVED">مؤرشفة</option>
          </select>
        </label>
      </div>
      <p className="text-xs text-slate-500">إيقاف المدرسة يمنع جميع حساباتها من الدخول حتى إعادة تفعيلها.</p>
      <Button type="button" className="px-3 py-1.5" disabled={saveSchool.isPending} onClick={() => saveSchool.mutate()}>حفظ بيانات المدرسة</Button>
      <ErrorLine error={saveSchool.error} />

      <div className="border-t border-slate-200 pt-3">
        <h4 className="font-bold text-slate-900">حسابات مديري المدرسة</h4>
        <p className="mb-3 text-xs text-slate-500">إدارة معرفات الدخول دون الاطلاع على كلمة المرور الحالية.</p>
        <div className="space-y-3">
          {(detail.managers ?? []).map((manager) => <ManagerAccountCard key={`${manager.membership_id}:${manager.name}:${manager.mobile}`} schoolId={detail.id} manager={manager} />)}
          {(detail.managers ?? []).length === 0 && <p className="rounded bg-amber-50 p-3 text-sm text-amber-800">لا يوجد مدير مرتبط بهذه المدرسة.</p>}
        </div>
      </div>

      <form className="border-t border-slate-200 pt-3" onSubmit={(event) => { event.preventDefault(); addManager.mutate(); }}>
        <h4 className="mb-2 font-bold text-slate-900">إضافة مدير آخر</h4>
        <div className="grid gap-2 sm:grid-cols-2">
          <input aria-label="اسم المدير الجديد" className="rounded border border-slate-300 px-3 py-2 text-sm" placeholder="اسم المدير" value={newManager.name} onChange={(event) => setNewManager({ ...newManager, name: event.target.value })} />
          <input aria-label="جوال المدير الجديد" dir="ltr" className="rounded border border-slate-300 px-3 py-2 text-left text-sm" placeholder="05XXXXXXXX" value={newManager.mobile} onChange={(event) => setNewManager({ ...newManager, mobile: event.target.value })} />
        </div>
        <Button type="submit" className="mt-2 px-3 py-1.5" disabled={addManager.isPending}>إضافة مدير</Button>
        <div className="mt-2"><ErrorLine error={addManager.error} /></div>
      </form>
      {credentials && <CredentialNotice mobile={credentials.manager.mobile} password={credentials.temporary_password} onClose={() => setCredentials(null)} />}
    </div>
  );
}

function PlanForm({ plans }: { plans: Plan[] }) {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const editing = plans.find((plan) => plan.id === editingId);
  const [form, setForm] = useState({
    code: "",
    name_ar: "",
    price_amount: "0",
    trial_days_default: 30,
    max_students: 1000,
    max_staff: 100,
    max_devices: 5,
    max_storage_gb: 10,
  });
  const [features, setFeatures] = useState<Record<string, boolean>>(
    Object.fromEntries(FEATURE_KEYS.map((key) => [key, true])),
  );

  const save = useMutation({
    mutationFn: (body: PlanInput) =>
      editingId ? updatePlan(editingId, body) : createPlan(body),
    onSuccess: async () => {
      setEditingId(null);
      setForm({ ...form, code: "", name_ar: "" });
      await queryClient.invalidateQueries({ queryKey: ["platform", "plans"] });
    },
  });

  function load(plan: Plan) {
    setEditingId(plan.id);
    setForm({
      code: plan.code,
      name_ar: plan.name_ar,
      price_amount: plan.price_amount,
      trial_days_default: plan.trial_days_default,
      max_students: Number(plan.entitlements.MAX_STUDENTS ?? 1000),
      max_staff: Number(plan.entitlements.MAX_STAFF ?? 100),
      max_devices: Number(plan.entitlements.MAX_DEVICES ?? 5),
      max_storage_gb: Number(plan.entitlements.MAX_STORAGE_GB ?? 10),
    });
    setFeatures(
      Object.fromEntries(FEATURE_KEYS.map((key) => [key, Boolean(plan.entitlements[key] ?? true)])),
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const entitlements: Record<string, number | boolean> = {
      MAX_STUDENTS: form.max_students,
      MAX_STAFF: form.max_staff,
      MAX_DEVICES: form.max_devices,
      MAX_STORAGE_GB: form.max_storage_gb,
      ...features,
    };
    save.mutate({
      ...(editing ? {} : { code: form.code }),
      name_ar: form.name_ar,
      price_amount: form.price_amount,
      currency: "SAR",
      billing_period: "ANNUAL",
      trial_days_default: form.trial_days_default,
      entitlements,
    });
  }

  return (
    <section className="space-y-4">
      <form onSubmit={submit} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-4">
        <input className="rounded border border-slate-300 px-3 py-2" placeholder="رمز الباقة" value={form.code} disabled={Boolean(editing)} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        <input className="rounded border border-slate-300 px-3 py-2" placeholder="اسم الباقة" value={form.name_ar} onChange={(e) => setForm({ ...form, name_ar: e.target.value })} />
        <input className="rounded border border-slate-300 px-3 py-2" placeholder="السعر" value={form.price_amount} onChange={(e) => setForm({ ...form, price_amount: e.target.value })} />
        <input className="rounded border border-slate-300 px-3 py-2" type="number" placeholder="أيام التجربة" value={form.trial_days_default} onChange={(e) => setForm({ ...form, trial_days_default: Number(e.target.value) })} />
        {LIMIT_KEYS.map((key) => (
          <label key={key} className="text-sm text-slate-600">
            {ENTITLEMENT_LABELS[key]}
            <input className="mt-1 w-full rounded border border-slate-300 px-3 py-2" type="number" value={form[LIMIT_FORM_KEYS[key]]} onChange={(e) => setForm({ ...form, [LIMIT_FORM_KEYS[key]]: Number(e.target.value) })} />
          </label>
        ))}
        <div className="md:col-span-4 grid gap-2 md:grid-cols-3">
          {FEATURE_KEYS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={features[key]} onChange={(e) => setFeatures({ ...features, [key]: e.target.checked })} />
              {ENTITLEMENT_LABELS[key]}
            </label>
          ))}
        </div>
        <div className="flex gap-2 md:col-span-4">
          <Button type="submit" disabled={save.isPending}>{editing ? "حفظ التعديل" : "إنشاء باقة"}</Button>
          {editing && <Button variant="secondary" onClick={() => setEditingId(null)}>إلغاء</Button>}
        </div>
        <div className="md:col-span-4"><ErrorLine error={save.error} /></div>
      </form>
      <div className="grid gap-3 md:grid-cols-2">
        {plans.map((plan) => (
          <article key={plan.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-bold text-slate-900">{plan.name_ar}</h3>
                <p className="text-sm text-slate-500">{plan.code} · {plan.price_amount} {plan.currency}</p>
              </div>
              <span className={`rounded px-2 py-1 text-xs ${plan.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{plan.is_active ? "متاحة" : "معطلة"}</span>
            </div>
            <div className="mt-3 flex gap-2">
              <Button variant="secondary" onClick={() => load(plan)}>تعديل</Button>
              <Button variant="danger" disabled={!plan.is_active} onClick={() => void disablePlan(plan.id).then(() => queryClient.invalidateQueries({ queryKey: ["platform", "plans"] }))}>تعطيل</Button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function SchoolsPanel({ plans }: { plans: Plan[] }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [planFilter, setPlanFilter] = useState("");
  const [expiresSoon, setExpiresSoon] = useState(false);
  const [overLimit, setOverLimit] = useState(false);
  const [selected, setSelected] = useState<SchoolRow | null>(null);
  const filters = { search, status: statusFilter, plan: planFilter, expires_soon: expiresSoon, over_limit: overLimit };
  const schools = useQuery({ queryKey: ["platform", "schools", filters], queryFn: ({ signal }) => getPlatformSchools(filters, signal) });
  const detail = useQuery({ queryKey: ["platform", "school", selected?.id], queryFn: ({ signal }) => getSchoolDetail(selected!.id, signal), enabled: Boolean(selected) });
  const history = useQuery({ queryKey: ["platform", "subscription", selected?.id], queryFn: ({ signal }) => getSubscriptionHistory(selected!.id, signal), enabled: Boolean(selected) });
  const events = useQuery({ queryKey: ["platform", "events", selected?.id], queryFn: ({ signal }) => getSubscriptionEvents(selected!.id, signal), enabled: Boolean(selected) });
  const [createForm, setCreateForm] = useState({ school_name: "", manager_name: "", manager_mobile: "", plan_id: "", subscription_mode: "TRIAL" as "TRIAL" | "ACTIVE" });
  const [actionPlanId, setActionPlanId] = useState("");
  const [actionDays, setActionDays] = useState(30);
  const preview = useQuery({
    queryKey: ["platform", "plan-preview", selected?.id, actionPlanId],
    queryFn: ({ signal }) => getPlanChangePreview(selected!.id, Number(actionPlanId), signal),
    enabled: Boolean(selected && actionPlanId),
  });
  const [createdCredentials, setCreatedCredentials] = useState<{ mobile: string; password: string | null } | null>(null);
  const createSchool = useMutation({
    mutationFn: () => createPlatformSchool({ ...createForm, plan_id: createForm.plan_id ? Number(createForm.plan_id) : undefined }),
    onSuccess: async (row) => {
      setCreatedCredentials({ mobile: createForm.manager_mobile, password: row.temporary_password });
      setSelected(row);
      setCreateForm({ school_name: "", manager_name: "", manager_mobile: "", plan_id: "", subscription_mode: "TRIAL" });
      await queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
    },
  });
  const action = useMutation({
    mutationFn: ({ name, body }: { name: string; body: Record<string, unknown> }) => runSubscriptionAction(selected!.id, name, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "school", selected?.id] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "subscription", selected?.id] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "events", selected?.id] }),
      ]);
    },
  });

  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_560px]">
      <div className="space-y-3">
        <form onSubmit={(e) => { e.preventDefault(); createSchool.mutate(); }} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-5">
          <input className="rounded border border-slate-300 px-3 py-2" placeholder="اسم المدرسة" value={createForm.school_name} onChange={(e) => setCreateForm({ ...createForm, school_name: e.target.value })} />
          <input className="rounded border border-slate-300 px-3 py-2" placeholder="اسم المدير" value={createForm.manager_name} onChange={(e) => setCreateForm({ ...createForm, manager_name: e.target.value })} />
          <input className="rounded border border-slate-300 px-3 py-2" placeholder="جوال المدير" value={createForm.manager_mobile} onChange={(e) => setCreateForm({ ...createForm, manager_mobile: e.target.value })} />
          <select className="rounded border border-slate-300 px-3 py-2" value={createForm.plan_id} onChange={(e) => setCreateForm({ ...createForm, plan_id: e.target.value })}>
            <option value="">بدون باقة</option>
            {plans.filter((plan) => plan.is_active).map((plan) => <option key={plan.id} value={plan.id}>{plan.name_ar}</option>)}
          </select>
          <Button type="submit" disabled={createSchool.isPending}>إنشاء</Button>
          <div className="md:col-span-5 space-y-2">
            <ErrorLine error={createSchool.error} />
            {createdCredentials && <CredentialNotice mobile={createdCredentials.mobile} password={createdCredentials.password} onClose={() => setCreatedCredentials(null)} />}
          </div>
        </form>
        <div className="grid gap-2 md:grid-cols-5">
          <input className="rounded border border-slate-300 px-3 py-2" placeholder="بحث في المدارس" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select aria-label="حالة الاشتراك" className="rounded border border-slate-300 px-3 py-2" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">كل الحالات</option>
            {(["TRIAL", "ACTIVE", "GRACE_PERIOD", "EXPIRED", "SUSPENDED", "CANCELLED"] as const).map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
          </select>
          <select aria-label="الباقة" className="rounded border border-slate-300 px-3 py-2" value={planFilter} onChange={(e) => setPlanFilter(e.target.value)}>
            <option value="">كل الباقات</option>
            {plans.map((plan) => <option key={plan.id} value={plan.code}>{plan.name_ar}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={expiresSoon} onChange={(e) => setExpiresSoon(e.target.checked)} />تنتهي قريبًا</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overLimit} onChange={(e) => setOverLimit(e.target.checked)} />فوق الحد</label>
        </div>
        {schools.isPending ? <Spinner label="جارٍ تحميل المدارس..." /> : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            {(schools.data?.results ?? []).map((school) => (
              <button key={school.id} className="flex w-full items-center justify-between border-b border-slate-100 px-4 py-3 text-start last:border-b-0 hover:bg-slate-50" onClick={() => setSelected(school)}>
                <span><b>{school.name}</b><span className="block text-xs text-slate-500">{school.plan_name ?? "بدون باقة"} · {school.manager?.name ?? "بلا مدير"}</span></span>
                <span className={`rounded px-2 py-1 text-xs ${statusClass(school.subscription_status)}`}>{statusLabel(school.subscription_status)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <aside className="space-y-3">
        {!selected && <div className="rounded-lg border border-slate-200 bg-white p-4 text-slate-600">اختر مدرسة لعرض الاشتراك والاستخدام.</div>}
        {detail.data && (
          <>
            <SchoolAccountManagement key={detail.data.id} detail={detail.data} />
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="font-bold text-slate-900">بيانات الاشتراك</h3>
              <p className="text-sm text-slate-500">{detail.data.subscription.plan?.name ?? "بدون اشتراك"} · {statusLabel(detail.data.subscription.status)}</p>
              <dl className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 text-xs">
                <div><dt className="text-slate-500">بداية الاشتراك</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.starts_at)}</dd></div>
                <div><dt className="text-slate-500">نهاية الاشتراك</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.ends_at)}</dd></div>
                <div><dt className="text-slate-500">نهاية التجربة</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.trial_ends_at)}</dd></div>
                <div><dt className="text-slate-500">نهاية السماح</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.grace_ends_at)}</dd></div>
                <div><dt className="text-slate-500">الأيام المتبقية</dt><dd className="font-semibold text-slate-800">{detail.data.subscription.days_remaining ?? "—"}</dd></div>
                <div><dt className="text-slate-500">صلاحية الاستخدام</dt><dd className="font-semibold text-slate-800">{detail.data.subscription.access_mode === "FULL" ? "كاملة" : detail.data.subscription.access_mode === "READ_ONLY" ? "قراءة فقط" : "محجوبة"}</dd></div>
              </dl>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <select aria-label="الباقة الجديدة" className="rounded border border-slate-300 px-2 py-2 text-sm" value={actionPlanId} onChange={(e) => setActionPlanId(e.target.value)}>
                  <option value="">اختر باقة</option>
                  {plans.filter((plan) => plan.is_active).map((plan) => <option key={plan.id} value={plan.id}>{plan.name_ar}</option>)}
                </select>
                <input aria-label="المدة" className="rounded border border-slate-300 px-2 py-2 text-sm" type="number" value={actionDays} onChange={(e) => setActionDays(Number(e.target.value))} />
              </div>
              {preview.data && (
                <div className="mt-3 border-y border-slate-100 py-2 text-xs text-slate-600" data-testid="plan-change-preview">
                  <p className="font-semibold">معاينة {preview.data.plan.name}</p>
                  {Object.entries(preview.data.impact).map(([key, value]) => (
                    <p key={key} className={value.over_limit ? "font-semibold text-red-700" : ""}>{ENTITLEMENT_LABELS[key] ?? key}: {"used_gb" in value ? value.used_gb : value.used} / {"new_limit_gb" in value ? value.new_limit_gb ?? "بلا حد" : value.new_limit ?? "بلا حد"}{value.over_limit ? " · تجاوز الحد" : ""}</p>
                  ))}
                  <p>لن تُحذف أي بيانات.</p>
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {([
                  ["start-trial", "بدء تجربة"],
                  ["activate", "تفعيل"],
                  ["change-plan", "تغيير الباقة"],
                  ["extend", "تمديد"],
                  ["suspend", "إيقاف"],
                  ["reactivate", "إعادة تفعيل"],
                  ["cancel", "إلغاء"],
                ] as [string, string][]).map(([name, label]) => (
                  <Button key={name} variant={name === "suspend" || name === "cancel" ? "danger" : "secondary"} className="px-3 py-1.5" disabled={action.isPending || (["start-trial", "activate", "change-plan"].includes(name) && !actionPlanId) || (["start-trial", "extend"].includes(name) && actionDays < 1)} onClick={() => {
                    action.mutate({ name, body: { plan_id: Number(actionPlanId), days: actionDays, trial_days: actionDays, months: 12, reason: "إجراء من إدارة المنصة" } });
                  }}>{label}</Button>
                ))}
              </div>
              <ErrorLine error={action.error} />
            </div>
            <UsageGrid usage={detail.data.usage} />
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h4 className="mb-2 font-bold">السجل</h4>
              {(history.data?.history ?? []).slice(0, 4).map((row) => <p key={row.id} className="text-sm text-slate-600">{row.plan_name} · {statusLabel(row.status)}</p>)}
              {(events.data ?? []).slice(0, 5).map((event) => <p key={event.id} className="mt-1 text-xs text-slate-500">{event.event_type} · {new Date(event.created_at).toLocaleDateString("ar-SA")}</p>)}
            </div>
          </>
        )}
      </aside>
    </section>
  );
}

export function PlatformAdminPage() {
  const [tab, setTab] = useState<"dashboard" | "schools" | "plans">("dashboard");
  const overview = useQuery({ queryKey: ["platform", "overview"], queryFn: ({ signal }) => getPlatformOverview(signal) });
  const plans = useQuery({ queryKey: ["platform", "plans"], queryFn: ({ signal }) => getPlans(signal) });
  const activePlans = useMemo(() => plans.data ?? [], [plans.data]);
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-5 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-screen-2xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">إدارة المنصة</h1>
          <p className="text-sm text-slate-500">إدارة المدارس والباقات والاشتراكات دون تصفح بيانات الطلاب.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-1">
          {(["dashboard", "schools", "plans"] as const).map((item) => (
            <button key={item} className={`rounded-md px-3 py-2 text-sm ${tab === item ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-50"}`} onClick={() => setTab(item)}>
              {item === "dashboard" ? "لوحة المؤشرات" : item === "schools" ? "المدارس" : "الباقات"}
            </button>
          ))}
          <button className="rounded-md px-3 py-2 text-sm text-red-700 hover:bg-red-50" onClick={() => void logout().then(() => navigate("/login", { replace: true }))}>تسجيل الخروج</button>
        </div>
      </div>
      {tab === "dashboard" && (
        overview.isPending ? <Spinner label="جارٍ تحميل لوحة المنصة..." /> : (
          <section className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">المدارس</p><p className="text-3xl font-bold">{overview.data?.schools_total ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">النشطة</p><p className="text-3xl font-bold">{overview.data?.subscriptions.active ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">التجريبية</p><p className="text-3xl font-bold">{overview.data?.subscriptions.trial ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">مهلة السماح</p><p className="text-3xl font-bold">{overview.data?.subscriptions.grace ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">المنتهية</p><p className="text-3xl font-bold">{overview.data?.subscriptions.expired ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">الموقوفة</p><p className="text-3xl font-bold">{overview.data?.subscriptions.suspended ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">القريبة من الانتهاء</p><p className="text-3xl font-bold">{overview.data?.expiring_soon.length ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">الطلاب النشطون</p><p className="text-3xl font-bold">{overview.data?.usage_totals?.active_students ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">الموظفون</p><p className="text-3xl font-bold">{overview.data?.usage_totals?.active_staff ?? 0}</p></div>
            <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">الأجهزة</p><p className="text-3xl font-bold">{overview.data?.usage_totals?.active_devices ?? 0}</p></div>
          </section>
        )
      )}
      {tab === "schools" && <SchoolsPanel plans={activePlans} />}
        {tab === "plans" && (plans.isPending ? <Spinner label="جارٍ تحميل الباقات..." /> : <PlanForm plans={activePlans} />)}
      </div>
    </main>
  );
}
