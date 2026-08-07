export function formatDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

export function parseDateInput(value: string): string | null {
  const trimmed = value.trim();
  const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  const frenchMatch = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(trimmed);
  const parts = isoMatch
    ? { year: isoMatch[1], month: isoMatch[2], day: isoMatch[3] }
    : frenchMatch
      ? { year: frenchMatch[3], month: frenchMatch[2], day: frenchMatch[1] }
      : null;
  if (!parts) return null;
  const year = Number(parts.year);
  const month = Number(parts.month);
  const day = Number(parts.day);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  )
    return null;
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function dayLabel(value: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
  }).format(new Date(`${value}T12:00:00`));
}

export function dayCount(value: string): string {
  const amount = Number(value);
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(amount)} ${amount > 1 ? "jours" : "jour"}`;
}
