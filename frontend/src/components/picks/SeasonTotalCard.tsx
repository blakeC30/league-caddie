export interface SeasonTotalCardProps {
  totalEarned: number;
}

export function SeasonTotalCard({ totalEarned }: SeasonTotalCardProps) {
  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-green-900 via-green-800 to-green-700 rounded-2xl p-6 text-white shadow-lg shadow-green-900/20">
      {/* Decorative blob */}
      <div className="absolute -top-8 -right-8 w-40 h-40 rounded-full bg-white/5 blur-2xl pointer-events-none" />
      <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-2">
        Season Total
      </p>
      <p className="text-4xl font-extrabold tabular-nums">
        {totalEarned < 0 ? "-" : ""}${Math.round(Math.abs(totalEarned)).toLocaleString()}
      </p>
    </div>
  );
}
