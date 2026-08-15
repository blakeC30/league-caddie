/**
 * StatCard — a labelled figure. Separated from its neighbours by the
 * page→sheet background step rather than by a border (DESIGN.md §4).
 */

export interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
}

export function StatCard({ label, value, sub }: StatCardProps) {
  return (
    <div className="bg-sheet rounded-sm shadow-sheet p-4">
      <p className="text-micro uppercase text-ink-500">{label}</p>
      <p className="font-display text-subhead text-ink-950 tabular-nums mt-1">{value}</p>
      {sub && <p className="text-small text-ink-500 mt-0.5 truncate">{sub}</p>}
    </div>
  );
}
