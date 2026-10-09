import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, MailCheck, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { TextareaField } from "@/components/FormField";
import { Modal } from "@/components/Modal";
import { Pagination } from "@/components/Pagination";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  getSchoolFamilies, sendFamilyInvitations, type FamilyInvitation, type SchoolFamily,
} from "@/features/parent/familyInvitations";
import { dateTime, surface } from "@/features/parent/shared";

export function FamilyInvitationBadge({ invitation }: { invitation: FamilyInvitation | null }) {
  if (!invitation) return <Badge tone="neutral">لم تُرسل دعوة</Badge>;
  if (invitation.lifecycle === "ACTIVATED") return <Badge tone="success"><CheckCircle2 size={14} aria-hidden />تم تفعيل الربط</Badge>;
  if (invitation.lifecycle === "NEEDS_REVIEW") return <Badge tone="danger">تغيرت البيانات — تحتاج مراجعة</Badge>;
  if (invitation.lifecycle === "EXPIRED") return <Badge tone="warning">انتهت الدعوة</Badge>;
  if (invitation.lifecycle === "REVOKED") return <Badge tone="neutral">دعوة ملغاة</Badge>;
  const state = invitation.delivery_status;
  if (state === "SENT") return <Badge tone="info"><MailCheck size={14} aria-hidden />دعوة مقبولة لدى مزود SMS</Badge>;
  if (state === "FAILED") return <Badge tone="danger">فشل إرسال الدعوة</Badge>;
  if (state === "UNKNOWN") return <Badge tone="warning">نتيجة الإرسال غير مؤكدة</Badge>;
  return <Badge tone="warning">{state === "SENDING" ? "جارٍ إرسال الدعوة" : "بانتظار الإرسال"}</Badge>;
}

interface ReviewedFamily { family: SchoolFamily; name: string; childIds: number[] }

export function FamilyInvitationsTab() {
  const me = useMe();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [review, setReview] = useState<ReviewedFamily[] | null>(null);
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(0);
  const key = schoolScopedKey(me.data?.active_school?.id ?? 0, "parents", "families");
  const families = useQuery({
    queryKey: [...key, page], queryFn: ({ signal }) => getSchoolFamilies(page, signal),
    refetchInterval: (query) => review || query.state.error ? false : 30_000,
    retry: false,
  });
  const send = useMutation({
    mutationFn: () => sendFamilyInvitations((review ?? []).map(({ family, name, childIds }) => ({
      mobile: family.mobile, name: name.trim(), relationship_type: "ولي أمر",
      verification_note: note.trim(), reissue: !!family.invitation,
      children: family.children.filter((child) => childIds.includes(child.id)).map(({ id, revision }) => ({ id, revision })),
    }))),
    onSuccess: async (result) => {
      setSubmitted(result.invitations.length);
      setReview(null); setSelected([]);
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: schoolScopedKey(me.data?.active_school?.id ?? 0, "parents", "registrations") });
    },
  });
  const ready = families.data?.sms_enabled && families.data.sms_configured;
  function open(rows: SchoolFamily[]) {
    setReview(rows.map((family) => ({ family, name: family.names.length === 1 ? family.name : "", childIds: family.children.map((child) => child.id) })));
    setNote(""); setConfirmed(false); setError(""); send.reset();
  }
  function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (!confirmed || note.trim().length < 10 || !review?.length || review.some((item) => item.name.trim().length < 3 || !item.childIds.length)) {
      setError("أكمل الاسم، واختر أبناء كل أسرة، ووثّق التحقق ثم أكد الاعتماد."); return;
    }
    send.mutate();
  }
  return <section className="space-y-5" aria-label="الأسر والدعوات">
    <div className={surface}>
      <h2 className="flex items-center gap-2 text-lg font-black"><Users aria-hidden size={20} />الأسر المستخرجة من بيانات الطلاب</h2>
      <p className="mt-2 text-sm leading-7 text-slate-600">يجمع النظام الأبناء بحسب رقم التواصل المدرسي. راجع صفة ولي الأمر والأبناء قبل الاعتماد؛ ترسل دعوة واحدة لكل أسرة، ولا يمنح التجميع وحده صلاحية متابعة.</p>
    </div>
    {families.isPending && <PageSkeleton label="جارٍ استخراج الأسر" />}
    {families.isError && <ErrorState error={families.error} />}
    {families.data && !families.isError && <>
      {!ready && <Alert tone="warning" title="إرسال الدعوات غير متاح حالياً">يلزم تفعيل خدمة الدعوات وتهيئة مزود SMS للمدرسة قبل الإرسال.</Alert>}
      {submitted > 0 && <Alert title="تم حفظ اعتماد الدعوات">راجع حالة الإرسال في كل بطاقة؛ قبول المزود لا يثبت وصول SMS أو توثيق البريد.</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-bold">{families.data.count} أسرة مقترحة</p>
        <Button disabled={!ready || !selected.length} onClick={() => open(families.data!.results.filter((row) => selected.includes(row.key)))}>مراجعة وإرسال للمحدد ({selected.length})</Button>
      </div>
      {!families.data.results.length && <EmptyState title="لا توجد أسر مقترحة" description="تظهر الأسر عند وجود طلاب نشطين وبيانات تواصل مدرسية." />}
      <div className="grid gap-4 xl:grid-cols-2">
        {families.data.results.map((family) => {
          const activated = family.invitation?.lifecycle === "ACTIVATED" && !family.invitation.partial;
          const eligible = !!family.mobile && !activated && family.child_count <= 50;
          const invited = !!family.invitation;
          return <article key={family.key} className={`${surface} min-w-0 ${invited ? "border-s-4 border-s-blue-400" : ""}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0"><h3 className="break-words font-black">{family.name}</h3><p className="mt-1 text-sm text-slate-600" dir="ltr">{family.mobile_masked}</p></div>
              <FamilyInvitationBadge invitation={family.invitation} />
            </div>
            {family.needs_review && <p className="mt-3 text-sm font-bold text-amber-800">راجع اختلاف الأسماء أو نقص بيانات التواصل قبل الدعوة.</p>}
            <p className="mt-3 text-sm font-bold">الأبناء المقترحون ({family.child_count})</p>
            <ul className="mt-2 flex flex-wrap gap-2">{family.children.map((child) => <li key={child.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">{child.name}</li>)}</ul>
            {family.invitation && <div className="mt-3 space-y-1 text-xs leading-6 text-slate-600">
              <p>الدعوة باسم: {family.invitation.name} — أُصدرت: {dateTime(family.invitation.created_at)}</p>
              <p>تشمل {family.invitation.student_ids.length} من الأبناء. {family.invitation.consumed_at ? `التفعيل: ${dateTime(family.invitation.consumed_at)}` : `تنتهي: ${dateTime(family.invitation.expires_at)}`}</p>
              {family.invitation.partial && <p className="font-bold text-amber-800">الدعوة السابقة لا تشمل كل الأبناء الحاليين؛ راجع الإضافات قبل إصدار دعوة أخرى.</p>}
            </div>}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!ready || !eligible || (!selected.includes(family.key) && selected.length >= 20)} checked={selected.includes(family.key)} onChange={(event) => setSelected((old) => event.target.checked ? [...old, family.key] : old.filter((key) => key !== family.key))} />اختيار {family.name}</label>
              <Button variant="secondary" disabled={!ready || !eligible} aria-label={`${activated ? "الربط مكتمل" : invited ? "مراجعة وإعادة دعوة" : "اعتماد وإرسال دعوة"} ${family.name}`} onClick={() => open([family])}>{activated ? "الربط مكتمل" : invited ? "مراجعة وإعادة إصدار" : "اعتماد وإرسال دعوة"}</Button>
            </div>
          </article>;
        })}
      </div>
      <Pagination page={page} hasNext={!!families.data.next} hasPrevious={!!families.data.previous} onChange={(value) => { setPage(value); setSelected([]); }} />
    </>}
    {review && !families.isError && <Modal title="مراجعة الأسرة واعتماد الدعوة" onClose={() => { if (!send.isPending) setReview(null); }}>
      <form onSubmit={submit} className="space-y-5">
        <Alert title="دعوة واحدة لكل أسرة">اختر الأبناء الذين أثبتت صفة ولي الأمر تجاههم. لا يُطلب من ولي الأمر إدخال معرفات الطلاب.</Alert>
        {review?.map((item, index) => <fieldset key={item.family.key} className="min-w-0 space-y-3 rounded-xl border border-slate-200 p-4">
          <legend className="px-2 text-sm font-bold" dir="ltr">{item.family.mobile_masked}</legend>
          <TextField label="اسم ولي الأمر المعتمد" value={item.name} required maxLength={150} onChange={(event) => setReview((old) => old!.map((row, i) => i === index ? { ...row, name: event.target.value } : row))} />
          {item.family.children.map((child) => <label key={child.id} className="flex items-start gap-2 text-sm leading-6"><input className="mt-1" type="checkbox" checked={item.childIds.includes(child.id)} onChange={(event) => setReview((old) => old!.map((row, i) => i === index ? { ...row, childIds: event.target.checked ? [...row.childIds, child.id] : row.childIds.filter((id) => id !== child.id) } : row))} />{child.name}</label>)}
          {item.family.invitation && <Alert tone="warning" title="إعادة إصدار بعد المراجعة">يُلغى الرابط السابق وتُرسل رسالة جديدة. إذا كانت نتيجة الإرسال غير مؤكدة، فقد تكون الرسالة السابقة وصلت؛ تحقق قبل المتابعة.</Alert>}
        </fieldset>)}
        <TextareaField label="توثيق التحقق من صفة ولي الأمر والرقم والأبناء" value={note} required minLength={10} maxLength={600} onChange={(event) => setNote(event.target.value)} />
        <label className="flex items-start gap-2 text-sm leading-7"><input className="mt-2" type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />أؤكد أنني تحققت من صفة ولي الأمر ورقم التواصل واعتمدت الأبناء المحددين لكل أسرة.</label>
        {error && <Alert tone="danger" title="أكمل مراجعة الدعوة">{error}</Alert>}
        {send.isError && <ErrorState error={send.error} />}
        <Button type="submit" loading={send.isPending} disabled={send.isPending || !confirmed}>اعتماد وإرسال {review?.length ?? 0} دعوة</Button>
      </form>
    </Modal>}
  </section>;
}
