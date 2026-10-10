import { ArrowLeft, Building2, Check, ChevronLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { PUBLIC_FEATURES, type PublicFeature } from "@/seo/content";

export function FeaturePage({ feature }: { feature: PublicFeature }) {
  return (
    <main className="min-h-dvh bg-[#f4f8f7] text-slate-900">
      <a href="#feature-content" className="skip-link">الانتقال إلى المحتوى</a>
      <header className="border-b border-slate-200 bg-white px-4 sm:px-6">
        <nav aria-label="التنقل العام" className="mx-auto flex min-h-20 max-w-6xl items-center justify-between gap-3">
          <Link to="/" className="flex min-h-11 items-center gap-2 font-black text-teal-800"><Building2 aria-hidden size={24} />منصة المواظبة</Link>
          <Link to="/login" className="inline-flex min-h-11 items-center rounded-xl bg-teal-700 px-4 text-sm font-bold text-white">تسجيل الدخول</Link>
        </nav>
      </header>
      <div id="feature-content" className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-16" tabIndex={-1}>
        <nav aria-label="مسار الصفحة" className="mb-8 flex flex-wrap items-center gap-2 text-sm text-slate-600"><Link to="/" className="min-h-11 content-center text-teal-800">الرئيسية</Link><ChevronLeft aria-hidden size={16} /><span aria-current="page">{feature.label}</span></nav>
        <section className="max-w-3xl">
          <p className="text-sm font-bold text-teal-700">إدارة مدرسية بواجهة عربية</p>
          <h1 className="mt-4 text-3xl font-black leading-snug sm:text-5xl">{feature.label}</h1>
          <p className="mt-6 text-lg leading-9 text-slate-600">{feature.intro}</p>
          <div className="mt-8 flex flex-wrap gap-3"><Link to="/register" className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-teal-700 px-5 font-bold text-white">سجّل مدرستك <ArrowLeft aria-hidden size={18} /></Link><Link to="/#plans" className="inline-flex min-h-12 items-center rounded-xl border border-teal-700 px-5 font-bold text-teal-800">استعرض الباقات</Link></div>
        </section>
        <div className="mt-14 grid gap-5 lg:grid-cols-3">
          {feature.sections.map((section) => <section key={section.title} className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8"><Check aria-hidden className="text-teal-700" size={24} /><h2 className="mt-5 text-xl font-black leading-8">{section.title}</h2><p className="mt-4 text-base leading-8 text-slate-600">{section.text}</p></section>)}
        </div>
        <section aria-labelledby="feature-faq" className="mt-16 max-w-3xl"><h2 id="feature-faq" className="text-2xl font-black">أسئلة شائعة</h2><div className="mt-6 space-y-4">{feature.questions.map(({ question, answer }) => <details key={question} className="rounded-2xl border border-slate-200 bg-white p-5"><summary className="min-h-11 cursor-pointer content-center font-bold">{question}</summary><p className="mt-3 leading-8 text-slate-600">{answer}</p></details>)}</div></section>
        <nav aria-label="اكتشف خدمات المنصة" className="mt-16 border-t border-slate-200 pt-8"><h2 className="text-xl font-black">اكتشف خدمات المنصة</h2><div className="mt-4 flex flex-wrap gap-3">{PUBLIC_FEATURES.filter((item) => item.path !== feature.path).map((item) => <Link key={item.path} to={item.path} className="min-h-11 content-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-teal-800">{item.label}</Link>)}</div></nav>
      </div>
      <footer className="border-t border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-600"><Link to="/" className="min-h-11 content-center font-bold text-teal-800">منصة المواظبة والمتابعة الطلابية</Link></footer>
    </main>
  );
}
