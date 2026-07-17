import createClient from "openapi-fetch";
import type { paths } from "./schema";
import type { ApiErrorBody } from "./types";

// This typed client ties the browser package to the generated OpenAPI contract.
export const contractClient = createClient<paths>({
  credentials: "same-origin",
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly fields: Record<string, string[]> = {},
  ) {
    super(message);
  }
}

function csrfToken(): string {
  const value = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("csrftoken="));
  return value ? decodeURIComponent(value.split("=").slice(1).join("=")) : "";
}

/** Fetch JSON using same-origin sessions and Django's CSRF cookie. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET")
    headers.set("X-CSRFToken", csrfToken());

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;
  const payload = (await response.json()) as T | ApiErrorBody;
  if (!response.ok) {
    const error = (payload as ApiErrorBody).error;
    if (response.status === 401) {
      window.location.assign(
        `/connexion/?next=${encodeURIComponent(window.location.pathname)}`,
      );
    }
    throw new ApiError(
      error?.message ?? "Une erreur inattendue est survenue.",
      response.status,
      error?.code ?? "request_error",
      error?.fields,
    );
  }
  return payload as T;
}
