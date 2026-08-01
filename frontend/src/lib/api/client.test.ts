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

  it("laisse le navigateur définir la frontière multipart des pièces", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const body = new FormData();
    body.set("revision", "2");
    body.set("file", new Blob(["pdf"], { type: "application/pdf" }), "tdr.pdf");

    await apiFetch("/api/v1/processes/1/documents/", { method: "POST", body });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });
});
