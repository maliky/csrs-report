import type {
  ChartPoint,
  Dashboard,
  PlanningOptions,
  ProposalGroups,
  Session,
  TaskDetail,
  TaskManagementPage,
  Team,
} from "../lib/api/types";

export const sessionFixture: Session = {
  user: {
    id: 8,
    name: "Aïssata Koné",
    position: "Directrice générale",
    login_alias: "dg",
  },
  csrf_token: "csrf-local",
  capabilities: {
    create_task: true,
    create_proposal: true,
    view_team: true,
    self_assign: true,
    admin: false,
    manage_visits: true,
    manage_availability: true,
    prepare_weekly_agenda: true,
    view_weekly_agenda: true,
    delete_tasks: false,
    manage_users: false,
    password_change_required: false,
  },
};

const chart: ChartPoint[] = Array.from({ length: 75 }, (_, index) => {
  const day = new Date("2026-05-04T12:00:00");
  day.setDate(day.getDate() + index);
  const iso = day.toISOString().slice(0, 10);
  const isWorking = day.getDay() !== 0 && day.getDay() !== 6;
  const observations: Record<number, number> = {
    0: 0,
    9: 10,
    18: 25,
    31: 45,
    42: 60,
    55: 72,
    66: 85,
    74: 90,
  };
  const prior =
    Object.keys(observations)
      .map(Number)
      .filter((key) => key <= index)
      .at(-1) ?? 0;
  return {
    task_id: 31,
    start_date: "2026-05-04",
    day: iso,
    is_working_day: isWorking,
    due_date: "2026-07-24",
    planned_work_days: 24,
    elapsed_work_days: Math.max(0, index - Math.floor(index / 7) * 2),
    remaining_schedule_days: Math.max(0, 24 - index),
    overdue_days: 0,
    percentage: observations[prior],
    observed: index in observations,
  };
});

const baseTask = {
  revision: 4,
  code: "ACT-GOUV-2026-0031",
  start_date: "2026-05-04",
  today: "2026-07-17",
  due_date: "2026-07-24",
  employee: sessionFixture.user,
  manager: sessionFixture.user,
  action: { id: 4, label: "ACT-GOUV — Renforcer le pilotage institutionnel" },
};

export const dashboardFixture: Dashboard = {
  period: {
    kind: "month",
    label: "juillet 2026",
    start: "2026-07-01",
    end: "2026-07-31",
    query: "month=2026-07",
    previous_query: "month=2026-06",
    next_query: "month=2026-08",
  },
  today: "2026-07-17",
  tasks: [
    {
      ...baseTask,
      id: 31,
      title: "Finaliser les priorités de la quinzaine",
      status: "active",
      status_label: "En cours",
      percentage: 90,
      progress_delta: 18,
      workload: { total: "24", completed: "21.6", remaining: "2.4" },
      deadline_level: "warning",
      blocked: false,
      latest_note:
        "Les arbitrages de la DAF et de la DRV sont intégrés; la note de synthèse est en relecture.",
    },
    {
      ...baseTask,
      id: 34,
      code: "TACHE-2026-0034",
      title: "Consolider le tableau des engagements",
      status: "awaiting_validation",
      status_label: "À valider",
      percentage: 100,
      progress_delta: 25,
      workload: { total: "8.5", completed: "8.5", remaining: "0" },
      deadline_level: "completed",
      blocked: false,
      latest_note:
        "Le tableau consolidé et ses pièces justificatives ont été transmis au secrétariat général.",
    },
    {
      ...baseTask,
      id: 37,
      code: "ACT-PART-2026-0037",
      title: "Préparer la rencontre avec les partenaires",
      status: "active",
      status_label: "En cours",
      percentage: 45,
      progress_delta: 5,
      workload: { total: "12", completed: "5.4", remaining: "6.6" },
      deadline_level: "urgent",
      blocked: true,
      latest_note:
        "Deux confirmations sont encore attendues avant de stabiliser l'ordre du jour.",
    },
  ],
};

export const taskManagementFixture: TaskManagementPage = {
  items: dashboardFixture.tasks.slice(0, 2).map((task) => ({
    id: task.id,
    revision: task.revision,
    task_id: task.id + 1000,
    code: task.code,
    title: task.title,
    status: task.status,
    status_label: task.status_label,
    percentage: task.percentage,
    start_date: task.start_date,
    due_date: task.due_date,
    employee: task.employee,
    manager: task.manager,
  })),
  total: 2,
  page: 1,
  pages: 1,
  page_size: 50,
  employees: [sessionFixture.user],
};

export const taskDetailFixture: TaskDetail = {
  ...dashboardFixture.tasks[0],
  description:
    "Produire une synthèse arbitrée des priorités opérationnelles pour la seconde quinzaine et confirmer les responsables de chaque engagement.",
  estimated_work_days: "24",
  calendar: { id: 1, label: "Côte d'Ivoire (2026.1)" },
  chart,
  activities: [
    {
      id: 81,
      kind: "progress",
      message:
        "Les arbitrages de la DAF et de la DRV sont intégrés; la note de synthèse est en relecture.",
      occurred_at: "2026-07-17T09:20:00Z",
      actor: sessionFixture.user,
      actor_short_name: "DG",
      percentage_before: 85,
      percentage_after: 90,
    },
    {
      id: 72,
      kind: "comment",
      message:
        "La Direction de la valorisation confirme la disponibilité des données de partenariat.",
      occurred_at: "2026-07-09T14:05:00Z",
      actor: {
        id: 14,
        name: "Serge Jardinier",
        position: "Directeur de la valorisation",
        login_alias: "drv",
      },
      actor_short_name: "DRV",
      percentage_before: null,
      percentage_after: null,
    },
  ],
  capabilities: {
    manage: true,
    comment: true,
    update_progress: true,
    self_managed: true,
  },
};

export const planningFixture: PlanningOptions = {
  employees: [
    sessionFixture.user,
    {
      id: 11,
      name: "Mariam Atall",
      position: "Responsable TSI",
      login_alias: "tsi",
    },
  ],
  actions: [
    { id: 4, label: "ACT-GOUV — Renforcer le pilotage institutionnel" },
  ],
  calendars: [{ id: 1, label: "Côte d'Ivoire (2026.1)" }],
  defaults: {
    calendar_id: 1,
    start_date: "2026-07-20",
    due_date: "2026-07-27",
    estimated_work_days: "5",
  },
};

const proposalBase = {
  revision: 2,
  description: "Structurer les livrables et préciser le résultat attendu.",
  estimated_work_days: "5",
  action: { id: 4, label: "ACT-GOUV — Renforcer le pilotage institutionnel" },
  calendar: { id: 1, label: "Côte d'Ivoire (2026.1)" },
  created_at: "2026-07-10T10:00:00Z",
};

export const proposalsFixture: ProposalGroups = {
  own: [
    {
      ...proposalBase,
      id: 41,
      title: "Clarifier la note de cadrage",
      status: "rejected",
      status_label: "Rejetée",
      start_date: "2026-07-13",
      due_date: "2026-07-17",
      employee: sessionFixture.user,
      accepted_assignment_id: null,
      decision_note: "Préciser les destinataires et le format attendu.",
      can_review: false,
      capabilities: { edit: true, resubmit: true, review: false },
    },
  ],
  reviewable: [
    {
      ...proposalBase,
      id: 45,
      revision: 1,
      title: "Formaliser le tableau de priorités",
      status: "submitted",
      status_label: "Soumise",
      start_date: "2026-07-21",
      due_date: "2026-07-27",
      employee: {
        id: 48,
        name: "Awa Finance",
        position: "Directrice administrative et financière",
        login_alias: "daf",
      },
      accepted_assignment_id: null,
      decision_note: "",
      can_review: true,
      capabilities: { edit: false, resubmit: false, review: true },
    },
  ],
  read_only: [
    {
      ...proposalBase,
      id: 38,
      title: "Consolider le tableau des engagements",
      status: "accepted",
      status_label: "Validée",
      start_date: "2026-06-22",
      due_date: "2026-07-03",
      employee: {
        id: 11,
        name: "Mariam Atall",
        position: "Responsable TSI",
        login_alias: "tsi",
      },
      accepted_assignment_id: 31,
      decision_note: "",
      can_review: false,
      capabilities: { edit: false, resubmit: false, review: false },
    },
  ],
};
export const teamFixture: Team = {
  period: dashboardFixture.period,
  nodes: [
    {
      employee: {
        id: 11,
        name: "Direction administrative et financière",
        position: "Directrice administrative et financière",
        login_alias: "daf",
      },
      task_count: 0,
      children: [
        {
          employee: {
            id: 12,
            name: "Awa Finances",
            position: "Responsable des finances",
            login_alias: "finances",
          },
          task_count: 2,
          children: [
            {
              employee: {
                id: 13,
                name: "Bamba Comptable",
                position: "Comptable",
                login_alias: "comptable",
              },
              task_count: 0,
              children: [],
            },
          ],
        },
      ],
    },
    {
      employee: {
        id: 14,
        name: "Direction de la valorisation",
        position: "Directeur de la valorisation",
        login_alias: "drv",
      },
      task_count: 1,
      children: [],
    },
    {
      employee: {
        id: 15,
        name: "Contrôle interne",
        position: "Responsable du contrôle interne",
        login_alias: "controle",
      },
      task_count: 0,
      children: [],
    },
  ],
};
