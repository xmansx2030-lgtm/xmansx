import { useMutation } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import {
  updateStudent,
  type SectionItem,
  type StudentRow,
  type StudentUpdateInput,
} from "@/features/students/api";
import { useActiveSchoolType } from "@/features/settings/hooks";
import { studentLabel } from "@/utils/roles";

export function StudentEditForm({
  student,
  sections,
  onUpdated,
  onCancel,
}: {
  student: StudentRow;
  sections: SectionItem[];
  onUpdated: (student: StudentRow) => void;
  onCancel: () => void;
}) {
  const schoolType = useActiveSchoolType();
  const studentName = studentLabel(schoolType, true);
  const [fullName, setFullName] = useState(student.full_name);
  const [nationalId, setNationalId] = useState("");
  const [studentNumber, setStudentNumber] = useState(student.student_number ?? "");
  const [guardianName, setGuardianName] = useState(student.guardian_name);
  const [guardianMobile, setGuardianMobile] = useState("");
  const [sectionId, setSectionId] = useState<number | "">(student.section?.id ?? "");
  const [gradeId, setGradeId] = useState<number | "">(student.grade?.id ?? "");
  const [validationError, setValidationError] = useState<string | null>(null);

  const grades = useMemo(() => {
    const values = new Map<number, string>();
    sections.forEach((section) => values.set(section.grade.id, section.grade.name));
    return [...values.entries()];
  }, [sections]);
  const visibleSections = sections.filter((section) => !gradeId || section.grade.id === gradeId);

  const mutation = useMutation({
    mutationFn: () => {
      const input: StudentUpdateInput = {
        full_name: fullName.trim(),
        student_number: studentNumber.trim(),
        guardian_name: guardianName.trim(),
        section_id: Number(sectionId),
      };
      if (nationalId.trim()) input.national_id = nationalId.trim();
      if (guardianMobile.trim()) input.guardian_mobile = guardianMobile.trim();
      return updateStudent(student.id, input);
    },
    onSuccess: onUpdated,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setValidationError(null);
    if (fullName.trim().length < 2 || !sectionId) {
      setValidationError(`أكمل اسم ${studentName} والصف والفصل.`);
      return;
    }
    mutation.mutate();
  }

  const apiMessage = mutation.error instanceof ApiError
    ? studentValidationMessage(mutation.error)
    : null;

  return (
    <form onSubmit={submit} noValidate data-testid="student-edit-form">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={`اسم ${studentName} الكامل *`} value={fullName} onChange={(event) => setFullName(event.target.value)} autoFocus />
        <div>
          <TextField label="تصحيح رقم الهوية أو الإقامة" value={nationalId} onChange={(event) => setNationalId(event.target.value)} inputMode="numeric" dir="ltr" placeholder="اتركه فارغًا للاحتفاظ بالرقم الحالي" />
          <p className="mt-1 text-xs text-slate-500">الرقم الحالي: <bdi>{student.national_id_masked}</bdi>. يجب أن يكون 10 أرقام ويبدأ بـ 1 للهوية أو 2 للإقامة.</p>
        </div>
        <TextField label={`رقم ${studentName}`} value={studentNumber} onChange={(event) => setStudentNumber(event.target.value)} dir="ltr" />
        <TextField label="اسم ولي الأمر" value={guardianName} onChange={(event) => setGuardianName(event.target.value)} />
        <div>
          <TextField label="تصحيح جوال ولي الأمر" value={guardianMobile} onChange={(event) => setGuardianMobile(event.target.value)} type="tel" inputMode="tel" dir="ltr" placeholder="اتركه فارغًا للاحتفاظ بالرقم الحالي" />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`student-edit-grade-${student.id}`} className="text-sm font-bold text-slate-700">الصف *</label>
          <select id={`student-edit-grade-${student.id}`} value={gradeId} onChange={(event) => { setGradeId(event.target.value ? Number(event.target.value) : ""); setSectionId(""); }} className="border px-3 py-2 text-sm">
            <option value="">اختر الصف</option>
            {grades.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1 sm:col-start-2">
          <label htmlFor={`student-edit-section-${student.id}`} className="text-sm font-bold text-slate-700">الفصل *</label>
          <select id={`student-edit-section-${student.id}`} value={sectionId} disabled={!gradeId} onChange={(event) => setSectionId(event.target.value ? Number(event.target.value) : "")} className="border px-3 py-2 text-sm">
            <option value="">اختر الفصل</option>
            {visibleSections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
          </select>
        </div>
      </div>

      {(validationError || apiMessage) && <p role="alert" className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">{validationError ?? apiMessage}</p>}
      <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">تصحيح الهوية يحدّث القيمة المشفرة والمقنّعة ومفتاح البحث معًا. تغيير الفصل يحفظ القيد السابق في السجل ولا يعيد كتابة حضور الأيام الماضية.</p>

      <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>إلغاء</Button>
        <Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "جارٍ الحفظ..." : "حفظ التعديلات"}</Button>
      </div>
    </form>
  );
}

function studentValidationMessage(error: ApiError): string {
  for (const field of ["national_id", "student_number", "guardian_mobile", "full_name", "section_id"]) {
    const detail = error.details[field];
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && typeof detail[0] === "string") return detail[0];
  }
  return error.message;
}
