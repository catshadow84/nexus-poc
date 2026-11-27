const pad = (n: number) => String(n).padStart(2, '0');

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export function toIso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function fromIso(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function addDays(iso: string, n: number): string {
  const d = fromIso(iso);
  d.setDate(d.getDate() + n);
  return toIso(d);
}

/** Whole nights from a to b (both YYYY-MM-DD). */
export function nightsBetween(a: string, b: string): number {
  return Math.round((fromIso(b).getTime() - fromIso(a).getTime()) / 86400000);
}

/** "Sat 26 Dec" */
export function prettyDate(iso: string): string {
  const d = fromIso(iso);
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)}`;
}

export function money(amount: number, currency: string): string {
  return `${amount.toFixed(2)} ${currency}`;
}

/** The server sends UTC times without a "Z"; read them as UTC. */
export function fromUtcIso(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
}

/** "Mon 28 Dec, 14:00" in the phone's own time zone. */
export function prettyMoment(iso: string): string {
  const d = fromUtcIso(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)}, ${hh}:${mm}`;
}

/** "482917" -> "482 917" */
export function groupPin(pin: string): string {
  return pin.replace(/(\d{3})(?=\d)/g, '$1 ');
}
