/**
 * How long password-reset links are valid (hours). Must match
 * RESET_TOKEN_EXPIRE_HOURS in the backend config (app/config.py).
 */
export const RESET_TOKEN_EXPIRE_HOURS = 1;

/**
 * Strips sponsorship suffixes from PGA Tour event names.
 * ESPN names include " pres. by Sponsor" or " presented by Sponsor".
 * Examples:
 *   "Arnold Palmer Invitational pres. by Mastercard" → "Arnold Palmer Invitational"
 *   "Cognizant Classic in The Palm Beaches"          → unchanged
 */
export function fmtTournamentName(name: string): string {
  return name.replace(/\s+(?:pres\.|presented)\s+by\s+.+$/i, "").trim();
}

/**
 * Returns an ISO year-week key (e.g. "2025-W12") for a YYYY-MM-DD date string.
 * Used to detect schedule conflicts where two tournaments fall in the same week.
 */
export function isoWeekKey(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(y, m - 1, d, 12); // noon to avoid DST edge cases
  const day = date.getDay() || 7; // convert Sun=0 to 7 (Mon=1..Sun=7)
  date.setDate(date.getDate() + 4 - day); // advance to Thursday of this ISO week
  const yearStart = new Date(date.getFullYear(), 0, 1, 12);
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${date.getFullYear()}-W${String(week).padStart(2, "0")}`;
}
