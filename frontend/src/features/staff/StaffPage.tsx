import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Ban,
  BriefcaseBusiness,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleUserRound,
  FilterX,
  Hash,
  KeyRound,
  Phone,
  Plus,
  Search,
  ShieldCheck,
  Sunrise,
  Trash2,
  Upload,
  UserCheck,
  UsersRound,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { useActiveSchoolId, useActiveSchoolType, useInvalidateSchoolData } from "@/features/settings/hooks";
import { ManualStaffForm } from "@/features/staff/ManualStaffForm";
import { CounselorSectionPicker } from "@/features/staff/CounselorSectionPicker";
import {
  activateStaff,
  addStaffRole,
  deleteStaff,
  getStaff,
  grantMorningAttendance,
  MEMBERSHIP_STATUS_LABELS,
  reinviteStaff,
  resetStaffPassword,
  revokeMorningAttendance,
  removeStaffRole,
  suspendStaff,
  updateStaff,
  updateCounselorSections,
  type StaffMember,
} from "@/features/staff/api";
import { getSections } from "@/features/students/api";
import type { SchoolRole, SchoolType } from "@/types/auth";
import { roleLabel } from "@/utils/roles";

const ROLE_FILTERS: SchoolRole[] = ["TEACHER", "COUNSELOR", "GATE_GUARD", "VICE_PRINCIPAL", "SCHOOL_MANAGER"];
const ASSIGNABLE_ROLES: SchoolRole[] = ["TEACHER", "COUNSELOR", "GATE_GUARD", "VICE_PRINCIPAL"];
const STATUS_OPTIONS = ["ACTIVE", "SUSPENDED", "INVITED", "DECLINED"];

export function StaffPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const isManager = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const canRead =
    me.data?.roles.some((role) => ["SCHOOL_MANAGER", "VICE_PRINCIPAL"].includes(role)) ?? true;

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [actionError, setActionError] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const invalidate = useInvalidateSchoolData();

  const staff = useQuery({
    queryKey: schoolScopedKey(schoolId, "staff", { page, search, roleFilter, statusFilter }),
    queryFn: ({ signal }) =>
      getStaff({ page, search, role: roleFilter, status: statusFilter }, signal),
    enabled: schoolId > 0 && canRead,
    placeholderData: (previous) => previous,
  });

  const totalPages = staff.data ? Math.max(1, Math.ceil(staff.data.count / 25)) : 1;
  const hasFilters = Boolean(search || roleFilter || statusFilter);

  function clearFilters() {
    setSearch("");
    setRoleFilter("");
    setStatusFilter("");
    setPage(1);
  }

  if (me.isSuccess && !canRead) {
    return (
      <section className="rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-100 text-slate-500">
          <ShieldCheck aria-hidden size={26} />
        </span>
        <h2 className="mt-4 text-xl font-black text-slate-900">لا تملك صلاحية عرض دليل الموظفين</h2>
        <p className="mt-2 text-sm text-slate-500">يمكن {schoolType === "GIRLS" ? "لمديرة المدرسة والوكيلة" : "لمدير المدرسة والوكيل"} فقط الاطلاع على هذا القسم.</p>
      </section>
    );
  }

  return (
    <div className="ds-page">
      <PageHeader
        icon={UsersRound}
        eyebrow="إدارة المدرسة"
        title="موظفو المدرسة"
        description="دليل موحد للموظفين والأدوار وحالات الوصول إلى المنصة."
        tone="executive"
        badge={!isManager ? <span className="inline-flex items-center gap-1.5"><CircleUserRound aria-hidden size={14} /> عرض الدليل فقط</span> : undefined}
        actions={isManager ? (
          <div className="flex flex-wrap gap-2">
              <Link to="/staff/import">
                <Button variant="headerGhost">
                  <Upload aria-hidden size={17} /> استيراد
                </Button>
              </Link>
              <Button variant="header" onClick={() => setManualOpen(true)}>
                <Plus aria-hidden size={17} /> إدخال يدوي
              </Button>
          </div>
        ) : undefined}
      />

      <section aria-label="البحث والتصفية" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-black text-slate-900">ابحث في الدليل</h2>
            <p className="mt-1 text-xs text-slate-500">ابحث بالاسم أو الرقم الوظيفي أو رقم الجوال كاملًا.</p>
          </div>
          {hasFilters && (
            <button type="button" onClick={clearFilters} className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100">
              <FilterX aria-hidden size={15} /> مسح الفلاتر
            </button>
          )}
        </div>
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_14rem_14rem]">
          <div>
            <label htmlFor="staff-search" className="sr-only">بحث عن موظف</label>
            <div className="relative">
              <Search aria-hidden size={18} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                id="staff-search"
                value={search}
                onChange={(event) => { setSearch(event.target.value); setPage(1); }}
                placeholder="اسم الموظف أو رقمه الوظيفي أو الجوال"
                className="h-11 w-full rounded-xl border border-slate-300 bg-slate-50 pr-10 pl-10 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-3 focus:ring-blue-100"
              />
              {search && (
                <button type="button" aria-label="مسح البحث" onClick={() => { setSearch(""); setPage(1); }} className="absolute left-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                  <X aria-hidden size={16} />
                </button>
              )}
            </div>
          </div>
          <div>
            <label htmlFor="staff-role" className="sr-only">تصفية حسب الدور</label>
            <select id="staff-role" value={roleFilter} onChange={(event) => { setRoleFilter(event.target.value); setPage(1); }} className="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700">
              <option value="">جميع الأدوار</option>
              {ROLE_FILTERS.map((role) => <option key={role} value={role}>{roleLabel(role, schoolType)}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="staff-status" className="sr-only">تصفية حسب الحالة</label>
            <select id="staff-status" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }} className="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700">
              <option value="">جميع الحالات</option>
              {STATUS_OPTIONS.map((status) => <option key={status} value={status}>{MEMBERSHIP_STATUS_LABELS[status]}</option>)}
            </select>
          </div>
        </div>
      </section>

      {actionError && (
        <div role="alert" className="flex items-start justify-between gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <span>{actionError}</span>
          <button type="button" aria-label="إغلاق الخطأ" onClick={() => setActionError(null)}><X aria-hidden size={17} /></button>
        </div>
      )}

      {staff.isPending && <div className="grid min-h-48 place-items-center rounded-2xl border border-slate-200 bg-white"><Spinner /></div>}
      {staff.isError && <ErrorState error={staff.error} />}

      {staff.data && (
        <section aria-label="قائمة الموظفين" className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-opacity ${staff.isFetching ? "opacity-70" : "opacity-100"}`}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
            <p className="text-sm font-bold text-slate-800">
              {hasFilters ? "نتائج البحث" : "دليل الموظفين"}
              <span className="mr-2 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">{staff.data.count}</span>
            </p>
            <p aria-live="polite" className="text-xs text-slate-500">صفحة {page} من {totalPages}</p>
          </div>
          <ul className="divide-y divide-slate-100">
            {staff.data.results.map((member) => (
              <StaffRow key={member.id} member={member} isManager={isManager} schoolType={schoolType} onError={setActionError} />
            ))}
            {staff.data.results.length === 0 && (
              <li className="px-5 py-14 text-center">
                <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-100 text-slate-400"><Search aria-hidden size={24} /></span>
                <h3 className="mt-4 font-black text-slate-800">لا توجد نتائج مطابقة</h3>
                <p className="mt-1 text-sm text-slate-500">جرّب تغيير عبارة البحث أو إزالة أحد الفلاتر.</p>
                {hasFilters && <Button variant="secondary" className="mt-4" onClick={clearFilters}><FilterX aria-hidden size={16} /> مسح الفلاتر</Button>}
              </li>
            )}
          </ul>
          {staff.data.results.length > 0 && (
            <div className="flex flex-col items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 p-3 sm:flex-row sm:px-5">
              <span className="text-xs font-medium text-slate-500">إجمالي النتائج: {staff.data.count}</span>
              <div className="flex gap-2">
                <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>السابق</Button>
                <Button variant="secondary" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>التالي</Button>
              </div>
            </div>
          )}
        </section>
      )}

      {manualOpen && (
        <Modal title="إضافة موظف" description="اختر بيانات الموظف ودوره الأول في المنصة." onClose={() => setManualOpen(false)}>
          <ManualStaffForm onClose={() => setManualOpen(false)} onCreated={() => { void invalidate("staff"); }} />
        </Modal>
      )}
    </div>
  );
}

type ConfirmAction = "suspend" | "delete" | "reset-password" | "revoke-morning" | null;

function StaffRow({ member, isManager, schoolType, onError }: { member: StaffMember; isManager: boolean; schoolType: SchoolType; onError: (message: string | null) => void }) {
  const invalidate = useInvalidateSchoolData();
  const [expanded, setExpanded] = useState(false);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [confirmationName, setConfirmationName] = useState("");
  const [rowError, setRowError] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async (action: () => Promise<StaffMember | void>) => action(),
    onSuccess: () => {
      setRowError(null);
      onError(null);
      setConfirmAction(null);
      setConfirmationName("");
      void invalidate("staff");
    },
    onError: (error) => {
      const message = error instanceof ApiError ? error.message : "تعذر تنفيذ الإجراء.";
      setRowError(message);
      onError(message);
    },
  });

  const initials = member.display_name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("");
  const isActive = member.membership_status === "ACTIVE";
  const isSchoolManagerAccount = member.roles.includes("SCHOOL_MANAGER");
  const managerLabel = schoolType === "GIRLS" ? "مديرة المدرسة" : "مدير المدرسة";
  const resetSubject = member.roles.includes("GATE_GUARD") && !member.roles.includes("TEACHER")
    ? (schoolType === "GIRLS" ? "الحارسة" : "الحارس")
    : (schoolType === "GIRLS" ? "المعلمة" : "المعلم");

  const resetPassword = useMutation({
    mutationFn: () => resetStaffPassword(member.id),
    onSuccess: (result) => {
      setTemporaryPassword(result.temporary_password);
      setConfirmAction(null);
      setRowError(null);
      onError(null);
    },
    onError: (error) => {
      const message = error instanceof ApiError ? error.message : "تعذر إعادة ضبط كلمة المرور.";
      setRowError(message);
      onError(message);
    },
  });

  function closeConfirmation() {
    if (mutation.isPending) return;
    setConfirmAction(null);
    setConfirmationName("");
    setRowError(null);
  }

  return (
    <li className={`p-4 transition-colors sm:p-5 ${expanded ? "bg-blue-50/30" : "hover:bg-slate-50/60"}`}>
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
        <div className="flex min-w-0 items-start gap-3.5">
          <span className={`grid size-11 shrink-0 place-items-center rounded-2xl text-sm font-black ${isActive ? "bg-gradient-to-br from-blue-600 to-teal-600 text-white" : "bg-slate-200 text-slate-600"}`}>
            {initials || <CircleUserRound aria-hidden size={21} />}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate font-black text-slate-900">{member.display_name}</h3>
              {member.is_current_user && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-bold text-violet-700">حسابك</span>}
              <StatusBadge status={member.membership_status} />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-500">
              {member.job_title && <span className="inline-flex items-center gap-1.5"><BriefcaseBusiness aria-hidden size={14} />{member.job_title}</span>}
              <span dir="ltr" className="inline-flex items-center gap-1.5"><Phone aria-hidden size={14} />{member.mobile}</span>
              {member.employee_number && <span className="inline-flex items-center gap-1.5"><Hash aria-hidden size={14} />{member.employee_number}</span>}
              <span className="inline-flex items-center gap-1.5"><CalendarDays aria-hidden size={14} />منذ {member.joined_at}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          {member.roles.map((role) => (
            <span key={role} className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-700 ring-1 ring-blue-100">
              {roleLabel(role as SchoolRole, schoolType)}
            </span>
          ))}
          {member.roles.includes("COUNSELOR") && (
            <span className="rounded-full bg-teal-50 px-2.5 py-1 text-[11px] font-bold text-teal-700 ring-1 ring-teal-100">
              مسؤول عن {member.counselor_section_count ?? 0} فصل
            </span>
          )}
          {(member.capabilities ?? []).includes("MORNING_ATTENDANCE") && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-bold text-amber-800 ring-1 ring-amber-200" data-testid={`morning-assignment-badge-${member.id}`}>
              <Sunrise aria-hidden size={13} /> متابعة التأخر الصباحي
            </span>
          )}
          {isManager && (
            <button
              type="button"
              aria-expanded={expanded}
              className="mr-auto inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-sm hover:border-blue-300 hover:text-blue-700 lg:mr-2"
              onClick={() => { setExpanded((value) => !value); setRowError(null); }}
            >
              إدارة {expanded ? <ChevronUp aria-hidden size={15} /> : <ChevronDown aria-hidden size={15} />}
            </button>
          )}
        </div>
      </div>

      {isManager && expanded && (
        isSchoolManagerAccount ? (
          <div className="mt-5 flex items-start gap-3 rounded-2xl border border-violet-200 bg-violet-50 p-4 text-violet-950 shadow-sm">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-violet-700 shadow-sm"><ShieldCheck aria-hidden size={20} /></span>
            <div>
              <h4 className="text-sm font-black">حساب {managerLabel} محمي</h4>
              <p className="mt-1 text-xs leading-6">لا يمكن تعديل دور {managerLabel} أو إيقاف الحساب أو حذفه من إدارة موظفي المدرسة. تتم إدارة بيانات دخوله مركزيًا من إدارة المنصة.</p>
            </div>
          </div>
        ) : (
        <div className="mt-5 grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:grid-cols-[minmax(0,1fr)_18rem]">
          <section aria-label={`أدوار ${member.display_name}`}>
            <StaffProfileEditor member={member} onError={(message) => { setRowError(message); onError(message); }} />
            <div className="mb-3">
              <h4 className="text-sm font-black text-slate-900">الصلاحيات والأدوار</h4>
              <p className="mt-1 text-xs text-slate-500">يمكن إسناد أكثر من دور للموظف حسب مسؤولياته.</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {ASSIGNABLE_ROLES.map((role) => {
                const hasRole = member.roles.includes(role);
                return (
                  <label key={role} className={`flex cursor-pointer items-center gap-2.5 rounded-xl border p-3 text-sm font-bold transition ${hasRole ? "border-blue-200 bg-blue-50 text-blue-800" : "border-slate-200 text-slate-600 hover:border-slate-300"}`}>
                    <input
                      type="checkbox"
                      checked={hasRole}
                      disabled={mutation.isPending || member.is_current_user}
                      onChange={() => mutation.mutate(() => hasRole ? removeStaffRole(member.id, role) : addStaffRole(member.id, role))}
                      className="size-4 accent-blue-600"
                    />
                    {roleLabel(role, schoolType)}
                  </label>
                );
              })}
            </div>
            {member.is_current_user && <p className="mt-3 text-xs font-medium text-violet-700">لحماية وصولك، اطلب من مدير آخر تعديل أدوار حسابك.</p>}
            <MorningAttendanceAssignment
              member={member}
              pending={mutation.isPending}
              onToggle={(assigned) => {
                if (assigned) {
                  setConfirmAction("revoke-morning");
                  return;
                }
                mutation.mutate(() => grantMorningAttendance(member.id));
              }}
            />
          </section>

          <section className="rounded-2xl bg-slate-50 p-4">
            <h4 className="text-sm font-black text-slate-900">حالة الوصول</h4>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {isActive ? "الموظف يستطيع الدخول واستخدام صلاحياته الحالية." : "الموظف لا يملك وصولًا فعالًا حاليًا."}
            </p>
            <div className="mt-4 space-y-2">
              {isActive && (
                <Button variant="secondary" className="w-full justify-start border-amber-200 text-amber-800 hover:bg-amber-50" disabled={mutation.isPending || member.is_current_user} onClick={() => setConfirmAction("suspend")}>
                  <Ban aria-hidden size={16} /> تعطيل الموظف
                </Button>
              )}
              {member.membership_status === "SUSPENDED" && (
                <Button className="w-full justify-start" disabled={mutation.isPending} onClick={() => mutation.mutate(() => activateStaff(member.id))}>
                  <UserCheck aria-hidden size={16} /> إعادة التفعيل
                </Button>
              )}
              {member.membership_status === "DECLINED" && (
                <Button className="w-full justify-start" disabled={mutation.isPending} onClick={() => mutation.mutate(() => reinviteStaff(member.id))}>
                  <CheckCircle2 aria-hidden size={16} /> إعادة إرسال الدعوة
                </Button>
              )}
              {isActive && (member.roles.includes("TEACHER") || member.roles.includes("GATE_GUARD")) && (
                <Button variant="secondary" className="w-full justify-start border-blue-200 text-blue-800 hover:bg-blue-50" disabled={mutation.isPending || resetPassword.isPending || member.is_current_user} onClick={() => { setTemporaryPassword(null); setConfirmAction("reset-password"); }}>
                  <KeyRound aria-hidden size={16} /> إعادة ضبط كلمة المرور
                </Button>
              )}
              <Button variant="secondary" className="w-full justify-start border-red-200 text-red-700 hover:bg-red-50" disabled={mutation.isPending || member.is_current_user} onClick={() => setConfirmAction("delete")}>
                <Trash2 aria-hidden size={16} /> حذف نهائي
              </Button>
            </div>
          </section>
          {member.roles.includes("COUNSELOR") && (
            <CounselorSectionsEditor member={member} onError={setRowError} />
          )}
          {rowError && <p role="alert" className="rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700 lg:col-span-2">{rowError}</p>}
          {temporaryPassword && (
            <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 lg:col-span-2">
              <p className="font-black">تمت إعادة ضبط كلمة المرور بنجاح.</p>
              <p className="mt-1">{`كلمة المرور المؤقتة هي رقم جوال ${resetSubject}:`}</p>
              <code dir="ltr" className="mt-2 inline-block rounded-lg bg-white px-3 py-2 font-mono text-base font-black ring-1 ring-emerald-200">{temporaryPassword}</code>
              <p className="mt-2 text-xs">{`سيُطلب من ${resetSubject} تغييرها فور تسجيل الدخول، وتظهر هنا مرة واحدة فقط.`}</p>
            </div>
          )}
        </div>
        )
      )}

      {confirmAction === "reset-password" && (
        <Modal title={`إعادة ضبط كلمة مرور ${member.display_name}`} description="سيُلغى عمل كلمة المرور الحالية فورًا." onClose={closeConfirmation}>
          <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
            <p className="font-black">{`ستصبح كلمة المرور المؤقتة هي رقم جوال ${resetSubject}.`}</p>
            <p className="mt-1">عند تسجيل الدخول بها سيُلزم الحساب باختيار كلمة مرور جديدة قبل استخدام النظام.</p>
          </div>
          {rowError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{rowError}</p>}
          <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="secondary" onClick={closeConfirmation} disabled={resetPassword.isPending}>إلغاء</Button>
            <Button onClick={() => resetPassword.mutate()} disabled={resetPassword.isPending}>
              <KeyRound aria-hidden size={16} /> {resetPassword.isPending ? "جارٍ إعادة الضبط..." : "تأكيد إعادة الضبط"}
            </Button>
          </div>
        </Modal>
      )}

      {confirmAction === "suspend" && (
        <Modal title={`تعطيل ${member.display_name}`} description="يمكن إعادة تفعيل الموظف لاحقًا دون فقد بياناته." onClose={closeConfirmation}>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <p className="font-bold text-amber-900">سيتوقف وصول الموظف إلى المدرسة فورًا.</p>
            <p className="mt-1 text-sm leading-6 text-amber-800">ستبقى بيانات الحساب وأدواره محفوظة، ويمكن {schoolType === "GIRLS" ? "لمديرة المدرسة" : "لمدير المدرسة"} إعادة تفعيله في أي وقت.</p>
          </div>
          {rowError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{rowError}</p>}
          <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="secondary" onClick={closeConfirmation} disabled={mutation.isPending}>إلغاء</Button>
            <Button variant="danger" onClick={() => mutation.mutate(() => suspendStaff(member.id))} disabled={mutation.isPending}>
              <Ban aria-hidden size={16} /> {mutation.isPending ? "جارٍ التعطيل..." : "تأكيد التعطيل"}
            </Button>
          </div>
        </Modal>
      )}

      {confirmAction === "revoke-morning" && (
        <Modal
          title={`سحب تكليف التأخر الصباحي من ${member.display_name}`}
          description="سيختفي قسم التأخر الصباحي من مساحة المعلم فورًا."
          onClose={closeConfirmation}
        >
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
            <p className="font-black">سيُسحب التكليف التشغيلي فقط.</p>
            <p className="mt-1">ستبقى أدوار الموظف ومهامه الأصلية دون تغيير.</p>
          </div>
          {rowError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{rowError}</p>}
          <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="secondary" onClick={closeConfirmation} disabled={mutation.isPending}>إلغاء</Button>
            <Button variant="danger" onClick={() => mutation.mutate(() => revokeMorningAttendance(member.id))} disabled={mutation.isPending}>
              <Sunrise aria-hidden size={16} /> {mutation.isPending ? "جارٍ سحب التكليف..." : "تأكيد سحب التكليف"}
            </Button>
          </div>
        </Modal>
      )}

      {confirmAction === "delete" && (
        <Modal title={`حذف ${member.display_name} نهائيًا`} description="هذا الإجراء لا يمكن التراجع عنه." onClose={closeConfirmation}>
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-900">
            <p className="font-black">سيُحذف سجل الموظف وأدواره من هذه المدرسة نهائيًا.</p>
            <p className="mt-1">لن يُحذف حساب المستخدم من مدارس أخرى، وستبقى المراجع التاريخية اللازمة للتقارير وسجل التدقيق.</p>
          </div>
          <div className="mt-5">
            <label htmlFor={`delete-staff-${member.id}`} className="text-sm font-bold text-slate-800">
              للتأكيد اكتب اسم الموظف: <span className="text-red-700">{member.display_name}</span>
            </label>
            <input
              id={`delete-staff-${member.id}`}
              value={confirmationName}
              onChange={(event) => setConfirmationName(event.target.value)}
              autoComplete="off"
              className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 text-sm outline-none focus:border-red-500 focus:ring-3 focus:ring-red-100"
            />
          </div>
          {rowError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{rowError}</p>}
          <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="secondary" onClick={closeConfirmation} disabled={mutation.isPending}>إلغاء</Button>
            <Button variant="danger" onClick={() => mutation.mutate(() => deleteStaff(member.id))} disabled={mutation.isPending || confirmationName.trim() !== member.display_name}>
              <Trash2 aria-hidden size={16} /> {mutation.isPending ? "جارٍ الحذف..." : "حذف نهائي"}
            </Button>
          </div>
        </Modal>
      )}
    </li>
  );
}

function MorningAttendanceAssignment({
  member,
  pending,
  onToggle,
}: {
  member: StaffMember;
  pending: boolean;
  onToggle: (assigned: boolean) => void;
}) {
  const assigned = (member.capabilities ?? []).includes("MORNING_ATTENDANCE");
  const active = member.membership_status === "ACTIVE";

  return (
    <section
      className={`mt-5 overflow-hidden rounded-2xl border ${assigned ? "border-amber-200 bg-amber-50/70" : "border-slate-200 bg-slate-50"}`}
      data-testid={`morning-assignment-${member.id}`}
    >
      <div className="flex flex-col justify-between gap-4 p-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-start gap-3">
          <span className={`grid size-11 shrink-0 place-items-center rounded-2xl ${assigned ? "bg-gradient-to-br from-amber-400 to-orange-600 text-white shadow-md shadow-amber-900/15" : "bg-white text-slate-500 ring-1 ring-slate-200"}`}>
            <Sunrise aria-hidden size={21} />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h5 className="text-sm font-black text-slate-900">مسؤول متابعة التأخر الصباحي</h5>
              {assigned && <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-black text-amber-800 ring-1 ring-amber-200">تكليف دائم</span>}
            </div>
            <p className="mt-1 max-w-xl text-xs leading-5 text-slate-600">
              تكليف مستقل متاح للمعلم أو الوكيل أو المرشد أو الحارس، دون تغيير أدواره أو مهامه الأصلية.
            </p>
          </div>
        </div>
        <Button
          variant={assigned ? "secondary" : "primary"}
          className={assigned ? "shrink-0 border-amber-300 text-amber-900 hover:bg-amber-100" : "shrink-0"}
          disabled={pending || !active}
          onClick={() => onToggle(assigned)}
          data-testid={`toggle-morning-assignment-${member.id}`}
        >
          <Sunrise aria-hidden size={16} />
          {pending ? "جارٍ الحفظ..." : assigned ? "سحب التكليف" : "تكليف بالمتابعة"}
        </Button>
      </div>
      {!active && <p className="border-t border-slate-200 px-4 py-2 text-xs font-medium text-amber-800">أعد تفعيل الموظف أولًا لمنحه هذا التكليف.</p>}
    </section>
  );
}

function StaffProfileEditor({ member, onError }: { member: StaffMember; onError: (message: string | null) => void }) {
  const invalidate = useInvalidateSchoolData();
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState(member.display_name);
  const [employeeNumber, setEmployeeNumber] = useState(member.employee_number ?? "");
  const [jobTitle, setJobTitle] = useState(member.job_title);

  const mutation = useMutation({
    mutationFn: () => updateStaff(member.id, {
      display_name: displayName.trim(),
      employee_number: employeeNumber.trim(),
      job_title: jobTitle.trim(),
    }),
    onSuccess: () => {
      setEditing(false);
      onError(null);
      void invalidate("staff");
    },
    onError: (error) => onError(
      error instanceof ApiError ? error.message : "تعذر تحديث بيانات الموظف.",
    ),
  });

  if (!editing) {
    return (
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div>
          <h4 className="text-sm font-black text-slate-900">البيانات الوظيفية</h4>
          <p className="mt-1 text-xs text-slate-500">الاسم والرقم الوظيفي والمسمى. رقم الجوال هو هوية الدخول ولا يغيّر من هنا.</p>
        </div>
        <Button variant="secondary" onClick={() => setEditing(true)}>تعديل البيانات</Button>
      </div>
    );
  }

  return (
    <form className="mb-5 rounded-2xl border border-blue-200 bg-blue-50/40 p-4" onSubmit={(event) => { event.preventDefault(); if (displayName.trim().length >= 2) mutation.mutate(); }} data-testid={`staff-edit-form-${member.id}`}>
      <h4 className="text-sm font-black text-slate-900">تعديل البيانات الوظيفية</h4>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <TextField label="الاسم الكامل *" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        <TextField label="الرقم الوظيفي" value={employeeNumber} onChange={(event) => setEmployeeNumber(event.target.value)} dir="ltr" />
        <TextField label="المسمى الوظيفي" value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} />
      </div>
      {displayName.trim().length < 2 && <p role="alert" className="mt-3 text-sm text-red-700">أدخل اسم الموظف كاملًا.</p>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={() => { setEditing(false); setDisplayName(member.display_name); setEmployeeNumber(member.employee_number ?? ""); setJobTitle(member.job_title); }} disabled={mutation.isPending}>إلغاء</Button>
        <Button type="submit" disabled={mutation.isPending || displayName.trim().length < 2}>{mutation.isPending ? "جارٍ الحفظ..." : "حفظ البيانات"}</Button>
      </div>
    </form>
  );
}

function CounselorSectionsEditor({ member, onError }: { member: StaffMember; onError: (message: string | null) => void }) {
  const schoolId = useActiveSchoolId();
  const invalidate = useInvalidateSchoolData();
  const [allSections, setAllSections] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>(
    () => (member.counselor_sections ?? []).map((section) => section.id),
  );
  const [modeTouched, setModeTouched] = useState(false);
  const [conflicts, setConflicts] = useState<
    { section_name: string; current_counselor_name: string }[]
  >([]);

  const sections = useQuery({
    queryKey: schoolScopedKey(schoolId, "sections"),
    queryFn: ({ signal }) => getSections(signal),
    enabled: schoolId > 0,
  });

  const initiallyCoversAll = Boolean(
    sections.data && (
      sections.data.length === 0 ||
      (selectedIds.length === sections.data.length && sections.data.every((section) => selectedIds.includes(section.id)))
    ),
  );
  const effectiveAllSections = allSections || (!modeTouched && initiallyCoversAll);

  const mutation = useMutation({
    mutationFn: (confirm: boolean) => updateCounselorSections(
      member.id,
      effectiveAllSections ? [] : selectedIds,
      confirm,
    ),
    onSuccess: (updated) => {
      const assigned = (updated.counselor_sections ?? []).map((section) => section.id);
      setSelectedIds(assigned);
      setAllSections(
        (sections.data?.length ?? 0) === 0 ||
        (assigned.length === sections.data?.length && sections.data.every((section) => assigned.includes(section.id))),
      );
      setModeTouched(true);
      setConflicts([]);
      onError(null);
      void invalidate("staff");
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "COUNSELOR_SECTION_REASSIGNMENT_REQUIRED") {
        setConflicts((error.details.conflicts ?? []) as { section_name: string; current_counselor_name: string }[]);
        onError(null);
        return;
      }
      onError(error instanceof Error ? error.message : "تعذر تحديث فصول المرشد.");
    },
  });

  function save(confirm = false) {
    if (!effectiveAllSections && selectedIds.length === 0) {
      onError("اختر فصلًا واحدًا على الأقل، أو اختر جميع الفصول.");
      return;
    }
    setConflicts([]);
    mutation.mutate(confirm);
  }

  return (
    <section className="rounded-2xl border border-teal-100 bg-teal-50/40 p-4 lg:col-span-2" data-testid={`counselor-sections-${member.id}`}>
      <div className="mb-4">
        <h4 className="text-sm font-black text-slate-900">توزيع فصول المرشد</h4>
        <p className="mt-1 text-xs text-slate-500">الإحالات الجديدة لطلاب هذه الفصول ستُسند لهذا المرشد تلقائيًا.</p>
      </div>
      {sections.isPending ? <p className="text-sm text-slate-500">جارٍ تحميل الفصول...</p> : sections.isError ? <p role="alert" className="text-sm text-red-700">تعذر تحميل الفصول.</p> : (
        <CounselorSectionPicker
          sections={sections.data ?? []}
          allSections={effectiveAllSections}
          selectedIds={selectedIds}
          onAllSectionsChange={(value) => { setAllSections(value); setModeTouched(true); }}
          onSelectedIdsChange={(value) => { setSelectedIds(value); setModeTouched(true); }}
          disabled={mutation.isPending}
        />
      )}
      {conflicts.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="edit-counselor-section-conflicts">
          <p className="font-black">سيتم نقل الفصول التالية من مرشد آخر:</p>
          <ul className="mt-2 list-inside list-disc">
            {conflicts.map((conflict) => <li key={`${conflict.section_name}-${conflict.current_counselor_name}`}>{conflict.section_name} — {conflict.current_counselor_name}</li>)}
          </ul>
          <Button className="mt-3" onClick={() => save(true)} disabled={mutation.isPending}>تأكيد نقل المسؤولية</Button>
        </div>
      )}
      <div className="mt-4 flex justify-end">
        <Button onClick={() => save(false)} disabled={mutation.isPending || sections.isPending}>
          {mutation.isPending ? "جارٍ الحفظ..." : "حفظ توزيع الفصول"}
        </Button>
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles = status === "ACTIVE"
    ? "bg-emerald-50 text-emerald-700 ring-emerald-100"
    : status === "SUSPENDED"
      ? "bg-amber-50 text-amber-800 ring-amber-100"
      : status === "INVITED"
        ? "bg-blue-50 text-blue-700 ring-blue-100"
        : "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ring-1 ${styles}`}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {MEMBERSHIP_STATUS_LABELS[status] ?? status}
    </span>
  );
}
