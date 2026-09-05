import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  GraduationCap,
  Info,
  Printer,
  QrCode,
  RefreshCw,
  Search,
  ShieldCheck,
  Smartphone,
  Sparkles,
  UsersRound,
} from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import {
  getAttendanceSections,
  getSectionQr,
  rotateSectionQr,
  type AttendanceSection,
} from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { STAGE_LABELS } from "@/features/settings/api";
import { useSettingsQuery } from "@/features/settings/hooks";

/** صفحة المدير: توليد/عرض/طباعة/تجديد رمز QR لكل فصل.
 *  الرمز مبهم ولا يمنح صلاحية — التجديد يبطل الملصقات القديمة فورًا. */
export function SectionQrPage() {
  const me = useMe();
  const settingsQuery = useSettingsQuery();
  const queryClient = useQueryClient();
  const activeSchoolId = me.data?.active_school?.id ?? 0;
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [gradeFilter, setGradeFilter] = useState("");
  const [rotating, setRotating] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled: activeSchoolId > 0,
  });

  const qrQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "section-qr", selectedId),
    queryFn: ({ signal }) => getSectionQr(selectedId as number, signal),
    enabled: activeSchoolId > 0 && selectedId !== null,
  });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const qrUrl = qrQuery.data ? `${window.location.origin}${qrQuery.data.url_path}` : null;
  const schoolName = settingsQuery.data?.school.name ?? me.data?.active_school?.name ?? "المدرسة";
  const logoUrl = settingsQuery.data?.logo_url ?? null;
  const stageLabel = settingsQuery.data
    ? STAGE_LABELS[settingsQuery.data.education_stage]
    : null;

  const grades = useMemo(
    () => [...new Set((sectionsQuery.data ?? []).map((section) => section.grade_name))],
    [sectionsQuery.data],
  );
  const filteredSections = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("ar");
    return (sectionsQuery.data ?? []).filter((section) => {
      const matchesGrade = gradeFilter === "" || section.grade_name === gradeFilter;
      const searchable = `${section.grade_name} ${section.name}`.toLocaleLowerCase("ar");
      return matchesGrade && (needle === "" || searchable.includes(needle));
    });
  }, [gradeFilter, search, sectionsQuery.data]);
  const selectedSection = (sectionsQuery.data ?? []).find((section) => section.id === selectedId);

  useEffect(() => {
    if (qrUrl && canvasRef.current) {
      void QRCode.toCanvas(canvasRef.current, qrUrl, {
        width: 640,
        margin: 3,
        errorCorrectionLevel: "H",
        color: { dark: "#0f172a", light: "#ffffff" },
      });
    }
  }, [qrUrl]);

  const handleRotate = async () => {
    if (selectedId === null) return;
    if (!window.confirm("تجديد الرمز يبطل جميع النسخ المطبوعة القديمة فورًا. هل تريد المتابعة؟")) return;
    setRotating(true);
    setActionError(null);
    try {
      const info = await rotateSectionQr(selectedId);
      queryClient.setQueryData(
        schoolScopedKey(activeSchoolId, "attendance", "section-qr", selectedId),
        info,
      );
    } catch (error) {
      setActionError(error);
    } finally {
      setRotating(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="section-qr-page">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-l from-slate-950 via-slate-900 to-teal-950 p-5 text-white shadow-xl shadow-slate-950/10 print:hidden sm:p-7">
        <div aria-hidden className="absolute -left-16 -top-20 size-64 rounded-full bg-teal-400/15 blur-3xl" />
        <div aria-hidden className="absolute -bottom-24 right-1/3 size-52 rounded-full bg-blue-500/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
          <div className="flex items-start gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/10 text-teal-200 ring-1 ring-white/15">
              <QrCode aria-hidden size={25} />
            </span>
            <div>
              <p className="flex items-center gap-1.5 text-xs font-bold text-teal-200"><Sparkles aria-hidden size={14} /> إدارة رموز الفصول</p>
              <h1 className="mt-2 text-2xl font-black sm:text-3xl">بطاقات QR جاهزة للطباعة</h1>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-300">
                اختر الفصل، راجع البطاقة بهوية المدرسة، ثم اطبعها وعلّقها في مكان واضح داخل الفصل.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-bold">
            <span className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 ring-1 ring-white/10"><ShieldCheck aria-hidden size={16} className="text-emerald-300" /> الرمز لا يمنح صلاحية</span>
            <span className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 ring-1 ring-white/10"><Printer aria-hidden size={16} className="text-blue-200" /> مهيأ لطباعة A4</span>
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm print:hidden sm:p-6" aria-labelledby="choose-section-title">
        <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <p className="text-xs font-bold text-teal-700">الخطوة 1</p>
            <h2 id="choose-section-title" className="mt-1 text-lg font-black text-slate-900">اختر الفصل المطلوب</h2>
            <p className="mt-1 text-sm text-slate-500">يمكنك البحث باسم الصف أو رقم الفصل.</p>
          </div>
          {sectionsQuery.isSuccess && (
            <span className="inline-flex w-fit items-center gap-2 rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold text-slate-700">
              <GraduationCap aria-hidden size={16} /> {sectionsQuery.data.length} فصلًا
            </span>
          )}
        </div>

        {sectionsQuery.isPending && <Spinner label="جارٍ تحميل الفصول..." />}
        {sectionsQuery.isError && <ErrorState error={sectionsQuery.error} />}
        {sectionsQuery.isSuccess && sectionsQuery.data.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <GraduationCap aria-hidden size={30} className="mx-auto text-slate-400" />
            <p className="mt-3 font-bold text-slate-800">لا توجد فصول متاحة بعد</p>
            <p className="mt-1 text-sm text-slate-500">أضف الطلاب والفصول أولًا، ثم عُد لطباعة الرموز.</p>
          </div>
        )}
        {sectionsQuery.isSuccess && sectionsQuery.data.length > 0 && (
          <>
            <div className="mb-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_15rem]">
              <label className="relative block">
                <span className="sr-only">البحث في الفصول</span>
                <Search aria-hidden size={18} className="pointer-events-none absolute inset-y-0 right-3 my-auto text-slate-400" />
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="ابحث عن صف أو فصل..."
                  className="min-h-11 w-full rounded-xl border border-slate-300 bg-white py-2 pe-10 ps-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-100"
                />
              </label>
              <label>
                <span className="sr-only">تصفية حسب الصف</span>
                <select
                  value={gradeFilter}
                  onChange={(event) => setGradeFilter(event.target.value)}
                  className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold text-slate-700 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-100"
                >
                  <option value="">كل الصفوف</option>
                  {grades.map((grade) => <option key={grade} value={grade}>{grade}</option>)}
                </select>
              </label>
            </div>

            {filteredSections.length === 0 ? (
              <p className="rounded-2xl bg-amber-50 p-4 text-center text-sm font-bold text-amber-800">لا توجد فصول مطابقة للبحث.</p>
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" data-testid="qr-sections-list">
                {filteredSections.map((section) => (
                  <li key={section.id}>
                    <SectionChoice
                      section={section}
                      selected={selectedId === section.id}
                      onSelect={() => {
                        setSelectedId(section.id);
                        setActionError(null);
                      }}
                    />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      {selectedId === null && sectionsQuery.isSuccess && sectionsQuery.data.length > 0 && (
        <section className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center print:hidden">
          <QrCode aria-hidden size={34} className="mx-auto text-slate-400" />
          <h2 className="mt-3 font-black text-slate-800">اختر فصلًا لمعاينة بطاقة الطباعة</h2>
          <p className="mt-1 text-sm text-slate-500">ستظهر هنا البطاقة النهائية كما ستبدو على ورقة A4.</p>
        </section>
      )}

      {selectedId !== null && (
        <section className="rounded-3xl border border-slate-200 bg-slate-100/70 p-3 shadow-sm print:border-0 print:bg-white print:p-0 print:shadow-none sm:p-5" aria-live="polite">
          {qrQuery.isPending && <div className="rounded-2xl bg-white p-10 print:hidden"><Spinner label="جارٍ تجهيز بطاقة الفصل..." /></div>}
          {qrQuery.isError && <div className="rounded-2xl bg-white p-5 print:hidden"><ErrorState error={qrQuery.error} /></div>}
          {qrQuery.isSuccess && selectedSection && (
            <div className="qr-print-preview grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
              <QrPrintSheet
                canvasRef={canvasRef}
                schoolName={schoolName}
                logoUrl={logoUrl}
                stageLabel={stageLabel}
                section={selectedSection}
              />

              <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm print:hidden">
                <p className="text-xs font-bold text-teal-700">الخطوة 2</p>
                <h2 className="mt-1 text-lg font-black text-slate-900">راجع البطاقة واطبعها</h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">تحقق من اسم المدرسة والصف والفصل قبل الطباعة.</p>

                <div className="mt-5 space-y-2 text-sm">
                  <ReviewItem label="المدرسة" value={schoolName} />
                  <ReviewItem label="الصف" value={qrQuery.data.grade_name} />
                  <ReviewItem label="الفصل" value={qrQuery.data.section_name} />
                </div>

                <Button onClick={() => window.print()} className="mt-5 w-full py-3" data-testid="print-qr">
                  <Printer aria-hidden size={18} /> طباعة بطاقة الفصل
                </Button>

                <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <p className="flex items-center gap-2 text-sm font-black text-amber-900"><Info aria-hidden size={17} /> هل تحتاج رمزًا جديدًا؟</p>
                  <p className="mt-2 text-xs leading-5 text-amber-800">التجديد يبطل الرمز الحالي فورًا، بما في ذلك جميع النسخ المطبوعة.</p>
                  <Button
                    variant="danger"
                    onClick={() => void handleRotate()}
                    disabled={rotating}
                    data-testid="rotate-qr"
                    className="mt-3 w-full"
                  >
                    <RefreshCw aria-hidden size={16} className={rotating ? "animate-spin" : ""} />
                    {rotating ? "جارٍ التجديد..." : "تجديد الرمز"}
                  </Button>
                </div>
                {actionError != null && <div className="mt-4"><ErrorState error={actionError} /></div>}
              </aside>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function SectionChoice({ section, selected, onSelect }: { section: AttendanceSection; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`group flex min-h-24 w-full items-center gap-3 rounded-2xl border p-3.5 text-start transition-all focus-visible:outline-2 focus-visible:outline-offset-2 ${
        selected
          ? "border-teal-500 bg-teal-50 shadow-sm ring-2 ring-teal-100"
          : "border-slate-200 bg-slate-50 hover:-translate-y-0.5 hover:border-teal-300 hover:bg-white hover:shadow-sm"
      }`}
      data-testid={`qr-section-${section.id}`}
    >
      <span className={`grid size-11 shrink-0 place-items-center rounded-xl text-lg font-black ${selected ? "bg-teal-700 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200"}`}>{section.name}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-black text-slate-900">الفصل {section.name}</span>
        <span className="mt-1 block truncate text-xs text-slate-500">{section.grade_name}</span>
        <span className="mt-1 flex items-center gap-1 text-[11px] font-bold text-slate-400"><UsersRound aria-hidden size={12} /> {section.students_count} طالبًا</span>
      </span>
      {selected && <CheckCircle2 aria-label="محدد" size={19} className="shrink-0 text-teal-700" />}
    </button>
  );
}

function QrPrintSheet({
  canvasRef,
  schoolName,
  logoUrl,
  stageLabel,
  section,
}: {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  schoolName: string;
  logoUrl: string | null;
  stageLabel: string | null;
  section: AttendanceSection;
}) {
  return (
    <article className="qr-print-sheet relative mx-auto w-full max-w-3xl overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-950/5 sm:p-9" data-testid="qr-print-sheet">
      <div aria-hidden className="absolute inset-x-0 top-0 h-2 bg-gradient-to-l from-teal-600 via-blue-700 to-slate-900" />
      <div aria-hidden className="absolute -left-20 -top-20 size-56 rounded-full bg-teal-50" />
      <div className="relative flex items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div className="flex min-w-0 items-center gap-4">
          {logoUrl ? (
            <img src={logoUrl} alt={`شعار ${schoolName}`} className="size-16 shrink-0 rounded-2xl border border-slate-200 bg-white object-contain p-1.5" />
          ) : (
            <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-slate-950 text-white shadow-sm"><GraduationCap aria-hidden size={31} /></span>
          )}
          <div className="min-w-0">
            <p className="text-[11px] font-black tracking-wide text-teal-700">منصة المواظبة والمتابعة الطلابية</p>
            <h2 className="mt-1 truncate text-xl font-black text-slate-950 sm:text-2xl" data-testid="qr-school-name">{schoolName}</h2>
            {stageLabel && <p className="mt-1 text-xs font-bold text-slate-500">المرحلة: {stageLabel}</p>}
          </div>
        </div>
        <span className="hidden shrink-0 rounded-full bg-teal-50 px-3 py-1.5 text-xs font-black text-teal-800 sm:inline-flex">بطاقة تحضير الفصل</span>
      </div>

      <div className="relative py-7 text-center">
        <p className="text-sm font-black text-teal-700">{section.grade_name}</p>
        <h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950 sm:text-5xl" data-testid="qr-section-title">الفصل {section.name}</h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-slate-500">امسح الرمز من داخل المنصة لفتح قائمة طلاب هذا الفصل والبدء في التحضير مباشرة.</p>

        <div className="mx-auto mt-6 w-fit rounded-[2rem] border-2 border-slate-900 bg-white p-3 shadow-sm ring-8 ring-slate-100">
          <canvas
            ref={canvasRef}
            data-testid="qr-canvas"
            role="img"
            aria-label={`رمز QR للفصل ${section.name} في ${section.grade_name}`}
            className="size-[min(72vw,20rem)] rounded-2xl bg-white"
          />
        </div>
      </div>

      <div className="relative grid gap-3 border-t border-slate-200 pt-5 sm:grid-cols-3">
        <Instruction icon={Smartphone} number="1" text="افتح ماسح QR من المنصة" />
        <Instruction icon={QrCode} number="2" text="وجّه الكاميرا نحو الرمز" />
        <Instruction icon={CheckCircle2} number="3" text="راجع الطلاب وابدأ التحضير" />
      </div>
      <div className="relative mt-5 flex flex-col justify-between gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-xs text-slate-300 sm:flex-row sm:items-center">
        <span className="inline-flex items-center gap-2 font-bold text-white"><ShieldCheck aria-hidden size={15} className="text-emerald-300" /> يلزم تسجيل الدخول والصلاحية المدرسية</span>
        <span>لا تشارك البطاقة خارج المدرسة</span>
      </div>
    </article>
  );
}

function Instruction({ icon: Icon, number, text }: { icon: typeof Smartphone; number: string; text: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-slate-50 p-3 text-start">
      <span className="relative grid size-10 shrink-0 place-items-center rounded-xl bg-white text-teal-700 ring-1 ring-slate-200"><Icon aria-hidden size={18} /><b className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-slate-950 text-[9px] text-white">{number}</b></span>
      <p className="text-xs font-bold leading-5 text-slate-700">{text}</p>
    </div>
  );
}

function ReviewItem({ label, value }: { label: string; value: string }) {
  return <div className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2.5"><span className="text-slate-500">{label}</span><strong className="text-left text-slate-900">{value}</strong></div>;
}
