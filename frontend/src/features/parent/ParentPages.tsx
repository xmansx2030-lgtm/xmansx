import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, GraduationCap, HeartHandshake, UserRound } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { TextareaField } from "@/components/FormField";
import { PasswordInput } from "@/components/PasswordInput";
import { Pagination } from "@/components/Pagination";
import { adaptivePollingInterval } from "@/app/polling";
import { useMe } from "@/features/auth/useMe";
import { safeReturnTo } from "@/features/auth/returnTo";
import {
  attachmentDownloadUrl,
  cancelExcuseRequest,
  changeParentPassword,
  getChildren,
  getNotifications,
  getRequests,
  notificationComplete,
  notificationRead,
  parentKey,
  resubmitExcuseRequest,
  uploadRequestAttachment,
  type FamilyRequest,
} from "@/features/parent/api";
import {
  dateTime,
  DayBadge,
  RELATION_LABELS,
  REQUEST_LABELS,
  surface,
} from "@/features/parent/shared";

export function ParentHomePage() {
  return <ChildrenCards attendance={false} />;
}
export function ParentAttendancePage() {
  return <ChildrenCards attendance />;
}
function ChildrenCards({ attendance }: { attendance: boolean }) {
  const me = useMe();
  const [page, setPage] = useState(1);
  const children = useQuery({
    queryKey: parentKey(me.data?.id, "children", page),
    queryFn: ({ signal }) => getChildren(signal, page),
    enabled: me.isSuccess,
    refetchInterval: adaptivePollingInterval(30_000),
    refetchIntervalInBackground: false,
  });
  return (
    <div className="ds-page">
      <PageHeader
        icon={HeartHandshake}
        eyebrow="متابعة الأسرة"
        title={attendance ? "المواظبة" : "أبنائي"}
        description={
          attendance
            ? "اختر الابن لعرض سجل المواظبة والحضور الصباحي عبر الفترات المسجلة."
            : "حالة اليوم والإجراءات المطلوبة لكل ابن، عبر المدارس المرتبطة بحسابك."
        }
        actions={
          <Link
            to="/parent/account"
            className="inline-flex min-h-11 items-center rounded-xl bg-white px-4 text-sm font-bold text-teal-900"
          >
            إضافة ابن
          </Link>
        }
      />
      {children.isPending && <PageSkeleton label="جارٍ تحميل الأبناء" />}
      {children.isError && <ErrorState error={children.error} />}
      {children.isSuccess &&
        (children.data.results.length === 0 ? (
          <EmptyState
            icon={GraduationCap}
            title="لا توجد علاقات معتمدة بعد"
            description="افتح رابط تسجيل أولياء الأمور الذي تزودك به المدرسة وقدم طلباً لكل ابن."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {children.data.results.map((child) => (
              <article
                key={child.relation_id}
                className={surface}
                data-testid={`parent-child-${child.relation_id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-teal-800">
                      {child.school.name}
                    </p>
                    <h2 className="mt-2 text-xl font-black">
                      {child.student?.full_name ?? "علاقة تحتاج مراجعة المدرسة"}
                    </h2>
                  </div>
                  <Badge
                    tone={child.status === "ACTIVE" ? "success" : "warning"}
                  >
                    {RELATION_LABELS[child.status]}
                  </Badge>
                </div>
                {child.status === "ACTIVE" && child.student ? (
                  <>
                    <p className="mt-2 text-sm text-slate-500">
                      {[
                        child.student.grade_name,
                        child.student.section_name
                          ? `الفصل ${child.student.section_name}`
                          : "",
                        child.student.department,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <div className="my-5">
                      <DayBadge day={child.today} />
                    </div>
                    <p className="text-xs text-slate-500">
                      آخر تحديث: {dateTime(child.today?.updated_at)}
                    </p>
                    <Link
                      to={`/parent/notifications?relation_id=${child.relation_id}`}
                      className="mt-4 grid min-h-11 grid-cols-2 gap-3 rounded-xl border border-teal-100 bg-teal-50/60 p-3 text-teal-900"
                      aria-label={`تنبيهات وإجراءات ${child.student.full_name}`}
                    >
                      <span className="text-xs">
                        تنبيهات جديدة{" "}
                        <strong className="mt-1 block text-xl">
                          {child.new_notifications ?? 0}
                        </strong>
                      </span>
                      <span className="text-xs">
                        إجراءات مطلوبة{" "}
                        <strong className="mt-1 block text-xl">
                          {child.required_actions ?? 0}
                        </strong>
                      </span>
                    </Link>
                    <Link
                      to={`/parent/children/${child.relation_id}${attendance ? "?tab=history" : ""}`}
                      className="mt-4 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-teal-700 px-4 font-bold text-white"
                    >
                      {attendance ? "عرض سجل المواظبة" : "متابعة المواظبة"}
                    </Link>
                  </>
                ) : (
                  <p className="mt-4 text-sm leading-7 text-slate-600">
                    تواصل مع المدرسة لمراجعة العلاقة. لا يمكن عرض بيانات الطالب
                    حتى اعتمادها.
                  </p>
                )}
              </article>
            ))}
          </div>
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!children.data?.next}
        hasPrevious={!!children.data?.previous}
      />
    </div>
  );
}

function RequestCard({ request }: { request: FamilyRequest }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const relation = request.relation_id;
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (attachment: File) =>
      uploadRequestAttachment(relation ?? 0, request.id, attachment),
    onSuccess: () => {
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "requests"),
      });
    },
  });
  const action = useMutation({
    mutationFn: (kind: "RESUBMIT" | "CANCEL") =>
      kind === "RESUBMIT"
        ? resubmitExcuseRequest(relation ?? 0, request.id, notes.trim())
        : cancelExcuseRequest(relation ?? 0, request.id),
    onSuccess: () => {
      setNotes("");
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "requests"),
      });
    },
  });
  return (
    <article className={surface}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-black">
          {request.type === "EXCUSE" ? "طلب عذر" : "طلب مراجعة الحضور"} #
          {request.id}
        </h2>
        <Badge
          tone={
            request.status === "APPROVED"
              ? "success"
              : request.status === "REJECTED"
                ? "danger"
                : "warning"
          }
        >
          {REQUEST_LABELS[request.status]}
        </Badge>
      </div>
      {request.student_name && (
        <p className="mt-2 font-bold text-slate-700">{request.student_name}</p>
      )}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-7">
        {request.type === "EXCUSE" ? request.notes : request.reason}
      </p>
      <p className="mt-2 text-xs text-slate-500">
        {request.type === "EXCUSE"
          ? request.targets
              .map(
                (target) =>
                  `${target.attendance_date}${target.period_sequence ? `، الحصة ${target.period_sequence}` : "، اليوم"}`,
              )
              .join(" · ")
          : `${request.attendance_date}، الحصة ${request.period_sequence}`}{" "}
        · {dateTime(request.created_at)}
      </p>
      {request.decision_note && (
        <Alert className="mt-4" title="رد المدرسة">
          {request.decision_note}
        </Alert>
      )}
      {request.type === "EXCUSE" &&
        relation &&
        request.attachments.length > 0 && (
          <ul className="mt-3 space-y-2">
            {request.attachments.map((attachment) => (
              <li key={attachment.id}>
                <a
                  className="inline-flex min-h-11 items-center font-bold text-teal-800 underline"
                  href={attachmentDownloadUrl(
                    relation,
                    request.id,
                    attachment.id,
                  )}
                >
                  {attachment.filename}
                </a>
              </li>
            ))}
          </ul>
        )}
      {request.type === "EXCUSE" &&
        relation &&
        ["PENDING", "NEEDS_INFO"].includes(request.status) && (
          <form
            className="mt-4 space-y-3 rounded-xl border border-slate-200 p-4"
            onSubmit={(event) => {
              event.preventDefault();
              setFileError("");
              if (!file) {
                setFileError("اختر مرفقاً لاستكمال طلب العذر.");
                return;
              }
              if (
                file.size > 5 * 1024 * 1024 ||
                !["application/pdf", "image/jpeg", "image/png"].includes(
                  file.type,
                )
              ) {
                setFileError(
                  "المرفق يجب أن يكون PDF أو صورة JPG/PNG وألا يتجاوز 5 ميجابايت.",
                );
                return;
              }
              upload.mutate(file);
            }}
          >
            <label className="block text-sm font-bold">
              {`استكمال مرفق العذر #${request.id}`}
              <input
                ref={fileInput}
                className="mt-2 block w-full min-w-0 text-sm"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  upload.reset();
                  setFileError("");
                }}
              />
            </label>
            <p className="text-xs text-slate-500">
              PDF أو JPG أو PNG، حتى 5 ميجابايت. يضاف المرفق إلى الطلب الحالي.
            </p>
            {fileError && <Alert tone="danger" title={fileError} />}
            {upload.isError && <ErrorState error={upload.error} />}
            {upload.isSuccess && (
              <Alert tone="success" title="تم استكمال مرفق العذر" />
            )}
            <Button
              type="submit"
              variant="secondary"
              loading={upload.isPending}
              disabled={action.isPending}
            >
              إضافة المرفق إلى الطلب
            </Button>
          </form>
        )}
      {request.type === "EXCUSE" &&
        relation &&
        request.status === "NEEDS_INFO" && (
          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (notes.trim()) action.mutate("RESUBMIT");
            }}
          >
            <TextareaField
              label="استكمال معلومات العذر"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              required
              maxLength={500}
            />
            <Button type="submit" loading={action.isPending}>
              إرسال الاستكمال
            </Button>
          </form>
        )}
      {request.type === "EXCUSE" &&
        relation &&
        ["PENDING", "NEEDS_INFO"].includes(request.status) && (
          <Button
            className="mt-3"
            variant="ghost"
            loading={action.isPending}
            onClick={() => action.mutate("CANCEL")}
          >
            إلغاء طلب العذر
          </Button>
        )}
      {action.isError && <ErrorState error={action.error} />}
    </article>
  );
}
export function ParentRequestsPage() {
  const me = useMe();
  const [page, setPage] = useState(1);
  const requests = useQuery({
    queryKey: parentKey(me.data?.id, "requests", page),
    queryFn: ({ signal }) => getRequests(signal, page),
    enabled: me.isSuccess,
  });
  return (
    <div className="ds-page">
      <PageHeader
        icon={HeartHandshake}
        eyebrow="متابعة الطلبات"
        title="طلباتي"
        description="أعذار الأسرة وطلبات مراجعة الحضور وقرارات المدرسة."
      />
      {requests.isPending && <PageSkeleton />}
      {requests.isError && <ErrorState error={requests.error} />}
      {requests.isSuccess &&
        (requests.data.items.length ? (
          requests.data.items.map((request) => (
            <RequestCard
              key={`${request.type}-${request.id}`}
              request={request}
            />
          ))
        ) : (
          <EmptyState
            title="لا توجد طلبات"
            description="يمكنك تقديم عذر أو طلب مراجعة حضور من ملف الابن."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!requests.data?.next}
        hasPrevious={!!requests.data?.previous}
      />
    </div>
  );
}
export function ParentNotificationsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [params] = useSearchParams();
  const requestedRelation = Number(params.get("relation_id"));
  const relation =
    Number.isSafeInteger(requestedRelation) && requestedRelation > 0
      ? requestedRelation
      : undefined;
  const notifications = useQuery({
    queryKey: parentKey(me.data?.id, "notifications", relation ?? null, page),
    queryFn: ({ signal }) => getNotifications(signal, page, relation),
    enabled: me.isSuccess,
    refetchInterval: adaptivePollingInterval(30_000),
    refetchIntervalInBackground: false,
  });
  const action = useMutation({
    mutationFn: ({ id, complete }: { id: number; complete: boolean }) =>
      complete ? notificationComplete(id) : notificationRead(id),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "notifications"),
      }),
  });
  return (
    <div className="ds-page">
      <PageHeader
        icon={Bell}
        eyebrow="متابعة الأسرة"
        title="التنبيهات"
        description="قراءة التنبيه منفصلة عن تنفيذ الإجراء وتأكيد الاطلاع على مستند رسمي."
        actions={
          relation ? (
            <Link
              to="/parent/notifications"
              onClick={() => setPage(1)}
              className="inline-flex min-h-11 items-center rounded-xl bg-white px-4 text-sm font-bold text-teal-900"
            >
              عرض جميع الأبناء
            </Link>
          ) : undefined
        }
      />
      {notifications.isPending && <PageSkeleton />}
      {notifications.isError && <ErrorState error={notifications.error} />}
      {action.isError && <ErrorState error={action.error} />}
      {notifications.isSuccess &&
        (notifications.data.items.length ? (
          notifications.data.items.map((item) => (
            <article key={item.id} className={surface}>
              {(item.student_name || item.school_name) && (
                <p className="mb-3 text-xs font-bold text-teal-800">
                  {[item.student_name, item.school_name]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
              <div className="flex flex-wrap justify-between gap-3">
                <h2 className="font-black">{item.title}</h2>
                <Badge tone={!item.read_at ? "brand" : "neutral"}>
                  {!item.read_at ? "جديد" : "مقروء"}
                </Badge>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-7">
                {item.body}
              </p>
              <p className="mt-2 text-xs text-slate-500">
                {dateTime(item.created_at)}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {!item.read_at && (
                  <Button
                    variant="secondary"
                    loading={action.isPending}
                    onClick={() =>
                      action.mutate({ id: item.id, complete: false })
                    }
                  >
                    تعليم كمقروء
                  </Button>
                )}
                {item.requires_action &&
                  !item.action_completed_at &&
                  item.kind !== "RELATION_STATUS" &&
                  item.kind !== "WARNING" && (
                    <Button
                      loading={action.isPending}
                      onClick={() =>
                        action.mutate({ id: item.id, complete: true })
                      }
                    >
                      تأكيد تنفيذ الإجراء
                    </Button>
                  )}
                {item.kind === "WARNING" && !item.action_completed_at && (
                  <Link
                    className="inline-flex min-h-11 items-center rounded-xl border border-teal-200 px-4 font-bold text-teal-800"
                    to={`/parent/children/${item.relation_id}?tab=warnings`}
                  >
                    مراجعة الإنذار وتأكيد الاطلاع
                  </Link>
                )}
                {item.kind === "FAMILY_PUBLICATION" &&
                  !item.action_completed_at && (
                    <Link
                      className="inline-flex min-h-11 items-center rounded-xl border border-teal-200 px-4 font-bold text-teal-800"
                      to={`/parent/children/${item.relation_id}?tab=family`}
                    >
                      مراجعة رسالة المدرسة وتأكيد الاطلاع
                    </Link>
                  )}
              </div>
              {item.kind === "FAMILY_PUBLICATION" &&
                item.requires_action &&
                !item.action_completed_at && (
                  <p className="mt-3 text-xs leading-6 text-slate-500">
                    أكد الاطلاع على رسالة المدرسة أولاً، ثم أكد تنفيذ الإجراء
                    المطلوب بعد إنجازه.
                  </p>
                )}
              {item.action_completed_at && (
                <p className="mt-3 text-sm font-bold text-emerald-800">
                  تم تأكيد تنفيذ الإجراء
                </p>
              )}
            </article>
          ))
        ) : (
          <EmptyState
            title="لا توجد تنبيهات جديدة"
            description="ستظهر هنا التنبيهات والقرارات المنشورة من مدارس أبنائك."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!notifications.data?.next}
        hasPrevious={!!notifications.data?.previous}
      />
    </div>
  );
}
export function ParentAccountPage() {
  const me = useMe();
  const navigate = useNavigate();
  const [schoolLink, setSchoolLink] = useState("");
  const [error, setError] = useState("");
  function openSchool() {
    setError("");
    try {
      const url = new URL(schoolLink, window.location.origin);
      const path = safeReturnTo(url.pathname);
      if (
        url.origin !== window.location.origin ||
        !path?.startsWith("/parent/register/") ||
        url.search ||
        url.hash
      )
        throw new Error();
      navigate(path);
    } catch {
      setError(
        "أدخل رابط تسجيل أولياء الأمور الصادر من المدرسة على هذه المنصة.",
      );
    }
  }
  return (
    <div className="ds-page">
      <PageHeader
        icon={UserRound}
        eyebrow="الحساب العالمي"
        title="حسابي"
        description="حساب واحد لجميع الأبناء، واعتماد مستقل لكل علاقة من مدرستها."
      />
      <section className={surface}>
        <h2 className="text-lg font-black">بيانات الحساب</h2>
        <dl className="mt-4 space-y-3">
          <div>
            <dt className="text-sm text-slate-500">الاسم</dt>
            <dd className="font-bold">{me.data?.name}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-500">جوال الدخول</dt>
            <dd className="font-bold" dir="ltr">
              {me.data?.mobile}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-sm leading-7 text-slate-600">
          تغيير جوال الدخول غير متاح في هذا الإصدار. تغيير رقم التواصل
          المدرسي لا يغير رقم حسابك.
        </p>
        <Link to="/parent/recovery-email" className="mt-3 inline-flex min-h-11 items-center font-bold text-teal-800">إدارة بريد استرداد كلمة المرور</Link>
      </section>
      <PasswordChange />
      <section className={surface}>
        <h2 className="text-lg font-black">إضافة ابن</h2>
        <p className="my-3 text-sm leading-7 text-slate-600">
          احصل على رابط التسجيل من مدرسة الابن. قدّم طلباً جديداً باستخدام جوال
          حسابك الحالي، ثم استكمل الربط بعد موافقة المدرسة.
        </p>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            openSchool();
          }}
        >
          <TextField
            label="رابط تسجيل أولياء الأمور"
            dir="ltr"
            type="url"
            value={schoolLink}
            onChange={(event) => setSchoolLink(event.target.value)}
            required
          />
          {error && <Alert tone="danger" title={error} />}
          <Button type="submit">فتح تسجيل المدرسة</Button>
        </form>
      </section>
    </div>
  );
}
function PasswordChange() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const action = useMutation({
    mutationFn: () => changeParentPassword(current, next, confirm),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
    },
  });
  return (
    <section className={surface}>
      <h2 className="text-lg font-black">تغيير كلمة المرور</h2>
      <form
        className="mt-4 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          if (
            !current ||
            next.length < 8 ||
            next !== confirm ||
            /^[0-9٠-٩]+$/.test(next)
          ) {
            setError(
              "أدخل كلمة المرور الحالية واختر كلمة مرور آمنة وطابق التأكيد.",
            );
            return;
          }
          action.mutate();
        }}
      >
        <PasswordInput
          label="كلمة المرور الحالية للحساب"
          autoComplete="current-password"
          required
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <PasswordInput
          label="كلمة المرور الجديدة للحساب"
          autoComplete="new-password"
          required
          value={next}
          onChange={(event) => setNext(event.target.value)}
        />
        <PasswordInput
          label="تأكيد كلمة المرور الجديدة للحساب"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
        {error && <Alert tone="danger" title={error} />}
        {action.isError && <ErrorState error={action.error} />}
        {action.isSuccess && (
          <Alert tone="success" title={action.data.message} live />
        )}
        <Button type="submit" loading={action.isPending}>
          حفظ كلمة المرور
        </Button>
      </form>
    </section>
  );
}
