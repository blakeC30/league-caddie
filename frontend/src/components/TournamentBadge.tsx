/**
 * TournamentBadge — shows tournament status and major/multiplier indicator.
 */

import type { Tournament } from "../api/endpoints";
import { formatDate as fmt, formatPurse } from "../utils";

const STATUS_STYLE: Record<Tournament["status"], string> = {
  scheduled: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-800",
  completed: "bg-gray-100 text-gray-600",
};

const STATUS_LABEL: Record<Tournament["status"], string> = {
  scheduled: "Upcoming",
  in_progress: "Live",
  completed: "Final",
};

interface Props {
  // Accept both plain Tournament and LeagueTournamentOut (which adds effective_multiplier).
  tournament: Tournament & { effective_multiplier?: number };
  showDates?: boolean;
  isPlayoff?: boolean;
}

export function TournamentBadge({ tournament, showDates = false, isPlayoff = false }: Props) {
  const mult = tournament.effective_multiplier;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_STYLE[tournament.status]}`}
      >
        {STATUS_LABEL[tournament.status]}
      </span>

      {showDates && (
        <span className="text-xs text-gray-500">
          {fmt(tournament.start_date)} – {fmt(tournament.end_date)}
        </span>
      )}

      {formatPurse(tournament.purse_usd) && (
        <span className="text-xs text-gray-400">
          {formatPurse(tournament.purse_usd)} purse
        </span>
      )}

      {mult !== undefined && mult >= 2 && (
        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-500 text-white flex-shrink-0">
          {mult}×
        </span>
      )}
      {mult !== undefined && mult > 1 && mult < 2 && (
        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-500 text-white flex-shrink-0">
          {mult}×
        </span>
      )}

      {isPlayoff && (
        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500 text-white flex-shrink-0">
          PLAYOFF
        </span>
      )}
    </div>
  );
}
