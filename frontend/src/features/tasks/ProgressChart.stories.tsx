import type { Meta, StoryObj } from "@storybook/react-vite";
import { taskDetailFixture } from "../../mocks/fixtures";
import { ProgressChart } from "./ProgressChart";

const meta = {
  title: "Tâches/Graphique de progression",
  component: ProgressChart,
} satisfies Meta<typeof ProgressChart>;
export default meta;
type Story = StoryObj<typeof meta>;
export const HistoriqueSurPlusieursSemaines: Story = {
  args: {
    points: taskDetailFixture.chart,
    today: taskDetailFixture.today,
    status: taskDetailFixture.status,
  },
};
