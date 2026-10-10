import { Link, useRouteError } from "react-router-dom";
import { useEffect } from "react";

import { Button } from "@/components/Button";
import { updatePageSeo } from "@/seo/SeoLayout";

/** صفحة الخطأ العامة للمسارات — لا تعرض تفاصيل تقنية للمستخدم. */
export function RouteErrorPage() {
  useRouteError(); // التفاصيل تبقى في الـ console للمطور فقط
  useEffect(() => { updatePageSeo("/not-found"); }, []);

  return (
    <main dir="rtl" className="flex min-h-dvh items-center justify-center p-6 text-center">
      <div>
        <h1 className="mb-2 text-xl font-bold">حدث خطأ غير متوقع</h1>
        <p className="mb-6 text-slate-600">نعتذر عن ذلك، حاول تحديث الصفحة أو العودة للرئيسية.</p>
        <Link to="/">
          <Button>العودة للرئيسية</Button>
        </Link>
      </div>
    </main>
  );
}
