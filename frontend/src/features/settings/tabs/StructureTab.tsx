import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CheckCircle2, GraduationCap, Layers3, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { useState, type ButtonHTMLAttributes, type ReactNode } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  createGrade, createSection, deleteGrade, deleteSection, getGrades, getSections,
  updateGrade, updateSection, type GradeItem, type SectionItem,
} from "@/features/students/api";

type Editor = { kind: "grade"; item: GradeItem } | { kind: "section"; item: SectionItem } | null;
type Confirmation =
  | { kind: "grade-status" | "grade-delete"; item: GradeItem }
  | { kind: "section-status" | "section-delete"; item: SectionItem }
  | null;
type StructureAction =
  | { kind: "update-grade"; id: number; body: Parameters<typeof updateGrade>[1] }
  | { kind: "update-section"; id: number; body: Parameters<typeof updateSection>[1] }
  | { kind: "grade-status"; item: GradeItem }
  | { kind: "section-status"; item: SectionItem }
  | { kind: "grade-delete"; item: GradeItem }
  | { kind: "section-delete"; item: SectionItem };

const inputClass = "mt-1.5 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm outline-none transition focus:border-blue-500 focus:ring-3 focus:ring-blue-100";

export function StructureTab({ canWrite }: { canWrite: boolean }) {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [grade, setGrade] = useState({ name: "", code: "", sequence: 1 });
  const [section, setSection] = useState({ grade_id: "", name: "", code: "" });
  const [editor, setEditor] = useState<Editor>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [feedback, setFeedback] = useState("");
  const gradesKey = schoolScopedKey(schoolId, "grades", "structure-management");
  const sectionsKey = schoolScopedKey(schoolId, "sections", "structure-management");
  const grades = useQuery({ queryKey: gradesKey, queryFn: ({ signal }) => getGrades(signal, true) });
  const sections = useQuery({ queryKey: sectionsKey, queryFn: ({ signal }) => getSections(signal, true) });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "grades") }),
      queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "sections") }),
    ]);
  };
  const gradeMutation = useMutation({
    mutationFn: () => createGrade({ ...grade, name: grade.name.trim(), code: grade.code.trim() }),
    onSuccess: async (created) => {
      setGrade((current) => ({
        name: "",
        code: "",
        sequence: Number.isFinite(created.sequence) ? created.sequence + 1 : current.sequence + 1,
      }));
      setSection((value) => ({ ...value, grade_id: String(created.id) }));
      setFeedback(`تمت إضافة الصف «${created.name}» بنجاح.`);
      await refresh();
    },
  });
  const sectionMutation = useMutation({
    mutationFn: () => createSection({ ...section, grade_id: Number(section.grade_id), name: section.name.trim(), code: section.code.trim() }),
    onSuccess: async (created) => {
      setSection((value) => ({ ...value, name: "", code: "" }));
      setFeedback(`تمت إضافة الفصل «${created.name}» بنجاح.`);
      await refresh();
    },
  });
  const actionMutation = useMutation({
    mutationFn: async (action: StructureAction) => {
      if (action.kind === "update-grade") {
        const updated = await updateGrade(action.id, action.body);
        return `تم حفظ تعديلات الصف «${updated.name}».`;
      }
      if (action.kind === "update-section") {
        const updated = await updateSection(action.id, action.body);
        return `تم حفظ تعديلات الفصل «${updated.name}».`;
      }
      if (action.kind === "grade-status") {
        const updated = await updateGrade(action.item.id, { is_active: !action.item.is_active });
        return updated.is_active ? `تمت إعادة تفعيل الصف «${updated.name}». فعّل فصوله المطلوبة بشكل مستقل.` : `تم إيقاف الصف «${updated.name}» وفصوله.`;
      }
      if (action.kind === "section-status") {
        const updated = await updateSection(action.item.id, { is_active: !action.item.is_active });
        return `تم ${updated.is_active ? "تفعيل" : "إيقاف"} الفصل «${updated.name}».`;
      }
      if (action.kind === "grade-delete") {
        await deleteGrade(action.item.id);
        return `تم حذف الصف «${action.item.name}» نهائيًا.`;
      }
      await deleteSection(action.item.id);
      return `تم حذف الفصل «${action.item.name}» نهائيًا.`;
    },
    onSuccess: async (message) => {
      setFeedback(message);
      setEditor(null);
      setConfirmation(null);
      await refresh();
    },
  });

  if (grades.isPending || sections.isPending) return <Spinner />;
  if (grades.isError) return <ErrorState error={grades.error} />;
  if (sections.isError) return <ErrorState error={sections.error} />;

  const activeGrades = grades.data.filter((item) => item.is_active).length;
  const activeSections = sections.data.filter((item) => item.is_active && item.grade.is_active).length;
  const inactiveCount = grades.data.length - activeGrades + sections.data.length - activeSections;
  const startEdit = (value: NonNullable<Editor>) => { actionMutation.reset(); setEditor(value); };
  const startConfirmation = (value: NonNullable<Confirmation>) => { actionMutation.reset(); setConfirmation(value); };

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-3xl border border-blue-100 bg-gradient-to-l from-blue-50 via-white to-teal-50 p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl"><p className="text-xs font-black text-blue-700">الهيكل الدراسي</p><h3 className="mt-1 text-xl font-black text-slate-950">إدارة الصفوف والفصول من مكان واحد</h3><p className="mt-2 text-sm leading-6 text-slate-600">عدّل بيانات الهيكل، أوقف العناصر مؤقتًا دون فقد التاريخ، أو احذف العناصر التي لم تُستخدم بعد.</p></div>
          <span className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-2 text-xs font-bold text-emerald-700 shadow-sm ring-1 ring-emerald-100"><CheckCircle2 aria-hidden size={15} /> محفوظ وآمن تاريخيًا</span>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2 sm:gap-3">
          <Metric label="صف نشط" value={activeGrades} icon={<GraduationCap aria-hidden size={18} />} tone="blue" />
          <Metric label="فصل نشط" value={activeSections} icon={<Layers3 aria-hidden size={18} />} tone="teal" />
          <Metric label="عنصر متوقف" value={inactiveCount} icon={<Ban aria-hidden size={18} />} tone="slate" />
        </div>
      </section>

      {feedback && <div role="status" className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-900"><CheckCircle2 aria-hidden size={18} className="mt-0.5 shrink-0" /> {feedback}</div>}

      {canWrite && <div className="grid gap-4 lg:grid-cols-2">
        <form className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" onSubmit={(event) => { event.preventDefault(); setFeedback(""); gradeMutation.mutate(); }}>
          <FormHeading icon={<Plus aria-hidden size={19} />} title="إضافة صف جديد" description="عرّف الصف وترتيبه في القوائم." tone="blue" />
          <label className="block text-sm font-bold text-slate-700">اسم الصف<input aria-label="اسم الصف" required placeholder="مثال: الأول الثانوي" value={grade.name} onChange={(event) => setGrade({ ...grade, name: event.target.value })} className={inputClass} /></label>
          <div className="mt-3 grid grid-cols-2 gap-3"><label className="text-sm font-bold text-slate-700">الرمز<input aria-label="رمز الصف" required placeholder="SEC-1" value={grade.code} onChange={(event) => setGrade({ ...grade, code: event.target.value })} className={inputClass} /></label><label className="text-sm font-bold text-slate-700">الترتيب<input aria-label="ترتيب الصف" required type="number" min="0" value={grade.sequence} onChange={(event) => setGrade({ ...grade, sequence: Number(event.target.value) })} className={inputClass} /></label></div>
          <Button type="submit" className="mt-4 w-full" disabled={gradeMutation.isPending}><Plus aria-hidden size={17} />{gradeMutation.isPending ? "جارٍ الحفظ..." : "حفظ الصف"}</Button>
          {gradeMutation.isError && <div className="mt-3"><ErrorState error={gradeMutation.error} /></div>}
        </form>
        <form className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" onSubmit={(event) => { event.preventDefault(); setFeedback(""); sectionMutation.mutate(); }}>
          <FormHeading icon={<Layers3 aria-hidden size={19} />} title="إضافة فصل جديد" description="اربط الفصل بأحد الصفوف النشطة." tone="teal" />
          <label className="block text-sm font-bold text-slate-700">الصف التابع له<select aria-label="الصف التابع له الفصل" required value={section.grade_id} onChange={(event) => setSection({ ...section, grade_id: event.target.value })} className={inputClass}><option value="">اختر الصف</option>{grades.data.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <div className="mt-3 grid grid-cols-2 gap-3"><label className="text-sm font-bold text-slate-700">اسم الفصل<input aria-label="اسم الفصل" required placeholder="1 أو أ" value={section.name} onChange={(event) => setSection({ ...section, name: event.target.value })} className={inputClass} /></label><label className="text-sm font-bold text-slate-700">الرمز<input aria-label="رمز الفصل" required placeholder="A" value={section.code} onChange={(event) => setSection({ ...section, code: event.target.value })} className={inputClass} /></label></div>
          <Button type="submit" className="mt-4 w-full" disabled={sectionMutation.isPending || activeGrades === 0}><Plus aria-hidden size={17} />{sectionMutation.isPending ? "جارٍ الحفظ..." : "حفظ الفصل"}</Button>
          {sectionMutation.isError && <div className="mt-3"><ErrorState error={sectionMutation.error} /></div>}
        </form>
      </div>}

      <section>
        <div className="mb-4 flex items-end justify-between gap-3"><div><h3 className="text-lg font-black text-slate-950">الصفوف والفصول المسجلة</h3><p className="mt-1 text-sm text-slate-500">العناصر المتوقفة تبقى محفوظة ولا تظهر في التحضير أو تسجيل الطلاب.</p></div><span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">{grades.data.length} صف · {sections.data.length} فصل</span></div>
        <div className="space-y-4">
          {grades.data.map((item) => {
            const gradeSections = sections.data.filter((row) => row.grade.id === item.id);
            return <article key={item.id} className={`overflow-hidden rounded-2xl border shadow-sm ${item.is_active ? "border-slate-200 bg-white" : "border-slate-200 bg-slate-50/70"}`} data-testid={`grade-card-${item.id}`}>
              <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4 sm:p-5">
                <div className="flex min-w-0 items-center gap-3"><span className={`grid size-11 shrink-0 place-items-center rounded-2xl ${item.is_active ? "bg-blue-50 text-blue-700" : "bg-slate-200 text-slate-500"}`}><GraduationCap aria-hidden size={21} /></span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h4 className="font-black text-slate-950">{item.name}</h4><StatusPill active={item.is_active} /></div><p className="mt-1 text-xs text-slate-500">الرمز: <b dir="ltr">{item.code}</b> · الترتيب: {item.sequence} · {gradeSections.length} فصل</p></div></div>
                {canWrite && <div className="flex flex-wrap gap-2"><SmallAction label={`تعديل الصف ${item.name}`} icon={<Pencil aria-hidden size={15} />} onClick={() => startEdit({ kind: "grade", item })}>تعديل</SmallAction><SmallAction label={`${item.is_active ? "إيقاف" : "تفعيل"} الصف ${item.name}`} icon={item.is_active ? <Power aria-hidden size={15} /> : <CheckCircle2 aria-hidden size={15} />} tone={item.is_active ? "amber" : "green"} onClick={() => startConfirmation({ kind: "grade-status", item })}>{item.is_active ? "إيقاف" : "تفعيل"}</SmallAction><SmallAction label={`حذف الصف ${item.name}`} icon={<Trash2 aria-hidden size={15} />} tone="red" disabled={gradeSections.length > 0} title={gradeSections.length > 0 ? "احذف الفصول التابعة أولًا" : undefined} onClick={() => startConfirmation({ kind: "grade-delete", item })}>حذف</SmallAction></div>}
              </header>
              <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5 xl:grid-cols-3">
                {gradeSections.map((row) => <div key={row.id} className={`flex items-center justify-between gap-3 rounded-2xl border p-3.5 ${row.is_active && item.is_active ? "border-slate-200 bg-white" : "border-slate-200 bg-slate-50"}`} data-testid={`section-card-${row.id}`}><div className="min-w-0"><div className="flex items-center gap-2"><span className={`size-2 rounded-full ${row.is_active && item.is_active ? "bg-emerald-500" : "bg-slate-400"}`} /><p className="truncate text-sm font-black text-slate-900">فصل {row.name}</p></div><p className="mt-1 text-xs text-slate-500">الرمز: <b dir="ltr">{row.code}</b> · {row.is_active && item.is_active ? "نشط" : "متوقف"}</p></div>{canWrite && <div className="flex shrink-0 gap-1"><IconAction label={`تعديل الفصل ${row.name}`} icon={<Pencil aria-hidden size={15} />} onClick={() => startEdit({ kind: "section", item: row })} /><IconAction label={`${row.is_active ? "إيقاف" : "تفعيل"} الفصل ${row.name}`} icon={row.is_active ? <Power aria-hidden size={15} /> : <CheckCircle2 aria-hidden size={15} />} disabled={!row.is_active && !item.is_active} onClick={() => startConfirmation({ kind: "section-status", item: row })} /><IconAction label={`حذف الفصل ${row.name}`} icon={<Trash2 aria-hidden size={15} />} tone="red" onClick={() => startConfirmation({ kind: "section-delete", item: row })} /></div>}</div>)}
                {gradeSections.length === 0 && <p className="col-span-full rounded-xl border border-dashed border-slate-200 p-4 text-center text-sm text-slate-500">لا توجد فصول تابعة لهذا الصف.</p>}
              </div>
            </article>;
          })}
          {grades.data.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center"><GraduationCap aria-hidden size={30} className="mx-auto text-slate-300" /><p className="mt-3 font-bold text-slate-700">لا توجد صفوف بعد</p><p className="mt-1 text-sm text-slate-500">ابدأ بإضافة أول صف، ثم أضف الفصول التابعة له.</p></div>}
        </div>
      </section>

      {editor?.kind === "grade" && <GradeEditor item={editor.item} pending={actionMutation.isPending} error={actionMutation.error} onClose={() => setEditor(null)} onSave={(body) => actionMutation.mutate({ kind: "update-grade", id: editor.item.id, body })} />}
      {editor?.kind === "section" && <SectionEditor item={editor.item} grades={grades.data} pending={actionMutation.isPending} error={actionMutation.error} onClose={() => setEditor(null)} onSave={(body) => actionMutation.mutate({ kind: "update-section", id: editor.item.id, body })} />}
      {confirmation && <ConfirmationModal confirmation={confirmation} pending={actionMutation.isPending} error={actionMutation.error} sectionCount={confirmation.kind.startsWith("grade") ? sections.data.filter((row) => row.grade.id === confirmation.item.id).length : 0} onClose={() => setConfirmation(null)} onConfirm={() => actionMutation.mutate(confirmation)} />}
    </div>
  );
}

function FormHeading({ icon, title, description, tone }: { icon: ReactNode; title: string; description: string; tone: "blue" | "teal" }) { return <div className="mb-4 flex items-center gap-3"><span className={`grid size-10 place-items-center rounded-xl ${tone === "blue" ? "bg-blue-50 text-blue-700" : "bg-teal-50 text-teal-700"}`}>{icon}</span><div><h3 className="font-black text-slate-950">{title}</h3><p className="text-xs text-slate-500">{description}</p></div></div>; }
function Metric({ label, value, icon, tone }: { label: string; value: number; icon: ReactNode; tone: "blue" | "teal" | "slate" }) { const tones = { blue: "bg-blue-600 text-white", teal: "bg-teal-600 text-white", slate: "bg-white text-slate-800 ring-1 ring-slate-200" }; return <div className={`rounded-2xl p-3 sm:p-4 ${tones[tone]}`}><span className="flex items-center gap-2 opacity-85">{icon}<span className="text-[11px] font-bold sm:text-xs">{label}</span></span><strong className="mt-2 block text-2xl font-black">{value}</strong></div>; }
function StatusPill({ active }: { active: boolean }) { return <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${active ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>{active ? "نشط" : "متوقف"}</span>; }
function SmallAction({ label, icon, children, tone = "slate", ...props }: { label: string; icon: ReactNode; children: ReactNode; tone?: "slate" | "amber" | "green" | "red" } & ButtonHTMLAttributes<HTMLButtonElement>) { const tones = { slate: "border-slate-200 text-slate-700 hover:bg-slate-50", amber: "border-amber-200 text-amber-800 hover:bg-amber-50", green: "border-emerald-200 text-emerald-700 hover:bg-emerald-50", red: "border-red-200 text-red-700 hover:bg-red-50" }; return <button type="button" aria-label={label} className={`inline-flex h-9 items-center gap-1.5 rounded-xl border px-3 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-40 ${tones[tone]}`} {...props}>{icon}{children}</button>; }
function IconAction({ label, icon, tone = "slate", ...props }: { label: string; icon: ReactNode; tone?: "slate" | "red" } & ButtonHTMLAttributes<HTMLButtonElement>) { return <button type="button" aria-label={label} title={label} className={`grid size-8 place-items-center rounded-lg transition disabled:cursor-not-allowed disabled:opacity-30 ${tone === "red" ? "text-red-600 hover:bg-red-50" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"}`} {...props}>{icon}</button>; }

function GradeEditor({ item, pending, error, onClose, onSave }: { item: GradeItem; pending: boolean; error: Error | null; onClose: () => void; onSave: (body: Parameters<typeof updateGrade>[1]) => void }) {
  const [value, setValue] = useState({ name: item.name, code: item.code, sequence: item.sequence });
  return <Modal title={`تعديل الصف ${item.name}`} description="حدّث الاسم أو الرمز أو موضع الصف في القوائم." onClose={onClose}><form onSubmit={(event) => { event.preventDefault(); onSave({ ...value, name: value.name.trim(), code: value.code.trim() }); }}><label className="block text-sm font-bold text-slate-700">اسم الصف<input aria-label="تعديل اسم الصف" required value={value.name} onChange={(event) => setValue({ ...value, name: event.target.value })} className={inputClass} /></label><div className="mt-4 grid grid-cols-2 gap-3"><label className="text-sm font-bold text-slate-700">الرمز<input aria-label="تعديل رمز الصف" required value={value.code} onChange={(event) => setValue({ ...value, code: event.target.value })} className={inputClass} /></label><label className="text-sm font-bold text-slate-700">الترتيب<input aria-label="تعديل ترتيب الصف" required type="number" min="0" value={value.sequence} onChange={(event) => setValue({ ...value, sequence: Number(event.target.value) })} className={inputClass} /></label></div>{error && <div className="mt-4"><ErrorState error={error} /></div>}<div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4"><Button variant="secondary" onClick={onClose} disabled={pending}>إلغاء</Button><Button type="submit" disabled={pending}><Pencil aria-hidden size={16} />{pending ? "جارٍ الحفظ..." : "حفظ التعديلات"}</Button></div></form></Modal>;
}
function SectionEditor({ item, grades, pending, error, onClose, onSave }: { item: SectionItem; grades: GradeItem[]; pending: boolean; error: Error | null; onClose: () => void; onSave: (body: Parameters<typeof updateSection>[1]) => void }) {
  const [value, setValue] = useState({ grade_id: item.grade.id, name: item.name, code: item.code });
  return <Modal title={`تعديل الفصل ${item.name}`} description="يمكنك تصحيح بيانات الفصل أو نقله إلى صف آخر." onClose={onClose}><form onSubmit={(event) => { event.preventDefault(); onSave({ ...value, name: value.name.trim(), code: value.code.trim() }); }}><label className="block text-sm font-bold text-slate-700">الصف التابع له<select aria-label="تعديل الصف التابع له الفصل" value={value.grade_id} onChange={(event) => setValue({ ...value, grade_id: Number(event.target.value) })} className={inputClass}>{grades.map((grade) => <option key={grade.id} value={grade.id} disabled={!grade.is_active && grade.id !== item.grade.id}>{grade.name}{grade.is_active ? "" : " — متوقف"}</option>)}</select></label><div className="mt-4 grid grid-cols-2 gap-3"><label className="text-sm font-bold text-slate-700">اسم الفصل<input aria-label="تعديل اسم الفصل" required value={value.name} onChange={(event) => setValue({ ...value, name: event.target.value })} className={inputClass} /></label><label className="text-sm font-bold text-slate-700">الرمز<input aria-label="تعديل رمز الفصل" required value={value.code} onChange={(event) => setValue({ ...value, code: event.target.value })} className={inputClass} /></label></div>{error && <div className="mt-4"><ErrorState error={error} /></div>}<div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4"><Button variant="secondary" onClick={onClose} disabled={pending}>إلغاء</Button><Button type="submit" disabled={pending}><Pencil aria-hidden size={16} />{pending ? "جارٍ الحفظ..." : "حفظ التعديلات"}</Button></div></form></Modal>;
}
function ConfirmationModal({ confirmation, pending, error, sectionCount, onClose, onConfirm }: { confirmation: NonNullable<Confirmation>; pending: boolean; error: Error | null; sectionCount: number; onClose: () => void; onConfirm: () => void }) {
  const isDelete = confirmation.kind.endsWith("delete"); const isGrade = confirmation.kind.startsWith("grade"); const active = confirmation.item.is_active; const label = isGrade ? "الصف" : "الفصل";
  const gradeActive = isGrade || ("grade" in confirmation.item && confirmation.item.grade.is_active);
  return <Modal title={isDelete ? `حذف ${label} «${confirmation.item.name}» نهائيًا` : `${active ? "إيقاف" : "إعادة تفعيل"} ${label} «${confirmation.item.name}»`} description={isDelete ? "الحذف النهائي متاح للعناصر غير المستخدمة فقط." : "يمكن تغيير الحالة لاحقًا دون فقد السجلات."} onClose={onClose}><div className={`rounded-2xl border p-4 text-sm leading-6 ${isDelete ? "border-red-200 bg-red-50 text-red-900" : active ? "border-amber-200 bg-amber-50 text-amber-900" : "border-emerald-200 bg-emerald-50 text-emerald-900"}`}><p className="font-black">{isDelete ? "تحقق من عدم استخدام هذا العنصر قبل الحذف." : active ? `لن يظهر ${label} في خيارات التشغيل الجديدة.` : `سيعود ${label} إلى خيارات التشغيل.`}</p><p className="mt-1">{isDelete ? "إذا وُجد طلاب أو حضور مرتبط فسيمنع النظام الحذف ويوجهك إلى الإيقاف." : isGrade && active ? `سيتم أيضًا إيقاف ${sectionCount} فصل تابع. إعادة تفعيل الصف لاحقًا لا تفعّل فصوله تلقائيًا.` : !gradeActive ? "يجب تفعيل الصف التابع أولًا." : "ستبقى جميع البيانات والسجلات التاريخية محفوظة."}</p></div>{error && <div className="mt-4"><ErrorState error={error} /></div>}<div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4"><Button variant="secondary" onClick={onClose} disabled={pending}>تراجع</Button><Button variant={isDelete || active ? "danger" : "primary"} onClick={onConfirm} disabled={pending || (!active && !gradeActive)}>{isDelete ? <Trash2 aria-hidden size={16} /> : active ? <Power aria-hidden size={16} /> : <CheckCircle2 aria-hidden size={16} />}{pending ? "جارٍ التنفيذ..." : isDelete ? "تأكيد الحذف" : active ? "تأكيد الإيقاف" : "إعادة التفعيل"}</Button></div></Modal>;
}
