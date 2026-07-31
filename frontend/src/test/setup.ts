import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "../mocks/server";
import { resetMockState } from "../mocks/handlers";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  resetMockState();
  cleanup();
});
afterAll(() => server.close());
