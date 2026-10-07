import { CalendarDays } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { CalendarTab } from "@/features/settings/tabs/CalendarTab";

export function SchoolCalendarPage() {
  return (
    <div className="ds-page min-w-0" data-testid="school-calendar-page">
      <PageHeader
        icon={CalendarDays}
        eyebrow="التشغيل الدراسي"
        title="التقويم الدراسي"
        description="مواعيد العام والفصول الدراسية، ومصدرها وحالة مزامنتها."
        tone="executive"
      />
      <CalendarTab canWrite={false} />
    </div>
  );
}
