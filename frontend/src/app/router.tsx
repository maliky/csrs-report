import { BrowserRouter, Route, Routes } from "../lib/router";
import { ErrorState } from "../components/ui";
import { EmployeePage } from "../features/team/EmployeePage";
import { ProposalDetailPage } from "../features/proposals/ProposalDetailPage";
import { ProposalFormPage } from "../features/proposals/ProposalFormPage";
import { ProposalsPage } from "../features/proposals/ProposalsPage";
import { TaskDetailPage } from "../features/tasks/TaskDetailPage";
import { TaskFormPage } from "../features/tasks/TaskFormPage";
import { DashboardPage } from "../features/tasks/DashboardPage";
import { TeamPage } from "../features/team/TeamPage";
import { AppShell } from "./AppShell";
import { AgendaPage } from "../features/agenda/AgendaPage";
import { AvailabilityPage } from "../features/agenda/AvailabilityPage";

export function AppRouter() {
  return (
    <BrowserRouter basename="/app">
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route
            path="taches/nouvelle"
            element={<TaskFormPage mode="create" />}
          />
          <Route path="taches/:taskId" element={<TaskDetailPage />} />
          <Route
            path="taches/:taskId/modifier"
            element={<TaskFormPage mode="edit" />}
          />
          <Route path="propositions" element={<ProposalsPage />} />
          <Route
            path="propositions/nouvelle"
            element={<ProposalFormPage mode="create" />}
          />
          <Route
            path="propositions/:proposalId"
            element={<ProposalDetailPage />}
          />
          <Route
            path="propositions/:proposalId/modifier"
            element={<ProposalFormPage mode="edit" />}
          />
          <Route path="equipe" element={<TeamPage />} />
          <Route path="equipe/:employeeId" element={<EmployeePage />} />
          <Route path="agenda" element={<AgendaPage />} />
          <Route path="absences" element={<AvailabilityPage />} />
        </Route>
        <Route
          path="*"
          element={
            <main style={{ padding: "2rem" }}>
              <ErrorState
                error={
                  new Error("Cette page n'existe pas ou n'est plus accessible.")
                }
              />
            </main>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
