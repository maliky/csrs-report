export type Person = {
  id: number;
  name: string;
  position: string;
  login_alias: string | null;
  avatar?: string;
};

export type UserProfile = Person & {
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  avatar: string;
  terms_of_reference: string;
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

export type RecurrenceSummary = {
  id: number;
  frequency: "weekly";
  frequency_label: string;
  status: "active" | "finished" | "cancelled";
  end_date: string;
  occurrence_number: number;
  planned_start_date: string;
  revision: number;
  can_cancel: boolean;
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
  recurrence?: RecurrenceSummary | null;
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
    validate: boolean;
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
    manage_visits: boolean;
    manage_availability: boolean;
    prepare_weekly_agenda: boolean;
    view_weekly_agenda: boolean;
    delete_tasks: boolean;
    manage_users: boolean;
    switch_role: boolean;
    password_change_required: boolean;
  };
  impersonation: {
    active: boolean;
    administrator: Person | null;
    target: Person | null;
  };
};

export type RoleSimulationRole = {
  code: string;
  name: string;
  unit_id: number | null;
  unit: string;
  scope: string;
};

export type RoleSimulationOption = Person & {
  roles: RoleSimulationRole[];
  units: Array<{
    id: number;
    code: string;
    name: string;
    is_primary: boolean;
  }>;
};

export type RoleSimulationOptions = {
  users: RoleSimulationOption[];
};

export type OrganizationUnitOption = {
  id: number;
  code: string;
  short_name: string;
  long_name: string;
  label: string;
};

export type ManagedUserSummary = Person & {
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  password_change_required: boolean;
  has_usable_password: boolean;
  primary_unit: OrganizationUnitOption | null;
  state_token: string;
  batch_capabilities: {
    deactivate: boolean;
    delete: boolean;
  };
};

export type ManagedUserDetail = ManagedUserSummary & {
  first_name: string;
  last_name: string;
  phone: string;
  agenda_direction: string;
  include_in_direction_agendas: boolean;
  unit_ids: number[];
  primary_unit_id: number | null;
  primary_supervisor: Person | null;
  state_token: string;
  capabilities: {
    deactivate: boolean;
    reactivate: boolean;
    reset_password: boolean;
    send_activation: boolean;
    edit: boolean;
  };
};

export type UserManagementPage = {
  items: ManagedUserSummary[];
  total: number;
  page: number;
  pages: number;
  page_size: number;
};

export type UserManagementOptions = {
  today: string;
  units: OrganizationUnitOption[];
  users: Person[];
  agenda_directions: Array<{ value: string; label: string }>;
};

export type UserBulkActionResult = {
  action: "deactivate" | "delete";
  affected: number;
};

export type CollaboratorManagement = {
  supervisor: Person;
  state_token: string;
  current: Person[];
  available: Person[];
  replacement_options: Record<string, Person[]>;
};

export type TemporaryPasswordResult = {
  temporary_password: string;
  state_token: string;
};

export type TaskManagementItem = {
  id: number;
  revision: number;
  task_id: number;
  code: string;
  title: string;
  status: string;
  status_label: string;
  percentage: number;
  start_date: string;
  due_date: string;
  employee: Person;
  manager: Person;
};

export type TaskManagementPage = {
  items: TaskManagementItem[];
  total: number;
  page: number;
  pages: number;
  page_size: number;
  employees: Person[];
};

export type TaskBulkDeleteResult = {
  audit_id: number;
  deleted_assignments: number;
  deleted_tasks: number;
};

export type AgendaPerson = Pick<Person, "id" | "name" | "position">;

export type VisitorVisit = {
  id: number;
  revision: number;
  party_size: number;
  visitor_names: string[];
  arrived_at: string;
  departed_at: string | null;
  cancelled_at: string | null;
};

export type VisitList = {
  period_start: string;
  period_end: string;
  visits: VisitorVisit[];
};

export type StaffAvailability = {
  id: number;
  revision: number;
  employee: AgendaPerson;
  kind: "leave" | "absence" | "mission";
  kind_label: string;
  start_date: string;
  end_date: string;
  note: string;
  cancelled_at: string | null;
};

export type AvailabilityOptions = {
  week_start: string;
  items: StaffAvailability[];
  employees: AgendaPerson[];
  kinds: { value: StaffAvailability["kind"]; label: string }[];
};

export type AgendaTask = {
  id: number;
  title: string;
  status: string;
  status_label: string;
  percentage: number;
  progress_delta: number;
  observation: string;
};

export type AgendaSnapshot = {
  schema_version: number;
  period_start: string;
  period_end: string;
  agenda_direction: AgendaDirection;
  agenda_direction_label: string;
  major_events: string;
  unclassified_users: AgendaPerson[];
  arrivals: VisitorVisit[];
  departures: VisitorVisit[];
  availability: Array<
    Omit<StaffAvailability, "revision" | "cancelled_at"> & {
      employee: AgendaPerson;
    }
  >;
  units: Array<{
    id: number;
    code: string;
    name: string;
    display_order: number;
    employees: Array<{
      person: AgendaPerson;
      unclassified: boolean;
      completion_rate: number;
      tasks: AgendaTask[];
    }>;
  }>;
};

export type AgendaPreview = {
  draft: {
    period_start: string;
    period_end: string;
    major_events: string;
    revision: number;
  };
  snapshot: AgendaSnapshot;
};

export type AgendaDirection = "programs" | "administration";

export type AgendaVersion = {
  id: number;
  period_start: string;
  period_end: string;
  agenda_direction: AgendaDirection | "legacy";
  agenda_direction_label: string;
  version: number;
  snapshot_sha256: string;
  pdf_sha256: string;
  pdf_size: number;
  generated_by: AgendaPerson;
  generated_at: string;
  pdf_url: string;
};

export type AgendaVersions = { versions: AgendaVersion[] };

export type ProcessSummary = {
  id: number;
  reference: string;
  revision: number;
  status: string;
  status_label: string;
  current_step: string;
  initiator: Person;
  origin_unit: { id: number; name: string; short_name: string };
  mission_type: "domestic" | "international";
  mission_type_label: string;
  destination: string;
  purpose: string;
  departure_date: string;
  return_date: string;
  created_at: string;
  updated_at: string;
  due_date: string | null;
  claimed_by: Person | null;
  available_actions: string[];
};

export type ProcessDocument = {
  id: number;
  kind: string;
  kind_label: string;
  name: string;
  content_type: string;
  size: number;
  sha256: string;
  scan_status: string;
  active: boolean;
  replaced_by_id: number | null;
  created_at: string;
  download_url: string | null;
};

export type ProcessEvent = {
  id: number;
  kind: string;
  from_status: string;
  to_status: string;
  message: string;
  actor: Person;
  occurred_at: string;
};

export type ProcessDetail = ProcessSummary & {
  mission: {
    itinerary: string;
    transport_mode: string;
    transport_company: string;
    funding_source: string;
    costs_covered: string;
    vehicle_required: boolean;
    vehicle_details: string;
    official_number: string;
  };
  participants: Person[];
  documents: ProcessDocument[];
  events: ProcessEvent[];
  capabilities: {
    edit: boolean;
    upload: boolean;
    download_documents: boolean;
    export: boolean;
  };
  signature: {
    signer: Person;
    signed_at: string;
    snapshot_sha256: string;
  } | null;
};

export type ProcessList = {
  items: ProcessSummary[];
  counters: { pending: number; correction_returns: number };
};

export type MissionOptions = { participants: Person[]; today: string };

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
  recurrence?: {
    frequency: "weekly";
    frequency_label: string;
    end_date: string;
    accepted_recurrence_id: number | null;
  } | null;
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
    delete: boolean;
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
  employee: UserProfile;
  tasks: TaskSummary[];
};

export type ApiErrorBody = {
  error: { code: string; message: string; fields: Record<string, string[]> };
};
