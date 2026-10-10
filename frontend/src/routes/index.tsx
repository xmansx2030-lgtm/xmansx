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
import { PageSkeleton } from "@/components/Skeleton";
import { PublicRootPage } from "@/features/public/PublicRootPage";
import { RegisterSchoolPage } from "@/features/public/RegisterSchoolPage";
import { FeaturePage } from "@/features/public/FeaturePage";
import { PUBLIC_FEATURES } from "@/seo/content";
import { SeoLayout } from "@/seo/SeoLayout";

export const routes = [
  {
    element: <SeoLayout />,
    errorElement: <RouteErrorPage />,
    hydrateFallbackElement: <div className="min-h-screen bg-slate-50 p-4 sm:p-8"><PageSkeleton label="جارٍ تحميل المنصة" /></div>,
    children: [
      { path: "/", element: <PublicRootPage /> },
      ...PUBLIC_FEATURES.map((feature) => ({ path: feature.path, element: <FeaturePage feature={feature} /> })),
      { path: "/register", element: <RegisterSchoolPage /> },
      { path: "/login", element: <LoginPage /> },
      { path: "*", element: <NotFoundPage /> },
      {
        path: "/forgot-password",
        lazy: async () => ({ Component: (await import("@/features/parent/EmailRecoveryPages")).ForgotParentPasswordPage }),
      },
      {
        path: "/reset-password",
        lazy: async () => ({ Component: (await import("@/features/parent/EmailRecoveryPages")).ResetParentPasswordPage }),
      },
      {
        path: "/parent/verify-email",
        lazy: async () => ({ Component: (await import("@/features/parent/EmailRecoveryPages")).VerifyRecoveryEmailPage }),
      },
      { path: "/change-password", element: <ChangeInitialPasswordPage /> },
      {
        path: "/parent/register/:schoolToken",
        lazy: async () => ({ Component: (await import("@/features/parent/RegistrationPage")).RegistrationPage }),
      },
      {
        path: "/parent/activate",
        lazy: async () => ({ Component: (await import("@/features/parent/ActivationPage")).ActivationPage }),
      },
      {
        path: "/parent/invitation",
        lazy: async () => ({ Component: (await import("@/features/parent/FamilyInvitationPage")).FamilyInvitationPage }),
      },
      {
        path: "/qr/:token",
        lazy: async () => ({
          Component: (await import("@/features/attendance/QrScanPage")).QrScanPage,
        }),
      },
      {
        element: <RequireAuth />,
        children: [
          {
            path: "/account/complete-email",
            lazy: async () => ({ Component: (await import("@/features/parent/EmailRecoveryPages")).CompleteSchoolEmailPage }),
          },
          {
            path: "/account/recovery-email",
            lazy: async () => ({ Component: (await import("@/features/parent/EmailRecoveryPages")).RecoveryEmailPage }),
          },
          {
            path: "/parent/recovery-email",
            lazy: async () => ({ Component: (await import("@/features/parent/EmailRecoveryPages")).RecoveryEmailPage }),
          },
          {
            path: "parent",
            lazy: async () => ({ Component: (await import("@/features/parent/ParentShell")).ParentShell }),
            children: [
              { index: true, lazy: async () => ({ Component: (await import("@/features/parent/ParentPages")).ParentHomePage }) },
              { path: "attendance", lazy: async () => ({ Component: (await import("@/features/parent/ParentPages")).ParentAttendancePage }) },
              { path: "children/:relationId", lazy: async () => ({ Component: (await import("@/features/parent/ChildPage")).ChildPage }) },
              { path: "requests", lazy: async () => ({ Component: (await import("@/features/parent/ParentPages")).ParentRequestsPage }) },
              { path: "notifications", lazy: async () => ({ Component: (await import("@/features/parent/ParentPages")).ParentNotificationsPage }) },
              { path: "account", lazy: async () => ({ Component: (await import("@/features/parent/ParentPages")).ParentAccountPage }) },
              { path: "*", element: <NotFoundPage /> },
            ],
          },
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
                lazy: async () => ({ Component: (await import("@/app/AppShell")).AppShell }),
                children: [
                  { path: "workspace", element: <HomePage /> },
                  {
                    path: "account",
                    lazy: async () => ({ Component: (await import("@/features/auth/AccountPage")).AccountPage }),
                  },
                  {
                    element: <RequireSchoolRoles allowedRoles={["SCHOOL_MANAGER", "VICE_PRINCIPAL"]} />,
                    children: [
                      {
                        path: "dashboard",
                        lazy: async () => ({ Component: (await import("@/features/dashboard/DashboardPage")).DashboardPage }),
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
                        path: "attendance/absence-messages",
                        lazy: async () => ({ Component: (await import("@/features/sms/AbsenceMessagesPage")).AbsenceMessagesPage }),
                      },
                      {
                        path: "student-leaves",
                        lazy: async () => ({ Component: (await import("@/features/leaves/StudentLeavesPage")).StudentLeavesPage }),
                      },
                    ],
                  },
                  {
                    element: (
                      <RequireSchoolRoles
                        allowedRoles={["SCHOOL_MANAGER", "VICE_PRINCIPAL"]}
                        allowedCapabilities={["MORNING_ATTENDANCE"]}
                      />
                    ),
                    children: [
                      {
                        path: "morning",
                        lazy: async () => ({ Component: (await import("@/features/devices/MorningPage")).MorningPage }),
                      },
                    ],
                  },
                  {
                    element: <RequireSchoolRoles allowedRoles={["SCHOOL_MANAGER", "VICE_PRINCIPAL", "GATE_GUARD"]} />,
                    children: [
                      {
                        path: "gate",
                        lazy: async () => ({ Component: (await import("@/features/gate/GatePage")).GatePage }),
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
                        path: "parent-management",
                        lazy: async () => ({ Component: (await import("@/features/parent/ParentManagementPage")).ParentManagementPage }),
                      },
                      {
                        path: "academic-calendar",
                        lazy: async () => ({ Component: (await import("@/features/settings/SchoolCalendarPage")).SchoolCalendarPage }),
                      },
                      {
                        path: "reports",
                        lazy: async () => ({ Component: (await import("@/features/reports/ReportsPage")).ReportsPage }),
                      },
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
                    element: <RequireSchoolRoles allowedRoles={["TEACHER", "SCHOOL_MANAGER", "VICE_PRINCIPAL"]} />,
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
