import { StatCard } from "./StatCard";
import { formatPoints } from "../../utils";

export interface PicksStatCardsProps {
  finalTournamentCount: number;
  submittedForFinalCount: number;
  scoredPicksCount: number;
  cutsMissedCount: number;
  bestPickPoints: number | null;
  bestPickGolferName?: string;
  avgEarnings: number | null;
}

export function PicksStatCards({
  finalTournamentCount,
  submittedForFinalCount,
  scoredPicksCount,
  cutsMissedCount,
  bestPickPoints,
  bestPickGolferName,
  avgEarnings,
}: PicksStatCardsProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Submission Rate"
          value={finalTournamentCount === 0 ? "—" : `${Math.round((submittedForFinalCount / finalTournamentCount) * 100)}%`}
          sub={finalTournamentCount > 0 ? `${submittedForFinalCount} / ${finalTournamentCount} tournaments` : undefined}
        />
        <StatCard
          label="Cuts Missed"
          value={scoredPicksCount > 0 ? `${Math.round((cutsMissedCount / scoredPicksCount) * 100)}%` : "—"}
          sub={scoredPicksCount > 0 ? `${cutsMissedCount} of ${scoredPicksCount} picks` : undefined}
        />
        <StatCard
          label="Best Pick"
          value={formatPoints(bestPickPoints)}
          sub={bestPickGolferName}
        />
        <StatCard
          label="Avg Points"
          value={formatPoints(avgEarnings !== null ? Math.round(avgEarnings) : null)}
        />
      </div>
  );
}
