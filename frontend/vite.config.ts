/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "prompt",
      includeAssets: ["icons/*.png"],
      manifest: {
        name: "منصة المواظبة والمتابعة الطلابية",
        short_name: "المواظبة",
        description: "منصة مدرسية للمواظبة والمتابعة الطلابية",
        lang: "ar",
        dir: "rtl",
        start_url: "/",
        scope: "/",
        display: "standalone",
        theme_color: "#0f4c81",
        background_color: "#f8fafc",
        icons: [
          { src: "/icons/pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/pwa-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/pwa-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
        shortcuts: [
          {
            name: "التأخر الصباحي",
            short_name: "التأخر الصباحي",
            description: "تسجيل وقت وصول الطلاب ومتابعة التأخر الصباحي",
            url: "/morning",
            icons: [{ src: "/icons/pwa-192.png", sizes: "192x192", type: "image/png" }],
          },
        ],
      },
      workbox: {
        cleanupOutdatedCaches: true,
        clientsClaim: false,
        skipWaiting: false,
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/media\//],
        globPatterns: ["**/*.{js,css,html,png,svg,woff2}"],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
            handler: "NetworkOnly",
            method: "GET",
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // نفس الـ Origin عبر Proxy — تقليل CORS حتى في التطوير
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    testTimeout: 20_000,
    // استقرار على أجهزة التطوير التي تشغل Docker بالتوازي
    maxWorkers: 4,
  },
});
