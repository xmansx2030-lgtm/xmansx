import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import {
  BadgeCheck,
  BriefcaseBusiness,
  Check,
  Copy,
  KeyRound,
  LockKeyhole,
  PencilLine,
  Plus,
  Power,
  ShieldCheck,
  UserRoundCog,
  UsersRound,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import {
  changePlatformPassword,
  createPlatformTeamMember,
  getPlatformAccount,
  getPlatformTeam,
  runPlatformTeamMemberAction,
  updatePlatformAccount,
  updatePlatformTeamMember,
  type PlatformStaffRole,
  type PlatformAccount,
  type PlatformTeamMember,
} from "@/features/platform/api";

const capabilityLabels: Record<string, string> = {
  DASHBOARD_VIEW: "المؤشرات",
  SCHOOLS_VIEW: "عرض المدارس",
  SCHOOLS_MANAGE: "إدارة المدارس",
  SCHOOL_ACCOUNTS_MANAGE: "حسابات المدارس",
  SUBSCRIPTIONS_MANAGE: "الاشتراكات",
  PLANS_VIEW: "عرض الباقات",
  PLANS_MANAGE: "إدارة الباقات",
  TEAM_VIEW: "عرض الفريق",
  TEAM_MANAGE: "إدارة الفريق",
};

const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "تعذر تنفيذ الطلب. حاول مرة أخرى.";

function CredentialNotice({ password, onClose }: { password: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(password).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    });
  };
  return (
    <section className="rounded-3xl border border-amber-200 bg-gradient-to-l from-amber-50 to-white p-5 shadow-sm" role="status">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="flex items-center gap-2 font-black text-amber-950"><KeyRound size={18} />كلمة مرور مؤقتة — تظهر مرة واحدة</p>
          <p className="mt-1 text-sm leading-6 text-amber-800">انسخها وأرسلها للموظف عبر قناة آمنة. سيُطلب منه تغييرها عند أول دخول.</p>
        </div>
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-white p-2 shadow-sm" dir="ltr">
          <code className="px-2 text-sm font-black text-slate-900">{password}</code>
          <button type="button" onClick={copy} className="grid size-9 place-items-center rounded-xl bg-slate-950 text-white" aria-label="نسخ كلمة المرور">
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>
      </div>
      <button type="button" onClick={onClose} className="mt-3 text-xs font-bold text-amber-800 underline underline-offset-4">فهمت، إخفاء كلمة المرور</button>
    </section>
  );
}

function MemberCard({ member, canManage, isCurrentUser }: { member: PlatformTeamMember; canManage: boolean; isCurrentUser: boolean }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [credential, setCredential] = useState<string | null>(null);
  const [form, setForm] = useState({ name: member.name, mobile: member.mobile, role: member.role, job_title: member.job_title });
  const update = useMutation({
    mutationFn: () => updatePlatformTeamMember(member.user_id, { ...form, role: form.role as PlatformStaffRole }),
    onSuccess: () => { setEditing(false); void queryClient.invalidateQueries({ queryKey: ["platform", "team"] }); },
  });
  const action = useMutation({
    mutationFn: (name: "suspend" | "reactivate" | "reset-password") => runPlatformTeamMemberAction(member.user_id, name),
    onSuccess: (data) => { setCredential(data.temporary_password); void queryClient.invalidateQueries({ queryKey: ["platform", "team"] }); },
  });
  const run = (name: "suspend" | "reactivate" | "reset-password") => {
    const label = name === "suspend" ? "إيقاف وصول هذا الموظف؟" : name === "reactivate" ? "إعادة تفعيل وصول هذا الموظف؟" : "إنشاء كلمة مرور مؤقتة جديدة؟";
    if (window.confirm(label)) action.mutate(name);
  };

  return (
    <article className={`rounded-3xl border bg-white p-5 shadow-sm ${member.status === "SUSPENDED" ? "border-slate-200 opacity-80" : member.is_owner ? "border-teal-200 ring-1 ring-teal-100" : "border-slate-200"}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className={`grid size-12 shrink-0 place-items-center rounded-2xl ${member.is_owner ? "bg-teal-950 text-teal-300" : "bg-slate-100 text-slate-700"}`}>
            {member.is_owner ? <ShieldCheck size={23} /> : <UserRoundCog size={23} />}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><h3 className="truncate font-black text-slate-950">{member.name}</h3>{member.is_owner && <span className="rounded-full bg-teal-50 px-2 py-1 text-[10px] font-black text-teal-800">حساب محمي</span>}</div>
            <p className="mt-1 text-sm font-semibold text-slate-500" dir="ltr">{member.mobile}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">{member.role_label}</span>
          <span className={`rounded-full px-3 py-1 text-xs font-bold ${member.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{member.status_label}</span>
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-600">{member.job_title || "موظف ضمن فريق تشغيل المنصة"}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {member.capabilities.map((capability) => <span key={capability} className="rounded-lg bg-slate-50 px-2 py-1 text-[11px] font-semibold text-slate-600">{capabilityLabels[capability] ?? capability}</span>)}
      </div>

      {credential && <div className="mt-4"><CredentialNotice password={credential} onClose={() => setCredential(null)} /></div>}
      {action.error && <p className="mt-3 text-sm font-bold text-red-700">{errorMessage(action.error)}</p>}

      {!member.is_owner && canManage && !isCurrentUser && !editing && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
          <Button variant="secondary" onClick={() => setEditing(true)}><PencilLine size={15} />تعديل</Button>
          <Button variant="secondary" onClick={() => run("reset-password")} disabled={action.isPending}><KeyRound size={15} />إعادة كلمة المرور</Button>
          <Button variant={member.status === "ACTIVE" ? "danger" : "secondary"} onClick={() => run(member.status === "ACTIVE" ? "suspend" : "reactivate")} disabled={action.isPending}><Power size={15} />{member.status === "ACTIVE" ? "إيقاف الوصول" : "إعادة التفعيل"}</Button>
        </div>
      )}
      {isCurrentUser && !member.is_owner && <p className="mt-4 rounded-xl bg-blue-50 p-3 text-xs font-bold text-blue-800">هذا حسابك الحالي؛ عدّل كلمة المرور من قسم «حسابي».</p>}

      {editing && (
        <form className="mt-5 grid gap-3 border-t border-slate-100 pt-5 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); update.mutate(); }}>
          <label className="text-xs font-bold text-slate-600">الاسم<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="text-xs font-bold text-slate-600">الجوال<input dir="ltr" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></label>
          <label className="text-xs font-bold text-slate-600">الدور<select className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as PlatformStaffRole })}><option value="OPERATIONS_MANAGER">مدير العمليات</option><option value="SUPPORT">خدمة المدارس</option><option value="BILLING">الاشتراكات والفوترة</option><option value="AUDITOR">مراجع</option></select></label>
          <label className="text-xs font-bold text-slate-600">المسمى الوظيفي<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} /></label>
          {update.error && <p className="text-sm font-bold text-red-700 sm:col-span-2">{errorMessage(update.error)}</p>}
          <div className="flex gap-2 sm:col-span-2"><Button type="submit" disabled={update.isPending}>{update.isPending ? "جارٍ الحفظ..." : "حفظ التعديلات"}</Button><Button type="button" variant="secondary" onClick={() => setEditing(false)}>إلغاء</Button></div>
        </form>
      )}
    </article>
  );
}

export function PlatformTeamPanel({ canManage, currentUserId }: { canManage: boolean; currentUserId?: number }) {
  const queryClient = useQueryClient();
  const team = useQuery({ queryKey: ["platform", "team"], queryFn: ({ signal }) => getPlatformTeam(signal) });
  const [showForm, setShowForm] = useState(false);
  const [credential, setCredential] = useState<string | null>(null);
  const [form, setForm] = useState<{ name: string; mobile: string; role: PlatformStaffRole; job_title: string }>({ name: "", mobile: "", role: "SUPPORT", job_title: "" });
  const create = useMutation({
    mutationFn: () => createPlatformTeamMember(form),
    onSuccess: (data) => {
      setCredential(data.temporary_password);
      setForm({ name: "", mobile: "", role: "SUPPORT", job_title: "" });
      setShowForm(false);
      void queryClient.invalidateQueries({ queryKey: ["platform", "team"] });
    },
  });

  if (team.isPending) return <div className="rounded-3xl border border-slate-200 bg-white p-10"><Spinner label="جارٍ تحميل فريق المنصة..." /></div>;
  if (team.isError || !team.data) return <div className="rounded-3xl border border-red-200 bg-white p-8 text-center font-bold text-red-700">تعذر تحميل فريق المنصة.</div>;
  const activeCount = team.data.members.filter((member) => member.status === "ACTIVE").length;

  return (
    <div className="space-y-5" data-testid="platform-team-panel">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-l from-slate-950 via-slate-900 to-teal-950 p-6 text-white shadow-xl">
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="flex items-center gap-2 text-sm font-bold text-teal-300"><UsersRound size={18} />فريق تشغيل المنصة</p><h2 className="mt-2 text-2xl font-black">صلاحيات واضحة، وصول آمن</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">كل موظف يمتلك ما يحتاجه فقط. مالك المنصة محمي ولا يمكن تعديله أو استنساخ صلاحياته.</p></div>
          <div className="flex items-center gap-5 rounded-2xl border border-white/10 bg-white/5 px-5 py-4"><div><p className="text-3xl font-black">{activeCount}</p><p className="text-xs text-slate-400">حسابات نشطة</p></div>{canManage && <Button onClick={() => setShowForm((value) => !value)}><Plus size={17} />إضافة موظف</Button>}</div>
        </div>
      </section>

      {credential && <CredentialNotice password={credential} onClose={() => setCredential(null)} />}

      {showForm && (
        <form onSubmit={(event: FormEvent) => { event.preventDefault(); create.mutate(); }} className="rounded-3xl border border-teal-200 bg-white p-5 shadow-lg shadow-teal-950/5">
          <div className="mb-5 flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-teal-50 text-teal-700"><BriefcaseBusiness size={20} /></span><div><h3 className="font-black text-slate-950">إضافة موظف للمنصة</h3><p className="text-xs text-slate-500">لا يمنح هذا النموذج صلاحية مالك أو Superuser.</p></div></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-xs font-bold text-slate-600">الاسم الكامل<input required className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="text-xs font-bold text-slate-600">رقم الجوال<input required dir="ltr" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" placeholder="05XXXXXXXX" value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></label>
            <label className="text-xs font-bold text-slate-600">الدور الوظيفي<select className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as PlatformStaffRole })}>{team.data.roles.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}</select></label>
            <label className="text-xs font-bold text-slate-600">المسمى الوظيفي<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" placeholder="مثال: أخصائي نجاح المدارس" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} /></label>
          </div>
          <div className="mt-4 rounded-2xl bg-slate-50 p-3 text-xs leading-6 text-slate-600"><LockKeyhole className="me-1 inline text-teal-700" size={15} />يجب استخدام حساب مستقل غير مرتبط بأي مدرسة. تُنشأ كلمة مرور قوية ومؤقتة تظهر مرة واحدة.</div>
          {create.error && <p className="mt-3 text-sm font-bold text-red-700">{errorMessage(create.error)}</p>}
          <div className="mt-4 flex gap-2"><Button type="submit" disabled={create.isPending}>{create.isPending ? "جارٍ الإنشاء..." : "إنشاء حساب الموظف"}</Button><Button type="button" variant="secondary" onClick={() => setShowForm(false)}>إلغاء</Button></div>
        </form>
      )}

      <section className="grid gap-4 lg:grid-cols-2">
        {team.data.members.map((member) => <MemberCard key={member.user_id} member={member} canManage={canManage} isCurrentUser={member.user_id === currentUserId} />)}
      </section>
    </div>
  );
}

function PlatformAccountContent({ accountData, refetch }: { accountData: PlatformAccount; refetch: () => unknown }) {
  const [profile, setProfile] = useState({ name: accountData.name, mobile: accountData.mobile, current_password: "" });
  const [password, setPassword] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [profileSaved, setProfileSaved] = useState(false);
  const [passwordSaved, setPasswordSaved] = useState(false);
  const update = useMutation({ mutationFn: () => updatePlatformAccount(profile), onSuccess: (data) => { refetch(); setProfile({ name: data.name, mobile: data.mobile, current_password: "" }); setProfileSaved(true); } });
  const changePassword = useMutation({ mutationFn: () => changePlatformPassword(password), onSuccess: () => { setPassword({ current_password: "", new_password: "", confirm_password: "" }); setPasswordSaved(true); } });

  return (
    <div className="space-y-5" data-testid="platform-account-panel">
      <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="bg-gradient-to-l from-teal-950 to-slate-950 p-6 text-white"><div className="flex items-center gap-4"><span className="grid size-14 place-items-center rounded-2xl bg-teal-400 text-slate-950"><ShieldCheck size={26} /></span><div><p className="text-sm font-bold text-teal-300">حساب المنصة</p><h2 className="mt-1 text-2xl font-black">{accountData.name}</h2><p className="mt-1 text-sm text-slate-300">{accountData.role_label} · جلسة إدارية محمية</p></div></div></div>
        <div className="grid gap-5 p-5 lg:grid-cols-[1fr_0.9fr]">
          <form onSubmit={(event) => { event.preventDefault(); setProfileSaved(false); update.mutate(); }}>
            <h3 className="flex items-center gap-2 font-black text-slate-950"><PencilLine size={18} className="text-teal-700" />البيانات الشخصية</h3>
            <div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-xs font-bold text-slate-600">الاسم<input className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} /></label><label className="text-xs font-bold text-slate-600">رقم الجوال<input dir="ltr" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={profile.mobile} onChange={(e) => setProfile({ ...profile, mobile: e.target.value })} /></label><label className="text-xs font-bold text-slate-600 sm:col-span-2">كلمة المرور الحالية عند تغيير الجوال<input type="password" autoComplete="current-password" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" placeholder="اتركها فارغة إذا لم تغيّر رقم الجوال" value={profile.current_password} onChange={(e) => setProfile({ ...profile, current_password: e.target.value })} /></label></div>
            {profileSaved && <p className="mt-3 flex items-center gap-1 text-sm font-bold text-emerald-700"><BadgeCheck size={17} />تم حفظ بيانات الحساب.</p>}
            {update.error && <p className="mt-3 text-sm font-bold text-red-700">{errorMessage(update.error)}</p>}
            <Button className="mt-4" type="submit" disabled={update.isPending}>{update.isPending ? "جارٍ الحفظ..." : "حفظ البيانات"}</Button>
          </form>
          <aside className="rounded-2xl bg-slate-50 p-4"><h3 className="font-black text-slate-900">نطاق الوصول</h3><p className="mt-1 text-xs leading-5 text-slate-500">هذه الصلاحيات يفرضها الخادم على كل طلب، وليست مجرد خيارات عرض.</p><div className="mt-3 flex flex-wrap gap-2">{accountData.capabilities.map((capability) => <span key={capability} className="rounded-lg bg-white px-2 py-1 text-xs font-bold text-slate-600 shadow-sm">{capabilityLabels[capability]}</span>)}</div>{accountData.is_owner && <p className="mt-4 flex items-start gap-2 rounded-xl bg-teal-50 p-3 text-xs font-bold leading-5 text-teal-800"><ShieldCheck className="mt-0.5 shrink-0" size={16} />حساب المالك محمي ولا يمكن إيقافه أو تعديله من إدارة الفريق.</p>}</aside>
        </div>
      </section>

      <form onSubmit={(event) => { event.preventDefault(); setPasswordSaved(false); changePassword.mutate(); }} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-amber-50 text-amber-700"><LockKeyhole size={20} /></span><div><h3 className="font-black text-slate-950">الأمان وكلمة المرور</h3><p className="text-xs text-slate-500">غيّر كلمة المرور دوريًا ولا تشاركها مع أي موظف.</p></div></div>
        <div className="mt-5 grid gap-4 md:grid-cols-3"><label className="text-xs font-bold text-slate-600">كلمة المرور الحالية<input required type="password" autoComplete="current-password" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={password.current_password} onChange={(e) => setPassword({ ...password, current_password: e.target.value })} /></label><label className="text-xs font-bold text-slate-600">كلمة المرور الجديدة<input required minLength={8} type="password" autoComplete="new-password" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={password.new_password} onChange={(e) => setPassword({ ...password, new_password: e.target.value })} /></label><label className="text-xs font-bold text-slate-600">تأكيد كلمة المرور<input required minLength={8} type="password" autoComplete="new-password" className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm" value={password.confirm_password} onChange={(e) => setPassword({ ...password, confirm_password: e.target.value })} /></label></div>
        {passwordSaved && <p className="mt-3 flex items-center gap-1 text-sm font-bold text-emerald-700"><BadgeCheck size={17} />تم تغيير كلمة المرور مع الحفاظ على جلستك الحالية.</p>}
        {changePassword.error && <p className="mt-3 text-sm font-bold text-red-700">{errorMessage(changePassword.error)}</p>}
        <Button className="mt-4" type="submit" disabled={changePassword.isPending}><KeyRound size={16} />{changePassword.isPending ? "جارٍ التغيير..." : "تغيير كلمة المرور"}</Button>
      </form>
    </div>
  );
}

export function PlatformAccountPanel() {
  const account = useQuery({ queryKey: ["platform", "account"], queryFn: ({ signal }) => getPlatformAccount(signal) });
  if (account.isPending) return <div className="rounded-3xl border border-slate-200 bg-white p-10"><Spinner label="جارٍ تحميل حسابك..." /></div>;
  if (!account.data) return <div className="rounded-3xl border border-red-200 bg-white p-8 text-center font-bold text-red-700">تعذر تحميل بيانات الحساب.</div>;
  return <PlatformAccountContent key={`${account.data.id}:${account.data.name}:${account.data.mobile}`} accountData={account.data} refetch={() => account.refetch()} />;
}
