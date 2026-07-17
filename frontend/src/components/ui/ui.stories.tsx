import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button, Card, EmptyState, Skeleton, StatusBadge } from ".";

const meta = {
  title: "Système de design/Primitives",
  component: Card,
} satisfies Meta<typeof Card>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Ensemble: Story = {
  render: () => (
    <div className="stack">
      <Card>
        <h2>Carte de contenu</h2>
        <p>Une surface claire destinée aux informations métier.</p>
        <div className="cluster">
          <Button>Action principale</Button>
          <Button variant="secondary">Action secondaire</Button>
          <StatusBadge status="awaiting_validation">À valider</StatusBadge>
        </div>
      </Card>
      <Skeleton />
      <EmptyState title="Aucun engagement">
        Cette période ne contient aucune tâche.
      </EmptyState>
    </div>
  ),
};
