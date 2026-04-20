/**
 * StandingsTr — a single row in the season standings table.
 */

import { useNavigate } from "react-router-dom";
import { formatPoints, formatRank, rankClass } from "../../utils";
import type { StandingsRow } from "../../api/endpoints";

export interface StandingsTrProps {
  row: StandingsRow;
  isMe: boolean;
  stripe: boolean;
  borderTop?: string;
  leagueId?: string;
}

export function StandingsTr({
  row,
  isMe,
  stripe,
  borderTop,
  leagueId,
}: StandingsTrProps) {
  const navigate = useNavigate();
  const picksHref = leagueId
    ? isMe
      ? `/leagues/${leagueId}/picks`
      : `/leagues/${leagueId}/picks?member=${row.user_id}`
    : undefined;

  return (
    <tr
      onClick={() => picksHref && navigate(picksHref)}
      className={`${borderTop ?? "border-t border-gray-100"} ${picksHref ? "cursor-pointer hover:bg-green-50" : ""} ${
        isMe
          ? "bg-green-50 border-l-2 border-l-green-400"
          : stripe
          ? "bg-gray-50"
          : "bg-white"
      }`}
    >
      <td className={`px-4 py-3 tabular-nums ${rankClass(row.rank)}`}>
        {formatRank(row.rank, row.is_tied)}
      </td>
      <td className={`px-4 py-3 ${isMe ? "font-semibold" : ""}`}>
        {row.display_name}
      </td>
      <td className="px-4 py-3 text-right tabular-nums font-medium">
        <span className="sm:hidden">{formatPoints(row.total_points)}</span>
        <span className="hidden sm:inline">{formatPoints(row.total_points, false)}</span>
      </td>
    </tr>
  );
}
