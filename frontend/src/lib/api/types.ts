export type Person = {
  id: number;
  name: string;
  position: string;
  login_alias: string | null;
};

export type Period = {
  kind: "week" | "month";
  label: string;
  start: string;
  end: string;
  query: string;
  previous_query: string;
  next_query: string;
};

export type Workload = {
  total: string;
  completed: string;
  remaining: string;
};

export type TaskSummary = {
  id: number;
  revision: number;
  code: string;
  title: string;
  status: string;
  status_label: string;
  percentage: number;
  progress_delta: number;
  start_date: string;
  today: string;
  due_date: string;
  workload: Workload;
  deadline_level: string;
  blocked: boolean;
  latest_note: string;
  employee: Person;
  manager: Person;
  action: { id: number; label: string } | null;
};

export type ChartPoint = {
  task_id: number;
  start_date: string;
  day: string;
  is_working_day: boolean;
  due_date: string;
  planned_work_days: number;
  elapsed_work_days: number;
  remaining_schedule_days: number;
  overdue_days: number;
  percentage: number;
  observed: boolean;
};

export type Activity = {
  id: number;
  kind: string;
  message: string;
  occurred_at: string;
  actor: Person;
  actor_short_name: string;
  percentage_before: number | null;
  percentage_after: number | null;
};

export type TaskDetail = Omit<
  TaskSummary,
  "progress_delta" | "deadline_level" | "blocked" | "latest_note"
> & {
  description: string;
  estimated_work_days: string;
  calendar: { id: number; label: string };
  chart: ChartPoint[];
  activities: Activity[];
  capabilities: {
    manage: boolean;
    comment: boolean;
    update_progress: boolean;
    self_managed: boolean;
  };
};

export type Session = {
  user: Person;
  csrf_token: string;
  capabilities: {
    create_task: boolean;
    create_proposal: boolean;
    view_team: boolean;
    self_assign: boolean;
    admin: boolean;
  };
};

export type Dashboard = { period: Period; today: string; tasks: TaskSummary[] };

export type PlanningOptions = {
  employees: Person[];
  actions: { id: number; label: string }[];
  calendars: { id: number; label: string }[];
  defaults: {
    calendar_id: number;
    start_date: string;
    due_date: string;
    estimated_work_days: string;
  };
};

export type Proposal = {
  id: number;
  revision: number;
  title: string;
  description: string;
  status: string;
  status_label: string;
  start_date: string;
  due_date: string;
  estimated_work_days: string;
  action: { id: number; label: string } | null;
  calendar: { id: number; label: string };
  employee: Person;
  accepted_assignment_id: number | null;
  decision_note: string;
  created_at: string;
  can_review: boolean;
  capabilities: {
    edit: boolean;
    resubmit: boolean;
    review: boolean;
  };
};

export type ProposalGroups = {
  own: Proposal[];
  reviewable: Proposal[];
  read_only: Proposal[];
};

export type TeamNode = {
  employee: Person;
  task_count: number;
  children: TeamNode[];
};

export type Team = { period: Period; nodes: TeamNode[] };
export type TeamEmployee = {
  period: Period;
  employee: Person;
  tasks: TaskSummary[];
};

export type ApiErrorBody = {
  error: { code: string; message: string; fields: Record<string, string[]> };
};
