import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireActiveSchool, RequireAuth } from "@/features/auth/guards";
import { SelectSchoolPage } from "@/features/auth/SelectSchoolPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { ImportWizard } from "@/features/students/ImportWizard";
import { StudentsPage } from "@/features/students/StudentsPage";
import { HomePage } from "@/routes/HomePage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { RouteErrorPage } from "@/routes/RouteErrorPage";

export const routes = [
  {
    errorElement: <RouteErrorPage />,
    children: [
      { path: "/login", element: <LoginPage /> },
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
                  { path: "students/import", element: <ImportWizard /> },
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
