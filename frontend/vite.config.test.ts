// @vitest-environment node

import { describe, expect, test } from "vitest";
import { djangoProxyRoutes } from "./vite.config";

describe("proxy Django de Vite", () => {
  test("garde API, authentification et fichiers statiques sur l'origine Vite", () => {
    const target = "http://127.0.0.1:9000";

    expect(djangoProxyRoutes(target)).toEqual({
      "/api": { target, changeOrigin: true },
      "/connexion": { target, changeOrigin: true },
      "/deconnexion": { target, changeOrigin: true },
      "/admin": { target, changeOrigin: true },
      "/static": { target, changeOrigin: true },
    });
  });
});
