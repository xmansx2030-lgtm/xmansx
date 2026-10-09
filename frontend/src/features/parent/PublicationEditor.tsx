import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { adaptivePollingInterval, POLLING } from "@/app/polling";
import { Alert } from "@/components/Alert";
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
  getStaffPublications,
  publishFamilyContent,
  revokeFamilyPublication,
} from "@/features/parent/api";
import { dateTime, fieldGrid, surface } from "@/features/parent/shared";

const familyPollInterval = adaptivePollingInterval(POLLING.counselorDashboard);
interface CaseFamilyContext {
  id: number;
  student_id: number;
  student_name: string;
}

export function PublicationEditor({
  counselorOnly,
  caseContext,
  canPublish = true,
}: {
  counselorOnly: boolean;
  caseContext?: CaseFamilyContext;
  canPublish?: boolean;
}) {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const key = schoolScopedKey(schoolId, "parents", "publications");
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [student, setStudent] = useState("");
  const [caseId, setCaseId] = useState("");
  const [document, setDocument] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [required, setRequired] = useState("");
  const [due, setDue] = useState("");
  const [error, setError] = useState("");
  const [revokeId, setRevokeId] = useState<number | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const publications = useQuery({
    queryKey: [...key, caseContext?.id ?? null, page],
    queryFn: ({ signal }) =>
      getStaffPublications(signal, page, caseContext?.id),
    enabled: schoolId > 0,
    refetchInterval: familyPollInterval,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
  });
  const refreshFamily = () => {
    void queryClient.invalidateQueries({ queryKey: key });
    for (const part of [
      "case",
      "case-timeline",
      "counselor-dashboard",
      "counselor-cases",
      "counselor-family-cases",
    ]) {
      void queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, part),
      });
    }
  };
  const publish = useMutation({
    mutationFn: () =>
      publishFamilyContent({
        student_id: caseContext?.student_id ?? Number(student),
        title: title.trim(),
        body: body.trim(),
        required_action: required.trim(),
        ...(caseContext
          ? { case_id: caseContext.id }
          : caseId
            ? { case_id: Number(caseId) }
            : {}),
        ...(!counselorOnly && document
          ? { document_id: Number(document) }
          : {}),
        ...(due ? { due_at: `${due}T23:59:00+03:00` } : {}),
      }),
    onSuccess: () => {
      setTitle("");
      setBody("");
      setRequired("");
      refreshFamily();
    },
  });
  const revoke = useMutation({
    mutationFn: () =>
      revokeFamilyPublication(revokeId ?? 0, revokeReason.trim()),
    onSuccess: () => {
      setRevokeId(null);
      refreshFamily();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (
      (caseContext?.student_id ?? Number(student)) < 1 ||
      !title.trim() ||
      !body.trim() ||
      (counselorOnly && !caseContext && Number(caseId) < 1)
    ) {
      setError(
        "حدد الطالب واكتب المحتوى المصرح للأسرة، وحدد حالتك المسندة عند النشر بصفة المرشد.",
      );
      return;
    }
    publish.mutate();
  }
  return (
    <div className="space-y-4">
      {canPublish && (
        <section className={surface}>
          <h2 className="text-lg font-black">نشر محتوى محدد للأسرة</h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            اكتب ملخصاً مصرحاً بمشاركته. راجع النص دون نسخ الملاحظات الداخلية أو
            بيانات طلاب آخرين.
          </p>
          {caseContext && (
            <p className="mt-3 rounded-xl bg-teal-50 p-3 font-bold text-teal-900">
              الأسرة المستهدفة: {caseContext.student_name}
            </p>
          )}
          <form className="mt-5 space-y-4" onSubmit={submit} noValidate>
            {!caseContext && (
              <div className={fieldGrid}>
                <TextField
                  label="رقم سجل الطالب للنشر"
                  type="number"
                  min="1"
                  required
                  value={student}
                  onChange={(event) => setStudent(event.target.value)}
                />
                <TextField
                  label="رقم الحالة الإرشادية المسندة"
                  type="number"
                  min="1"
                  required={counselorOnly}
                  value={caseId}
                  onChange={(event) => setCaseId(event.target.value)}
                />
              </div>
            )}
            <TextField
              label="عنوان الرسالة للأسرة"
              required
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={180}
            />
            <TextareaField
              label="المحتوى المصرح بنشره"
              required
              value={body}
              onChange={(event) => setBody(event.target.value)}
              maxLength={4000}
            />
            <TextareaField
              label="الإجراء المطلوب من الأسرة (اختياري)"
              value={required}
              onChange={(event) => setRequired(event.target.value)}
              maxLength={500}
            />
            <div className={fieldGrid}>
              <TextField
                label="موعد المتابعة المطلوب (اختياري)"
                type="date"
                value={due}
                onChange={(event) => setDue(event.target.value)}
              />
              {!counselorOnly && (
                <TextField
                  label="رقم المستند المصرح (اختياري)"
                  type="number"
                  min="1"
                  value={document}
                  onChange={(event) => setDocument(event.target.value)}
                />
              )}
            </div>
            {error && <Alert tone="danger" title={error} />}
            {publish.isError && <ErrorState error={publish.error} />}
            {publish.isSuccess && (
              <Alert tone="success" title="تم نشر المحتوى داخل بوابة الأسرة" />
            )}
            <Button type="submit" loading={publish.isPending}>
              نشر المحتوى للأسرة
            </Button>
          </form>
        </section>
      )}
      <section className={surface}>
        <h2 className="text-lg font-black">المحتوى الذي يمكنك إدارته</h2>
        {publications.isPending && <PageSkeleton />}
        {publications.isError && <ErrorState error={publications.error} />}
        {publications.data?.items.length === 0 && (
          <EmptyState
            title="لا توجد توصيات منشورة"
            description="تظهر هنا التوصيات المصرح بها وتفاعل الأسرة معها."
          />
        )}
        {publications.data?.items.map((item) => (
          <article
            key={item.id}
            className="mt-4 rounded-xl border border-slate-200 p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-bold">{item.title}</h3>
              {item.revoked_at && (
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold">
                  مسحوب
                </span>
              )}
            </div>
            {item.student_name && (
              <p className="mt-2 text-sm font-bold text-teal-800">
                {item.student_name}
              </p>
            )}
            {!caseContext && item.case_id && (
              <Link
                className="mt-2 inline-flex min-h-11 items-center text-sm font-bold text-teal-800"
                to={`/counselor/cases/${item.case_id}?tab=family`}
              >
                فتح متابعة الأسرة في الحالة
              </Link>
            )}
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7">
              {item.body}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              {dateTime(item.published_at)}
            </p>
            {item.required_action && (
              <div className="mt-3 rounded-xl border border-teal-100 bg-teal-50/50 p-3 text-sm">
                <p className="font-bold">
                  الإجراء المطلوب: {item.required_action}
                </p>
                {item.due_at && (
                  <p className="mt-1">موعد المتابعة: {dateTime(item.due_at)}</p>
                )}
                {!item.revoked_at && (
                  <>
                    <p className="mt-2 font-bold" role="status">
                      {(item.action_count ?? 0) === 0
                        ? "لا توجد أسرة نشطة مرتبطة تتلقى الإجراء"
                        : `تأكيدات تنفيذ الإجراء: ${item.completed_action_count ?? 0} من ${item.action_count}`}
                    </p>
                    {(item.completed_action_count ?? 0) <
                      (item.action_count ?? 0) && (
                      <p>
                        بانتظار تنفيذ الأسرة
                        {item.action_overdue ? " · تجاوز الموعد" : ""}
                      </p>
                    )}
                    {item.action_completed_at && (
                      <p className="mt-1 text-xs text-slate-600">
                        آخر تأكيد تنفيذ: {dateTime(item.action_completed_at)}
                      </p>
                    )}
                  </>
                )}
              </div>
            )}
            <details className="mt-3 rounded-xl bg-slate-50 p-3">
              <summary className="min-h-11 cursor-pointer text-sm font-bold">
                تأكيدات الاطلاع: {item.ack_count ?? 0}
              </summary>
              {!!item.acknowledgements?.length && (
                <ul className="mt-2 space-y-2 text-xs">
                  {item.acknowledgements.map((ack) => (
                    <li key={`${ack.relation_id}-${ack.acknowledged_at}`}>
                      {ack.parent_name} · {dateTime(ack.acknowledged_at)}
                    </li>
                  ))}
                </ul>
              )}
            </details>
            {!item.revoked_at && (
              <Button
                className="mt-3"
                variant="secondary"
                onClick={() => {
                  setRevokeId(item.id);
                  setRevokeReason("");
                }}
              >
                سحب المحتوى المنشور
              </Button>
            )}
          </article>
        ))}
        <Pagination
          page={page}
          onChange={setPage}
          hasNext={!!publications.data?.next}
          hasPrevious={!!publications.data?.previous}
        />
      </section>
      {revokeId && (
        <Modal title="سحب محتوى منشور" onClose={() => setRevokeId(null)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (revokeReason.trim()) revoke.mutate();
            }}
          >
            <TextareaField
              label="سبب سحب المحتوى"
              required
              value={revokeReason}
              onChange={(event) => setRevokeReason(event.target.value)}
            />
            {revoke.isError && <ErrorState error={revoke.error} />}
            <Button type="submit" variant="danger" loading={revoke.isPending}>
              سحب المحتوى
            </Button>
          </form>
        </Modal>
      )}
    </div>
  );
}
