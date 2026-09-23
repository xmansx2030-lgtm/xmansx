import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, BarChart3, BellRing, BookOpenCheck, Building2, Check,
  ChevronLeft, CircleAlert, Fingerprint, GraduationCap, HeartHandshake, Menu,
  QrCode, RefreshCw, ShieldCheck, Sparkles, UsersRound, X,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { getPublicPlans, type PublicPlan } from "@/features/public/api";
import { formatPlanDuration } from "@/utils/planDuration";

const WHATSAPP_MESSAGE = "السلام عليكم، أود معرفة المزيد عن منصة المواظبة XMANSX.";
const WHATSAPP_URL = `https://wa.me/966537720207?text=${encodeURIComponent(WHATSAPP_MESSAGE)}`;

const FEATURES: Array<{
  id: string;
  title: string;
  eyebrow: string;
  description: string;
  icon: LucideIcon;
  points: string[];
  stat: string;
  statLabel: string;
}> = [
  {
    id: "attendance",
    title: "حضور يُفهم لحظيًا",
    eyebrow: "المواظبة اليومية",
    description: "من الحصة الأولى إلى التأخر الصباحي، ترى الإدارة ما اكتمل وما يحتاج تدخلاً دون جمع يدوي أو ملفات متفرقة.",
    icon: BookOpenCheck,
    points: ["تحضير مرن للمعلم", "متابعة مباشرة للإدارة", "تكامل أجهزة الحضور وQR"],
    stat: "لحظي",
    statLabel: "تحديث حالة التحضير",
  },
  {
    id: "followup",
    title: "متابعة تربط المعلومة بالإجراء",
    eyebrow: "الرعاية الطلابية",
    description: "الأعذار والإنذارات والإحالات والخطط الإرشادية في سياق موحد يوضح ما حدث، ومن يتابع، وما الخطوة التالية.",
    icon: HeartHandshake,
    points: ["ملف مواظبة لكل طالب", "إحالات ومسارات متابعة", "سجل إجراءات قابل للتتبع"],
    stat: "360°",
    statLabel: "صورة الطالب التشغيلية",
  },
  {
    id: "decisions",
    title: "قرارات تستند إلى صورة واضحة",
    eyebrow: "القيادة المدرسية",
    description: "لوحة مركزة وتقارير قابلة للتصدير تكشف الاتجاهات والاستثناءات، مع صلاحيات تناسب كل مسؤول في المدرسة.",
    icon: BarChart3,
    points: ["مؤشرات يومية مركزة", "تقارير Excel وCSV", "عزل كامل لبيانات المدارس"],
    stat: "واحدة",
    statLabel: "لوحة لكل العمليات",
  },
];

const FEATURE_ICONS = [BookOpenCheck, Fingerprint, BellRing, QrCode, HeartHandshake, BarChart3];

const SCHOOL_TEAMS: Array<{ label: string; icon: LucideIcon }> = [
  { label: "شؤون الطلاب", icon: GraduationCap },
  { label: "الهيئة التعليمية", icon: UsersRound },
  { label: "الإرشاد الطلابي", icon: HeartHandshake },
  { label: "القيادة المدرسية", icon: BarChart3 },
];

const JOURNEY_STEPS = [
  { n: "01", t: "أنشئ المدرسة", d: "أدخل بيانات المدرسة والمدير، واختر الباقة العامة المناسبة." },
  { n: "02", t: "اضبط التشغيل", d: "أكمل العام الدراسي والجداول، ثم استورد المعلمين والطلاب." },
  { n: "03", t: "تابع بثقة", d: "ابدأ التحضير، راقب المؤشرات، واتخذ الإجراء من نفس المساحة." },
];

function planHighlights(plan: PublicPlan) {
  const items: string[] = [];
  const students = plan.entitlements.MAX_STUDENTS;
  const staff = plan.entitlements.MAX_STAFF;
  const devices = plan.entitlements.MAX_DEVICES;
  if (typeof students === "number") items.push(`حتى ${students.toLocaleString("ar-SA")} طالب`);
  if (typeof staff === "number") items.push(`حتى ${staff.toLocaleString("ar-SA")} موظف`);
  if (typeof devices === "number" && devices > 0) items.push(`${devices.toLocaleString("ar-SA")} أجهزة حضور`);
  const accessLabel = Number(plan.price_amount) > 0 && plan.trial_days > 0
    ? "تشغيل كامل خلال التجربة"
    : "تشغيل كامل طوال مدة الباقة";
  return [...items, accessLabel, "دعم فني باللغة العربية"].slice(0, 4);
}

function planContactUrl(planName: string) {
  const message = `السلام عليكم، أرغب في الاشتراك في ${planName} لمنصة المواظبة XMANSX.`;
  return `https://wa.me/966537720207?text=${encodeURIComponent(message)}`;
}

function ProductPreview() {
  return (
    <div className="landing-product relative mx-auto w-full max-w-[42rem]" aria-label="نموذج توضيحي للوحة منصة المواظبة">
      <div className="absolute -inset-12 -z-10 rounded-full bg-teal-400/10 blur-3xl" />
      <div className="overflow-hidden rounded-[1.75rem] border border-white/15 bg-[#0a211d]/92 p-2 shadow-[0_40px_100px_rgba(0,0,0,0.38)] backdrop-blur-xl sm:p-3">
        <div className="flex items-center justify-between border-b border-white/10 px-3 py-3 sm:px-5">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-emerald-400" />
            <span className="text-xs font-bold text-white">ثانوية الإتقان</span>
          </div>
          <span className="rounded-full bg-white/8 px-3 py-1 text-[11px] text-teal-100">اليوم الدراسي مباشر</span>
        </div>
        <div className="grid min-h-[25rem] grid-cols-[4.25rem_1fr] sm:grid-cols-[9rem_1fr]">
          <div className="border-l border-white/8 p-2.5 sm:p-4">
            <div className="mb-5 grid size-9 place-items-center rounded-xl bg-teal-400 text-slate-950"><Building2 size={17} /></div>
            <div className="space-y-2">
              {FEATURE_ICONS.map((Icon, index) => (
                <div key={index} className={`flex h-10 items-center gap-2 rounded-xl px-2.5 ${index === 0 ? "bg-white/10 text-teal-200" : "text-slate-500"}`}>
                  <Icon size={16} />
                  <span className="hidden text-[11px] font-bold sm:inline">{["لوحة الإدارة", "الحضور", "الإنذارات", "رموز QR", "الإرشاد", "التقارير"][index]}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="min-w-0 bg-[#f4f8f7] p-3 text-slate-900 sm:p-5">
            <div className="mb-5 flex items-start justify-between gap-3">
              <div><p className="text-[10px] font-bold text-teal-700">مركز المتابعة</p><p className="mt-1 text-sm font-black sm:text-base">صباح الخير، أ. ريم</p></div>
              <span className="grid size-9 place-items-center rounded-xl bg-white text-teal-800 shadow-sm"><BellRing size={15} /></span>
            </div>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {[{ n: "24/28", l: "فصل مكتمل", c: "text-teal-700" }, { n: "96%", l: "حضور اليوم", c: "text-emerald-700" }, { n: "4", l: "تحتاج متابعة", c: "text-amber-700" }].map((item) => (
                <div key={item.l} className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm last:col-span-2 sm:last:col-span-1">
                  <p className={`text-lg font-black ${item.c}`}>{item.n}</p><p className="mt-1 text-[10px] text-slate-500">{item.l}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
              <div className="mb-4 flex items-center justify-between"><p className="text-xs font-black">اكتمال التحضير</p><span className="text-[10px] text-slate-400">آخر 6 حصص</span></div>
              <div className="flex h-24 items-end gap-2" aria-hidden="true">
                {[54, 72, 64, 88, 78, 96].map((height, index) => <span key={index} style={{ height: `${height}%` }} className="flex-1 rounded-t-md bg-gradient-to-t from-teal-700 to-teal-300" />)}
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700"><Sparkles size={15} /></span>
              <div className="min-w-0"><p className="text-[11px] font-black">تنبيه ذكي للإدارة</p><p className="mt-0.5 truncate text-[10px] text-slate-500">فصلان لم يكتمل تحضيرهما بعد</p></div>
            </div>
          </div>
        </div>
      </div>
      <div className="landing-float absolute -bottom-5 -left-2 rounded-2xl border border-white/15 bg-white/95 p-3 text-slate-900 shadow-2xl sm:-left-6 sm:p-4">
        <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><ShieldCheck size={19} /></span><div><p className="text-xs font-black">بيانات مدرستك معزولة</p><p className="mt-0.5 text-[10px] text-slate-500">صلاحيات دقيقة وسجل تدقيق</p></div></div>
      </div>
    </div>
  );
}

export function LandingPage() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeFeature, setActiveFeature] = useState(FEATURES[0]!.id);
  const plans = useQuery({ queryKey: ["public-plans"], queryFn: ({ signal }) => getPublicPlans(signal), staleTime: 5 * 60_000 });
  const selectedFeature = FEATURES.find((feature) => feature.id === activeFeature) ?? FEATURES[0]!;
  const FeatureIcon = selectedFeature.icon;

  return (
    <main className="landing-page min-h-dvh overflow-hidden bg-[#061916] text-white">
      <a href="#landing-content" className="skip-link">الانتقال إلى المحتوى</a>
      <header className="fixed inset-x-0 top-0 z-50 px-3 pt-3 sm:px-5">
        <nav aria-label="التنقل العام" className="mx-auto flex h-16 max-w-7xl items-center gap-6 rounded-2xl border border-white/10 bg-[#061916]/88 px-4 shadow-[0_12px_40px_rgba(0,0,0,0.18)] backdrop-blur-xl sm:px-5 lg:px-6">
          <Link to="/" className="flex min-h-11 items-center gap-3" aria-label="منصة المواظبة — الرئيسية">
            <span className="grid size-10 place-items-center rounded-xl bg-teal-400 text-slate-950"><Building2 size={20} strokeWidth={2.4} /></span>
            <span><strong className="block text-sm font-black">منصة المواظبة</strong><span className="block text-[10px] text-teal-100/60">إدارة مدرسية بوضوح</span></span>
          </Link>
          <div className="hidden flex-1 items-center justify-center gap-7 text-sm font-bold text-slate-300 lg:flex">
            <a href="#capabilities" className="min-h-11 content-center hover:text-white">المنصة</a><a href="#journey" className="min-h-11 content-center hover:text-white">كيف تبدأ</a><a href="#plans" className="min-h-11 content-center hover:text-white">الباقات</a>
          </div>
          <div className="ms-auto hidden items-center gap-2 sm:flex">
            <Link to="/login" className="inline-flex min-h-11 items-center justify-center rounded-xl px-4 text-sm font-bold text-white hover:bg-white/8">تسجيل الدخول</Link>
            <Link to="/register" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-400 px-5 text-sm font-black text-slate-950 transition hover:-translate-y-0.5 hover:bg-teal-300">ابدأ مدرستك <ArrowLeft size={16} /></Link>
          </div>
          <button type="button" className="ms-auto grid size-11 place-items-center rounded-xl border border-white/10 bg-white/5 sm:hidden" aria-label={mobileNavOpen ? "إغلاق القائمة" : "فتح القائمة"} aria-expanded={mobileNavOpen} aria-controls="mobile-navigation" onClick={() => setMobileNavOpen((value) => !value)}>{mobileNavOpen ? <X size={20} /> : <Menu size={20} />}</button>
        </nav>
        {mobileNavOpen && <div id="mobile-navigation" className="mx-auto mt-2 max-w-7xl rounded-2xl border border-white/10 bg-[#08211d]/98 p-4 shadow-2xl backdrop-blur-xl sm:hidden"><div className="grid gap-2 text-sm font-bold"><a onClick={() => setMobileNavOpen(false)} href="#capabilities" className="flex min-h-11 items-center rounded-xl px-3 hover:bg-white/5">المنصة</a><a onClick={() => setMobileNavOpen(false)} href="#journey" className="flex min-h-11 items-center rounded-xl px-3 hover:bg-white/5">كيف تبدأ</a><a onClick={() => setMobileNavOpen(false)} href="#plans" className="flex min-h-11 items-center rounded-xl px-3 hover:bg-white/5">الباقات</a><Link to="/login" className="flex min-h-11 items-center rounded-xl px-3 hover:bg-white/5">تسجيل الدخول</Link><Link to="/register" className="mt-2 flex min-h-12 items-center justify-center rounded-xl bg-teal-400 px-4 text-slate-950">ابدأ مدرستك</Link></div></div>}
      </header>

      <div id="landing-content" tabIndex={-1}>
        <section className="landing-hero relative isolate px-4 pb-24 pt-36 sm:px-6 sm:pb-32 sm:pt-44 lg:px-8">
          <div className="landing-grid absolute inset-0 -z-20 opacity-30" />
          <div className="absolute -right-48 top-16 -z-10 size-[32rem] rounded-full bg-teal-500/12 blur-[110px]" />
          <div className="mx-auto grid max-w-7xl items-center gap-20 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="max-w-2xl">
              <p className="mb-6 inline-flex min-h-9 items-center gap-2 rounded-full border border-teal-300/20 bg-teal-300/8 px-4 text-xs font-bold text-teal-200"><span className="size-1.5 rounded-full bg-teal-300 shadow-[0_0_12px_#5eead4]" /> منصة تشغيل يومية للمدرسة</p>
              <h1 className="text-4xl font-black leading-[1.25] tracking-[-0.035em] sm:text-6xl lg:text-[4.35rem]">كل تفاصيل المواظبة.<br /><span className="landing-shimmer">في صورة واحدة واضحة.</span></h1>
              <p className="mt-7 max-w-xl text-base leading-8 text-slate-300 sm:text-lg">منصة عربية تجمع الحضور والمتابعة الطلابية والإجراءات والتقارير؛ لتعمل الإدارة والمعلم والإرشاد من مساحة واحدة، بثقة وسرعة.</p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link to="/register" className="inline-flex min-h-13 items-center justify-center gap-2 rounded-2xl bg-teal-400 px-7 text-base font-black text-slate-950 shadow-[0_14px_45px_rgba(45,212,191,0.2)] transition hover:-translate-y-1 hover:bg-teal-300">أنشئ مدرستك الآن <ArrowLeft size={19} /></Link>
                <a href="#capabilities" className="inline-flex min-h-13 items-center justify-center rounded-2xl border border-white/12 bg-white/5 px-7 text-base font-bold text-white transition hover:bg-white/9">استكشف المنصة</a>
              </div>
              <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-slate-400"><span className="flex items-center gap-2"><Check size={16} className="text-teal-300" /> تجربة دون بطاقة دفع</span><span className="flex items-center gap-2"><Check size={16} className="text-teal-300" /> إعداد ذاتي سريع</span><span className="flex items-center gap-2"><Check size={16} className="text-teal-300" /> دعم عربي</span></div>
            </div>
            <ProductPreview />
          </div>
        </section>

        <section aria-label="فرق المدرسة المستفيدة" className="border-y border-white/8 bg-white/[0.025] px-4 py-6 sm:px-6">
          <div className="mx-auto grid max-w-7xl gap-3 sm:grid-cols-2 lg:grid-cols-[auto_repeat(4,1fr)] lg:items-center">
            <div className="px-2 py-2"><p className="text-xs font-black text-teal-300">تشغيل مدرسي موحّد</p><p className="mt-1 text-sm text-slate-500">مساحة واحدة لكل فريق</p></div>
            {SCHOOL_TEAMS.map(({ icon: ItemIcon, label }) => <div key={label} className="flex min-h-16 items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.035] px-4 text-sm font-bold text-slate-300"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-teal-300/10 text-teal-300"><ItemIcon size={18} /></span>{label}</div>)}
          </div>
        </section>

        <section id="capabilities" className="scroll-mt-20 bg-[#f4f8f7] px-4 py-24 text-slate-900 sm:px-6 lg:px-8 lg:py-32">
          <div className="mx-auto max-w-7xl">
            <div className="max-w-2xl"><p className="text-sm font-black text-teal-700">منصة تنمو مع يومك المدرسي</p><h2 className="mt-4 text-3xl font-black leading-tight sm:text-5xl">ليست سجلاً للحضور فقط.<br />إنها دورة متابعة متكاملة.</h2><p className="mt-5 text-base leading-8 text-slate-600">اختر المحور لترى كيف تتحول البيانات اليومية إلى عمل واضح بين فريق المدرسة.</p></div>
            <div className="mt-12 grid gap-6 lg:grid-cols-[0.82fr_1.18fr]">
              <div role="tablist" aria-label="محاور المنصة" className="space-y-3">{FEATURES.map((feature, index) => { const Icon = feature.icon; const active = feature.id === activeFeature; return <button key={feature.id} id={`feature-tab-${feature.id}`} type="button" role="tab" aria-controls="feature-panel" aria-selected={active} onClick={() => setActiveFeature(feature.id)} className={`flex min-h-20 w-full items-center gap-4 rounded-2xl border p-4 text-start transition ${active ? "border-teal-200 bg-white shadow-[0_18px_50px_rgba(15,118,110,0.1)]" : "border-transparent bg-transparent hover:border-slate-200 hover:bg-white/70"}`}><span className={`grid size-11 shrink-0 place-items-center rounded-xl ${active ? "bg-teal-700 text-white" : "bg-slate-200/70 text-slate-600"}`}><Icon size={20} /></span><span className="min-w-0 flex-1"><span className="block text-xs font-bold text-teal-700">{feature.eyebrow}</span><span className="mt-1 block font-black">{feature.title}</span></span><span className="text-xs font-black text-slate-300">0{index + 1}</span><ChevronLeft size={18} className={active ? "text-teal-700" : "text-slate-300"} /></button>; })}</div>
              <article id="feature-panel" aria-labelledby={`feature-tab-${selectedFeature.id}`} role="tabpanel" className="relative overflow-hidden rounded-[2rem] bg-[#09231f] p-6 text-white shadow-[0_30px_70px_rgba(7,27,25,0.2)] sm:p-10">
                <div className="absolute -left-24 -top-24 size-72 rounded-full bg-teal-400/12 blur-3xl" />
                <div className="relative"><span className="grid size-14 place-items-center rounded-2xl bg-teal-300 text-slate-950"><FeatureIcon size={26} /></span><p className="mt-8 text-sm font-bold text-teal-200">{selectedFeature.eyebrow}</p><h3 className="mt-2 text-2xl font-black sm:text-3xl">{selectedFeature.title}</h3><p className="mt-5 max-w-xl text-base leading-8 text-slate-300">{selectedFeature.description}</p><ul className="mt-8 grid gap-3 sm:grid-cols-2">{selectedFeature.points.map((point) => <li key={point} className="flex min-h-12 items-center gap-3 rounded-xl border border-white/8 bg-white/5 px-4 text-sm font-bold"><Check size={17} className="text-teal-300" />{point}</li>)}</ul><div className="mt-10 flex items-end justify-between border-t border-white/10 pt-7"><div><p className="text-4xl font-black text-teal-300">{selectedFeature.stat}</p><p className="mt-1 text-xs text-slate-400">{selectedFeature.statLabel}</p></div><span className="rounded-full border border-white/10 px-4 py-2 text-xs text-slate-400">يتغير حسب المحور</span></div></div>
              </article>
            </div>
          </div>
        </section>

        <section id="journey" className="scroll-mt-20 px-4 py-24 sm:px-6 lg:px-8 lg:py-32"><div className="mx-auto max-w-7xl"><div className="mx-auto max-w-3xl text-center"><p className="text-sm font-black text-teal-300">ابدأ بلا تعقيد</p><h2 className="mt-4 text-3xl font-black sm:text-5xl">من التسجيل إلى التشغيل في رحلة واضحة</h2><p className="mt-5 text-base leading-8 text-slate-400">ثلاث خطوات عملية تنقل مدرستك من الإعداد الأول إلى متابعة اليوم الدراسي.</p></div><div className="relative mt-14 grid gap-4 md:grid-cols-3"><div className="absolute inset-x-[16%] top-12 hidden h-px bg-gradient-to-l from-transparent via-teal-300/35 to-transparent md:block" aria-hidden="true" />{JOURNEY_STEPS.map((step) => <article key={step.n} className="group relative overflow-hidden rounded-[1.75rem] border border-white/9 bg-white/[0.045] p-7 transition hover:-translate-y-1 hover:border-teal-300/25 hover:bg-white/[0.065]"><span className="absolute -left-2 -top-5 text-8xl font-black text-white/[0.025]" aria-hidden="true">{step.n}</span><span className="relative grid size-11 place-items-center rounded-2xl border border-teal-300/20 bg-teal-300/8 text-sm font-black text-teal-300">{step.n}</span><h3 className="relative mt-8 text-xl font-black">{step.t}</h3><p className="relative mt-3 text-sm leading-7 text-slate-400">{step.d}</p></article>)}</div><a href="#plans" className="mx-auto mt-8 flex w-fit min-h-11 items-center gap-2 text-sm font-black text-teal-300 hover:text-teal-200">استعرض الباقات المتاحة <ArrowLeft size={16} /></a></div></section>

        <section id="plans" className="scroll-mt-20 bg-[#f4f8f7] px-4 py-24 text-slate-900 sm:px-6 lg:px-8 lg:py-32">
          <div className="mx-auto max-w-7xl">
            <div className="mx-auto max-w-3xl text-center">
              <p className="text-sm font-black text-teal-700">اختر ما يناسب مدرستك</p>
              <h2 className="mt-3 text-3xl font-black sm:text-5xl">باقات واضحة، وبداية أسهل</h2>
            </div>
            {plans.isPending ? (
              <div className="mt-12 grid gap-5 md:grid-cols-2" aria-label="جاري تحميل الباقات"><div className="h-80 animate-pulse rounded-[2rem] bg-slate-200" /><div className="h-80 animate-pulse rounded-[2rem] bg-slate-200" /></div>
            ) : plans.isError ? (
              <div className="mx-auto mt-12 max-w-xl rounded-3xl border border-amber-200 bg-white p-8 text-center shadow-sm"><span className="mx-auto grid size-12 place-items-center rounded-2xl bg-amber-50 text-amber-700"><CircleAlert size={22} /></span><h3 className="mt-4 text-xl font-black">تعذر تحميل الباقات الآن</h3><p className="mt-2 text-sm leading-7 text-slate-600">تحقق من اتصالك ثم أعد المحاولة، أو تواصل معنا لمساعدتك في اختيار الباقة.</p><button type="button" onClick={() => void plans.refetch()} className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-black text-white hover:bg-teal-800"><RefreshCw size={16} /> إعادة المحاولة</button></div>
            ) : plans.data && plans.data.length > 0 ? (
              <div className={`mt-12 grid gap-5 ${plans.data.length === 1 ? "mx-auto max-w-md" : plans.data.length === 2 ? "mx-auto max-w-4xl md:grid-cols-2" : "md:grid-cols-2 xl:grid-cols-3"}`} aria-label="باقات المنصة">
                {plans.data.map((plan, index) => {
                  const isFree = Number(plan.price_amount) === 0;
                  const duration = formatPlanDuration(plan.duration_value, plan.duration_unit);
                  return (
                    <article key={plan.id} className={`group relative flex flex-col rounded-[2rem] border bg-white p-7 shadow-sm transition duration-300 hover:-translate-y-1 hover:shadow-[0_24px_60px_rgba(15,118,110,0.12)] ${index === 0 ? "border-teal-300 ring-4 ring-teal-100/60" : "border-slate-200 hover:border-teal-200"}`}>
                      {index === 0 && <span className="absolute -top-3 right-7 rounded-full bg-teal-700 px-4 py-1.5 text-xs font-black text-white">الخيار المقترح</span>}
                      <div className="flex items-center justify-between gap-3"><p className="text-sm font-black text-teal-700">{plan.name}</p><span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-black text-slate-500">{isFree ? "بدء مجاني" : plan.can_self_register ? "تسجيل مباشر" : "بطلب اشتراك"}</span></div>
                      <div className="mt-6 flex items-end gap-2"><strong className="text-4xl font-black tracking-tight">{isFree ? "مجانية" : Number(plan.price_amount).toLocaleString("ar-SA")}</strong>{!isFree && <span className="mb-1 text-sm font-bold text-slate-500">{plan.currency}</span>}</div>
                      <div className="mt-4 flex flex-wrap gap-2"><p className="inline-flex w-fit rounded-full bg-teal-50 px-3 py-1.5 text-sm font-black text-teal-800">مدة الباقة: {duration}</p>{plan.one_time_per_school && <p className="inline-flex rounded-full bg-amber-50 px-3 py-1.5 text-xs font-black text-amber-700">لمرة واحدة لكل مدرسة</p>}</div>
                      <p className="mt-4 min-h-14 text-sm leading-7 text-slate-600">{plan.description || "كل ما تحتاجه مدرستك لبدء المواظبة والمتابعة من مساحة موحدة."}</p>
                      <div className="my-6 h-px bg-slate-100" />
                      <ul className="flex-1 space-y-3">{planHighlights(plan).map((item) => <li key={item} className="flex items-center gap-2 text-sm font-semibold text-slate-700"><span className="grid size-6 place-items-center rounded-full bg-teal-50 text-teal-700"><Check size={14} /></span>{item}</li>)}</ul>
                      {plan.can_self_register ? (
                        <Link to={`/register?plan=${plan.id}`} className="mt-7 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-black text-white transition group-hover:bg-teal-800">{isFree ? `ابدأ مجانًا لمدة ${duration}` : plan.trial_days > 0 ? `ابدأ تجربة ${plan.trial_days.toLocaleString("ar-SA")} يومًا` : "ابدأ التسجيل"} <ArrowLeft size={16} /></Link>
                      ) : (
                        <a href={planContactUrl(plan.name)} target="_blank" rel="noreferrer" className="mt-7 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-black text-white transition group-hover:bg-teal-800">اطلب هذه الباقة <ArrowLeft size={16} /></a>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="mt-12 rounded-3xl border border-slate-200 bg-white p-8 text-center"><h3 className="text-xl font-black">سيتم إعلان الباقات قريبًا</h3><p className="mt-2 text-sm text-slate-600">تواصل معنا لتجهيز مدرستك وخطة التشغيل المناسبة.</p><a href={WHATSAPP_URL} target="_blank" rel="noreferrer" className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-teal-700 px-5 text-sm font-black text-white">تواصل معنا</a></div>
            )}
          </div>
        </section>

        <section className="px-4 py-24 sm:px-6 lg:px-8"><div className="relative mx-auto max-w-7xl overflow-hidden rounded-[2.5rem] border border-teal-300/18 bg-gradient-to-l from-teal-300 to-emerald-300 p-8 text-slate-950 sm:p-12 lg:p-16"><div className="landing-grid absolute inset-0 opacity-15" /><div className="relative max-w-3xl"><p className="text-sm font-black">خطوتك التالية بسيطة</p><h2 className="mt-4 text-3xl font-black leading-tight sm:text-5xl">اجعل يوم مدرستك أوضح من أول حصة.</h2><p className="mt-5 max-w-2xl text-base leading-8 text-slate-800">أنشئ مدرستك، ادخل مباشرة إلى لوحة التشغيل، وأكمل الإعداد وفق خطوات جاهزية واضحة.</p><div className="mt-8 flex flex-col gap-3 sm:flex-row"><Link to="/register" className="inline-flex min-h-13 items-center justify-center gap-2 rounded-2xl bg-slate-950 px-7 font-black text-white">أنشئ مدرستك الآن <ArrowLeft size={18} /></Link><a href={WHATSAPP_URL} target="_blank" rel="noreferrer" className="inline-flex min-h-13 items-center justify-center rounded-2xl border border-slate-950/15 bg-white/45 px-7 font-black">تحدث مع فريقنا</a></div></div></div></section>
      </div>

      <footer className="border-t border-white/8 px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-5 text-center sm:flex-row sm:text-start"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-teal-400 text-slate-950"><Building2 size={20} /></span><div><p className="text-sm font-black">منصة المواظبة</p><p className="mt-0.5 text-xs text-slate-500">تشغيل مدرسي أكثر وضوحًا</p></div></div><div className="flex flex-wrap justify-center gap-5 text-sm font-semibold text-slate-400"><Link to="/login" className="hover:text-white">تسجيل الدخول</Link><Link to="/register" className="hover:text-white">تسجيل مدرسة</Link><a href={WHATSAPP_URL} target="_blank" rel="noreferrer" className="hover:text-white">تواصل معنا</a></div><p className="text-xs text-slate-600">© {new Date().getFullYear()} XMANSX</p></div></footer>
    </main>
  );
}
