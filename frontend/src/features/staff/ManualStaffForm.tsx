import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Copy, Info, KeyRound, ShieldCheck, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { schoolScopedKey } from "@/features/auth/useMe";
import { CounselorSectionPicker } from "@/features/staff/CounselorSectionPicker";
import { VicePrincipalScopePicker } from "@/features/staff/VicePrincipalScopePicker";
import { createStaff, type ManualStaffResult } from "@/features/staff/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import { getSections } from "@/features/students/api";
import { roleLabel } from "@/utils/roles";

const ROLES = ["TEACHER", "COUNSELOR", "GATE_GUARD", "VICE_PRINCIPAL"] as const;
const ROLE_DESCRIPTIONS: Record<(typeof ROLES)[number], string> = {
  TEACHER: "تحضير الطلاب والوصول إلى الفصول المسندة إليه.",
  COUNSELOR: "متابعة الحالات والإحالات والسلوك والإنذارات.",
  GATE_GUARD: "عرض استئذانات اليوم وتأكيد خروج الطلاب من البوابة فقط.",
  VICE_PRINCIPAL: "معالجة إحالات الطلاب ضمن الصفوف أو الفصول المسندة إليه.",
};

export function ManualStaffForm({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const managerLabel = schoolType === "GIRLS" ? "مديرة المدرسة" : "مدير المدرسة";
  const singleManagerLabel = schoolType === "GIRLS" ? "مديرة واحدة" : "مدير واحد";
  const [displayName, setDisplayName] = useState("");
  const [mobile, setMobile] = useState("");
  const [employeeNumber, setEmployeeNumber] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number]>("TEACHER");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [result, setResult] = useState<ManualStaffResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [allSections, setAllSections] = useState(true);
  const [selectedSectionIds, setSelectedSectionIds] = useState<number[]>([]);
  const [sectionConflicts, setSectionConflicts] = useState<
    { section_name: string; current_counselor_name: string }[]
  >([]);
  const [selectedViceGradeIds, setSelectedViceGradeIds] = useState<number[]>([]);
  const [selectedViceSectionIds, setSelectedViceSectionIds] = useState<number[]>([]);
  const [scopeConflicts, setScopeConflicts] = useState<
    { target_name: string; current_vice_principal_name: string }[]
  >([]);

  const sections = useQuery({
    queryKey: schoolScopedKey(schoolId, "sections"),
    queryFn: ({ signal }) => getSections(signal),
    enabled: schoolId > 0 && (role === "COUNSELOR" || role === "VICE_PRINCIPAL"),
  });

  const mutation = useMutation({
    mutationFn: (confirmSectionReassignment: boolean) => createStaff({
      display_name: displayName.trim(),
      mobile: mobile.trim(),
      employee_number: employeeNumber.trim(),
      job_title: jobTitle.trim(),
      role,
      counselor_section_ids: role === "COUNSELOR"
        ? (allSections ? [] : selectedSectionIds)
        : undefined,
      confirm_section_reassignment: confirmSectionReassignment,
      vice_principal_grade_ids: role === "VICE_PRINCIPAL" ? selectedViceGradeIds : undefined,
      vice_principal_section_ids: role === "VICE_PRINCIPAL" ? selectedViceSectionIds : undefined,
      confirm_scope_reassignment: confirmSectionReassignment,
    }),
    onSuccess: (data) => { setResult(data); onCreated(); },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "COUNSELOR_SECTION_REASSIGNMENT_REQUIRED") {
        setSectionConflicts((error.details.conflicts ?? []) as { section_name: string; current_counselor_name: string }[]);
      }
      if (error instanceof ApiError && error.code === "VICE_PRINCIPAL_SCOPE_REASSIGNMENT_REQUIRED") {
        setScopeConflicts((error.details.conflicts ?? []) as { target_name: string; current_vice_principal_name: string }[]);
      }
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setValidationError(null);
    if (displayName.trim().length < 2 || !mobile.trim()) {
      setValidationError("أكمل اسم الموظف ورقم الجوال.");
      return;
    }
    if (role === "COUNSELOR" && !allSections && selectedSectionIds.length === 0) {
      setValidationError("اختر فصلًا واحدًا على الأقل، أو اختر جميع الفصول.");
      return;
    }
    if (
      role === "VICE_PRINCIPAL" &&
      (sections.data?.length ?? 0) > 0 &&
      selectedViceGradeIds.length === 0 &&
      selectedViceSectionIds.length === 0
    ) {
      setValidationError("حدد صفًا كاملًا أو فصلًا واحدًا على الأقل لمسؤولية الوكيل.");
      return;
    }
    setSectionConflicts([]);
    setScopeConflicts([]);
    mutation.mutate(false);
  }

  if (result) {
    return (
      <div className="text-center">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-emerald-100 text-emerald-700"><CheckCircle2 aria-hidden size={28} /></span>
        <h3 className="mt-4 text-xl font-black">تمت إضافة {result.display_name}</h3>
        {result.temporary_password ? (
          <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-start">
            <p className="flex items-center gap-2 font-bold text-amber-900"><KeyRound size={18} /> كلمة المرور الأولية</p>
            <p className="mt-1 text-sm leading-6 text-amber-800">تظهر مرة واحدة فقط. وهي رقم الجوال بصيغة 05XXXXXXXX، وسيُطلب من الموظف تغييرها فور أول تسجيل دخول.</p>
            <div className="mt-3 flex items-center gap-2 rounded-xl bg-white p-2 ring-1 ring-amber-200">
              <code dir="ltr" className="min-w-0 flex-1 select-all text-center text-base font-black">{result.temporary_password}</code>
              <button type="button" aria-label="نسخ كلمة المرور" onClick={() => { void navigator.clipboard.writeText(result.temporary_password!); setCopied(true); }} className="grid size-9 place-items-center rounded-lg text-amber-800 hover:bg-amber-50"><Copy size={17} /></button>
            </div>
            {copied && <p role="status" className="mt-2 text-xs font-bold text-emerald-700">تم النسخ.</p>}
          </div>
        ) : (
          <p className="mt-4 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">الحساب موجود مسبقًا؛ أُرسلت إليه دعوة للانضمام إلى المدرسة.</p>
        )}
        <Button className="mt-6 w-full" onClick={onClose}>تم</Button>
      </div>
    );
  }

  const apiMessage = mutation.error instanceof ApiError ? mutation.error.message : null;
  return (
    <form onSubmit={submit} noValidate>
      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-blue-900">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white text-blue-700 shadow-sm"><UserPlus aria-hidden size={18} /></span>
        <div><p className="text-sm font-black">إضافة سريعة وآمنة</p><p className="mt-1 text-xs leading-5 text-blue-800">إذا كان الجوال مسجلًا فستُرسل دعوة دون تغيير كلمة مروره. أما الحساب الجديد فكلمة دخوله الأولى هي رقم الجوال، مع إلزامه بتغييرها فورًا.</p></div>
      </div>

      <div className="rounded-2xl border border-slate-200 p-4 sm:p-5">
        <h3 className="mb-4 text-sm font-black text-slate-900">بيانات الموظف</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="اسم الموظف الكامل *" value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoFocus />
          <TextField label="رقم الجوال *" value={mobile} onChange={(e) => setMobile(e.target.value)} type="tel" inputMode="tel" dir="ltr" placeholder="05XXXXXXXX" />
          <TextField label="الرقم الوظيفي" value={employeeNumber} onChange={(e) => setEmployeeNumber(e.target.value)} dir="ltr" placeholder="اختياري" />
          <TextField label="المسمى الوظيفي" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder={`مثال: ${roleLabel("TEACHER", schoolType)} رياضيات`} />
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 p-4 sm:p-5">
        <div className="mb-3 flex items-center gap-2"><ShieldCheck aria-hidden size={18} className="text-blue-700" /><h3 className="text-sm font-black text-slate-900">الدور والصلاحيات</h3></div>
        <div className="mb-4 rounded-xl border border-violet-200 bg-violet-50 p-3 text-xs leading-5 text-violet-900">
          <p className="font-black">حساب {managerLabel} محمي</p>
          <p className="mt-1">للمدرسة {singleManagerLabel} فقط، ولا يمكن إضافة مدير آخر أو تعيينه من إدارة الموظفين. تتم إدارة حساب {managerLabel} مركزيًا من إدارة المنصة.</p>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="manual-staff-role" className="text-sm font-bold text-slate-700">الدور الأول في المنصة *</label>
          <select id="manual-staff-role" value={role} onChange={(e) => { setRole(e.target.value as (typeof ROLES)[number]); setSectionConflicts([]); setScopeConflicts([]); }} className="h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm">
            {ROLES.map((value) => <option key={value} value={value}>{roleLabel(value, schoolType)}</option>)}
          </select>
          <p className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-slate-500"><Info aria-hidden size={14} className="mt-0.5 shrink-0" />{ROLE_DESCRIPTIONS[role]} ويمكن تعديل الأدوار لاحقًا من إدارة الموظف.</p>
        </div>
      </div>
      {role === "COUNSELOR" && (
        <div className="mt-4 rounded-2xl border border-slate-200 p-4 sm:p-5">
          {sections.isPending ? (
            <p className="text-sm text-slate-500">جارٍ تحميل الفصول...</p>
          ) : sections.isError ? (
            <p role="alert" className="text-sm text-red-700">تعذر تحميل فصول المدرسة.</p>
          ) : (
            <CounselorSectionPicker
              sections={sections.data ?? []}
              allSections={allSections}
              selectedIds={selectedSectionIds}
              onAllSectionsChange={setAllSections}
              onSelectedIdsChange={setSelectedSectionIds}
              disabled={mutation.isPending}
            />
          )}
        </div>
      )}
      {role === "VICE_PRINCIPAL" && (
        <div className="mt-4 rounded-2xl border border-violet-200 bg-violet-50/30 p-4 sm:p-5">
          {sections.isPending ? (
            <p className="text-sm text-slate-500">جارٍ تحميل الصفوف والفصول...</p>
          ) : sections.isError ? (
            <p role="alert" className="text-sm text-red-700">تعذر تحميل صفوف المدرسة وفصولها.</p>
          ) : (
            <VicePrincipalScopePicker
              sections={sections.data ?? []}
              selectedGradeIds={selectedViceGradeIds}
              selectedSectionIds={selectedViceSectionIds}
              onSelectedGradeIdsChange={setSelectedViceGradeIds}
              onSelectedSectionIdsChange={setSelectedViceSectionIds}
              disabled={mutation.isPending}
            />
          )}
        </div>
      )}
      {sectionConflicts.length > 0 && (
        <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" data-testid="counselor-section-conflicts">
          <p className="font-black">توجد فصول مرتبطة بمرشد آخر</p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            {sectionConflicts.map((conflict) => (
              <li key={`${conflict.section_name}-${conflict.current_counselor_name}`}>
                {conflict.section_name} — {conflict.current_counselor_name}
              </li>
            ))}
          </ul>
          <Button type="button" className="mt-3" onClick={() => mutation.mutate(true)} disabled={mutation.isPending}>
            تأكيد نقل الفصول وإضافة المرشد
          </Button>
        </div>
      )}
      {scopeConflicts.length > 0 && (
        <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" data-testid="vice-principal-scope-conflicts">
          <p className="font-black">توجد نطاقات مرتبطة بوكيل آخر</p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            {scopeConflicts.map((conflict) => (
              <li key={`${conflict.target_name}-${conflict.current_vice_principal_name}`}>
                {conflict.target_name} — {conflict.current_vice_principal_name}
              </li>
            ))}
          </ul>
          <Button type="button" className="mt-3" onClick={() => mutation.mutate(true)} disabled={mutation.isPending}>
            تأكيد نقل المسؤولية وإضافة الوكيل
          </Button>
        </div>
      )}
      {(validationError || apiMessage) && <p role="alert" className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">{validationError ?? apiMessage}</p>}
      <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onClose}>إلغاء</Button>
        <Button type="submit" disabled={mutation.isPending || ((role === "COUNSELOR" || role === "VICE_PRINCIPAL") && sections.isPending)}>{mutation.isPending ? "جارٍ الإضافة..." : "إضافة الموظف"}</Button>
      </div>
    </form>
  );
}
