import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./client";

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("transforme une erreur HTML en erreur API lisible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<!doctype html><title>Erreur</title>", {
          status: 500,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    await expect(apiFetch("/api/v1/proposals/45/decision/")).rejects.toEqual(
      expect.objectContaining({
        message: "Le serveur n'a pas pu traiter cette demande.",
        status: 500,
        code: "invalid_response",
      }),
    );
  });

  it("conserve le contrat JSON des réponses valides", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "accepted" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/v1/proposals/45/")).resolves.toEqual({
      status: "accepted",
    });
  });
});
