import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartHandshake } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SelectField, TextareaField } from "@/components/FormField";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { toCanonicalMobile } from "@/features/auth/mobile";
import {
  blockRecipient,
  decideFamilyRequest,
  decideRegistration,
  decideRelation,
  getContactReviews,
  getGlobalMobileChanges,
  getRecipientBlocks,
  getRegistrationDetail,
  getRegistrations,
  getStaffRelations,
  getStaffRequests,
  getStaffPublications,
  getStaffAcknowledgements,
  publishFamilyContent,
  reissueActivation,
  requestGlobalMobileChange,
  resolveContactReview,
  resolveRecipientBlock,
  revokeFamilyPublication,
  staffAttachmentDownloadUrl,
  updateParentContact,
  type FamilyRequest,
  type RelationStatus,
  type StaffRelation,
} from "@/features/parent/api";
import {
  ActivationDeliveryHistory,
  ActivationDeliveryResult,
} from "@/features/parent/ActivationDelivery";
import { ParentSettingsTab } from "@/features/parent/ParentSettingsTab";
import {
  dateTime,
  fieldGrid,
  RELATION_LABELS,
  REQUEST_LABELS,
  surface,
} from "@/features/parent/shared";

type Tab =
  | "registrations"
  | "relations"
  | "requests"
  | "contacts"
  | "acknowledgements"
  | "publications"
  | "settings";
const tabLabels: Record<Tab, string> = {
  registrations: "طلبات التسجيل",
  relations: "العلاقات",
  requests: "طلبات الأسرة",
  contacts: "مراجعة التواصل",
  acknowledgements: "تأكيدات الاطلاع",
  publications: "المحتوى المنشور",
  settings: "التسجيل والإحصائيات",
};
export function ParentManagementPage() {
  const me = useMe();
  const administrator =
    me.data?.roles.some((role) =>
      ["SCHOOL_MANAGER", "VICE_PRINCIPAL"].includes(role),
    ) ?? false;
  const [selected, setSelected] = useState<Tab>("registrations");
  const tab = administrator ? selected : "publications";
  const available = administrator
    ? (Object.keys(tabLabels) as Tab[])
    : (["publications"] as Tab[]);
  return (
    <div className="ds-page">
      <PageHeader
        icon={HeartHandshake}
        eyebrow="إدارة المدرسة"
        title="إدارة أولياء الأمور"
        description={
          administrator
            ? "مراجعة العلاقات وطلبات الأسرة وبيانات التواصل، ضمن نطاق المدرسة الحالية."
            : "نشر توصيات محددة للأسرة من حالاتك المسندة بعد مراجعة المحتوى."
        }
      />
      <nav
        className="flex overflow-x-auto rounded-2xl border border-slate-200 bg-white p-2"
        aria-label="أقسام إدارة أولياء الأمور"
      >
        {available.map((item) => (
          <Button
            key={item}
            variant={tab === item ? "primary" : "ghost"}
            className="shrink-0"
            aria-pressed={tab === item}
            onClick={() => setSelected(item)}
          >
            {tabLabels[item]}
          </Button>
        ))}
      </nav>
      {tab === "registrations" && <Registrations />}
      {tab === "relations" && <Relations />}
      {tab === "requests" && <StaffRequests />}
      {tab === "contacts" && <Contacts />}
      {tab === "acknowledgements" && <Acknowledgements />}
      {tab === "publications" && (
        <PublicationEditor counselorOnly={!administrator} />
      )}
      {tab === "settings" && <ParentSettingsTab />}
    </div>
  );
}
function useStaffKey(part: string) {
  const me = useMe();
  return schoolScopedKey(me.data?.active_school?.id ?? 0, "parents", part);
}
function Acknowledgements() {
  const key = useStaffKey("acknowledgements");
  const [page, setPage] = useState(1);
  const records = useQuery({
    queryKey: [...key, page],
    queryFn: ({ signal }) => getStaffAcknowledgements(signal, page),
  });
  return (
    <section className={`${surface} space-y-4`}>
      <h2 className="text-lg font-black">تأكيدات اطلاع الأسرة</h2>
      <p className="text-sm leading-7 text-slate-600">
        تأكيد صريح للاطلاع على إنذار أو رسالة منشورة؛ لا يعني قبول محتوى الإنذار
        أو تنفيذ الإجراء المطلوب.
      </p>
      {records.isPending && <PageSkeleton />}
      {records.isError && <ErrorState error={records.error} />}
      {records.isSuccess &&
        (records.data.items.length ? (
          <div className="max-w-full overflow-x-auto">
            <table className="w-full min-w-[560px] text-right text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th scope="col" className="p-3">
                    الطالب
                  </th>
                  <th scope="col" className="p-3">
                    ولي الأمر
                  </th>
                  <th scope="col" className="p-3">
                    المحتوى
                  </th>
                  <th scope="col" className="p-3">
                    وقت التأكيد
                  </th>
                </tr>
              </thead>
              <tbody>
                {records.data.items.map((item) => (
                  <tr
                    key={`${item.type}-${item.id}`}
                    className="border-b border-slate-100"
                  >
                    <td className="p-3 font-bold">{item.student_name}</td>
                    <td className="p-3">{item.parent_name}</td>
                    <td className="p-3">
                      {item.type === "WARNING" ? "إنذار" : "رسالة المدرسة"} #
                      {item.target_id}
                    </td>
                    <td className="p-3">{dateTime(item.acknowledged_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="لا توجد تأكيدات اطلاع مسجلة"
            description="تظهر التأكيدات بعد إجراء ولي الأمر الصريح داخل بوابة الأسرة."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!records.data?.next}
        hasPrevious={!!records.data?.previous}
      />
    </section>
  );
}
function ActivationReissue() {
  const [id, setId] = useState("");
  const [proof, setProof] = useState("");
  const [delivery, setDelivery] = useState<"EMAIL" | "SMS" | "MANUAL">("EMAIL");
  const action = useMutation({
    mutationFn: () => reissueActivation(Number(id), delivery, proof.trim()),
  });
  return (
    <details className={surface}>
      <summary className="min-h-11 cursor-pointer font-bold">
        إعادة تسليم التفعيل لطلب معتمد
      </summary>
      <form
        className="mt-4 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (Number(id) > 0 && proof.trim()) action.mutate();
        }}
      >
        <TextField
          label="رقم طلب التسجيل المعتمد"
          type="number"
          min="1"
          required
          value={id}
          onChange={(event) => {
            setId(event.target.value);
            action.reset();
          }}
        />
        <SelectField
          label="طريقة إعادة تسليم التفعيل"
          value={delivery}
          onChange={(event) =>
            setDelivery(event.target.value as "EMAIL" | "SMS" | "MANUAL")
          }
                >
                  <option value="EMAIL">البريد الإلكتروني — التفعيل وتوثيق البريد</option>
                  <option value="SMS">SMS عبر تكامل المدرسة (مسار سابق)</option>
          <option value="MANUAL">تسليم موثق بعد التحقق الحضوري</option>
        </SelectField>
        <TextareaField
          label="توثيق التحقق الحديث من صاحب الصفة"
          required
          value={proof}
          onChange={(event) => setProof(event.target.value)}
          maxLength={600}
        />
        {action.isError && <ErrorState error={action.error} />}
        {action.isSuccess && (
          <>
            <Alert tone="success" title="تم إصدار تفعيل جديد" />
            <ActivationDeliveryResult status={action.data.delivery_status} />
            {action.data.activation_url && (
              <TextField
                label="رابط التفعيل الجديد (يظهر مرة واحدة)"
                dir="ltr"
                readOnly
                value={action.data.activation_url}
              />
            )}
          </>
        )}
        <Button type="submit" loading={action.isPending}>
          إصدار وتسليم تفعيل جديد
        </Button>
      </form>
    </details>
  );
}
function Registrations() {
  const key = useStaffKey("registrations");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [review, setReview] = useState<number | null>(null);
  const registrations = useQuery({
    queryKey: [...key, page, status],
    queryFn: ({ signal }) => getRegistrations(signal, page, status),
  });
  return (
    <>
      <div className={surface}>
        <SelectField
          label="حالة طلبات التسجيل"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">جميع الحالات</option>
          {Object.entries(REQUEST_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
      </div>
      <ActivationReissue />
      {registrations.isPending && <PageSkeleton />}
      {registrations.isError && <ErrorState error={registrations.error} />}
      {registrations.isSuccess &&
        (registrations.data.results.length ? (
          <div className="space-y-3">
            {registrations.data.results.map((item) => (
              <article className={surface} key={item.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-black">{item.name}</h2>
                    <p dir="ltr" className="mt-1 text-sm text-slate-500">
                      {item.mobile_masked ?? item.mobile}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {dateTime(item.created_at)}
                    </p>
                  </div>
                  <Badge tone="neutral">
                    {REQUEST_LABELS[item.status] ?? item.status}
                  </Badge>
                  <Button
                    variant="secondary"
                    onClick={() => setReview(item.id)}
                  >
                    مراجعة الطلب #{item.id}
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="لا توجد طلبات تسجيل"
            description="شارك رابط التسجيل بعد تفعيل استقبال الطلبات."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!registrations.data?.next}
        hasPrevious={!!registrations.data?.previous}
      />
      {review !== null && (
        <RegistrationReview id={review} onClose={() => setReview(null)} />
      )}
    </>
  );
}
function RegistrationReview({
  id,
  onClose,
}: {
  id: number;
  onClose: () => void;
}) {
  const key = useStaffKey("registrations");
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState("APPROVE");
  const [student, setStudent] = useState("");
  const [verification, setVerification] = useState("");
  const [reason, setReason] = useState("");
  const [bound, setBound] = useState(true);
  const [delivery, setDelivery] = useState<"EMAIL" | "SMS" | "MANUAL">("EMAIL");
  const [error, setError] = useState("");
  const detail = useQuery({
    queryKey: [...key, id],
    queryFn: ({ signal }) => getRegistrationDetail(id, signal),
    retry: false,
  });
  const action = useMutation({
    mutationFn: () =>
      decideRegistration(id, {
        decision,
        ...(student ? { student_id: Number(student) } : {}),
        verification_note: verification.trim(),
        decision_reason: reason.trim(),
        contact_bound: bound,
        delivery,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key }),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (decision === "APPROVE" && (!student || !verification.trim())) {
      setError("اختر الطالب المحدد وسجل التحقق من هوية مقدم الطلب وصفته.");
      return;
    }
    if (decision !== "APPROVE" && !reason.trim()) {
      setError("سجل سبب القرار.");
      return;
    }
    action.mutate();
  }
  return (
    <Modal title={`مراجعة طلب التسجيل #${id}`} onClose={onClose}>
      {detail.isPending && <PageSkeleton />}
      {detail.isError && <ErrorState error={detail.error} />}
      {detail.isSuccess && (
        <form onSubmit={submit} className="space-y-4">
          <p className="font-bold">{detail.data.request.name}</p>
          <p dir="ltr">{detail.data.request.mobile}</p>
          <p className="text-sm text-slate-500">
            {detail.data.student_match?.national_id_masked ??
              "راجع معرف الطالب مع مقدم الطلب"}
          </p>
          {detail.data.request.applicant_note && (
            <Alert title="استكمال مقدم الطلب">
              {detail.data.request.applicant_note}
            </Alert>
          )}
          <ActivationDeliveryHistory records={detail.data.activations ?? []} />
          <SelectField
            label="الطالب الذي تعتمد علاقته"
            value={student}
            onChange={(event) => setStudent(event.target.value)}
          >
            <option value="">اختر طالباً واحداً بصورة صريحة</option>
            {[detail.data.student_match, ...detail.data.sibling_candidates]
              .filter(
                (item, index, all) =>
                  item &&
                  all.findIndex((candidate) => candidate?.id === item.id) ===
                    index,
              )
              .map(
                (item) =>
                  item && (
                    <option value={item.id} key={item.id}>
                      {item.full_name} · {item.grade_name} · {item.section_name}
                    </option>
                  ),
              )}
          </SelectField>
          {!detail.data.student_match && (
            <Alert tone="warning" title="لا يوجد تطابق مؤكد">
              راجع معرف الطالب مع مقدم الطلب قبل الاعتماد.
            </Alert>
          )}
          {detail.data.existing_relations.length > 0 && (
            <Alert title="توجد علاقات سابقة">
              {detail.data.existing_relations.length} علاقة مسجلة؛ راجع عدم
              تعارض الصفة.
            </Alert>
          )}
          <SelectField
            label="قرار المدرسة"
            value={decision}
            onChange={(event) => setDecision(event.target.value)}
          >
            <option value="APPROVE">الموافقة</option>
            <option value="NEEDS_INFO">طلب استكمال</option>
            <option value="REJECT">الرفض</option>
          </SelectField>
          <TextareaField
            label="توثيق التحقق من الهوية والصفة"
            required={decision === "APPROVE"}
            value={verification}
            onChange={(event) => setVerification(event.target.value)}
            maxLength={600}
          />
          <TextareaField
            label="سبب القرار أو المطلوب استكماله"
            required={decision !== "APPROVE"}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={300}
          />
          {decision === "APPROVE" && (
            <>
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={bound}
                  onChange={(event) => setBound(event.target.checked)}
                />
                العلاقة تعتمد رقم التواصل المدرسي الحالي
              </label>
              <SelectField
                label="تسليم التفعيل"
                value={delivery}
                onChange={(event) =>
                  setDelivery(event.target.value as "EMAIL" | "SMS" | "MANUAL")
                }
              >
                <option value="EMAIL">البريد الإلكتروني — التفعيل وتوثيق البريد</option>
          <option value="SMS">SMS عبر تكامل المدرسة (مسار سابق)</option>
                <option value="MANUAL">تسليم موثق بعد التحقق الحضوري</option>
              </SelectField>
            </>
          )}
          {error && <Alert tone="danger" title={error} />}
          {action.isError && <ErrorState error={action.error} />}
          {action.isSuccess ? (
            <>
              <Alert tone="success" title="تم حفظ قرار المدرسة" live />
              <ActivationDeliveryResult status={action.data.delivery_status} />
              {action.data.activation_url && (
                <Alert tone="warning" title="رابط تفعيل شخصي يظهر مرة واحدة">
                  <TextField
                    label="رابط التفعيل"
                    value={action.data.activation_url}
                    readOnly
                    dir="ltr"
                  />
                  <p className="mt-2">
                    سلمه فقط لصاحب الصفة الذي جرى التحقق منه. الحساب الموجود
                    يتطلب دخوله بكلمة مروره.
                  </p>
                  <Button
                    className="mt-2"
                    variant="secondary"
                    onClick={() =>
                      void navigator.clipboard?.writeText(
                        action.data.activation_url ?? "",
                      )
                    }
                  >
                    نسخ رابط التفعيل
                  </Button>
                </Alert>
              )}
            </>
          ) : (
            <Button type="submit" fullWidth loading={action.isPending}>
              حفظ القرار
            </Button>
          )}
        </form>
      )}
    </Modal>
  );
}
function Relations() {
  const key = useStaffKey("relations");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<StaffRelation | null>(null);
  const relations = useQuery({
    queryKey: [...key, page, status],
    queryFn: ({ signal }) => getStaffRelations(signal, page, status),
  });
  return (
    <>
      <div className={surface}>
        <SelectField
          label="حالة العلاقات"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">جميع الحالات</option>
          {Object.entries(RELATION_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
      </div>
      {relations.isPending && <PageSkeleton />}
      {relations.isError && <ErrorState error={relations.error} />}
      {relations.isSuccess &&
        (relations.data.results.length ? (
          <div className="space-y-3">
            {relations.data.results.map((relation) => (
              <article key={relation.id} className={surface}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-black">{relation.student_name}</h2>
                    <p className="mt-1 text-sm text-slate-600">
                      {relation.parent_name ?? relation.user_name}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      إصدار الاعتماد: {relation.approval_revision}
                    </p>
                  </div>
                  <Badge
                    tone={relation.status === "ACTIVE" ? "success" : "warning"}
                  >
                    {RELATION_LABELS[relation.status]}
                  </Badge>
                  <Button
                    variant="secondary"
                    onClick={() => setSelected(relation)}
                  >
                    مراجعة العلاقة
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="لا توجد علاقات"
            description="تعتمد العلاقات بعد مراجعة طلبات التسجيل والتفعيل."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!relations.data?.next}
        hasPrevious={!!relations.data?.previous}
      />
      {selected && (
        <RelationDecision
          relation={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
function RelationDecision({
  relation,
  onClose,
}: {
  relation: StaffRelation;
  onClose: () => void;
}) {
  const key = useStaffKey("relations");
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<RelationStatus>(
    relation.status === "ACTIVE" ? "SUSPENDED_CONTACT_REVIEW" : "ACTIVE",
  );
  const [reason, setReason] = useState("");
  const [proof, setProof] = useState("");
  const action = useMutation({
    mutationFn: () =>
      decideRelation(relation.id, status, reason.trim(), proof.trim()),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key }),
  });
  return (
    <Modal title={`مراجعة علاقة ${relation.student_name}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (reason.trim() && (status !== "ACTIVE" || proof.trim()))
            action.mutate();
        }}
      >
        <SelectField
          label="حالة العلاقة الجديدة"
          value={status}
          onChange={(event) => setStatus(event.target.value as RelationStatus)}
        >
          <option value="ACTIVE">إعادة الاعتماد بعد التحقق</option>
          <option value="SUSPENDED_CONTACT_REVIEW">تعليق للمراجعة</option>
          <option value="REVOKED">سحب العلاقة</option>
        </SelectField>
        <TextareaField
          label="سبب القرار"
          required
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <TextareaField
          label="توثيق التحقق وإعادة الاعتماد"
          required={status === "ACTIVE"}
          value={proof}
          onChange={(event) => setProof(event.target.value)}
        />
        {action.isError && <ErrorState error={action.error} />}
        {action.isSuccess ? (
          <Alert tone="success" title="تم تحديث العلاقة" />
        ) : (
          <Button type="submit" loading={action.isPending}>
            حفظ قرار العلاقة
          </Button>
        )}
      </form>
    </Modal>
  );
}
function StaffRequests() {
  const key = useStaffKey("requests");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<FamilyRequest | null>(null);
  const requests = useQuery({
    queryKey: [...key, page],
    queryFn: ({ signal }) => getStaffRequests(signal, page),
  });
  const items = [
    ...(requests.data?.excuses ?? []),
    ...(requests.data?.corrections ?? []),
  ];
  return (
    <>
      {requests.isPending && <PageSkeleton />}
      {requests.isError && <ErrorState error={requests.error} />}
      {requests.isSuccess &&
        (items.length ? (
          <div className="space-y-3">
            {items.map((request) => (
              <article
                className={surface}
                key={`${request.type}-${request.id}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-black">
                    {request.type === "EXCUSE" ? "عذر" : "مراجعة حضور"} #
                    {request.id}{" "}
                    {request.student_name && `· ${request.student_name}`}
                  </h2>
                  <Badge tone="neutral">{REQUEST_LABELS[request.status]}</Badge>
                  <Button
                    variant="secondary"
                    onClick={() => setSelected(request)}
                  >
                    مراجعة طلب الأسرة
                  </Button>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7">
                  {request.type === "EXCUSE" ? request.notes : request.reason}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="لا توجد طلبات أسرة"
            description="ستظهر الأعذار وطلبات مراجعة الحضور المقدمة من أولياء الأمور."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!requests.data?.next}
        hasPrevious={!!requests.data?.previous}
      />
      {selected && (
        <FamilyDecision request={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
function FamilyDecision({
  request,
  onClose,
}: {
  request: FamilyRequest;
  onClose: () => void;
}) {
  const key = useStaffKey("requests");
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState("APPROVED");
  const [note, setNote] = useState("");
  const action = useMutation({
    mutationFn: () =>
      decideFamilyRequest(
        request.type,
        request.id,
        decision,
        note.trim(),
        request.type === "CORRECTION" ? request.session_updated_at : undefined,
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key }),
  });
  return (
    <Modal title={`قرار طلب الأسرة #${request.id}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (note.trim()) action.mutate();
        }}
      >
        <p className="whitespace-pre-wrap text-sm leading-7">
          {request.type === "EXCUSE" ? request.notes : request.reason}
        </p>
        {request.type === "EXCUSE" &&
          request.attachments.map((attachment) => (
            <a
              key={attachment.id}
              href={staffAttachmentDownloadUrl(request.id, attachment.id)}
              className="inline-flex min-h-11 items-center font-bold text-teal-800 underline"
            >
              {attachment.filename}
            </a>
          ))}
        <Alert
          title={
            request.type === "EXCUSE"
              ? "اعتماد العذر يطبق التغطية الإدارية"
              : "قبول التصحيح يستخدم خدمة الحضور الرسمية"
          }
        >
          {request.type === "EXCUSE"
            ? "يبقى الغياب الفعلي محفوظاً."
            : "يسجل النظام الموظف والسبب والتاريخ في سجل التغيير."}
        </Alert>
        <SelectField
          label="قرار الطلب"
          value={decision}
          onChange={(event) => setDecision(event.target.value)}
        >
          <option value="APPROVED">الموافقة</option>
          <option value="REJECTED">الرفض</option>
          {request.type === "EXCUSE" && (
            <option value="NEEDS_INFO">طلب استكمال</option>
          )}
        </SelectField>
        <TextareaField
          label="سبب القرار ورد المدرسة"
          required
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={600}
        />
        {action.isError && <ErrorState error={action.error} />}
        {action.isSuccess ? (
          <Alert tone="success" title="تم حفظ القرار" />
        ) : (
          <Button type="submit" loading={action.isPending}>
            حفظ قرار الطلب
          </Button>
        )}
      </form>
    </Modal>
  );
}
function Contacts() {
  const key = useStaffKey("contacts");
  const queryClient = useQueryClient();
  const [reviewPage, setReviewPage] = useState(1);
  const [blockPage, setBlockPage] = useState(1);
  const [changePage, setChangePage] = useState(1);
  const reviews = useQuery({
    queryKey: [...key, "reviews", reviewPage],
    queryFn: ({ signal }) => getContactReviews(signal, reviewPage),
  });
  const blocks = useQuery({
    queryKey: [...key, "blocks", blockPage],
    queryFn: ({ signal }) => getRecipientBlocks(signal, blockPage),
  });
  const changes = useQuery({
    queryKey: [...key, "mobile", changePage],
    queryFn: ({ signal }) => getGlobalMobileChanges(signal, changePage),
  });
  const [selected, setSelected] = useState<{
    kind: "REVIEW" | "BLOCK";
    id: number;
  } | null>(null);
  const [reason, setReason] = useState("");
  const [proof, setProof] = useState("");
  const [verified, setVerified] = useState(false);
  const resolve = useMutation({
    mutationFn: () =>
      selected?.kind === "REVIEW"
        ? resolveContactReview(selected.id, reason.trim(), proof.trim())
        : resolveRecipientBlock(selected?.id ?? 0, reason.trim(), proof.trim()),
    onSuccess: () => {
      setSelected(null);
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
  return (
    <div className="space-y-4">
      <Alert title="مراجعة التواصل مستقلة عن اعتماد العلاقة">
        إنهاء المراجعة لا يعيد صلاحية متابعة الطالب تلقائياً. أعد اعتماد العلاقة
        بعد التحقق من صفة صاحب الحساب.
      </Alert>
      <section className={surface}>
        <h2 className="text-lg font-black">تغييرات نور والتعديلات اليدوية</h2>
        {reviews.isPending && <PageSkeleton />}
        {reviews.isError && <ErrorState error={reviews.error} />}
        {reviews.isSuccess &&
          (reviews.data.results.length ? (
            <ul className="mt-4 space-y-3">
              {reviews.data.results.map((review) => (
                <li
                  key={review.id}
                  className="rounded-xl border border-slate-200 p-4"
                >
                  <h3 className="font-bold">{review.student_name}</h3>
                  <p className="mt-2 text-sm">
                    إصدار التواصل: {review.previous_revision} ←{" "}
                    {review.current_revision}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">{review.reason}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    {dateTime(review.created_at)} · {review.actor_name}
                  </p>
                  {!review.resolved_at && (
                    <Button
                      className="mt-3"
                      variant="secondary"
                      onClick={() => {
                        setSelected({ kind: "REVIEW", id: review.id });
                        setReason("");
                        setProof("");
                        setVerified(false);
                      }}
                    >
                      إنهاء المراجعة بعد التحقق
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              لا توجد تغييرات تحتاج مراجعة.
            </p>
          ))}
        <Pagination
          page={reviewPage}
          onChange={setReviewPage}
          hasNext={!!reviews.data?.next}
          hasPrevious={!!reviews.data?.previous}
        />
      </section>
      <ContactEditor
        onSaved={() => void queryClient.invalidateQueries({ queryKey: key })}
      />
      <section className={surface}>
        <h2 className="text-lg font-black">
          الأرقام المحظورة لتعارض موثوقية المستلم
        </h2>
        {blocks.isError && <ErrorState error={blocks.error} />}
        {blocks.data?.results.map((block) => (
          <article
            className="mt-3 rounded-xl border border-slate-200 p-4"
            key={block.id}
          >
            <p className="font-bold">
              {block.student_name ?? `الطالب #${block.student_id}`}
            </p>
            <p dir="ltr" className="mt-1 text-sm">
              {block.mobile_masked}
            </p>
            <p className="mt-1 text-sm text-slate-600">{block.reason}</p>
            {!block.resolved_at && (
              <Button
                className="mt-3"
                variant="secondary"
                onClick={() => {
                  setSelected({ kind: "BLOCK", id: block.id });
                  setReason("");
                  setProof("");
                  setVerified(false);
                }}
              >
                إنهاء تعارض الرقم
              </Button>
            )}
          </article>
        ))}
        <Pagination
          page={blockPage}
          onChange={setBlockPage}
          hasNext={!!blocks.data?.next}
          hasPrevious={!!blocks.data?.previous}
        />
      </section>
      <section className={surface}>
        <h2 className="text-lg font-black">طلبات تغيير جوال الدخول العالمي</h2>
        <p className="mt-2 text-sm leading-7 text-slate-600">
          هذه طلبات مراجعة موثقة؛ لا تغير رقم الحساب العالمي آلياً.
        </p>
        {changes.isError && <ErrorState error={changes.error} />}
        {changes.data?.results.map((change) => (
          <article
            key={change.id}
            className="mt-3 rounded-xl border border-slate-200 p-4"
          >
            <p className="font-bold">طلب #{change.id} · قيد المراجعة</p>
            <p dir="ltr" className="mt-1">
              {change.new_mobile_masked}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {dateTime(change.created_at)}
            </p>
          </article>
        ))}
        <Pagination
          page={changePage}
          onChange={setChangePage}
          hasNext={!!changes.data?.next}
          hasPrevious={!!changes.data?.previous}
        />
      </section>
      {selected && (
        <Modal title="إغلاق مراجعة التواصل" onClose={() => setSelected(null)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (verified && reason.trim() && proof.trim()) resolve.mutate();
            }}
          >
            <TextareaField
              label="سبب إغلاق المراجعة"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required
            />
            <TextareaField
              label="توثيق التحقق من الهوية والصفة"
              value={proof}
              onChange={(event) => setProof(event.target.value)}
              required
            />
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={verified}
                onChange={(event) => setVerified(event.target.checked)}
                required
              />
              تحققت من صاحب الصفة والرقم المتأثر
            </label>
            {resolve.isError && <ErrorState error={resolve.error} />}
            <Button
              type="submit"
              loading={resolve.isPending}
              disabled={!verified}
            >
              حفظ إنهاء المراجعة
            </Button>
          </form>
        </Modal>
      )}
    </div>
  );
}
function ContactEditor({ onSaved }: { onSaved: () => void }) {
  const [kind, setKind] = useState("CONTACT");
  const [student, setStudent] = useState("");
  const [relation, setRelation] = useState("");
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [reason, setReason] = useState("");
  const [proof, setProof] = useState("");
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState("");
  const action = useMutation({
    mutationFn: () =>
      kind === "CONTACT"
        ? updateParentContact(
            Number(student),
            mobile.trim() ? (toCanonicalMobile(mobile) ?? "") : "",
            name.trim(),
            reason.trim(),
            proof.trim(),
          )
        : kind === "BLOCK"
          ? blockRecipient(
              Number(student),
              toCanonicalMobile(mobile) ?? "",
              reason.trim(),
              proof.trim(),
            )
          : requestGlobalMobileChange(
              Number(student),
              Number(relation),
              toCanonicalMobile(mobile) ?? "",
              reason.trim(),
              proof.trim(),
            ),
    onSuccess: onSaved,
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (
      Number(student) < 1 ||
      !reason.trim() ||
      !proof.trim() ||
      !verified ||
      (mobile.trim() && !toCanonicalMobile(mobile)) ||
      (kind !== "CONTACT" && !mobile.trim()) ||
      (kind === "GLOBAL" && Number(relation) < 1)
    ) {
      setError("أكمل الطالب والجوال الصحيح وسبب الإجراء وتوثيق التحقق.");
      return;
    }
    action.mutate();
  }
  return (
    <details className={surface}>
      <summary className="min-h-11 cursor-pointer font-black">
        تحديث التواصل أو تسجيل إجراء موثق
      </summary>
      <form className="mt-4 space-y-4" onSubmit={submit} noValidate>
        <SelectField
          label="نوع إجراء التواصل"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value);
            action.reset();
          }}
        >
          <option value="CONTACT">تحديث رقم التواصل المدرسي</option>
          <option value="BLOCK">حظر رقم ثبت تعارض موثوقيته لهذا الطالب</option>
          <option value="GLOBAL">طلب مراجعة تغيير جوال الدخول العالمي</option>
        </SelectField>
        <div className={fieldGrid}>
          <TextField
            label="رقم سجل الطالب"
            type="number"
            min="1"
            required
            value={student}
            onChange={(event) => setStudent(event.target.value)}
          />
          {kind === "GLOBAL" && (
            <TextField
              label="رقم علاقة الحساب بالطالب"
              type="number"
              min="1"
              required
              value={relation}
              onChange={(event) => setRelation(event.target.value)}
            />
          )}
          {kind === "CONTACT" && (
            <TextField
              label="اسم ولي الأمر في سجل التواصل"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          )}
        </div>
        <TextField
          label={
            kind === "GLOBAL" ? "جوال الدخول الجديد المطلوب" : "رقم التواصل"
          }
          type="tel"
          dir="ltr"
          required={kind !== "CONTACT"}
          description={
            kind === "CONTACT"
              ? "ترك الرقم فارغاً يعني طلب مسح رقم التواصل الحالي صراحة."
              : undefined
          }
          value={mobile}
          onChange={(event) => setMobile(event.target.value)}
        />
        <TextareaField
          label="سبب إجراء التواصل"
          required
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <TextareaField
          label="توثيق التحقق"
          required
          value={proof}
          onChange={(event) => setProof(event.target.value)}
        />
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={verified}
            onChange={(event) => setVerified(event.target.checked)}
          />
          تحققت من الهوية والصفة حضوريّاً وفق إجراء المدرسة
        </label>
        {error && <Alert tone="danger" title={error} />}
        {action.isError && <ErrorState error={action.error} />}
        {action.isSuccess && (
          <Alert
            tone="success"
            title={
              kind === "GLOBAL"
                ? "تم حفظ طلب المراجعة دون تغيير الحساب"
                : "تم حفظ الإجراء"
            }
          />
        )}
        <Button type="submit" loading={action.isPending}>
          حفظ إجراء التواصل
        </Button>
      </form>
    </details>
  );
}
function PublicationEditor({ counselorOnly }: { counselorOnly: boolean }) {
  const key = useStaffKey("publications");
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
    queryKey: [...key, page],
    queryFn: ({ signal }) => getStaffPublications(signal, page),
  });
  const publish = useMutation({
    mutationFn: () =>
      publishFamilyContent({
        student_id: Number(student),
        title: title.trim(),
        body: body.trim(),
        required_action: required.trim(),
        ...(caseId ? { case_id: Number(caseId) } : {}),
        ...(document ? { document_id: Number(document) } : {}),
        ...(due ? { due_at: `${due}T23:59:00+03:00` } : {}),
      }),
    onSuccess: () => {
      setTitle("");
      setBody("");
      setRequired("");
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
  const revoke = useMutation({
    mutationFn: () =>
      revokeFamilyPublication(revokeId ?? 0, revokeReason.trim()),
    onSuccess: () => {
      setRevokeId(null);
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (
      Number(student) < 1 ||
      !title.trim() ||
      !body.trim() ||
      (counselorOnly && Number(caseId) < 1)
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
      <section className={surface}>
        <h2 className="text-lg font-black">نشر محتوى محدد للأسرة</h2>
        <p className="mt-2 text-sm leading-7 text-slate-600">
          اكتب ملخصاً مصرحاً بمشاركته. راجع النص دون نسخ الملاحظات الداخلية أو
          بيانات طلاب آخرين.
        </p>
        <form className="mt-5 space-y-4" onSubmit={submit} noValidate>
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
            <TextField
              label="رقم المستند المصرح (اختياري)"
              type="number"
              min="1"
              value={document}
              onChange={(event) => setDocument(event.target.value)}
            />
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
      <section className={surface}>
        <h2 className="text-lg font-black">المحتوى الذي يمكنك إدارته</h2>
        {publications.isPending && <PageSkeleton />}
        {publications.isError && <ErrorState error={publications.error} />}
        {publications.data?.items.map((item) => (
          <article
            key={item.id}
            className="mt-4 rounded-xl border border-slate-200 p-4"
          >
            <h3 className="font-bold">{item.title}</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7">
              {item.body}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              {dateTime(item.published_at)}
            </p>
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
