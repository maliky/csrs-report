import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "./AppShell";
import { DashboardPage } from "../features/tasks/DashboardPage";
import { TaskDetailPage } from "../features/tasks/TaskDetailPage";
import { TaskFormPage } from "../features/tasks/TaskFormPage";
import { ProposalsPage } from "../features/proposals/ProposalsPage";
import { ProposalFormPage } from "../features/proposals/ProposalFormPage";
import { ProposalDetailPage } from "../features/proposals/ProposalDetailPage";
import { TeamPage } from "../features/team/TeamPage";
import { EmployeePage } from "../features/team/EmployeePage";
import { ErrorState } from "../components/ui";

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppShell />,
      errorElement: (
        <main style={{ padding: "2rem" }}>
          <ErrorState
            error={
              new Error("Cette page n'existe pas ou n'est plus accessible.")
            }
          />
        </main>
      ),
      children: [
        { index: true, element: <DashboardPage /> },
        { path: "taches/nouvelle", element: <TaskFormPage mode="create" /> },
        { path: "taches/:taskId", element: <TaskDetailPage /> },
        {
          path: "taches/:taskId/modifier",
          element: <TaskFormPage mode="edit" />,
        },
        { path: "propositions", element: <ProposalsPage /> },
        {
          path: "propositions/nouvelle",
          element: <ProposalFormPage mode="create" />,
        },
        {
          path: "propositions/:proposalId",
          element: <ProposalDetailPage />,
        },
        {
          path: "propositions/:proposalId/modifier",
          element: <ProposalFormPage mode="edit" />,
        },
        { path: "equipe", element: <TeamPage /> },
        { path: "equipe/:employeeId", element: <EmployeePage /> },
      ],
    },
  ],
  { basename: "/app" },
);
