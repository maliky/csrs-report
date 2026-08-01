import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppRouter } from "./app/router";
import "./styles/tokens.css";
import "./styles/global.css";

async function enableMocking() {
  if (import.meta.env.VITE_USE_MOCKS !== "true") return;
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

await enableMocking();
const root = document.getElementById("root");
if (!root) throw new Error("Le point de montage React est absent.");
createRoot(root).render(
  <StrictMode>
    <AppRouter />
  </StrictMode>,
);
