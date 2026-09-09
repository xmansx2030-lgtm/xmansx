import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// الجهاز ووكيل CI يشغلان ملفات Vitest بالتوازي؛ امنح تحميل React Query
// وقتًا كافيًا قبل اعتبار findBy/waitFor فاشلًا تحت ضغط الموارد.
configure({ asyncUtilTimeout: 8000 });
