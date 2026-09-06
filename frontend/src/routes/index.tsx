import { createBrowserRouter } from "react-router-dom";

import { ChangeInitialPasswordPage } from "@/features/auth/ChangeInitialPasswordPage";
import { LoginPage } from "@/features/auth/LoginPage";
import {
  RequireActiveSchool,
  RequireAuth,
  RequirePlatformAdmin,
  RequireSchoolRoles,
} from "@/features/auth/guards";
import { SelectSchoolPage } from "@/features/auth/SelectSchoolPage";
import { HomePage } from "@/routes/HomePage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { RouteErrorPage } from "@/routes/RouteErrorPage";

export const routes = [
  {
    errorElement: <RouteErrorPage />,
    hydrateFallbackElement: (
      <div className="grid min-h-screen place-items-center bg-slate-50 text-sm font-bold text-slate-600">
        جارٍ تحميل المنصة...
      </div>
    ),
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/change-password", element: <ChangeInitialPasswordPage /> },
      {
        path: "/qr/:token",
        lazy: async () => ({
          Component: (await import("@/features/attendance/QrScanPage")).QrScanPage,
        }),
      },
      {
        element: <RequireAuth />,
        children: [
          { path: "/select-school", element: <SelectSchoolPage /> },
          {
            element: <RequirePlatformAdmin />,
            children: [
              {
                path: "/platform",
                lazy: async () => ({
                  Component: (await import("@/features/platform/PlatformAdminPage")).PlatformAdminPage,
                }),
              },
            ],
          },
          {
            element: <RequireActiveSchool />,
            children: [
              {
                path: "/",
                lazy: async () => ({ Component: (await import("@/app/AppShell")).AppShell }),
                children: [
                  { index: true, element: <HomePage /> },
                  {
                    element: <RequireSchoolRoles allowedRoles={["SCHOOL_MANAGER", "VICE_PRINCIPAL"]} />,
                    children: [
                      {
                        path: "dashboard",
                        lazy: async () => ({ Component: (await import("@/features/dashboard/DashboardPage")).DashboardPage }),
                      },
                      {
                        path: "morning",
                        lazy: async () => ({ Component: (await import("@/features/devices/MorningPage")).MorningPage }),
                      },
                      {
                        path: "warnings",
                        lazy: async () => ({ Component: (await import("@/features/warnings/WarningsDashboardPage")).WarningsDashboardPage }),
                      },
                      {
                        path: "staff",
                        lazy: async () => ({ Component: (await import("@/features/staff/StaffPage")).StaffPage }),
                      },
                      {
                        path: "students/inactive",
                        lazy: async () => ({ Component: (await import("@/features/students/InactiveStudentsPage")).InactiveStudentsPage }),
                      },
                      {
                        path: "attendance/monitoring",
                        lazy: async () => ({ Component: (await import("@/features/attendance/MonitoringPage")).MonitoringPage }),
                      },
                      {
                        path: "attendance/analytics",
                        lazy: async () => ({ Component: (await import("@/features/attendance/AnalyticsPage")).AnalyticsPage }),
                      },
                      {
                        path: "student-leaves",
                        lazy: async () => ({ Component: (await import("@/features/leaves/StudentLeavesPage")).StudentLeavesPage }),
                      },
                    ],
                  },
                  {
                    element: <RequireSchoolRoles allowedRoles={["SCHOOL_MANAGER"]} />,
                    children: [
                      {
                        path: "devices",
                        lazy: async () => ({ Component: (await import("@/features/devices/DevicesSettingsPage")).DevicesSettingsPage }),
                      },
                      {
                        path: "devices/roster-sync",
                        lazy: async () => ({ Component: (await import("@/features/devices/DeviceRosterSyncPage")).DeviceRosterSyncPage }),
                      },
                      {
                        path: "subscription",
                        lazy: async () => ({ Component: (await import("@/features/platform/SchoolSubscriptionPage")).SchoolSubscriptionPage }),
                      },
                      {
                        path: "students/import",
                        lazy: async () => ({ Component: (await import("@/features/students/ImportWizard")).ImportWizard }),
                      },
                      {
                        path: "staff/import",
                        lazy: async () => ({ Component: (await import("@/features/staff/StaffImportWizard")).StaffImportWizard }),
                      },
                      {
                        path: "attendance/qr",
                        lazy: async () => ({ Component: (await import("@/features/attendance/SectionQrPage")).SectionQrPage }),
                      },
                      {
                        path: "settings",
                        lazy: async () => ({ Component: (await import("@/features/settings/SettingsPage")).SettingsPage }),
                      },
                    ],
                  },
                  {
                    element: <RequireSchoolRoles allowedRoles={["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"]} />,
                    children: [
                      {
                        path: "students",
                        lazy: async () => ({ Component: (await import("@/features/students/StudentsPage")).StudentsPage }),
                      },
                      {
                        path: "students/:studentId/attendance",
                        lazy: async () => ({ Component: (await import("@/features/students/StudentAttendanceProfilePage")).StudentAttendanceProfilePage }),
                      },
                      {
                        path: "excuses",
                        lazy: async () => ({ Component: (await import("@/features/excuses/ExcusesPage")).ExcusesPage }),
                      },
                      {
                        path: "referrals",
                        lazy: async () => ({ Component: (await import("@/features/referrals/ReferralsPage")).ReferralsPage }),
                      },
                      {
                        path: "counselor",
                        lazy: async () => ({ Component: (await import("@/features/counseling/CounselorDashboardPage")).CounselorDashboardPage }),
                      },
                      {
                        path: "counselor/cases/:caseId",
                        lazy: async () => ({ Component: (await import("@/features/counseling/CaseDetailPage")).CaseDetailPage }),
                      },
                    ],
                  },
                  {
                    element: <RequireSchoolRoles allowedRoles={["TEACHER"]} />,
                    children: [
                      {
                        path: "attendance/section/:sectionId",
                        lazy: async () => ({ Component: (await import("@/features/attendance/AttendanceSessionPage")).AttendanceSessionPage }),
                      },
                    ],
                  },
                  {
                    element: <RequireSchoolRoles allowedRoles={["TEACHER"]} />,
                    children: [
                      {
                        path: "referrals/mine",
                        lazy: async () => ({ Component: (await import("@/features/referrals/MyReferralsPage")).MyReferralsPage }),
                      },
                      {
                        path: "teacher/follow-ups",
                        lazy: async () => ({ Component: (await import("@/features/counseling/TeacherFollowUpPage")).TeacherFollowUpPage }),
                      },
                    ],
                  },
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
