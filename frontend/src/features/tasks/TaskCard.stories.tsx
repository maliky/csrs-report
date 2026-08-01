import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "../../lib/router";
import { dashboardFixture } from "../../mocks/fixtures";
import { TaskCard } from "./TaskCard";

const meta = {
  title: "Tâches/Carte",
  component: TaskCard,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <div style={{ maxWidth: 440 }}>
          <Story />
        </div>
      </MemoryRouter>
    ),
  ],
} satisfies Meta<typeof TaskCard>;
export default meta;
type Story = StoryObj<typeof meta>;

export const EnCours: Story = { args: { task: dashboardFixture.tasks[0] } };
export const AValider: Story = { args: { task: dashboardFixture.tasks[1] } };
export const BloqueeEtUrgente: Story = {
  args: { task: dashboardFixture.tasks[2] },
};
