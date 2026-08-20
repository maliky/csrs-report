import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export const DJANGO_PROXY_PATHS = [
  "/api",
  "/connexion",
  "/deconnexion",
  "/admin",
  "/static",
] as const;

export function djangoProxyRoutes(
  target = process.env.CSRS_DJANGO_URL ?? "http://127.0.0.1:8000",
) {
  return Object.fromEntries(
    DJANGO_PROXY_PATHS.map((path) => [path, { target, changeOrigin: true }]),
  );
}

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Django serves production assets below /static; Vite development keeps
  // root history fallback so React Router can exercise /app/* routes.
  base: command === "build" ? "/static/react/" : "/",
  build: {
    outDir: "../static/react",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (asset) =>
          asset.names.some((name) => name.endsWith(".css"))
            ? "assets/app.css"
            : "assets/[name]-[hash][extname]",
      },
    },
  },
  server: {
    port: 5173,
    proxy: djangoProxyRoutes(),
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    globals: true,
    maxWorkers: 2,
    exclude: ["e2e/**", "manual-e2e/**", "node_modules/**"],
  },
}));
