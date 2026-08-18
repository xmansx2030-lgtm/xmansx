import { Link } from "react-router-dom";

import { Button } from "@/components/Button";

export function NotFoundPage() {
  return (
    <section className="py-16 text-center">
      <p className="mb-2 text-5xl font-black text-slate-300">404</p>
      <h2 className="mb-2 text-xl font-bold">الصفحة غير موجودة</h2>
      <p className="mb-6 text-slate-600">الرابط الذي وصلت إليه غير صحيح أو تم نقله.</p>
      <Link to="/">
        <Button>العودة للرئيسية</Button>
      </Link>
    </section>
  );
}
