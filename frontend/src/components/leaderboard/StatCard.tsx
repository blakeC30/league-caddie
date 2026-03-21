/**
 * StatCard — small metric card used in the tournament breakdown section.
 */

export interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

export function StatCard({ label, value, sub, color = "text-gray-900" }: StatCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 space-y-0.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}
