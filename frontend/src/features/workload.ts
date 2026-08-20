export type WorkloadUnit = "days" | "hours";

export const HOURS_PER_WORKDAY = 8;

function workloadPrecision(unit: WorkloadUnit): number {
  return unit === "days" ? 0.25 : 0.5;
}

function workloadMinimum(unit: WorkloadUnit): number {
  return unit === "days" ? 0.5 : 1;
}

function formatWorkloadInput(value: number, unit: WorkloadUnit): string {
  const normalized = Math.max(workloadMinimum(unit), value);
  return Number(normalized.toFixed(unit === "days" ? 2 : 1)).toString();
}

function roundToPrecision(value: number, unit: WorkloadUnit): number {
  const precision = workloadPrecision(unit);
  const rounded = Math.round((value + Number.EPSILON) / precision) * precision;
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
  const inputValue = unit === "days" ? days : days * HOURS_PER_WORKDAY;
  return formatWorkloadInput(roundToPrecision(inputValue, unit), unit);
}

export function estimatedWorkDaysFromInput(
  input: string,
  unit: WorkloadUnit,
): string | null {
  const parsed = Number.parseFloat(input);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const normalized = roundToPrecision(parsed, unit);
  const days = unit === "days" ? normalized : normalized / HOURS_PER_WORKDAY;
  const fixed = days.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return fixed.includes(".") ? fixed : `${fixed}.0`;
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
  if (!Number.isFinite(parsed) || parsed <= 0)
    return formatWorkloadInput(workloadMinimum(unit), unit);
  const next = parsed + direction * workloadPrecision(unit);
  const normalized = roundToPrecision(next, unit);
  return formatWorkloadInput(normalized, unit);
}
