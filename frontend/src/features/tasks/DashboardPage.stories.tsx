import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "../../lib/router";
import {
  emptyDashboardHandler,
  handlers,
  slowDashboardHandler,
} from "../../mocks/handlers";
import { DashboardPage } from "./DashboardPage";

const meta = {
  title: "Pages/Tableau de bord",
  component: DashboardPage,
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/?month=2026-07"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
  parameters: { msw: { handlers } },
} satisfies Meta<typeof DashboardPage>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Normal: Story = {};
export const Vide: Story = {
  parameters: { msw: { handlers: [emptyDashboardHandler] } },
};
export const ChargementLent: Story = {
  parameters: { msw: { handlers: [slowDashboardHandler] } },
};
