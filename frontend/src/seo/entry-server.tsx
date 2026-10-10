import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { FeaturePage } from "@/features/public/FeaturePage";
import { LandingPage } from "@/features/public/LandingPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { PUBLIC_FEATURES } from "./content";

export * from "./site";

export function renderPublicPage(pathname: string) {
  const feature = PUBLIC_FEATURES.find((item) => item.path === pathname);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  try {
    return renderToString(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[pathname]}>
          {pathname === "/" ? <LandingPage /> : feature ? <FeaturePage feature={feature} /> : <NotFoundPage />}
        </MemoryRouter>
      </QueryClientProvider>,
    );
  } finally { queryClient.clear(); }
}
