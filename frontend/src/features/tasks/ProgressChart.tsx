import { useId, useMemo, useState } from "react";
import type { ChartPoint } from "../../lib/api/types";
import { dayLabel, formatDate } from "../../lib/format";
import styles from "./tasks.module.css";

const WIDTH = 760;
const HEIGHT = 250;
const MARGIN = { top: 18, right: 20, bottom: 42, left: 42 };

export function ProgressChart({
  points,
  today,
}: {
  points: ChartPoint[];
  today: string;
}) {
  const titleId = useId();
  const [active, setActive] = useState<number | null>(null);
  const data = useMemo(
    () =>
      points.map((point) => ({
        ...point,
        timestamp: new Date(`${point.day}T12:00:00`).getTime(),
      })),
    [points],
  );
  if (!data.length)
    return <p className="muted">Aucune progression n'est encore disponible.</p>;

  const min = data[0].timestamp;
  const max = data[data.length - 1].timestamp;
  const span = Math.max(1, max - min);
  const x = (timestamp: number) =>
    MARGIN.left +
    ((timestamp - min) / span) * (WIDTH - MARGIN.left - MARGIN.right);
  const y = (percentage: number) =>
    HEIGHT -
    MARGIN.bottom -
    (percentage / 100) * (HEIGHT - MARGIN.top - MARGIN.bottom);
  const path = data
    .map(
      (point, index) =>
        `${index ? "L" : "M"}${x(point.timestamp).toFixed(1)},${y(point.percentage).toFixed(1)}`,
    )
    .join(" ");
  const labels = [
    data[0],
    data[Math.floor((data.length - 1) / 2)],
    data[data.length - 1],
  ];
  const todayPoint = new Date(`${today}T12:00:00`).getTime();
  const selected = active === null ? null : data[active];

  return (
    <div className={styles.chartWrap}>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          Progression réelle de la tâche du {formatDate(data[0].day)} au{" "}
          {formatDate(data[data.length - 1].day)}
        </title>
        {data
          .filter((point) => !point.is_working_day)
          .map((point) => (
            <rect
              key={point.day}
              className={styles.weekend}
              x={x(point.timestamp) - 2}
              y={MARGIN.top}
              width={4}
              height={HEIGHT - MARGIN.top - MARGIN.bottom}
            />
          ))}
        {[0, 25, 50, 75, 100].map((value) => (
          <g key={value}>
            <line
              className={styles.gridLine}
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={y(value)}
              y2={y(value)}
            />
            <text className={styles.axisLabel} x={4} y={y(value) + 4}>
              {value} %
            </text>
          </g>
        ))}
        {todayPoint >= min && todayPoint <= max && (
          <line
            className={styles.todayLine}
            x1={x(todayPoint)}
            x2={x(todayPoint)}
            y1={MARGIN.top}
            y2={HEIGHT - MARGIN.bottom}
          />
        )}
        <path className={styles.line} d={path} />
        {data.map(
          (point, index) =>
            point.observed && (
              <circle
                key={point.day}
                className={styles.dot}
                cx={x(point.timestamp)}
                cy={y(point.percentage)}
                r={5}
                tabIndex={0}
                role="button"
                aria-label={`${formatDate(point.day)}, progression observée ${point.percentage} %`}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
                onMouseEnter={() => setActive(index)}
                onMouseLeave={() => setActive(null)}
              />
            ),
        )}
        {labels.map((point, index) => (
          <text
            key={`${point.day}-${index}`}
            className={styles.axisLabel}
            x={x(point.timestamp)}
            y={HEIGHT - 12}
            textAnchor={index === 0 ? "start" : index === 2 ? "end" : "middle"}
          >
            {dayLabel(point.day)}
          </text>
        ))}
      </svg>
      {selected && (
        <div
          className={styles.tooltip}
          role="status"
          style={{
            left: `${(x(selected.timestamp) / WIDTH) * 100}%`,
            top: `${(y(selected.percentage) / HEIGHT) * 100}%`,
          }}
        >
          <strong>{selected.percentage} %</strong>
          <br />
          {formatDate(selected.day)}
          <br />
          {selected.is_working_day ? "Jour ouvré" : "Jour non ouvré"}
        </div>
      )}
      <details>
        <summary>Afficher les données du graphique</summary>
        <div style={{ overflowX: "auto" }}>
          <table className={styles.chartTable}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Jour</th>
                <th>Progression</th>
                <th>Observation</th>
              </tr>
            </thead>
            <tbody>
              {data.map((point) => (
                <tr key={point.day}>
                  <td>{formatDate(point.day)}</td>
                  <td>{point.is_working_day ? "Ouvré" : "Non ouvré"}</td>
                  <td>{point.percentage} %</td>
                  <td>{point.observed ? "Saisie" : "Reportée"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
