import { useMutation } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { createStudent, type SectionItem, type StudentRow } from "@/features/students/api";

export function ManualStudentForm({
  sections,
  onCreated,
  onCancel,
}: {
  sections: SectionItem[];
  onCreated: (student: StudentRow) => void;
  onCancel: () => void;
}) {
  const [fullName, setFullName] = useState("");
  const [nationalId, setNationalId] = useState("");
  const [studentNumber, setStudentNumber] = useState("");
  const [guardianName, setGuardianName] = useState("");
  const [guardianMobile, setGuardianMobile] = useState("");
  const [gradeId, setGradeId] = useState<number | "">("");
  const [sectionId, setSectionId] = useState<number | "">("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const grades = useMemo(() => {
    const values = new Map<number, string>();
    sections.forEach((section) => values.set(section.grade.id, section.grade.name));
    return [...values.entries()];
  }, [sections]);
  const visibleSections = sections.filter((section) => !gradeId || section.grade.id === gradeId);

  const mutation = useMutation({
    mutationFn: () => createStudent({
      full_name: fullName.trim(),
      national_id: nationalId.trim(),
      student_number: studentNumber.trim(),
      guardian_name: guardianName.trim(),
      guardian_mobile: guardianMobile.trim(),
      section_id: Number(sectionId),
    }),
    onSuccess: onCreated,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setValidationError(null);
    if (fullName.trim().length < 2 || !nationalId.trim() || !sectionId) {
      setValidationError("أكمل اسم الطالب ورقم الهوية والصف والفصل.");
      return;
    }
    mutation.mutate();
  }

  const apiMessage = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="اسم الطالب الكامل *" value={fullName} onChange={(e) => setFullName(e.target.value)} autoFocus />
        <TextField label="رقم الهوية أو الإقامة *" value={nationalId} onChange={(e) => setNationalId(e.target.value)} inputMode="numeric" dir="ltr" placeholder="1XXXXXXXXX" />
        <TextField label="رقم الطالب" value={studentNumber} onChange={(e) => setStudentNumber(e.target.value)} dir="ltr" />
        <TextField label="اسم ولي الأمر" value={guardianName} onChange={(e) => setGuardianName(e.target.value)} />
        <TextField label="جوال ولي الأمر" value={guardianMobile} onChange={(e) => setGuardianMobile(e.target.value)} type="tel" inputMode="tel" dir="ltr" placeholder="05XXXXXXXX" />
        <div className="flex flex-col gap-1">
          <label htmlFor="manual-student-grade" className="text-sm font-bold text-slate-700">الصف *</label>
          <select id="manual-student-grade" value={gradeId} onChange={(e) => { setGradeId(e.target.value ? Number(e.target.value) : ""); setSectionId(""); }} className="border px-3 py-2 text-sm">
            <option value="">اختر الصف</option>
            {grades.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1 sm:col-start-2">
          <label htmlFor="manual-student-section" className="text-sm font-bold text-slate-700">الفصل *</label>
          <select id="manual-student-section" value={sectionId} disabled={!gradeId} onChange={(e) => setSectionId(e.target.value ? Number(e.target.value) : "")} className="border px-3 py-2 text-sm">
            <option value="">اختر الفصل</option>
            {visibleSections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
          </select>
        </div>
      </div>

      {(validationError || apiMessage) && <p role="alert" className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">{validationError ?? apiMessage}</p>}
      {sections.length === 0 && <p role="alert" className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">لا توجد صفوف وفصول متاحة. أضفها من الإعدادات أولًا.</p>}

      <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>إلغاء</Button>
        <Button type="submit" disabled={mutation.isPending || sections.length === 0}>{mutation.isPending ? "جارٍ الإضافة..." : "إضافة الطالب"}</Button>
      </div>
    </form>
  );
}
