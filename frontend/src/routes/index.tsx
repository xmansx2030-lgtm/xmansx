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
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ExcusesPage } from "@/features/excuses/ExcusesPage";
import { CaseDetailPage } from "@/features/counseling/CaseDetailPage";
import { CounselorDashboardPage } from "@/features/counseling/CounselorDashboardPage";
import { TeacherFollowUpPage } from "@/features/counseling/TeacherFollowUpPage";
import { MyReferralsPage } from "@/features/referrals/MyReferralsPage";
import { ReferralsPage } from "@/features/referrals/ReferralsPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { DeviceRosterSyncPage } from "@/features/devices/DeviceRosterSyncPage";
import { DevicesSettingsPage } from "@/features/devices/DevicesSettingsPage";
import { MorningPage } from "@/features/devices/MorningPage";
import { WarningsDashboardPage } from "@/features/warnings/WarningsDashboardPage";
import { StudentAttendanceProfilePage } from "@/features/students/StudentAttendanceProfilePage";
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
                  { path: "dashboard", element: <DashboardPage /> },
                  { path: "settings", element: <SettingsPage /> },
                  { path: "devices", element: <DevicesSettingsPage /> },
                  { path: "devices/roster-sync", element: <DeviceRosterSyncPage /> },
                  { path: "morning", element: <MorningPage /> },
                  { path: "warnings", element: <WarningsDashboardPage /> },
                  { path: "students", element: <StudentsPage /> },
                  {
                    path: "students/:studentId/attendance",
                    element: <StudentAttendanceProfilePage />,
                  },
                  { path: "students/inactive", element: <InactiveStudentsPage /> },
                  { path: "students/import", element: <ImportWizard /> },
                  { path: "staff", element: <StaffPage /> },
                  { path: "staff/import", element: <StaffImportWizard /> },
                  { path: "attendance/section/:sectionId", element: <AttendanceSessionPage /> },
                  { path: "attendance/monitoring", element: <MonitoringPage /> },
                  { path: "attendance/analytics", element: <AnalyticsPage /> },
                  { path: "attendance/qr", element: <SectionQrPage /> },
                  { path: "excuses", element: <ExcusesPage /> },
                  { path: "referrals", element: <ReferralsPage /> },
                  { path: "referrals/mine", element: <MyReferralsPage /> },
                  { path: "counselor", element: <CounselorDashboardPage /> },
                  { path: "counselor/cases/:caseId", element: <CaseDetailPage /> },
                  { path: "teacher/follow-ups", element: <TeacherFollowUpPage /> },
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
