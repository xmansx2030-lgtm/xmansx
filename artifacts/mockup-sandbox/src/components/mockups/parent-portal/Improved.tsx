import { useEffect, useRef, useState } from "react";
import { Bell, BookOpenCheck, CalendarDays, Check, ChevronLeft, CircleAlert, CircleHelp, Clock3, GraduationCap, HeartHandshake, Home, Info, NotebookPen, School, UserRound, X } from "lucide-react";
import { demoChildren } from "./_fixtures";
import { dateTime, dayLabel, isIncomplete, RELATION_LABELS } from "./_shared";
import "./_group.css";
import "./_improved.css";

type Panel = { title: string; description: string; items?: { title: string; detail: string }[] } | null;
const navItems = [
  { key: "children", label: "أبنائي", Icon: Home },
  { key: "attendance", label: "المواظبة", Icon: BookOpenCheck },
  { key: "requests", label: "طلباتي", Icon: NotebookPen },
  { key: "notifications", label: "التنبيهات", Icon: Bell },
  { key: "account", label: "حسابي", Icon: UserRound },
];

function dateLabel() {
  const demoDate = demoChildren.find((child) => child.today)?.today?.date;
  return new Intl.DateTimeFormat("ar-SA", { dateStyle: "full", calendar: "gregory", timeZone: "Asia/Riyadh" }).format(new Date(`${demoDate}T12:00:00+03:00`));
}

export function Improved() {
  const [panel, setPanel] = useState<Panel>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!panel) return;
    previousFocus.current = document.activeElement as HTMLElement;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPanel(null);
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button,[href],[tabindex]:not([tabindex='-1'])")).filter((el) => !el.hasAttribute("disabled"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus.current?.focus();
    };
  }, [panel]);

  const openPanel = (next: NonNullable<Panel>) => setPanel(next);
  const openRequiredAction = () => openPanel({
    title: "الإجراء المطلوب لسارة",
    description: "يوجد إجراء واحد مطلوب مرتبط بمدرسة الأمل المتوسطة.",
    items: [
      { title: "مراجعة إشعار المدرسة", detail: "تفاصيل الإجراء تُعرض في إشعار المدرسة داخل البوابة الأصلية، وليست طلب ربط جديدًا." },
      { title: "معاينة فقط", detail: "هذه المعاينة لا تتصل بالمدرسة، ولا تسجل اطلاعًا أو إقرارًا أو إتمامًا للإجراء." },
    ],
  });
  const navPanel = (key: string) => {
    if (key === "children") return;
    const copy: Record<string, Panel> = {
      attendance: { title: "المواظبة", description: "اختر أحد أبنائك للاطلاع على حالة اليوم. هذه المعاينة لا تتصل بسجل المدرسة.", items: demoChildren.filter((child) => child.status === "ACTIVE" && child.student).map((child) => ({ title: child.student!.full_name, detail: `${child.school.name} · ${dayLabel(child.today)}` })) },
      requests: { title: "طلباتي", description: "عرض الطلبات وتقديمها يتم عبر بوابة المدرسة. لا يمكن إرسال طلب من هذه المعاينة.", items: [{ title: "طلبات ولي الأمر", detail: "استخدم رابط التسجيل الذي تزودك به المدرسة لبدء طلب ربط جديد." }] },
      notifications: { title: "التنبيهات الجديدة", description: "تنبيهان جديدان مرتبطان بسارة. الإشعارات منفصلة عن الإجراءات المطلوبة.", items: [{ title: "تحديث المواظبة", detail: "يوجد تحديث جديد في سجل المواظبة. افتح سجل سارة للاطلاع." }, { title: "إشعار من المدرسة", detail: "لديك تنبيه جديد مرتبط بمدرسة الأمل المتوسطة." }] },
      account: { title: "حساب ولي الأمر", description: "معلومات الحساب وإعداداته تُدار في البوابة الأصلية. هذه شاشة تصميم ببيانات اصطناعية.", items: [{ title: "محمد ولي الأمر", detail: "بيانات الحساب الحقيقية غير متاحة في هذه المعاينة." }] },
    };
    openPanel(copy[key] ?? { title: "بوابة ولي الأمر", description: "هذه الميزة غير متاحة في المعاينة." });
  };
  const openChild = (name: string, school: string, status: string, update: string | null, incomplete: boolean) => openPanel({
    title: `مواظبة ${name}`,
    description: `${school} · ${status}`,
    items: [
      { title: incomplete ? "بانتظار حالة يومية معتمدة" : status, detail: incomplete ? "لم تتوفر حالة يومية معتمدة بعد. لا يمكن الجزم بالحضور أو الغياب حتى تسجل المدرسة الحالة الرسمية." : `حالة اليوم حسب آخر تحديث معتمد · ${update ? dateTime(update) : "لم يسجل تحديث اليوم"}` },
      { title: "عرض سجل المواظبة", detail: "السجل الكامل متاح في البوابة الأصلية. لم نعرض بيانات غير موجودة في هذه المعاينة." },
    ],
  });

  return (
    <div className="parent-improved" dir="rtl">
      <a className="skip-link" href="#pi-main">الانتقال إلى المحتوى</a>
      <header className="pi-topbar">
        <div className="pi-wrap pi-topbar-inner">
          <span className="pi-brand-mark" aria-hidden="true"><HeartHandshake size={22} /></span>
          <div className="pi-brand-copy"><strong>منصة المواظبة</strong><span>بوابة ولي الأمر</span></div>
          <div className="pi-header-spacer" />
          <span className="pi-preview-chip"><i className="pi-preview-dot" />معاينة تصميم · بيانات توضيحية</span>
          <div className="pi-account"><span className="pi-account-avatar">م</span><span>محمد ولي الأمر</span></div>
        </div>
      </header>
      <nav className="pi-nav" aria-label="تنقل بوابة ولي الأمر">
        <div className="pi-wrap pi-nav-inner">
          {navItems.map(({ key, label, Icon }) => <button key={key} type="button" aria-current={key === "children" ? "page" : undefined} onClick={() => navPanel(key)}>
            <Icon size={17} aria-hidden="true" />{label}{key === "notifications" && <span className="pi-nav-count" aria-label="تنبيهان جديدان">٢</span>}
          </button>)}
        </div>
      </nav>
      <main className="pi-wrap pi-main" id="pi-main" tabIndex={-1}>
        <div className="pi-heading-row">
          <div>
            <div className="pi-eyebrow"><span className="pi-eyebrow-line" />متابعة الأسرة</div>
            <h1>أبنائي</h1>
            <p>اطمئن على حالة اليوم، واعرف ما يحتاج إلى متابعة.</p>
          </div>
          <div className="pi-date"><CalendarDays size={15} aria-hidden="true" />اليوم<strong>{dateLabel()}</strong></div>
        </div>
        <section className="pi-focus" aria-labelledby="pi-focus-title">
          <div className="pi-focus-content">
            <span className="pi-focus-icon"><Info size={20} aria-hidden="true" /></span>
            <div><h2 id="pi-focus-title">متابعة واحدة بانتظارك</h2><p>لدى سارة إجراء مطلوب من المدرسة، وهناك تنبيهان جديدان للاطلاع. يمكنك مراجعة كل منهما على حدة.</p></div>
          </div>
          <div className="pi-focus-actions">
            <button className="pi-btn pi-btn-primary" type="button" onClick={openRequiredAction}><NotebookPen size={16} />الإجراء المطلوب</button>
            <button className="pi-btn pi-btn-soft" type="button" onClick={() => navPanel("notifications")}><Bell size={16} />التنبيهات <span>٢</span></button>
          </div>
        </section>
        <div className="pi-section-head">
          <div className="pi-section-title"><h2>حالة الأبناء</h2><span>٢ علاقة معتمدة</span></div>
          <button className="pi-btn pi-btn-soft" type="button" onClick={() => openPanel({ title: "إضافة ابن", description: "تبدأ إضافة ابن من خلال رابط تسجيل أولياء الأمور الذي تزودك به المدرسة.", items: [{ title: "رابط المدرسة", detail: "اطلب رابط التسجيل من المدرسة، ثم قدّم طلب ربط الطالب عبر الرابط الرسمي." }, { title: "حماية البيانات", detail: "لا تبحث هذه المعاينة عن الطلاب ولا تجمع أي بيانات شخصية." }] })}><GraduationCap size={16} />إضافة ابن</button>
        </div>
        <section className="pi-children" aria-label="الأبناء">
          {demoChildren.filter((child) => child.status === "ACTIVE" && child.student).map((child) => {
            const student = child.student!;
            const incomplete = !child.today || isIncomplete(child.today);
            const state = incomplete ? "incomplete" : child.today?.absence_status === "NONE" ? "present" : child.today?.absence_status === "FULL" ? "absent" : "partial";
            const update = child.today?.updated_at ?? null;
            return <article className="pi-child-card" key={child.relation_id}>
              <div className="pi-child-top">
                <span className="pi-avatar" aria-hidden="true">{student.full_name.slice(0, 1)}</span>
                <div className="pi-child-ident"><h3>{student.full_name}</h3><p>{student.grade_name}{student.section_name ? ` · الفصل ${student.section_name}` : ""}</p></div>
                <span className="pi-relation">{RELATION_LABELS[child.status]}</span>
              </div>
              <div className="pi-child-school"><School size={13} style={{ verticalAlign: "-2px", marginInlineEnd: 5 }} />{child.school.name}</div>
              <button className="pi-attendance" type="button" onClick={() => openChild(student.full_name, child.school.name, dayLabel(child.today), update, incomplete)} aria-label={`تفاصيل مواظبة ${student.full_name}: ${dayLabel(child.today)}`}>
                <span className={`pi-state-mark ${state}`}>{incomplete ? <Clock3 size={17} /> : state === "present" ? <Check size={17} /> : <CircleAlert size={17} />}</span>
                <span className="pi-attendance-copy"><strong>{dayLabel(child.today)}</strong><span>{incomplete ? "بانتظار تسجيل المدرسة للحالة الرسمية" : "حالة اليوم حسب آخر تحديث للمدرسة"}</span></span>
                <ChevronLeft className="pi-arrow" size={18} aria-hidden="true" />
              </button>
              <div className="pi-child-meta"><span>آخر تحديث</span><span>{update ? dateTime(update) : "لم يسجل بعد"}</span></div>
              <div className="pi-child-footer">
                <div className="pi-counter notification"><Bell size={15} /><strong>{child.new_notifications ?? 0}</strong><span>تنبيهات جديدة</span></div>
                <div className="pi-counter"><NotebookPen size={15} /><strong>{child.required_actions ?? 0}</strong><span>إجراءات مطلوبة</span></div>
                <button className="pi-btn pi-btn-primary pi-card-action" type="button" onClick={() => openChild(student.full_name, child.school.name, dayLabel(child.today), update, incomplete)}>متابعة المواظبة</button>
              </div>
            </article>;
          })}
          {demoChildren.filter((child) => child.status !== "ACTIVE" || !child.student).map((child) => <article className="pi-pending-card" key={child.relation_id}>
            <div className="pi-pending-top"><span className="pi-pending-icon"><School size={19} /></span><div><h3>علاقة بانتظار المراجعة</h3><span className="pi-child-ident"><p>{child.school.name} · {RELATION_LABELS[child.status]}</p></span></div></div>
            <p>تواصل مع المدرسة لمراجعة العلاقة. لن تظهر بيانات الطالب حتى اعتمادها.</p>
            <button className="pi-btn pi-btn-soft" type="button" onClick={() => openPanel({ title: "مراجعة العلاقة", description: `${child.school.name} · ${RELATION_LABELS[child.status]}`, items: [{ title: "الخطوة التالية", detail: "تواصل مع المدرسة لمتابعة اعتماد العلاقة. بيانات الطالب تبقى مخفية حتى الاعتماد." }] })}><CircleHelp size={15} />كيف أتابع؟</button>
          </article>)}
        </section>
        <div className="pi-bottom-note"><Info size={14} />حالة المواظبة تعتمد على الحالة الرسمية التي تسجلها المدرسة، ولا تعني اكتمال الفترات أن الطالب حاضر تلقائياً.</div>
      </main>
      <nav className="pi-mobile-nav" aria-label="تنقل سريع">
        {navItems.map(({ key, label, Icon }) => <button key={key} type="button" aria-current={key === "children" ? "page" : undefined} onClick={() => navPanel(key)}>
          <Icon size={19} aria-hidden="true" />{label}{key === "notifications" && <span className="pi-nav-count">٢</span>}
        </button>)}
      </nav>
      {panel && <div className="pi-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPanel(null); }}>
        <section className="pi-dialog" role="dialog" aria-modal="true" aria-labelledby="pi-dialog-title" ref={dialogRef}>
          <div className="pi-dialog-head"><div><h2 id="pi-dialog-title">{panel.title}</h2><p>{panel.description}</p></div><button className="pi-icon-button" type="button" ref={closeRef} aria-label="إغلاق النافذة" onClick={() => setPanel(null)}><X size={19} /></button></div>
          {panel.items && <div className="pi-dialog-list">{panel.items.map((item) => <div className="pi-dialog-item" key={item.title}><strong>{item.title}</strong><span>{item.detail}</span></div>)}</div>}
          <div className="pi-dialog-foot"><button className="pi-btn pi-btn-soft" type="button" onClick={() => setPanel(null)}>إغلاق</button></div>
        </section>
      </div>}
    </div>
  );
}
