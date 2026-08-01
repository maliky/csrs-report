import { Link } from "../../lib/router";
import type { TaskSummary } from "../../lib/api/types";
import { dayCount, formatDate } from "../../lib/format";
import { AlertBadge, Card, StatusBadge } from "../../components/ui";
import styles from "./tasks.module.css";

export function TaskCard({
  task,
  showEmployee = false,
}: {
  task: TaskSummary;
  showEmployee?: boolean;
}) {
  return (
    <Card className={`${styles.task} ${styles[task.deadline_level] ?? ""}`}>
      <header className={styles.taskHeader}>
        <div>
          <div className={styles.code}>
            {task.code}
            {showEmployee ? ` · ${task.employee.name}` : ""}
          </div>
          <h2>
            <Link to={`/taches/${task.id}`}>{task.title}</Link>
          </h2>
        </div>
        <div className={styles.badges}>
          {task.blocked && <AlertBadge>Point d'attention</AlertBadge>}
          <StatusBadge status={task.status}>{task.status_label}</StatusBadge>
        </div>
      </header>
      <div>
        <div className="cluster">
          <strong>{task.percentage} %</strong>
          {task.progress_delta !== 0 && (
            <span className="muted">
              {task.progress_delta > 0 ? "+" : ""}
              {task.progress_delta} sur la période
            </span>
          )}
        </div>
        <div
          className={styles.meter}
          role="progressbar"
          aria-valuenow={task.percentage}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Progression de ${task.title}`}
        >
          <span style={{ width: `${task.percentage}%` }} />
        </div>
      </div>
      <div className={styles.taskFacts}>
        <div className={styles.taskFact}>
          Début<strong>{formatDate(task.start_date)}</strong>
        </div>
        <div className={styles.taskFact}>
          Fin prévue<strong>{formatDate(task.due_date)}</strong>
        </div>
        <div className={styles.taskFact}>
          Charge restante<strong>{dayCount(task.workload.remaining)}</strong>
        </div>
      </div>
      {task.latest_note && (
        <p className={styles.observation}>{task.latest_note}</p>
      )}
    </Card>
  );
}
