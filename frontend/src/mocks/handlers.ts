import { delay, http, HttpResponse } from "msw";
import {
  dashboardFixture,
  planningFixture,
  proposalsFixture,
  sessionFixture,
  taskDetailFixture,
  teamFixture,
} from "./fixtures";

export const handlers = [
  http.get("/api/v1/session/", () => HttpResponse.json(sessionFixture)),
  http.get("/api/v1/dashboard/", () => HttpResponse.json(dashboardFixture)),
  http.get("/api/v1/tasks/:id/", () => HttpResponse.json(taskDetailFixture)),
  http.get("/api/v1/planning/options/", () =>
    HttpResponse.json(planningFixture),
  ),
  http.get("/api/v1/proposals/", () => HttpResponse.json(proposalsFixture)),
  http.get("/api/v1/team/", () => HttpResponse.json(teamFixture)),
  http.get("/api/v1/team/:id/", () =>
    HttpResponse.json({
      period: teamFixture.period,
      employee: teamFixture.nodes[0].employee,
      tasks: dashboardFixture.tasks,
    }),
  ),
  http.post("/api/v1/planning/preview/", async ({ request }) =>
    HttpResponse.json(await request.json()),
  ),
];

export const slowDashboardHandler = http.get("/api/v1/dashboard/", async () => {
  await delay(1200);
  return HttpResponse.json(dashboardFixture);
});
export const emptyDashboardHandler = http.get("/api/v1/dashboard/", () =>
  HttpResponse.json({ ...dashboardFixture, tasks: [] }),
);
export const forbiddenHandler = http.get("/api/v1/dashboard/", () =>
  HttpResponse.json(
    {
      error: {
        code: "forbidden",
        message: "Vous n'avez pas accès à cette vue.",
        fields: {},
      },
    },
    { status: 403 },
  ),
);
