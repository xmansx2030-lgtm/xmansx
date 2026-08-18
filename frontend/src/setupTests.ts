import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// الجهاز يشغل Docker أثناء الاختبارات — مهلة أوسع لـ findBy/waitFor ضد الوميض الزمني
configure({ asyncUtilTimeout: 4000 });
