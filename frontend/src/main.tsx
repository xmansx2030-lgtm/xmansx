import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";

import "@/styles/index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

document.documentElement.dataset.appVersion =
  import.meta.env.VITE_APP_VERSION ?? "development";

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
