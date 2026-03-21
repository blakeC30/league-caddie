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
 * Formats a YYYY-MM-DD date string as "Mar 16" (short month + day).
 * Appends T12:00:00 to avoid UTC→local date shift on midnight boundaries.
 */
export function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/**
 * Formats an ISO datetime string as "March 16, 2025" (long month + day + year).
 */
export function formatDateLong(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Formats a point/dollar amount with sign, abbreviation (M/K), and $ prefix.
 * Returns "—" for null values.
 */
export function formatPoints(pts: number | null): string {
  if (pts === null) return "—";
  const sign = pts < 0 ? "-" : "";
  const abs = Math.abs(pts);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

/**
 * Formats a purse/dollar amount with M/K abbreviation.
 * Returns null when the input is null.
 */
export function formatPurse(purse: number | null): string | null {
  if (purse === null) return null;
  if (purse >= 1_000_000) {
    const m = purse / 1_000_000;
    return `$${m % 1 === 0 ? m : m.toFixed(1)}M`;
  }
  return `$${Math.round(purse / 1000)}K`;
}

/** Golf-style rank label: "1", "T2", "T2", "4" */
export function formatRank(rank: number, isTied: boolean): string {
  return isTied ? `T${rank}` : `${rank}`;
}

/** Returns a Tailwind text-color class based on podium position. */
export function rankClass(rank: number): string {
  if (rank === 1) return "text-amber-500 font-bold";
  if (rank === 2) return "text-slate-400 font-semibold";
  if (rank === 3) return "text-orange-400 font-semibold";
  return "text-gray-500";
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
