// Faithfully extracted from origin/main ParentShell + ChildrenCards. API/auth/router boundary replaced only in this isolated preview.
import { Bell, BookOpenCheck, GraduationCap, HeartHandshake, Home, LogOut, NotebookPen, UserRound } from "lucide-react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { Button } from "./_Button";
import { Badge } from "./_Badge";
import { PageHeader } from "./_PageHeader";
import { Pagination } from "./_Pagination";
import { DayBadge, RELATION_LABELS, dateTime, surface } from "./_shared";
import { demoChildren } from "./_fixtures";
import "./_group.css";
function Link({to,children,...props}:AnchorHTMLAttributes<HTMLAnchorElement> & {to:string}) { return <a {...props} href="#" onClick={e=>{e.preventDefault();window.alert("هذه معاينة ببيانات توضيحية. المسار الأصلي: "+to);}}>{children}</a>; }
function NavLink({to,end:_,className,children}:{to:string;end?:boolean;className:(s:{isActive:boolean})=>string;children:ReactNode}) {return <Link to={to} className={className({isActive:to==="/parent"})}>{children}</Link>;}
function PageSkeleton({label}:{label:string}) { return <p>{label}</p>; }
function ErrorState({error:_}:{error:unknown}) { return <p>تعذر التحميل</p>; }
function EmptyState({title,description}:{icon:unknown;title:string;description:string}) {return <div><h2>{title}</h2><p>{description}</p></div>;}
const links = [
  { to: "/parent", label: "أبنائي", Icon: Home },
  { to: "/parent/attendance", label: "المواظبة", Icon: BookOpenCheck },
  { to: "/parent/requests", label: "طلباتي", Icon: NotebookPen },
  { to: "/parent/notifications", label: "التنبيهات", Icon: Bell },
  { to: "/parent/account", label: "حسابي", Icon: UserRound },
];
export function Current() {
  return (
    <div dir="rtl" className="parent-current min-h-dvh bg-[#f4f8f6]" data-testid="parent-shell">
      <a href="#parent-content" className="skip-link">
        الانتقال إلى المحتوى
      </a>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-teal-800 text-white">
            <HeartHandshake aria-hidden size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-black">بوابة ولي الأمر</p>
            <p className="truncate text-xs text-slate-500">محمد ولي الأمر</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="تسجيل الخروج"
            onClick={() => window.alert("معاينة مستقلة — لم يتم تسجيل خروج أي حساب.")}
          >
            <LogOut aria-hidden size={19} />
          </Button>
        </div>
      </header>
      <nav
        aria-label="تنقل بوابة ولي الأمر"
        className="sticky top-[69px] z-20 border-b border-slate-200 bg-white"
      >
        <div className="mx-auto grid max-w-6xl grid-cols-5 px-2">
          {links.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/parent"}
              className={({ isActive }) =>
                `flex min-h-14 flex-col items-center justify-center gap-1 border-b-2 px-1 py-2 text-xs font-bold sm:flex-row sm:gap-2 sm:text-sm ${isActive ? "border-teal-700 bg-teal-50 text-teal-900" : "border-transparent text-slate-500 hover:bg-slate-50"}`
              }
            >
              <Icon aria-hidden size={17} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
      <main
        id="parent-content"
        className="mx-auto w-full max-w-6xl px-3 py-5 sm:px-6 sm:py-8"
        tabIndex={-1}
      >
        <ChildrenCards attendance={false} />
      </main>
    </div>
  );
}

function ChildrenCards({ attendance }: { attendance: boolean }) {
  const page = 1;
  const setPage = () => {};
  const children = { isPending: false, isError: false, isSuccess: true, error: null, data: { results: demoChildren, next: null, previous: null } };
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
