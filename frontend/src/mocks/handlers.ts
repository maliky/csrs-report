import { delay, http, HttpResponse } from "msw";
import type {
  Proposal,
  ProposalGroups,
  TaskDetail,
  TeamNode,
} from "../lib/api/types";
import {
  dashboardFixture,
  planningFixture,
  proposalsFixture,
  sessionFixture,
  taskDetailFixture,
  teamFixture,
} from "./fixtures";

let taskState: TaskDetail;
let proposalState: ProposalGroups;

export function resetMockState() {
  taskState = structuredClone(taskDetailFixture);
  proposalState = structuredClone(proposalsFixture);
}

resetMockState();

function taskGroups() {
  return {
    ...dashboardFixture,
    tasks: dashboardFixture.tasks.map((task) =>
      task.id === taskState.id
        ? {
            ...task,
            revision: taskState.revision,
            percentage: taskState.percentage,
            status: taskState.status,
            status_label: taskState.status_label,
            workload: taskState.workload,
          }
        : task,
    ),
  };
}

function allProposals(): Proposal[] {
  return [
    ...proposalState.own,
    ...proposalState.reviewable,
    ...proposalState.read_only,
  ];
}

function proposalById(id: number): Proposal | undefined {
  return allProposals().find((proposal) => proposal.id === id);
}

function teamNodeById(nodes: TeamNode[], id: number): TeamNode | undefined {
  for (const node of nodes) {
    if (node.employee.id === id) return node;
    const child = teamNodeById(node.children, id);
    if (child) return child;
  }
  return undefined;
}

function replaceProposal(updated: Proposal) {
  proposalState = {
    own: proposalState.own.map((item) =>
      item.id === updated.id ? updated : item,
    ),
    reviewable: proposalState.reviewable.map((item) =>
      item.id === updated.id ? updated : item,
    ),
    read_only: proposalState.read_only.map((item) =>
      item.id === updated.id ? updated : item,
    ),
  };
}

function apiError(status: number, code: string, message: string, fields = {}) {
  return HttpResponse.json({ error: { code, message, fields } }, { status });
}

export const handlers = [
  http.get("/api/v1/session/", () => HttpResponse.json(sessionFixture)),
  http.post(
    "/api/v1/session/logout/",
    () => new HttpResponse(null, { status: 204 }),
  ),
  http.get("/api/v1/dashboard/", () => HttpResponse.json(taskGroups())),
  http.get("/api/v1/tasks/:id/", () => HttpResponse.json(taskState)),
  http.get("/api/v1/planning/options/", () =>
    HttpResponse.json(planningFixture),
  ),
  http.post("/api/v1/planning/preview/", async ({ request }) => {
    const body = (await request.json()) as {
      start_date: string;
      due_date: string;
      estimated_work_days: string;
    };
    return HttpResponse.json({
      start_date: body.start_date,
      due_date: body.due_date,
      estimated_work_days: body.estimated_work_days,
    });
  }),
  http.post("/api/v1/tasks/", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    taskState = {
      ...taskState,
      id: 99,
      revision: 1,
      title: String(body.title),
      description: String(body.description),
      start_date: String(body.start_date),
      due_date: String(body.due_date),
      estimated_work_days: String(body.estimated_work_days),
      percentage: 0,
      chart: [],
      activities: [],
    };
    return HttpResponse.json(taskState, { status: 201 });
  }),
  http.patch("/api/v1/tasks/:id/", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (body.revision !== taskState.revision)
      return apiError(
        409,
        "stale_revision",
        "Cette ressource a été modifiée depuis son chargement.",
        { revision: [String(taskState.revision)] },
      );
    taskState = {
      ...taskState,
      revision: taskState.revision + 1,
      title: String(body.title),
      description: String(body.description),
      start_date: String(body.start_date),
      due_date: String(body.due_date),
      estimated_work_days: String(body.estimated_work_days),
    };
    return HttpResponse.json(taskState);
  }),
  http.post("/api/v1/tasks/:id/progress/", async ({ request }) => {
    const body = (await request.json()) as {
      revision: number;
      percentage: number;
      note: string;
      blocked: boolean;
    };
    if (body.revision !== taskState.revision)
      return apiError(
        409,
        "stale_revision",
        "Cette ressource a été modifiée depuis son chargement.",
        { revision: [String(taskState.revision)] },
      );
    if (
      (body.percentage < taskState.percentage || body.blocked) &&
      !body.note.trim()
    )
      return apiError(
        400,
        "validation_error",
        "Une note est obligatoire pour une régression ou un point d'attention.",
        { note: ["Ce champ est obligatoire."] },
      );
    const previous = taskState.percentage;
    const total = Number(taskState.workload.total);
    taskState = {
      ...taskState,
      revision: taskState.revision + 1,
      percentage: body.percentage,
      status: body.percentage === 100 ? "awaiting_validation" : "active",
      status_label: body.percentage === 100 ? "À valider" : "En cours",
      workload: {
        total: taskState.workload.total,
        completed: String((total * body.percentage) / 100),
        remaining: String((total * (100 - body.percentage)) / 100),
      },
      chart: taskState.chart.map((point) =>
        point.day === taskState.today
          ? { ...point, percentage: body.percentage, observed: true }
          : point,
      ),
      activities: [
        {
          id:
            Math.max(
              0,
              ...taskState.activities.map((activity) => activity.id),
            ) + 1,
          kind: "progress",
          message:
            body.note || `Progression enregistrée à ${body.percentage} %.`,
          occurred_at: `${taskState.today}T12:00:00Z`,
          actor: sessionFixture.user,
          actor_short_name: "DG",
          percentage_before: previous,
          percentage_after: body.percentage,
        },
        ...taskState.activities,
      ],
    };
    return HttpResponse.json(taskState);
  }),
  http.post("/api/v1/tasks/:id/observations/", async ({ request }) => {
    const body = (await request.json()) as {
      revision: number;
      message: string;
    };
    taskState = {
      ...taskState,
      revision: taskState.revision + 1,
      activities: [
        {
          id:
            Math.max(
              0,
              ...taskState.activities.map((activity) => activity.id),
            ) + 1,
          kind: "comment",
          message: body.message,
          occurred_at: `${taskState.today}T12:00:00Z`,
          actor: sessionFixture.user,
          actor_short_name: "DG",
          percentage_before: null,
          percentage_after: null,
        },
        ...taskState.activities,
      ],
    };
    return HttpResponse.json(taskState);
  }),
  http.post("/api/v1/tasks/:id/transition/", async ({ request }) => {
    const body = (await request.json()) as { transition: string };
    const next =
      body.transition === "validate"
        ? ["completed", "Terminée"]
        : body.transition === "close_early"
          ? ["closed_early", "Clôturée avant achèvement"]
          : ["active", "En cours"];
    taskState = {
      ...taskState,
      revision: taskState.revision + 1,
      status: next[0],
      status_label: next[1],
    };
    return HttpResponse.json(taskState);
  }),
  http.get("/api/v1/proposals/", () => HttpResponse.json(proposalState)),
  http.get("/api/v1/proposals/:id/", ({ params }) => {
    const proposal = proposalById(Number(params.id));
    return proposal
      ? HttpResponse.json(proposal)
      : apiError(404, "not_found", "Proposition introuvable.");
  }),
  http.post("/api/v1/proposals/", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const proposal = {
      id: 101,
      revision: 1,
      title: String(body.title),
      description: String(body.description),
      status: "submitted",
      status_label: "Soumise",
      start_date: String(body.start_date),
      due_date: String(body.due_date),
      estimated_work_days: String(body.estimated_work_days),
      action: null,
      calendar: planningFixture.calendars[0],
      employee: sessionFixture.user,
      accepted_assignment_id: null,
      decision_note: "",
      created_at: `${taskState.today}T12:00:00Z`,
      can_review: false,
      capabilities: { edit: true, resubmit: false, review: false },
    };
    proposalState = { ...proposalState, own: [proposal, ...proposalState.own] };
    return HttpResponse.json(proposal, { status: 201 });
  }),
  http.patch("/api/v1/proposals/:id/", async ({ request, params }) => {
    const proposal = proposalById(Number(params.id));
    if (!proposal)
      return apiError(404, "not_found", "Proposition introuvable.");
    const body = (await request.json()) as Record<string, unknown>;
    if (body.revision !== proposal.revision)
      return apiError(
        409,
        "stale_revision",
        "Cette ressource a été modifiée depuis son chargement.",
      );
    const updated: Proposal = {
      ...proposal,
      revision: proposal.revision + 1,
      title: String(body.title),
      description: String(body.description),
      start_date: String(body.start_date),
      due_date: String(body.due_date),
      estimated_work_days: String(body.estimated_work_days),
    };
    replaceProposal(updated);
    return HttpResponse.json(updated);
  }),
  http.post("/api/v1/proposals/:id/resubmit/", async ({ request, params }) => {
    const proposal = proposalById(Number(params.id));
    if (!proposal)
      return apiError(404, "not_found", "Proposition introuvable.");
    const body = (await request.json()) as { revision: number };
    if (body.revision !== proposal.revision)
      return apiError(
        409,
        "stale_revision",
        "Cette ressource a été modifiée depuis son chargement.",
      );
    const updated: Proposal = {
      ...proposal,
      revision: proposal.revision + 1,
      status: "submitted",
      status_label: "Soumise",
      decision_note: "",
      can_review: false,
      capabilities: { edit: true, resubmit: false, review: false },
    };
    replaceProposal(updated);
    return HttpResponse.json(updated);
  }),
  http.post("/api/v1/proposals/:id/decision/", async ({ request, params }) => {
    const body = (await request.json()) as { decision: string; reason: string };
    const proposal = proposalById(Number(params.id));
    if (!proposal)
      return apiError(404, "not_found", "Proposition introuvable.");
    const updated: Proposal = {
      ...proposal,
      revision: proposal.revision + 1,
      status: body.decision === "accept" ? "accepted" : "rejected",
      status_label: body.decision === "accept" ? "Validée" : "Rejetée",
      accepted_assignment_id: body.decision === "accept" ? taskState.id : null,
      decision_note: body.reason,
      can_review: false,
      capabilities: { edit: false, resubmit: false, review: false },
    };
    proposalState = {
      ...proposalState,
      reviewable: proposalState.reviewable.filter(
        (item) => item.id !== proposal.id,
      ),
      read_only: [updated, ...proposalState.read_only],
    };
    return HttpResponse.json(updated);
  }),
  http.get("/api/v1/team/", () => HttpResponse.json(teamFixture)),
  http.get("/api/v1/team/:id/", ({ params }) => {
    const node = teamNodeById(teamFixture.nodes, Number(params.id));
    if (!node) return apiError(404, "not_found", "Collaborateur introuvable.");
    return HttpResponse.json({
      period: teamFixture.period,
      employee: node.employee,
      tasks: taskGroups()
        .tasks.slice(0, node.task_count)
        .map((task) => ({ ...task, employee: node.employee })),
    });
  }),
];

export const slowDashboardHandler = http.get("/api/v1/dashboard/", async () => {
  await delay(1200);
  return HttpResponse.json(taskGroups());
});
export const emptyDashboardHandler = http.get("/api/v1/dashboard/", () =>
  HttpResponse.json({ ...taskGroups(), tasks: [] }),
);
export const forbiddenHandler = http.get("/api/v1/dashboard/", () =>
  apiError(403, "forbidden", "Vous n'avez pas accès à cette vue."),
);
