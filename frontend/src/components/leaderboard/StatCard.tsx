/**
 * StatCard — small metric card used in the tournament breakdown section.
 *
 * Separated from its neighbours by the page→sheet background step rather than
 * by a border (DESIGN.md §4).
 */

export interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  /** Optional tone override for the figure, e.g. "text-flag-600" for under par. */
  color?: string;
}

export function StatCard({ label, value, sub, color = "text-ink-950" }: StatCardProps) {
  return (
    <div className="bg-sheet rounded-sm shadow-sheet px-4 py-3">
      <p className="text-micro uppercase text-ink-500">{label}</p>
      <p className={`font-display text-subhead tabular-nums mt-1 ${color}`}>{value}</p>
      {sub && <p className="text-small text-ink-500 mt-0.5">{sub}</p>}
    </div>
  );
}
