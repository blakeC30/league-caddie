/**
 * StandingsTable — displays league standings rows.
 *
 * Pairings Sheet table (DESIGN.md §6): no outer box, micro column headers over
 * a rule, rows separated by hairlines, figures right-aligned and tabular. The
 * current user's row is the one place in the app permitted a coloured left
 * strip, because "this row is you" is genuine semantic state rather than
 * decoration.
 */

import { useNavigate, useParams } from "react-router-dom";
import type { StandingsRow } from "../api/endpoints";
import { useAuthStore } from "../store/authStore";
import { formatPoints, formatRank, rankClass } from "../utils";

interface Props {
  rows: StandingsRow[];
  limit?: number; // show only top N rows (undefined = all)
}

export function StandingsTable({ rows, limit }: Props) {
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();
  const displayed = limit ? rows.slice(0, limit) : rows;

  return (
    <table className="w-full">
      {/* Standings are the leaderboard, so they get the board header — the same
          treatment the Dashboard and Standings pages use. */}
      <thead className="bg-fairway-900 text-white">
        <tr className="text-micro uppercase">
          <th className="text-left font-semibold py-2.5 pl-3 pr-2 w-14">Pos</th>
          <th className="text-left font-semibold py-2.5 px-2">Player</th>
          <th className="text-right font-semibold py-2.5 pl-2 pr-3">Points</th>
        </tr>
      </thead>
      <tbody>
        {displayed.map((row) => {
          const isMe = row.user_id === currentUserId;
          const picksHref = leagueId
            ? isMe
              ? `/leagues/${leagueId}/picks`
              : `/leagues/${leagueId}/picks?member=${row.user_id}`
            : undefined;
          return (
            <tr
              key={row.user_id}
              onClick={() => picksHref && navigate(picksHref)}
              className={`border-b border-ink-200 transition-colors duration-[120ms] ease-board ${
                picksHref ? "cursor-pointer hover:bg-ink-100" : ""
              } ${isMe ? "bg-fairway-50" : ""}`}
            >
              <td
                className={`py-3 pl-3 pr-2 font-mono text-data tabular-nums ${rankClass(row.rank)} ${
                  isMe ? "border-l-2 border-l-fairway-700 pl-2.5" : ""
                }`}
              >
                {formatRank(row.rank, row.is_tied)}
              </td>
              <td className={`py-3 px-2 text-body ${isMe ? "font-semibold text-ink-950" : "text-ink-800"}`}>
                {row.display_name}
              </td>
              <td className="py-3 pl-2 pr-3 text-right font-mono text-data tabular-nums text-ink-950">
                <span className="sm:hidden">{formatPoints(row.total_points)}</span>
                <span className="hidden sm:inline">{formatPoints(row.total_points, false)}</span>
              </td>
            </tr>
          );
        })}
        {displayed.length === 0 && (
          <tr>
            <td colSpan={3} className="py-8 px-3 text-body text-ink-500">
              No standings yet — these fill in as tournaments complete.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
