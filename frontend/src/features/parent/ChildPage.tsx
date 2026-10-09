import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, BookOpenCheck, FileText, Sunrise } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { adaptivePollingInterval } from "@/app/polling";
import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SelectField, TextareaField } from "@/components/FormField";
import { Pagination } from "@/components/Pagination";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { Tabs } from "@/components/Tabs";
import { useMe } from "@/features/auth/useMe";
import { REASON_LABELS, type ReasonType } from "@/features/excuses/api";
import {
  acknowledgePublication,
  acknowledgeWarning,
  createCorrectionRequest,
  createExcuseRequest,
  getChild,
  getHistory,
  getPublications,
  getWarnings,
  parentKey,
  publicationDownloadUrl,
  uploadRequestAttachment,
  type ChildDetail,
} from "@/features/parent/api";
import {
  dateTime,
  DayBadge,
  fieldGrid,
  isIncomplete,
  surface,
  timeOnly,
  todayDate,
} from "@/features/parent/shared";

const tabs = [
  { id: "today", label: "اليوم", Icon: Sunrise },
  { id: "history", label: "سجل المواظبة", Icon: BookOpenCheck },
  { id: "requests", label: "تقديم طلب", Icon: FileText },
  { id: "warnings", label: "الإنذارات", Icon: BellRing },
  { id: "family", label: "رسائل المدرسة", Icon: FileText },
] as const;
type Tab = (typeof tabs)[number]["id"];
const accessDenied = (error: unknown): error is ApiError =>
  error instanceof ApiError && [401, 403, 404].includes(error.status);
const interval = adaptivePollingInterval(30_000);
type AccessErrorHandler = (error: unknown, part?: string) => void;

export function ChildPage() {
  const { relationId } = useParams();
  const relation = Number(relationId);
  const [params] = useSearchParams();
  const me = useMe();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>(
    tabs.find((item) => item.id === params.get("tab"))?.id ?? "today",
  );
  const [revoked, setRevoked] = useState(false);
  const [date, setDate] = useState(todayDate());
  const detail = useQuery({
    queryKey: parentKey(me.data?.id, "child", relation, "detail", date),
    queryFn: ({ signal }) => getChild(relation, signal, date),
    enabled:
      me.isSuccess &&
      Number.isSafeInteger(relation) &&
      relation > 0 &&
      !revoked,
    refetchInterval: (query) =>
      accessDenied(query.state.error) ? false : interval(query),
    refetchIntervalInBackground: false,
    retry: false,
  });
  const refetchDetail = detail.refetch;
  const handleAccessError = useCallback<AccessErrorHandler>(
    (error, part) => {
      if (!accessDenied(error)) return;
      void (async () => {
        await purgeSensitiveBrowserCaches();
        if (error.status === 401 || error.code === "AUTHENTICATION_REQUIRED") {
          await queryClient.cancelQueries();
          queryClient.clear();
          navigate("/login", { replace: true });
          return;
        }
        // A rejected write or revoked publication need not revoke the child grant.
        const verified = await refetchDetail();
        if (!verified.isError && part) {
          await queryClient.invalidateQueries({
            queryKey: parentKey(me.data?.id, "child", relation, part),
          });
        }
      })();
    },
    [refetchDetail, me.data?.id, navigate, queryClient, relation],
  );
  useEffect(() => {
    if (detail.isError && accessDenied(detail.error)) {
      if (detail.error.status === 401 || detail.error.code === "AUTHENTICATION_REQUIRED") {
        handleAccessError(detail.error);
        return;
      }
      void Promise.all([
        queryClient.cancelQueries({
          queryKey: parentKey(me.data?.id, "child", relation),
        }),
        purgeSensitiveBrowserCaches(),
      ]).then(() => {
        setRevoked(true);
        queryClient.removeQueries({
          queryKey: parentKey(me.data?.id, "child", relation),
        });
        // Aggregate pages can contain the same child's names, requests or documents.
        for (const part of ["children", "requests", "notifications"]) {
          queryClient.removeQueries({
            queryKey: parentKey(me.data?.id, part),
          });
        }
      });
    }
  }, [detail.isError, detail.error, handleAccessError, me.data?.id, queryClient, relation]);
  if (revoked || detail.isError)
    return (
      <div className="ds-page">
        <Link
          to="/parent"
          className="inline-flex min-h-11 items-center font-bold text-teal-800"
        >
          العودة إلى أبنائي
        </Link>
        <Alert tone="warning" title="تعذر عرض بيانات الابن">
          قد تحتاج العلاقة إلى مراجعة المدرسة. تواصل مع الإدارة لاستكمال التحقق.
        </Alert>
      </div>
    );
  if (detail.isPending) return <PageSkeleton label="جارٍ تحميل مواظبة الابن" />;
  const data = detail.data;
  return (
    <div className="ds-page" data-testid="parent-child-detail">
      <Link
        to="/parent"
        className="inline-flex min-h-11 items-center text-sm font-bold text-teal-800"
      >
        العودة إلى أبنائي
      </Link>
      <PageHeader
        icon={BookOpenCheck}
        eyebrow={data.child.school.name}
        title={data.child.student?.full_name ?? "مواظبة الابن"}
        description={[
          data.child.student?.grade_name,
          data.child.student?.section_name
            ? `الفصل ${data.child.student.section_name}`
            : "",
          data.child.student?.department,
        ]
          .filter(Boolean)
          .join(" · ")}
        badge={<DayBadge day={data.today} />}
      />
      <div className={surface}>
        <TextField
          label="يوم المتابعة"
          type="date"
          value={date}
          max={todayDate()}
          onChange={(event) => setDate(event.target.value)}
        />
      </div>
      <Tabs
        idPrefix="child"
        value={tab}
        onChange={setTab}
        label="متابعة الابن"
        items={tabs.map(({ id, label, Icon }) => ({
          value: id,
          label: (
            <span className="inline-flex items-center gap-2">
              <Icon aria-hidden size={16} />
              {label}
            </span>
          ),
        }))}
      />
      <section
        role="tabpanel"
        id={`child-panel-${tab}`}
        aria-labelledby={`child-tab-${tab}`}
        className="space-y-4"
      >
        {tab === "today" && <Today detail={data} />}
        {tab === "history" && <History relation={relation} onAccessError={handleAccessError} />}
        {tab === "requests" && (
          <RequestForms key={date} relation={relation} detail={data} onAccessError={handleAccessError} />
        )}
        {tab === "warnings" && <Warnings relation={relation} onAccessError={handleAccessError} />}
        {tab === "family" && <FamilyContent relation={relation} onAccessError={handleAccessError} />}
      </section>
    </div>
  );
}

function Today({ detail }: { detail: ChildDetail }) {
  const morning = detail.morning;
  return (
    <>
      {isIncomplete(detail.today) && (
        <Alert tone="warning" title="لم يكتمل تحضير اليوم">
          النتائج الحالية للحصص المعتمدة فقط. لا نعرض هذا اليوم باعتباره غياب
          يوم كامل مؤكداً حتى اكتمال بياناته.
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <section className={surface}>
          <h2 className="font-black">الحضور الصباحي</h2>
          <p className="mt-3 text-lg font-bold">
            {morning.arrival_time
              ? `وقت الوصول: ${timeOnly(morning.arrival_time)}`
              : "لم تسجل بصمة وصول"}
          </p>
          {morning.arrival_time && (
            <p className="mt-2 text-sm">
              {morning.counted_late_minutes > 0
                ? `تأخر صباحي محتسب: ${morning.counted_late_minutes} دقيقة`
                : "لا يوجد تأخر صباحي محتسب"}
            </p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            {!morning.arrival_time
              ? "غياب بصمة الوصول لا يعني غياب الطالب عن المدرسة."
              : `آخر تحديث: ${dateTime(morning.updated_at)}`}
          </p>
        </section>
        <section className={surface}>
          <h2 className="font-black">الحصص المعتمدة اليوم</h2>
          <p className="mt-3 text-2xl font-black text-teal-800">
            {detail.today.submitted_periods}{" "}
            <span className="text-base font-medium text-slate-500">
              من {detail.today.expected_periods}
            </span>
          </p>
          <p className="mt-2 text-sm">
            حضور: {detail.today.present_periods} · غياب:{" "}
            {detail.today.absent_periods}
          </p>
          <p className="mt-3 text-xs text-slate-500">
            آخر تحديث: {dateTime(detail.today.updated_at)}
          </p>
        </section>
      </div>
      <section className={surface}>
        <h2 className="mb-4 text-lg font-black">تفاصيل الحصص</h2>
        {detail.periods.length === 0 ? (
          <EmptyState
            compact
            title="لا توجد حصص لهذا اليوم"
            description="ستظهر الحصص وفق الجدول الدراسي المسجل."
          />
        ) : (
          <ul className="space-y-3">
            {detail.periods.map((period) => (
              <li
                key={period.sequence}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 p-4"
              >
                <div>
                  <h3 className="font-bold">
                    {period.name || `الحصة ${period.sequence}`}
                  </h3>
                  <p dir="ltr" className="mt-1 text-xs text-slate-500">
                    {period.start_time ?? "—"} – {period.end_time ?? "—"}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    آخر تحديث: {dateTime(period.updated_at)}
                  </p>
                </div>
                <Badge
                  tone={
                    period.status === "ABSENT"
                      ? "danger"
                      : period.status === "PRESENT"
                        ? "success"
                        : "warning"
                  }
                >
                  {period.status_label}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
function History({ relation, onAccessError }: { relation: number; onAccessError: AccessErrorHandler }) {
  const me = useMe();
  const current = todayDate();
  const [from, setFrom] = useState(`${current.slice(0, 7)}-01`);
  const [to, setTo] = useState(current);
  const history = useQuery({
    queryKey: parentKey(me.data?.id, "child", relation, "history", from, to),
    queryFn: ({ signal }) => getHistory(relation, from, to, signal),
    enabled: !!from && !!to && from <= to,
    retry: false,
  });
  useEffect(() => {
    if (history.isError) onAccessError(history.error);
  }, [history.isError, history.error, onAccessError]);
  return (
    <div className="space-y-4">
      <div className={`${surface} ${fieldGrid}`}>
        <TextField
          label="من تاريخ"
          type="date"
          value={from}
          max={to}
          onChange={(event) => setFrom(event.target.value)}
        />
        <TextField
          label="إلى تاريخ"
          type="date"
          value={to}
          min={from}
          max={current}
          onChange={(event) => setTo(event.target.value)}
        />
      </div>
      {history.isPending && <PageSkeleton />}
      {history.isError && <ErrorState error={history.error} />}
      {history.isSuccess && (
        <>
          <section className={surface}>
            <h2 className="font-black">ملخص الفترة</h2>
            <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
              {[
                ["غياب كامل مكتمل", history.data.summary.full_absence_days],
                ["غياب جزئي", history.data.summary.partial_absence_days],
                ["حصص بعذر", history.data.summary.excused_absent_periods],
                ["حصص دون عذر", history.data.summary.unexcused_absent_periods],
                ["أيام التأخر الصباحي", history.data.summary.morning_late_days],
                [
                  "دقائق التأخر المحتسبة",
                  history.data.summary.counted_late_minutes,
                ],
                ["الحصص الحاضرة", history.data.summary.present_periods],
                ["الحصص الغائبة", history.data.summary.absent_periods],
                ["أيام غير مكتملة", history.data.summary.incomplete_days],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="mt-1 text-xl font-black">{value}</dd>
                </div>
              ))}
            </dl>
          </section>
          {history.data.results.length ? (
            <div className="space-y-3">
              {history.data.results.map((day) => (
                <article key={day.date} className={surface}>
                  <div className="flex flex-wrap justify-between gap-3">
                    <h3 dir="ltr" className="font-bold">
                      {day.date}
                    </h3>
                    <DayBadge day={day} />
                  </div>
                  <p className="mt-3 text-sm">
                    حصص معتمدة: {day.submitted_periods} / {day.expected_periods}{" "}
                    · حضور: {day.present_periods} · غياب: {day.absent_periods}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    بعذر: {day.excused_absent_periods} · دون عذر:{" "}
                    {day.unexcused_absent_periods}
                    {day.morning?.arrival_time
                      ? ` · تأخر صباحي: ${day.morning.counted_late_minutes} دقيقة`
                      : ""}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="لا توجد أيام مسجلة في الفترة"
              description="اختر فترة أخرى أو انتظر اعتماد التحضير."
            />
          )}
        </>
      )}
    </div>
  );
}
function RequestForms({
  relation,
  detail,
  onAccessError,
}: {
  relation: number;
  detail: ChildDetail;
  onAccessError: AccessErrorHandler;
}) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [date, setDate] = useState(detail.today.date);
  const [reason, setReason] = useState<ReasonType>("MEDICAL_REPORT");
  const [notes, setNotes] = useState("");
  const [scope, setScope] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<number | null>(null);
  const [session, setSession] = useState("");
  const [objection, setObjection] = useState("");
  const upload = useMutation({
    mutationFn: ({
      request,
      attachment,
    }: {
      request: number;
      attachment: File;
    }) => uploadRequestAttachment(relation, request, attachment),
    onError: (error) => onAccessError(error),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "requests"),
      }),
  });
  const excuse = useMutation({
    mutationFn: () =>
      createExcuseRequest(relation, {
        reason_type: reason,
        notes: notes.trim(),
        targets: [
          {
            attendance_date: date,
            period_sequence: scope ? Number(scope) : null,
          },
        ],
      }),
    onError: (error) => onAccessError(error),
    onSuccess: (request) => {
      setCreated(request.id);
      if (file) upload.mutate({ request: request.id, attachment: file });
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "requests"),
      });
    },
  });
  const correction = useMutation({
    mutationFn: () =>
      createCorrectionRequest(relation, Number(session), objection.trim()),
    onError: (error) => onAccessError(error),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "requests"),
      }),
  });
  function submitExcuse(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!date || !notes.trim()) {
      setError("اختر يوم الغياب واكتب سبب العذر.");
      return;
    }
    if (
      file &&
      (file.size > 5 * 1024 * 1024 ||
        !["application/pdf", "image/jpeg", "image/png"].includes(file.type))
    ) {
      setError(
        "المرفق يجب أن يكون PDF أو صورة JPG/PNG وألا يتجاوز 5 ميجابايت.",
      );
      return;
    }
    excuse.mutate();
  }
  const absent = detail.periods.filter(
    (period) => period.status === "ABSENT" && period.session_id,
  );
  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <section className={surface}>
        <h2 className="text-lg font-black">تقديم عذر</h2>
        <p className="my-3 text-sm leading-7 text-slate-600">
          تراجع المدرسة الطلب. اعتماد العذر لا يغير حقيقة الغياب المسجلة.
        </p>
        {created ? (
          <>
            <Alert
              tone="success"
              title={`تم إرسال طلب العذر #${created}`}
              live
            />
            <Link
              to="/parent/requests"
              className="mt-3 inline-flex min-h-11 items-center font-bold text-teal-800"
            >
              متابعة القرار
            </Link>
            {upload.isPending && <p role="status">جارٍ رفع المرفق...</p>}
            {upload.isError && (
              <>
                <ErrorState error={upload.error} />
                <Button
                  variant="secondary"
                  onClick={() => {
                    if (file)
                      upload.mutate({ request: created, attachment: file });
                  }}
                >
                  إعادة رفع المرفق
                </Button>
              </>
            )}
            {upload.isSuccess && (
              <p className="text-sm text-emerald-800">تم رفع المرفق.</p>
            )}
          </>
        ) : (
          <form className="space-y-4" onSubmit={submitExcuse} noValidate>
            <TextField
              label="تاريخ الغياب"
              type="date"
              required
              value={date}
              max={todayDate()}
              onChange={(event) => {
                setDate(event.target.value);
                setScope("");
              }}
            />
            <SelectField
              label="نطاق العذر"
              value={scope}
              onChange={(event) => setScope(event.target.value)}
            >
              <option value="">اليوم كاملاً</option>
              {detail.periods.map((period) => (
                <option key={period.sequence} value={period.sequence}>
                  {period.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="نوع العذر"
              value={reason}
              onChange={(event) => setReason(event.target.value as ReasonType)}
            >
              {Object.entries(REASON_LABELS).map(([key, label]) => (
                <option value={key} key={key}>
                  {label}
                </option>
              ))}
            </SelectField>
            <TextareaField
              label="سبب العذر"
              required
              maxLength={500}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
            <label className="block text-sm font-bold">
              مرفق العذر (اختياري)
              <input
                className="mt-2 block w-full min-w-0 text-sm"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <p className="text-xs text-slate-500">
              PDF أو JPG أو PNG، حتى 5 ميجابايت.
            </p>
            {error && <Alert tone="danger" title={error} />}
            {excuse.isError && <ErrorState error={excuse.error} />}
            <Button type="submit" fullWidth loading={excuse.isPending}>
              إرسال طلب العذر
            </Button>
          </form>
        )}
      </section>
      <section className={surface}>
        <h2 className="text-lg font-black">طلب مراجعة الحضور</h2>
        <p className="my-3 text-sm leading-7 text-slate-600">
          إذا كان الابن حاضراً وسجل غائباً، اطلب مراجعة المدرسة للحصة. الطلب لا
          يعدل الحضور مباشرة.
        </p>
        {correction.isSuccess ? (
          <Alert
            tone="success"
            title={`تم إرسال طلب المراجعة #${correction.data.id}`}
            live
          />
        ) : absent.length ? (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (session && objection.trim()) correction.mutate();
            }}
          >
            <SelectField
              label="حصة الغياب المطلوب مراجعتها"
              required
              value={session}
              onChange={(event) => setSession(event.target.value)}
            >
              <option value="">اختر الحصة</option>
              {absent.map((period) => (
                <option key={period.sequence} value={period.session_id ?? ""}>
                  {period.name} · {period.attendance_date}
                </option>
              ))}
            </SelectField>
            <TextareaField
              label="سبب الاعتراض"
              required
              maxLength={500}
              value={objection}
              onChange={(event) => setObjection(event.target.value)}
            />
            {correction.isError && <ErrorState error={correction.error} />}
            <Button type="submit" fullWidth loading={correction.isPending}>
              طلب مراجعة الحضور
            </Button>
          </form>
        ) : (
          <EmptyState
            compact
            title="لا يوجد غياب معتمد اليوم"
            description="تتاح المراجعة للحصص التي سجل فيها الغياب بعد اعتماد التحضير."
          />
        )}
      </section>
    </div>
  );
}
function Warnings({ relation, onAccessError }: { relation: number; onAccessError: AccessErrorHandler }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const warnings = useQuery({
    queryKey: parentKey(me.data?.id, "child", relation, "warnings", page),
    queryFn: ({ signal }) => getWarnings(relation, signal, page),
    retry: false,
  });
  useEffect(() => {
    if (warnings.isError) onAccessError(warnings.error);
  }, [warnings.isError, warnings.error, onAccessError]);
  const ack = useMutation({
    mutationFn: (id: number) => acknowledgeWarning(relation, id),
    onError: (error) => onAccessError(error, "warnings"),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "child", relation, "warnings"),
      }),
  });
  return (
    <>
      {warnings.isPending && <PageSkeleton />}
      {warnings.isError && <ErrorState error={warnings.error} />}
      {ack.isError && <ErrorState error={ack.error} />}
      {warnings.isSuccess &&
        (warnings.data.items.length ? (
          warnings.data.items.map((warning) => (
            <article className={surface} key={warning.id}>
              <h2 className="font-black">
                {warning.warning_type === "MORNING_LATE_OCCURRENCES"
                  ? "إنذار التأخر الصباحي"
                  : "إنذار الغياب"}{" "}
                ·{" "}
                {(
                  {
                    LEVEL_1: "الأول",
                    LEVEL_2: "الثاني",
                    LEVEL_3: "الثالث",
                  } as Record<string, string>
                )[warning.level] ?? warning.level}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                {dateTime(warning.issued_at)}
              </p>
              {warning.status !== "ISSUED" ? (
                <Badge tone="neutral">ملغى</Badge>
              ) : (
                <>
                  <div className="mt-3 flex flex-wrap gap-3">
                    {warning.documents
                      .filter((document) => document.status === "READY")
                      .map((document) => (
                        <a
                          href={publicationDownloadUrl(
                            relation,
                            document.publication_id,
                          )}
                          className="inline-flex min-h-11 items-center font-bold text-teal-800 underline"
                          key={document.publication_id}
                        >
                          عرض مستند الإنذار
                        </a>
                      ))}
                  </div>
                  {warning.acknowledged_at ? (
                    <p className="mt-3 text-sm font-bold text-emerald-800">
                      تم تأكيد الاطلاع: {dateTime(warning.acknowledged_at)}
                    </p>
                  ) : (
                    <>
                      <p className="my-3 text-xs text-slate-500">
                        تأكيد الاطلاع يسجل علمك بالإنذار ولا يعني الموافقة على
                        محتواه.
                      </p>
                      <Button
                        loading={ack.isPending}
                        onClick={() => ack.mutate(warning.id)}
                      >
                        تأكيد الاطلاع على الإنذار
                      </Button>
                    </>
                  )}
                </>
              )}
            </article>
          ))
        ) : (
          <EmptyState
            title="لا توجد إنذارات صادرة"
            description="تظهر الإنذارات التي أصدرتها المدرسة فقط."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!warnings.data?.next}
        hasPrevious={!!warnings.data?.previous}
      />
    </>
  );
}
function FamilyContent({ relation, onAccessError }: { relation: number; onAccessError: AccessErrorHandler }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const publications = useQuery({
    queryKey: parentKey(me.data?.id, "child", relation, "publications", page),
    queryFn: ({ signal }) => getPublications(relation, signal, page),
    retry: false,
  });
  useEffect(() => {
    if (publications.isError) onAccessError(publications.error);
  }, [publications.isError, publications.error, onAccessError]);
  const ack = useMutation({
    mutationFn: (id: number) => acknowledgePublication(relation, id),
    onError: (error) => onAccessError(error, "publications"),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: parentKey(me.data?.id, "child", relation, "publications"),
      }),
  });
  return (
    <>
      {publications.isPending && <PageSkeleton />}
      {publications.isError && <ErrorState error={publications.error} />}
      {ack.isError && <ErrorState error={ack.error} />}
      {publications.isSuccess &&
        (publications.data.items.length ? (
          publications.data.items.map((publication) => (
            <article key={publication.id} className={surface}>
              <h2 className="text-lg font-black">{publication.title}</h2>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-8">
                {publication.body}
              </p>
              <p className="mt-3 text-xs text-slate-500">
                {dateTime(publication.published_at)}
              </p>
              {publication.required_action && (
                <Alert className="mt-4" title="المطلوب من الأسرة">
                  {publication.required_action}
                  {publication.due_at && (
                    <p>قبل: {dateTime(publication.due_at)}</p>
                  )}
                </Alert>
              )}
              {publication.document && (
                <a
                  className="mt-3 inline-flex min-h-11 items-center font-bold text-teal-800 underline"
                  href={publicationDownloadUrl(relation, publication.id)}
                >
                  عرض المستند المنشور
                </a>
              )}
              {!publication.acknowledged_at ? (
                <Button
                  className="mt-3"
                  loading={ack.isPending}
                  onClick={() => ack.mutate(publication.id)}
                >
                  تأكيد الاطلاع على الرسالة
                </Button>
              ) : (
                <p className="mt-3 text-sm font-bold text-emerald-800">
                  تم تأكيد الاطلاع
                </p>
              )}
            </article>
          ))
        ) : (
          <EmptyState
            title="لا توجد رسائل منشورة للأسرة"
            description="تظهر هنا التوجيهات التي تختار المدرسة مشاركتها مع الأسرة."
          />
        ))}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!publications.data?.next}
        hasPrevious={!!publications.data?.previous}
      />
    </>
  );
}
