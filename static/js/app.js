"use strict";

const palette = ["#006b54", "#285b9b", "#7a4e9d", "#a14f1f", "#297783", "#765f18"];
const nonWorkingDayWeight = 0.25;

function colorFor(key) {
  let hash = 0;
  for (const character of key) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return palette[Math.abs(hash) % palette.length];
}

function parseDate(value) {
  if (!value) return null;
  const text = String(value).trim();
  const parts = text.includes("/") ? text.split("/").map(Number) : text.split("-").map(Number);
  const [year, month, day] = text.includes("/") ? [parts[2], parts[1], parts[0]] : parts;
  if (![year, month, day].every(Number.isFinite)) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function isoDate(value) {
  return value.toISOString().slice(0, 10);
}

function inputDate(value) {
  return `${String(value.getUTCDate()).padStart(2, "0")}/${String(value.getUTCMonth() + 1).padStart(2, "0")}/${value.getUTCFullYear()}`;
}

function formatNumber(value) {
  return Number(value).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
}

function formatDate(value) {
  const parsed = parseDate(value);
  if (!parsed) return String(value || "");
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(parsed);
}

document.querySelectorAll("[data-progress]").forEach((slider) => {
  const form = slider.closest("[data-progress-baseline]");
  const output = form ? form.querySelector("#progress-output") : null;
  const note = form ? form.querySelector("[name='note']") : null;
  const attention = form ? form.querySelector("[name='blocked']") : null;
  const warning = form ? form.querySelector(".progress-regression-note") : null;
  const baseline = form ? Number(form.dataset.progressBaseline) : Number(slider.value);
  const update = () => {
    if (output) output.textContent = `${slider.value} %`;
    const decrease = baseline - Number(slider.value);
    const explanationRequired = decrease > 0 || Boolean(attention && attention.checked);
    if (form) form.classList.toggle("progress-regression", decrease > 0);
    if (warning) warning.textContent = decrease > 0 ? `Progression réduite de ${decrease} points` : "";
    if (note) {
      note.required = explanationRequired;
      note.setAttribute("aria-required", explanationRequired ? "true" : "false");
    }
  };
  slider.addEventListener("input", update);
  if (attention) attention.addEventListener("change", update);
  update();
});

function renderWorkloadChart(element) {
  if (!window.d3) return;
  const total = Number(element.dataset.total);
  const completed = Number(element.dataset.completed);
  if (!Number.isFinite(total) || total <= 0) return;
  element.querySelectorAll("svg").forEach((svg) => svg.remove());
  const width = Math.max(220, element.clientWidth || 280);
  const height = 66;
  const margin = { top: 18, right: 8, bottom: 20, left: 8 };
  const x = d3.scaleLinear().domain([0, total]).range([margin.left, width - margin.right]);
  const svg = d3.select(element).insert("svg", ":first-child").attr("viewBox", `0 0 ${width} ${height}`).attr("aria-hidden", "true");
  svg.append("rect").attr("x", x(0)).attr("y", 22).attr("width", x(total) - x(0)).attr("height", 16).attr("rx", 5).attr("class", "workload-remaining");
  svg.append("rect").attr("x", x(0)).attr("y", 22).attr("width", Math.max(0, x(completed) - x(0))).attr("height", 16).attr("rx", 5).attr("class", "workload-completed");
  svg.append("text").attr("x", x(Math.min(completed, total))).attr("y", 14).attr("text-anchor", completed > total / 2 ? "end" : "start").attr("class", "chart-label").text(`${completed.toLocaleString("fr-FR")} j réalisés`);
  svg.append("g").attr("transform", "translate(0,40)").attr("class", "workload-axis").call(d3.axisBottom(x).tickValues([0, total]).tickFormat((value) => `${value} j`));
}

document.querySelectorAll(".workload-chart").forEach(renderWorkloadChart);

function normalizeProgressRows(rows) {
  return rows.map((row) => ({
    taskId: Number(row.task_id),
    date: parseDate(row.day),
    dayText: row.day,
    startDate: parseDate(row.start_date),
    dueDate: parseDate(row.due_date),
    isWorkingDay: row.is_working_day === true || row.is_working_day === 1 || row.is_working_day === "true",
    plannedWorkDays: Number(row.planned_work_days),
    elapsedWorkDays: Number(row.elapsed_work_days),
    remainingScheduleDays: Number(row.remaining_schedule_days),
    overdueDays: Number(row.overdue_days),
    percentage: Math.max(0, Math.min(100, Number(row.percentage))),
    observed: row.observed === true || row.observed === 1 || row.observed === "true",
  })).filter((row) => row.date instanceof Date && !Number.isNaN(row.date.valueOf()) && Number.isFinite(row.percentage)).sort((left, right) => left.date - right.date);
}

let tooltipElement = null;

function chartTooltip() {
  if (tooltipElement) return tooltipElement;
  tooltipElement = document.createElement("div");
  tooltipElement.className = "progress-chart-tooltip";
  tooltipElement.setAttribute("role", "status");
  tooltipElement.setAttribute("aria-live", "polite");
  tooltipElement.hidden = true;
  document.body.append(tooltipElement);
  return tooltipElement;
}

function positionTooltip(clientX, clientY) {
  const tooltip = chartTooltip();
  const gap = 14;
  const bounds = tooltip.getBoundingClientRect();
  let left = clientX + gap;
  let top = clientY - bounds.height - gap;
  if (left + bounds.width > window.innerWidth - 8) left = clientX - bounds.width - gap;
  if (top < 8) top = clientY + gap;
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${Math.min(window.innerHeight - bounds.height - 8, Math.max(8, top))}px`;
}

function showProgressTooltip(point, clientX, clientY) {
  const tooltip = chartTooltip();
  const dateLabel = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "long", year: "numeric", timeZone: "UTC" }).format(point.date);
  const lines = [
    dateLabel,
    point.isWorkingDay ? "Jour ouvré" : "Jour non ouvré",
    `Jour calendrier : ${point.calendarDay}`,
    `Jours ouvrés écoulés : ${point.elapsedWorkDays}`,
    `Progression connue : ${point.percentage} %`,
    `Retard : ${formatNumber(point.overdueDays)} j ouvré${point.overdueDays > 1 ? "s" : ""}`,
    point.observed ? "Saisie réelle ce jour" : "Dernière valeur reportée",
  ];
  tooltip.replaceChildren(...lines.map((line, index) => {
    const item = document.createElement("div");
    item.textContent = line;
    if (index === 0) item.className = "progress-tooltip-title";
    return item;
  }));
  tooltip.hidden = false;
  positionTooltip(clientX, clientY);
}

function hideProgressTooltip() {
  if (tooltipElement) tooltipElement.hidden = true;
}

function weightedCalendar(rows, start, end) {
  const explicit = new Map(rows.map((row) => [row.dayText, row.isWorkingDay]));
  const dates = d3.utcDay.range(d3.utcDay.floor(start), d3.utcDay.offset(d3.utcDay.floor(end), 1));
  let total = 0;
  const segments = dates.map((date) => {
    const key = d3.utcFormat("%Y-%m-%d")(date);
    const working = explicit.has(key) ? explicit.get(key) : date.getUTCDay() !== 0 && date.getUTCDay() !== 6;
    const weight = working ? 1 : nonWorkingDayWeight;
    const segment = { date, working, u0: total, u1: total + weight };
    total += weight;
    return segment;
  });
  return { segments, total: Math.max(total, 1) };
}

function renderProgressChart(element, rawRows, { variant = "compact" } = {}) {
  if (!window.d3) return;
  const rows = normalizeProgressRows(rawRows);
  if (!rows.length) return;
  element.querySelectorAll("svg").forEach((svg) => svg.remove());
  const start = parseDate(element.dataset.start) || rows[0].startDate;
  const today = parseDate(element.dataset.today) || rows.at(-1).date;
  const due = parseDate(element.dataset.due) || rows[0].dueDate;
  const last = rows.at(-1).date;
  const open = element.dataset.open === "true";
  const end = open
    ? new Date(Math.max(today.valueOf(), due.valueOf(), last.valueOf()))
    : last;
  element.dataset.chartEnd = isoDate(end);
  const compact = variant === "compact";
  const width = Math.max(compact ? 270 : 640, element.clientWidth || (compact ? 320 : 860));
  const height = compact ? 128 : 330;
  const margin = compact ? { top: 27, right: 10, bottom: 25, left: 30 } : { top: 42, right: 22, bottom: 48, left: 48 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const calendar = weightedCalendar(rows, start, end);
  const unitScale = d3.scaleLinear().domain([0, calendar.total]).range([0, innerWidth]);
  const segmentByDay = new Map(calendar.segments.map((segment) => [isoDate(segment.date), segment]));
  const xDate = (date) => {
    const segment = segmentByDay.get(isoDate(date));
    if (!segment) return date <= start ? 0 : innerWidth;
    return unitScale((segment.u0 + segment.u1) / 2);
  };
  const y = d3.scaleLinear().domain([0, 100]).range([innerHeight, 0]);
  const color = colorFor(element.dataset.action || "sans-action");
  const svg = d3.select(element).insert("svg", ":first-child").attr("viewBox", `0 0 ${width} ${height}`).attr("aria-hidden", "true");
  const chart = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  if (open && today > due && rows.at(-1).percentage < 100) {
    chart.append("rect").attr("x", xDate(due)).attr("y", 0).attr("width", Math.max(0, xDate(today) - xDate(due))).attr("height", innerHeight).attr("class", "chart-overrun-zone");
  }
  chart.append("g").attr("class", "chart-non-working-days").selectAll("rect").data(calendar.segments.filter((segment) => !segment.working)).join("rect").attr("x", (segment) => unitScale(segment.u0)).attr("y", 0).attr("width", (segment) => Math.max(1, unitScale(segment.u1) - unitScale(segment.u0))).attr("height", innerHeight);
  [0, 25, 50, 75, 100].forEach((value) => chart.append("line").attr("x1", 0).attr("x2", innerWidth).attr("y1", y(value)).attr("y2", y(value)).attr("class", "chart-guide"));

  const markerData = [
    { date: start, label: "Début", className: "chart-start-line" },
    { date: today, label: "Aujourd’hui", className: "chart-today-line" },
    { date: due, label: "Fin prévue", className: "chart-due-line" },
  ];
  markerData.filter((marker) => marker.date >= start && marker.date <= end).forEach((marker, index) => {
    const position = xDate(marker.date);
    chart.append("line").attr("x1", position).attr("x2", position).attr("y1", 0).attr("y2", innerHeight).attr("class", marker.className);
    if (!compact) chart.append("text").attr("x", position).attr("y", -10 - (index % 2) * 14).attr("text-anchor", position < innerWidth * 0.18 ? "start" : position > innerWidth * 0.82 ? "end" : "middle").attr("class", `chart-marker-label ${marker.className}-label`).text(`${marker.label} ${d3.utcFormat("%d/%m/%Y")(marker.date)}`);
  });

  const area = d3.area().x((point) => xDate(point.date)).y0(y(0)).y1((point) => y(point.percentage)).curve(d3.curveStepAfter);
  const line = d3.line().x((point) => xDate(point.date)).y((point) => y(point.percentage)).curve(d3.curveStepAfter);
  if (!compact) chart.append("path").datum(rows).attr("d", area).attr("class", "chart-progress-area").attr("fill", color);
  chart.append("path").datum(rows).attr("d", line).attr("fill", "none").attr("stroke", color).attr("class", "chart-progress-line");
  chart.selectAll("circle.chart-point").data(rows).join("circle").attr("class", (point) => point.observed ? "chart-point chart-point-observed" : "chart-point chart-point-carried").attr("cx", (point) => xDate(point.date)).attr("cy", (point) => y(point.percentage)).attr("r", (point) => point.observed ? (compact ? 3.2 : 4.2) : (compact ? 2.1 : 3)).attr("fill", (point) => point.observed ? color : "white").attr("stroke", color);

  const maxLabels = Math.max(2, Math.floor(innerWidth / (compact ? 72 : 84)));
  const step = Math.max(1, Math.ceil(calendar.segments.length / maxLabels));
  const tickSegments = calendar.segments.filter((_segment, index) => index % step === 0 || index === calendar.segments.length - 1);
  const axis = chart.append("g").attr("transform", `translate(0,${innerHeight})`).attr("class", "profile-axis");
  axis.append("line").attr("x1", 0).attr("x2", innerWidth).attr("stroke", "currentColor");
  axis.selectAll("line.day-tick").data(calendar.segments).join("line").attr("class", "day-tick").attr("x1", (segment) => xDate(segment.date)).attr("x2", (segment) => xDate(segment.date)).attr("y1", 0).attr("y2", (segment) => segment.working ? 6 : 3);
  axis.selectAll("text.day-label").data(tickSegments).join("text").attr("class", "day-label").attr("x", (segment) => xDate(segment.date)).attr("y", 18).attr("text-anchor", "middle").text((segment) => d3.utcFormat("%d/%m")(segment.date));
  if (!compact) chart.append("g").attr("class", "profile-axis").call(d3.axisLeft(y).tickValues([0, 25, 50, 75, 100]).tickFormat((value) => `${value}%`).tickSize(0)).call((group) => group.select(".domain").remove());

  const focusLine = chart.append("line").attr("y1", 0).attr("y2", innerHeight).attr("class", "chart-focus-line").style("display", "none");
  const focusPoint = chart.append("circle").attr("r", compact ? 4 : 5.5).attr("fill", "white").attr("stroke", color).attr("stroke-width", 2).style("display", "none");
  const rowByDay = new Map(rows.map((row) => [row.dayText, row]));
  const selectPoint = (segment, clientX, clientY) => {
    let point = rowByDay.get(isoDate(segment.date));
    if (!point) {
      point = rows[Math.max(0, d3.bisector((row) => row.date).right(rows, segment.date) - 1)];
    }
    const enriched = { ...point, date: segment.date, isWorkingDay: segment.working, calendarDay: d3.utcDay.count(start, segment.date) };
    const x = xDate(segment.date);
    focusLine.attr("x1", x).attr("x2", x).style("display", null);
    focusPoint.attr("cx", x).attr("cy", y(point.percentage)).style("display", null);
    showProgressTooltip(enriched, clientX, clientY);
  };
  const segmentEnds = calendar.segments.map((segment) => unitScale(segment.u1));
  const overlay = chart.append("rect").attr("width", innerWidth).attr("height", innerHeight).attr("fill", "transparent").attr("class", "chart-pointer-layer");
  overlay.on("pointermove", function (event) {
    const [pointerX] = d3.pointer(event, this);
    const index = Math.min(calendar.segments.length - 1, d3.bisectRight(segmentEnds, Math.max(0, Math.min(innerWidth - 0.001, pointerX))));
    selectPoint(calendar.segments[index], event.clientX, event.clientY);
  }).on("pointerleave", () => {
    focusLine.style("display", "none");
    focusPoint.style("display", "none");
    hideProgressTooltip();
  });

  element.tabIndex = element.tabIndex >= 0 ? element.tabIndex : 0;
  let keyboardIndex = Math.max(0, calendar.segments.length - 1);
  const keyboardPoint = () => {
    const rect = element.getBoundingClientRect();
    const segment = calendar.segments[keyboardIndex];
    const clientX = rect.left + margin.left / width * rect.width + xDate(segment.date) / width * rect.width;
    const clientY = rect.top + rect.height / 2;
    selectPoint(segment, clientX, clientY);
  };
  element.onfocus = keyboardPoint;
  element.onkeydown = (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      keyboardIndex = Math.max(0, Math.min(calendar.segments.length - 1, keyboardIndex + (event.key === "ArrowLeft" ? -1 : 1)));
      keyboardPoint();
    } else if (event.key === "Escape") {
      hideProgressTooltip();
    }
  };
  element.onblur = hideProgressTooltip;
  element.dataset.chartRendered = "true";
}

async function renderTaskHistory(element) {
  if (!window.d3 || !element.dataset.progressUrl) return;
  try {
    const response = await fetch(element.dataset.progressUrl, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderProgressChart(element, await response.json(), {
      variant: element.dataset.chartVariant === "compact" ? "compact" : "full",
    });
  } catch (_error) {
    element.classList.add("chart-load-error");
  }
}

document.querySelectorAll(".task-history-chart").forEach(renderTaskHistory);

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function marker(label, className, symbol) {
  const item = createElement("b", `marker ${className}`, symbol);
  item.title = label;
  return item;
}

function taskProfile(task) {
  const article = createElement("article", `task-profile task-profile-${task.deadline_level}`);
  const row = createElement("div", "task-profile-row");
  const button = createElement("button", "task-profile-toggle");
  button.type = "button";
  button.setAttribute("aria-expanded", "false");
  button.append(createElement("span", "task-profile-title", task.task_title));
  const markers = createElement("span", "task-markers");
  markers.setAttribute("aria-label", "Alertes");
  if (task.blocked) markers.append(marker("Point d’attention", "marker-blocked", "●"));
  if (task.late) markers.append(marker("Retard", "marker-late", "▲"));
  if (task.missing_update) markers.append(marker("Absence de mise à jour", "marker-missing", "○"));
  button.append(markers);
  const chart = createElement("div", "task-profile-chart workload-chart");
  chart.dataset.total = task.planned_work_days;
  chart.dataset.completed = task.completed_work_days;
  chart.dataset.remaining = task.remaining_work_days;
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", `${task.task_title}, ${formatNumber(task.completed_work_days)} jours réalisés, ${formatNumber(task.remaining_work_days)} jours restants`);
  row.append(button, chart);
  const details = createElement("div", "task-profile-details");
  details.hidden = true;
  details.append(
    createElement("p", "", `${task.percentage} % réalisé · ${formatNumber(task.remaining_work_days)} j restants · ${formatNumber(task.planned_work_days)} j initialement`),
    createElement("p", "", `Début ${formatDate(task.start_date)} · Aujourd’hui ${formatDate(task.today)} · Fin prévue ${formatDate(task.due_date)}`),
  );
  const link = createElement("a", "", "Ouvrir la tâche");
  link.href = task.detail_url;
  details.append(link);
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    details.hidden = !expanded;
  });
  article.append(row, details);
  requestAnimationFrame(() => renderWorkloadChart(chart));
  return article;
}

function renderEmployeeProfile(branch, payload) {
  const target = branch.querySelector(":scope > .team-node-content > [data-team-profile-content]");
  if (!target) return;
  const profiles = createElement("div", "task-profiles");
  profiles.append(createElement("h3", "", "Profil des tâches"));
  if (payload.tasks.length) payload.tasks.forEach((task) => profiles.append(taskProfile(task)));
  else profiles.append(createElement("p", "", "Aucune tâche sur cette période."));
  target.replaceChildren(profiles);
}

async function loadTeamBranch(branch) {
  if (branch.dataset.teamLoadState === "loaded" || branch.dataset.teamLoadState === "loading") return;
  const target = branch.querySelector(":scope > .team-node-content > [data-team-profile-content]");
  const status = target ? target.querySelector("[data-team-profile-status]") : null;
  branch.dataset.teamLoadState = "loading";
  if (status) status.textContent = "Chargement des indicateurs et graphiques…";
  try {
    const response = await fetch(branch.dataset.teamProfileUrl, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderEmployeeProfile(branch, await response.json());
    branch.dataset.teamLoadState = "loaded";
  } catch (_error) {
    branch.dataset.teamLoadState = "error";
    if (!target) return;
    const message = createElement("p", "team-profile-status", "Chargement impossible.");
    message.setAttribute("role", "alert");
    const retry = createElement("button", "button", "Réessayer");
    retry.type = "button";
    retry.addEventListener("click", () => loadTeamBranch(branch));
    target.replaceChildren(message, retry);
  }
}

document.querySelectorAll(".team-branch").forEach((branch) => {
  branch.dataset.teamLoadState = "idle";
  const subteam = branch.querySelector(":scope > .team-node-content > .subteam");
  branch.addEventListener("toggle", () => {
    if (branch.open) {
      if (subteam) subteam.open = true;
      loadTeamBranch(branch);
      return;
    }
    if (subteam) subteam.open = false;
    branch.querySelectorAll(".team-branch[open]").forEach((descendant) => {
      descendant.open = false;
    });
  });
});

document.querySelectorAll("[data-schedule-form]").forEach((form) => {
  const start = form.querySelector("[data-schedule-start]");
  const due = form.querySelector("[data-schedule-due]");
  const workload = form.querySelector("[data-schedule-workload]");
  const source = form.querySelector("[name='schedule_source']");
  const overridesInput = form.querySelector("[name='calendar_overrides']");
  if (!start || !due || !workload || !source) return;
  let overrides = {};
  try { overrides = JSON.parse(overridesInput ? overridesInput.value : "{}"); } catch (_error) { overrides = {}; }
  const working = (day) => Object.prototype.hasOwnProperty.call(overrides, isoDate(day)) ? Boolean(overrides[isoDate(day)]) : day.getUTCDay() > 0 && day.getUTCDay() < 6;
  const calculateDue = () => {
    if (!start.value || !workload.value || Number(workload.value) <= 0) return;
    const cursor = parseDate(start.value);
    let remaining = Math.ceil(Number(workload.value));
    while (remaining > 0) {
      cursor.setUTCDate(cursor.getUTCDate() + 1);
      if (working(cursor)) remaining -= 1;
    }
    due.value = inputDate(cursor);
  };
  const calculateWorkload = () => {
    if (!start.value || !due.value) return;
    const cursor = parseDate(start.value);
    const end = parseDate(due.value);
    let days = 0;
    while (cursor < end) {
      cursor.setUTCDate(cursor.getUTCDate() + 1);
      if (working(cursor)) days += 1;
    }
    workload.value = days > 0 ? String(days) : "";
  };
  start.addEventListener("change", () => { source.value = "due"; due.value ? calculateWorkload() : calculateDue(); });
  due.addEventListener("change", () => { source.value = "due"; calculateWorkload(); });
  workload.addEventListener("input", () => { source.value = "workload"; calculateDue(); });
});

document.querySelectorAll(".legend-toggle").forEach((button) => {
  const legend = document.getElementById(button.getAttribute("aria-controls"));
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (legend) legend.hidden = !expanded;
  });
});

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  const target = document.getElementById(button.dataset.copyTarget);
  const status = document.querySelector("[data-copy-status]");
  if (!target) return;
  button.addEventListener("click", async () => {
    const value = "value" in target ? target.value : target.textContent;
    try {
      await navigator.clipboard.writeText(value || "");
      if (status) status.textContent = `${button.dataset.copyLabel || "Contenu"} copié.`;
    } catch (_error) {
      if ("select" in target) target.select();
      if (status) status.textContent = "Copie automatique impossible. Sélectionnez puis copiez le contenu.";
    }
  });
});
