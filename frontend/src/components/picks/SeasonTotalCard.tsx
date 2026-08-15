/**
 * SeasonTotalCard — the running total, shown as a board panel.
 *
 * Was a three-stop gradient with a blurred blob behind it. Under the Pairings
 * Sheet language this is one flat fill and one big tabular figure, because the
 * number is the only thing on it worth looking at.
 */

export interface SeasonTotalCardProps {
  totalEarned: number;
  hasPlayoffs?: boolean;
}

export function SeasonTotalCard({ totalEarned, hasPlayoffs }: SeasonTotalCardProps) {
  return (
    <div className="bg-fairway-900 rounded-sm px-5 py-5 text-white">
      <p className="text-micro uppercase text-fairway-400">
        {hasPlayoffs ? "Regular season total" : "Season total"}
      </p>
      <p className="font-display text-figure tabular-nums mt-1.5">
        {totalEarned < 0 ? "-" : ""}${Math.round(Math.abs(totalEarned)).toLocaleString()}
      </p>
    </div>
  );
}
