import { area, bisector, curveStepAfter, line, scaleLinear } from "d3";
import {
  useId,
  useMemo,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import type { ChartPoint } from "../../lib/api/types";
import { dayLabel, formatDate } from "../../lib/format";
import styles from "./tasks.module.css";

const WIDTH = 760;
const HEIGHT = 300;
const MARGIN = { top: 46, right: 22, bottom: 46, left: 46 };
const NON_WORKING_DAY_WEIGHT = 0.18;
const CHART_PALETTE = [
  "#006b54",
  "#285b9b",
  "#7a4e9d",
  "#a14f1f",
  "#297783",
  "#765f18",
];
const NUMBER_FORMATTER = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 1,
});

type CalendarSegment = {
  day: string;
  isWorkingDay: boolean;
  startUnit: number;
  endUnit: number;
};

type PlotPoint = ChartPoint & {
  unit: number;
};

function parseDay(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function isoDay(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function colorFor(value: string | number): string {
  let hash = 0;
  for (const character of String(value))
    hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return CHART_PALETTE[Math.abs(hash) % CHART_PALETTE.length];
}

function formatNumber(value: number): string {
  return NUMBER_FORMATTER.format(value);
}

function workDayLabel(value: number): string {
  return `${formatNumber(value)} jour${value === 1 ? "" : "s"} ouvré${value === 1 ? "" : "s"}`;
}

function calendarDay(start: string, selected: string): number {
  return Math.max(
    0,
    Math.round(
      (parseDay(selected).getTime() - parseDay(start).getTime()) / 86_400_000,
    ),
  );
}

function calendarDays(start: string, end: string): string[] {
  const days: string[] = [];
  const cursor = parseDay(start);
  const last = parseDay(end);
  while (cursor <= last) {
    days.push(isoDay(cursor));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return days;
}

function weightedCalendar(
  points: ChartPoint[],
  start: string,
  end: string,
): CalendarSegment[] {
  const explicitDays = new Map(
    points.map((point) => [point.day, point.is_working_day]),
  );
  let unit = 0;
  return calendarDays(start, end).map((day) => {
    const date = parseDay(day);
    const isWorkingDay =
      explicitDays.get(day) ?? ![0, 6].includes(date.getUTCDay());
    const weight = isWorkingDay ? 1 : NON_WORKING_DAY_WEIGHT;
    const segment = {
      day,
      isWorkingDay,
      startUnit: unit,
      endUnit: unit + weight,
    };
    unit += weight;
    return segment;
  });
}

export function ProgressChart({
  points,
  today,
  status,
  previewPercentage,
  actionKey,
}: {
  points: ChartPoint[];
  today: string;
  status: string;
  previewPercentage?: number;
  actionKey?: string | number | null;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const [active, setActive] = useState<number | null>(null);
  const chart = useMemo(() => {
    if (!points.length) return null;
    const start = points[0].start_date;
    const due = points[0].due_date;
    const last = points[points.length - 1].day;
    const isOpen = !["completed", "closed_early"].includes(status);
    const end = isOpen ? ([today, due, last].sort().at(-1) ?? last) : last;
    const calendar = weightedCalendar(points, start, end);
    const segmentByDay = new Map(
      calendar.map((segment) => [segment.day, segment]),
    );
    const totalUnits = calendar.at(-1)?.endUnit ?? 1;
    const xScale = scaleLinear()
      .domain([0, Math.max(1, totalUnits)])
      .range([MARGIN.left, WIDTH - MARGIN.right]);
    const yScale = scaleLinear()
      .domain([0, 100])
      .range([HEIGHT - MARGIN.bottom, MARGIN.top]);
    const position = (day: string) => {
      const segment = segmentByDay.get(day);
      return xScale(
        segment ? (segment.startUnit + segment.endUnit) / 2 : totalUnits,
      );
    };
    const serverPoints: PlotPoint[] = points.map((point) => ({
      ...point,
      unit: position(point.day),
    }));
    const previewActive =
      previewPercentage !== undefined &&
      previewPercentage !== points[points.length - 1].percentage;
    const displayPoints = serverPoints.map((point) =>
      previewActive && point.day === today
        ? { ...point, percentage: previewPercentage }
        : point,
    );
    const lineGenerator = line<PlotPoint>()
      .x((point) => point.unit)
      .y((point) => yScale(point.percentage))
      .curve(curveStepAfter);
    const areaGenerator = area<PlotPoint>()
      .x((point) => point.unit)
      .y0(yScale(0))
      .y1((point) => yScale(point.percentage))
      .curve(curveStepAfter);
    const labelsEvery = Math.max(1, Math.ceil(calendar.length / 6));
    const labels = calendar.filter(
      (_segment, index) =>
        index === 0 ||
        index === calendar.length - 1 ||
        index % labelsEvery === 0,
    );
    return {
      start,
      due,
      isOpen,
      calendar,
      xScale,
      yScale,
      position,
      serverPoints,
      displayPoints,
      previewActive,
      serverPath: lineGenerator(serverPoints) ?? "",
      displayPath: lineGenerator(displayPoints) ?? "",
      displayArea: areaGenerator(displayPoints) ?? "",
      labels,
    };
  }, [points, previewPercentage, status, today]);

  if (!chart)
    return <p className="muted">Aucune progression n'est encore disponible.</p>;

  const renderedChart = chart;
  const selected = active === null ? null : chart.displayPoints[active];
  const todayIndex = chart.displayPoints.findIndex(
    (point) => point.day === today,
  );
  const currentPoint =
    chart.displayPoints[todayIndex] ?? chart.displayPoints.at(-1);
  const currentOverdue = currentPoint?.overdue_days ?? 0;
  const markerData = [
    {
      day: chart.start,
      label: "Début",
      className: styles.startLine,
      labelClassName: styles.startLabel,
    },
    {
      day: today,
      label: "Aujourd'hui",
      className: styles.todayLine,
      labelClassName: styles.todayLabel,
    },
    {
      day: chart.due,
      label: "Fin prévue",
      className: styles.dueLine,
      labelClassName: styles.dueLabel,
    },
  ].filter((marker) =>
    chart.calendar.some((segment) => segment.day === marker.day),
  );
  const lastPercentage = chart.displayPoints.at(-1)?.percentage ?? 0;
  const showOverrun = chart.isOpen && today > chart.due && lastPercentage < 100;
  const chartColor = colorFor(actionKey ?? "sans-action");

  function moveSelection(event: KeyboardEvent<HTMLDivElement>) {
    if (
      !["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)
    )
      return;
    event.preventDefault();
    if (event.key === "Escape") {
      setActive(null);
      return;
    }
    if (event.key === "Home") {
      setActive(0);
      return;
    }
    if (event.key === "End") {
      setActive(renderedChart.displayPoints.length - 1);
      return;
    }
    setActive((current) => {
      const start = current ?? renderedChart.displayPoints.length - 1;
      const delta = event.key === "ArrowLeft" ? -1 : 1;
      return Math.max(
        0,
        Math.min(renderedChart.displayPoints.length - 1, start + delta),
      );
    });
  }

  function selectFromPointer(clientX: number, element: SVGSVGElement) {
    const bounds = element.getBoundingClientRect();
    const svgX = ((clientX - bounds.left) / Math.max(1, bounds.width)) * WIDTH;
    const index = bisector((point: PlotPoint) => point.unit).center(
      renderedChart.displayPoints,
      svgX,
    );
    setActive(
      Math.max(0, Math.min(renderedChart.displayPoints.length - 1, index)),
    );
  }

  return (
    <div
      className={styles.chartWrap}
      style={{ "--chart-color": chartColor } as CSSProperties}
      tabIndex={0}
      onKeyDown={moveSelection}
      onFocus={() =>
        setActive((current) => current ?? chart.displayPoints.length - 1)
      }
      onBlur={() => setActive(null)}
      aria-label="Graphique de progression. Utilisez les flèches gauche et droite pour parcourir les dates."
    >
      {chart.previewActive && (
        <p className={styles.previewNotice} role="status">
          Aperçu non enregistré : {previewPercentage} %
        </p>
      )}
      {showOverrun && currentOverdue > 0 && (
        <p className={styles.overdueNotice} role="status">
          Retard : {workDayLabel(currentOverdue)}
        </p>
      )}
      <details className={styles.chartLegend}>
        <summary>Comprendre le graphique</summary>
        <p>
          Les points pleins sont des saisies réelles ; les points creux
          reportent la dernière valeur connue.
        </p>
        <p>
          Les bandes grises représentent les jours non ouvrés comprimés. La zone
          rose après l’échéance indique le retard d’une tâche ouverte.
        </p>
      </details>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={`${titleId} ${descriptionId}`}
        onPointerMove={(event) =>
          selectFromPointer(event.clientX, event.currentTarget)
        }
        onPointerLeave={() => setActive(null)}
      >
        <title id={titleId}>
          Progression réelle de la tâche du {formatDate(chart.start)} au{" "}
          {formatDate(chart.displayPoints.at(-1)?.day ?? chart.start)}
        </title>
        <desc id={descriptionId}>
          Aujourd’hui {formatDate(today)}. Fin prévue {formatDate(chart.due)}.
          {showOverrun && currentOverdue > 0
            ? ` Retard de ${workDayLabel(currentOverdue)}.`
            : " Aucun retard en cours."}
        </desc>
        {showOverrun && (
          <rect
            className={styles.overrun}
            x={chart.position(chart.due)}
            y={MARGIN.top}
            width={Math.max(
              0,
              chart.position(today) - chart.position(chart.due),
            )}
            height={HEIGHT - MARGIN.top - MARGIN.bottom}
          />
        )}
        {chart.calendar
          .filter((segment) => !segment.isWorkingDay)
          .map((segment) => (
            <rect
              key={segment.day}
              className={styles.weekend}
              x={chart.xScale(segment.startUnit)}
              y={MARGIN.top}
              width={Math.max(
                1,
                chart.xScale(segment.endUnit) - chart.xScale(segment.startUnit),
              )}
              height={HEIGHT - MARGIN.top - MARGIN.bottom}
            />
          ))}
        {[0, 25, 50, 75, 100].map((value) => (
          <g key={value}>
            <line
              className={styles.gridLine}
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={chart.yScale(value)}
              y2={chart.yScale(value)}
            />
            <text
              className={styles.axisLabel}
              x={4}
              y={chart.yScale(value) + 4}
            >
              {value} %
            </text>
          </g>
        ))}
        {markerData.map((marker, index) => {
          const markerPosition = chart.position(marker.day);
          const textAnchor: "start" | "middle" | "end" =
            markerPosition < WIDTH * 0.18
              ? "start"
              : markerPosition > WIDTH * 0.82
                ? "end"
                : "middle";
          return (
            <g key={marker.label}>
              <line
                className={marker.className}
                x1={markerPosition}
                x2={markerPosition}
                y1={MARGIN.top}
                y2={HEIGHT - MARGIN.bottom}
              />
              <text
                className={`${styles.markerLabel} ${marker.labelClassName}`}
                x={markerPosition}
                y={14 + index * 13}
                textAnchor={textAnchor}
              >
                {marker.label} {formatDate(marker.day)}
              </text>
            </g>
          );
        })}
        <path className={styles.area} d={chart.displayArea} />
        {chart.previewActive && (
          <path className={styles.serverLine} d={chart.serverPath} />
        )}
        <path
          className={chart.previewActive ? styles.previewLine : styles.line}
          d={chart.displayPath}
        />
        {chart.serverPoints.map((point) => (
          <circle
            key={point.day}
            className={point.observed ? styles.dotObserved : styles.dotCarried}
            cx={point.unit}
            cy={chart.yScale(point.percentage)}
            r={point.observed ? 4.2 : 2.4}
          />
        ))}
        {chart.previewActive && todayIndex >= 0 && (
          <circle
            className={styles.previewDot}
            cx={chart.displayPoints[todayIndex].unit}
            cy={chart.yScale(chart.displayPoints[todayIndex].percentage)}
            r={6}
          />
        )}
        {selected && (
          <>
            <line
              className={styles.focusLine}
              x1={selected.unit}
              x2={selected.unit}
              y1={MARGIN.top}
              y2={HEIGHT - MARGIN.bottom}
            />
            <circle
              className={styles.focusDot}
              cx={selected.unit}
              cy={chart.yScale(selected.percentage)}
              r={6}
            />
          </>
        )}
        {chart.labels.map((segment) => (
          <text
            key={segment.day}
            className={styles.axisLabel}
            x={chart.position(segment.day)}
            y={HEIGHT - 12}
            textAnchor="middle"
          >
            {dayLabel(segment.day)}
          </text>
        ))}
      </svg>
      {selected && (
        <div
          className={styles.tooltip}
          role="status"
          style={{
            left: `${(selected.unit / WIDTH) * 100}%`,
            top: `${(chart.yScale(selected.percentage) / HEIGHT) * 100}%`,
          }}
        >
          <strong>{selected.percentage} %</strong>
          <br />
          {formatDate(selected.day)}
          <br />
          {selected.is_working_day ? "Jour ouvré" : "Jour non ouvré"}
          <br />
          Jour calendrier : {calendarDay(chart.start, selected.day)}
          <br />
          Jours ouvrés écoulés : {formatNumber(selected.elapsed_work_days)}
          <br />
          Retard : {workDayLabel(selected.overdue_days)}
          <br />
          {selected.observed ? "Saisie réelle" : "Valeur reportée"}
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
                <th>Jours ouvrés écoulés</th>
                <th>Retard</th>
                <th>Observation</th>
              </tr>
            </thead>
            <tbody>
              {chart.displayPoints.map((point, index) => {
                const isPreview = chart.previewActive && point.day === today;
                return (
                  <tr key={point.day}>
                    <td>{formatDate(point.day)}</td>
                    <td>{point.is_working_day ? "Ouvré" : "Non ouvré"}</td>
                    <td>
                      {point.percentage} %{isPreview ? " (aperçu)" : ""}
                    </td>
                    <td>{formatNumber(point.elapsed_work_days)}</td>
                    <td>{workDayLabel(point.overdue_days)}</td>
                    <td>
                      {isPreview
                        ? `Non enregistré, valeur serveur ${chart.serverPoints[index].percentage} %`
                        : point.observed
                          ? "Saisie"
                          : "Reportée"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
