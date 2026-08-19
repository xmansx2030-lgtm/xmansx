import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { ChangeInitialPasswordPage } from "@/features/auth/ChangeInitialPasswordPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireActiveSchool, RequireAuth } from "@/features/auth/guards";
import { SelectSchoolPage } from "@/features/auth/SelectSchoolPage";
import { AnalyticsPage } from "@/features/attendance/AnalyticsPage";
import { AttendanceSessionPage } from "@/features/attendance/AttendanceSessionPage";
import { MonitoringPage } from "@/features/attendance/MonitoringPage";
import { QrScanPage } from "@/features/attendance/QrScanPage";
import { SectionQrPage } from "@/features/attendance/SectionQrPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StaffImportWizard } from "@/features/staff/StaffImportWizard";
import { StaffPage } from "@/features/staff/StaffPage";
import { ImportWizard } from "@/features/students/ImportWizard";
import { InactiveStudentsPage } from "@/features/students/InactiveStudentsPage";
import { StudentsPage } from "@/features/students/StudentsPage";
import { HomePage } from "@/routes/HomePage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { RouteErrorPage } from "@/routes/RouteErrorPage";

export const routes = [
  {
    errorElement: <RouteErrorPage />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/change-password", element: <ChangeInitialPasswordPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: "/select-school", element: <SelectSchoolPage /> },
          {
            element: <RequireActiveSchool />,
            children: [
              {
                path: "/",
                element: <AppShell />,
                children: [
                  { index: true, element: <HomePage /> },
                  { path: "settings", element: <SettingsPage /> },
                  { path: "students", element: <StudentsPage /> },
                  { path: "students/inactive", element: <InactiveStudentsPage /> },
                  { path: "students/import", element: <ImportWizard /> },
                  { path: "staff", element: <StaffPage /> },
                  { path: "staff/import", element: <StaffImportWizard /> },
                  { path: "attendance/section/:sectionId", element: <AttendanceSessionPage /> },
                  { path: "attendance/monitoring", element: <MonitoringPage /> },
                  { path: "attendance/analytics", element: <AnalyticsPage /> },
                  { path: "attendance/qr", element: <SectionQrPage /> },
                  { path: "qr/:token", element: <QrScanPage /> },
                  { path: "*", element: <NotFoundPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
