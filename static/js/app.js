"use strict";

const palette = ["#006b54", "#285b9b", "#7a4e9d", "#a14f1f", "#297783", "#765f18"];

function colorFor(key) {
  let hash = 0;
  for (const character of key) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return palette[Math.abs(hash) % palette.length];
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

function renderTaskProfile(element) {
  if (!window.d3) return;
  const planned = Number(element.dataset.planned);
  const percentage = Number(element.dataset.percentage);
  const open = element.dataset.open === "true";
  const points = Array.from(element.querySelectorAll("[data-x]")).map((point) => ({ date: parseDate(point.dataset.date), y: Number(point.dataset.y), observed: point.dataset.observed !== "false" })).filter((point) => point.date instanceof Date && !Number.isNaN(point.date.valueOf()));
  if (!points.length) return;
  const start = parseDate(element.dataset.start);
  const today = parseDate(element.dataset.today);
  const due = parseDate(element.dataset.due);
  if (!start || !today || !due) return;
  const end = new Date(Math.max(today.valueOf(), due.valueOf(), points[points.length - 1].date.valueOf()));
  const width = Math.max(250, element.clientWidth || 300);
  const height = 106;
  const margin = { top: 31, right: 12, bottom: 22, left: 27 };
  const x = d3.scaleUtc().domain([start, end]).range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain([0, 100]).range([height - margin.bottom, margin.top]);
  const color = colorFor(element.dataset.action || "sans-action");
  const svg = d3.select(element).insert("svg", ":first-child").attr("viewBox", `0 0 ${width} ${height}`).attr("aria-hidden", "true");
  if (open && today > due) svg.append("rect").attr("x", x(due)).attr("y", margin.top).attr("width", x(today) - x(due)).attr("height", height - margin.top - margin.bottom).attr("class", "chart-overrun-zone");
  [25, 50, 75].forEach((value) => svg.append("line").attr("x1", margin.left).attr("x2", width - margin.right).attr("y1", y(value)).attr("y2", y(value)).attr("class", "chart-guide"));
  renderDateMarkers(svg, x, { start, today, due }, margin.top, height - margin.bottom);
  const line = d3.line().x((point) => x(point.date)).y((point) => y(point.y)).curve(d3.curveMonotoneX);
  svg.append("path").datum(points).attr("d", line).attr("fill", "none").attr("stroke", color).attr("stroke-opacity", 0.35 + percentage / 155).attr("class", "chart-progress-line");
  const circles = svg.selectAll(".chart-point").data(points).enter().append("circle").attr("cx", (point) => x(point.date)).attr("cy", (point) => y(point.y)).attr("r", (_point, index) => index === points.length - 1 ? 4 : 2.2).attr("fill", (point) => point.observed ? color : "white").attr("stroke", color).attr("fill-opacity", (point) => point.observed ? 0.3 + point.y / 145 : 1).attr("class", (point) => point.observed ? "chart-point chart-point-observed" : "chart-point chart-point-carried");
  addPointTitles(circles);
  svg.append("g").attr("transform", `translate(0,${height - margin.bottom})`).attr("class", "profile-axis").call(d3.axisBottom(x).tickValues(uniqueDates([start, today, due])).tickFormat(d3.utcFormat("%d/%m")));
  svg.append("g").attr("transform", `translate(${margin.left},0)`).attr("class", "profile-axis").call(d3.axisLeft(y).tickValues([25, 50, 75]).tickFormat((value) => `${value}%`));
}

document.querySelectorAll(".workload-chart").forEach(renderWorkloadChart);
document.querySelectorAll(".task-profile-chart").forEach(renderTaskProfile);

function parseDate(value) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function uniqueDates(values) {
  const seen = new Set();
  return values.filter((value) => {
    const key = value.valueOf();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((left, right) => left - right);
}

function renderDateMarkers(svg, x, dates, top, bottom) {
  const format = d3.utcFormat("%d/%m/%Y");
  const markers = [
    { date: dates.start, label: "Début", className: "chart-start-line", row: 10 },
    { date: dates.today, label: "Aujourd’hui", className: "chart-today-line", row: 25 },
    { date: dates.due, label: "Fin prévue", className: "chart-due-line", row: 10 },
  ];
  markers.forEach((marker) => {
    const position = x(marker.date);
    const domain = x.range();
    const ratio = (position - domain[0]) / Math.max(1, domain[1] - domain[0]);
    const anchor = ratio < 0.2 ? "start" : ratio > 0.8 ? "end" : "middle";
    svg.append("line").attr("x1", position).attr("x2", position).attr("y1", top).attr("y2", bottom).attr("class", marker.className);
    svg.append("text").attr("x", position).attr("y", marker.row).attr("text-anchor", anchor).attr("class", `chart-marker-label ${marker.className}-label`).text(`${marker.label} ${format(marker.date)}`);
  });
}

function addPointTitles(circles) {
  const format = d3.utcFormat("%d/%m/%Y");
  circles.append("title").text((point) => `${format(point.date)} — ${point.y} % — ${point.observed ? "saisie historique" : "valeur reportée"}`);
}

function isoDate(value) {
  return value.toISOString().slice(0, 10);
}

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
    due.value = isoDate(cursor);
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
    workload.value = days > 0 ? days.toFixed(2) : "";
  };
  start.addEventListener("change", () => { source.value = "due"; due.value ? calculateWorkload() : calculateDue(); });
  due.addEventListener("change", () => { source.value = "due"; calculateWorkload(); });
  workload.addEventListener("input", () => { source.value = "workload"; calculateDue(); });
});

async function renderTaskHistory(element) {
  if (!window.d3) return;
  let points = Array.from(element.querySelectorAll("[data-x]")).map((point) => ({
    date: parseDate(point.dataset.date), y: Number(point.dataset.y), observed: point.dataset.observed === "true",
  }));
  if (element.dataset.progressUrl) {
    try {
      const response = await fetch(element.dataset.progressUrl, { headers: { Accept: "application/json" } });
      if (response.ok) {
        const rows = await response.json();
        points = rows.map((row) => ({ date: parseDate(row.day), y: Number(row.percentage), observed: Boolean(row.observed) }));
      }
    } catch (_error) { /* The embedded, server-authorized series remains usable. */ }
  }
  points = points.filter((point) => point.date instanceof Date && !Number.isNaN(point.date.valueOf()));
  if (!points.length) return;
  const start = parseDate(element.dataset.start);
  const today = parseDate(element.dataset.today);
  const due = parseDate(element.dataset.due);
  if (!start || !today || !due) return;
  const lastDate = points[points.length - 1].date;
  const end = new Date(Math.max(today.valueOf(), due.valueOf(), lastDate.valueOf()));
  const width = Math.max(300, element.clientWidth || 620);
  const height = 250;
  const margin = { top: 38, right: 18, bottom: 38, left: 42 };
  const x = d3.scaleUtc().domain([start, end]).range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain([0, 100]).range([height - margin.bottom, margin.top]);
  const color = colorFor(element.dataset.action || "sans-action");
  const svg = d3.select(element).insert("svg", ":first-child").attr("viewBox", `0 0 ${width} ${height}`).attr("aria-hidden", "true");
  [25, 50, 75].forEach((value) => svg.append("line").attr("x1", margin.left).attr("x2", width - margin.right).attr("y1", y(value)).attr("y2", y(value)).attr("class", "chart-guide"));
  if (element.dataset.open === "true" && today > due) svg.append("rect").attr("x", x(due)).attr("y", margin.top).attr("width", x(today) - x(due)).attr("height", height - margin.top - margin.bottom).attr("class", "chart-overrun-zone");
  renderDateMarkers(svg, x, { start, today, due }, margin.top, height - margin.bottom);
  const line = d3.line().x((point) => x(point.date)).y((point) => y(point.y)).curve(d3.curveMonotoneX);
  svg.append("path").datum(points).attr("d", line).attr("fill", "none").attr("stroke", color).attr("class", "history-progress-line");
  const circles = svg.selectAll(".history-point").data(points).enter().append("circle").attr("cx", (point) => x(point.date)).attr("cy", (point) => y(point.y)).attr("r", (point) => point.observed ? 3.4 : 2.4).attr("fill", (point) => point.observed ? color : "white").attr("stroke", color).attr("class", (point) => point.observed ? "history-point observed" : "history-point carried");
  addPointTitles(circles);
  svg.append("g").attr("transform", `translate(0,${height - margin.bottom})`).attr("class", "profile-axis").call(d3.axisBottom(x).ticks(Math.min(7, points.length)).tickFormat(d3.utcFormat("%d/%m")));
  svg.append("g").attr("transform", `translate(${margin.left},0)`).attr("class", "profile-axis").call(d3.axisLeft(y).tickValues([0, 25, 50, 75, 100]).tickFormat((value) => `${value}%`));
}

document.querySelectorAll(".task-history-chart").forEach(renderTaskHistory);

document.querySelectorAll(".task-profile-toggle").forEach((button) => {
  const profile = button.closest(".task-profile");
  const details = profile ? profile.querySelector(".task-profile-details") : null;
  const setExpanded = (expanded) => {
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (details) details.hidden = !expanded;
  };
  button.addEventListener("click", () => setExpanded(button.getAttribute("aria-expanded") !== "true"));
  profile.addEventListener("focusout", () => setTimeout(() => { if (!profile.contains(document.activeElement)) setExpanded(false); }, 0));
});

document.querySelectorAll(".legend-toggle").forEach((button) => {
  const legend = document.getElementById(button.getAttribute("aria-controls"));
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (legend) legend.hidden = !expanded;
  });
});
