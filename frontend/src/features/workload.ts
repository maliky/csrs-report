export type WorkloadUnit = "days" | "hours";

export const HOURS_PER_WORKDAY = 8;

function workloadPrecision(unit: WorkloadUnit): number {
  return unit === "days" ? 0.5 : 1;
}

function workloadMinimum(unit: WorkloadUnit): number {
  return unit === "days" ? 0.5 : 1;
}

function formatWorkloadInput(value: number, unit: WorkloadUnit): string {
  if (unit === "hours") return String(Math.max(workloadMinimum(unit), Math.round(value)));
  return Number(value).toString();
}

function roundToPrecision(value: number, unit: WorkloadUnit): number {
  const precision = workloadPrecision(unit);
  const rounded = Math.round(value / precision) * precision;
  const minimum = workloadMinimum(unit);
  return Math.max(minimum, rounded);
}

export function workloadInputMin(unit: WorkloadUnit): number {
  return workloadMinimum(unit);
}

export function workloadInputStep(unit: WorkloadUnit): number {
  return workloadPrecision(unit);
}

export function workloadInputFromDays(
  estimatedWorkDays: string,
  unit: WorkloadUnit,
): string {
  const days = Number.parseFloat(estimatedWorkDays);
  if (!Number.isFinite(days) || days <= 0) return "";
  const normalizedDays = roundToPrecision(days, unit);
  if (unit === "hours")
    return String(Math.max(1, Math.round(normalizedDays * HOURS_PER_WORKDAY)));
  return formatWorkloadInput(normalizedDays, unit);
}

export function estimatedWorkDaysFromInput(
  input: string,
  unit: WorkloadUnit,
): string | null {
  const parsed = Number.parseFloat(input);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const normalized = roundToPrecision(parsed, unit);
  const days =
    unit === "days" ? normalized : normalized / HOURS_PER_WORKDAY;
  return days.toFixed(1);
}

export function normalizeWorkloadInputValue(
  input: string,
  unit: WorkloadUnit,
): string {
  const parsed = Number.parseFloat(input);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  const normalized = roundToPrecision(parsed, unit);
  return formatWorkloadInput(normalized, unit);
}

export function nextWorkloadInputValue(
  current: string,
  unit: WorkloadUnit,
  direction: -1 | 1,
): string {
  const parsed = Number.parseFloat(current);
  if (!Number.isFinite(parsed) || parsed <= 0) return formatWorkloadInput(workloadMinimum(unit), unit);
  const next = parsed + direction * workloadPrecision(unit);
  const normalized = roundToPrecision(next, unit);
  return formatWorkloadInput(normalized, unit);
}
