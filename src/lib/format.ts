/** Presentation helpers — formatting only, no domain logic. */

export const percent = (value: number, digits = 0) =>
  `${(value * 100).toFixed(digits)}%`;

export const metres = (value: number) => `${value.toFixed(2)} m`;

export const mmPerHour = (value: number) => `${value.toFixed(0)} mm/hr`;

export const compactNumber = (value: number) =>
  new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

export const fullNumber = (value: number) => new Intl.NumberFormat('en-IN').format(value);

/** "1 hr 45 min" / "40 min" / "—" for a null lead time. */
export function duration(minutes: number | null): string {
  if (minutes === null) return '—';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
}

export function clockAt(minutesFromNow: number, from = new Date()): string {
  const at = new Date(from.getTime() + minutesFromNow * 60_000);
  return at.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
}
