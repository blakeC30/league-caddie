/**
 * StandingsTable — displays league standings rows.
 */

import type { StandingsRow } from "../api/endpoints";
import { useAuthStore } from "../store/authStore";

function formatPoints(pts: number): string {
  return `$${Math.round(pts).toLocaleString()}`;
}

/** Golf-style rank label: "1", "T2", "T2", "4" */
function formatRank(rank: number, isTied: boolean): string {
  return isTied ? `T${rank}` : `${rank}`;
}

function rankClass(rank: number): string {
  if (rank === 1) return "text-amber-500 font-bold";
  if (rank === 2) return "text-slate-400 font-semibold";
  if (rank === 3) return "text-orange-400 font-semibold";
  return "text-gray-500";
}

interface Props {
  rows: StandingsRow[];
  limit?: number; // show only top N rows (undefined = all)
}

export function StandingsTable({ rows, limit }: Props) {
  const currentUserId = useAuthStore((s) => s.user?.id);
  const displayed = limit ? rows.slice(0, limit) : rows;

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200">
      <table className="min-w-full text-sm">
        <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
          <tr>
            <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold w-12">Pos</th>
            <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Player</th>
            <th className="px-4 py-2.5 text-right text-xs uppercase tracking-wider font-semibold">Points</th>
          </tr>
        </thead>
        <tbody>
          {displayed.map((row, i) => {
            const isMe = row.user_id === currentUserId;
            return (
              <tr
                key={row.user_id}
                className={`border-t border-gray-100 ${
                  isMe
                    ? "bg-green-50 border-l-2 border-l-green-400"
                    : i % 2 === 0
                    ? "bg-white"
                    : "bg-gray-50"
                }`}
              >
                <td className={`px-4 py-3 tabular-nums ${rankClass(row.rank)}`}>
                  {formatRank(row.rank, row.is_tied)}
                </td>
                <td className={`px-4 py-3 ${isMe ? "font-semibold" : ""}`}>
                  {row.display_name}
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-medium">
                  {formatPoints(row.total_points)}
                </td>
              </tr>
            );
          })}
          {displayed.length === 0 && (
            <tr>
              <td colSpan={3} className="px-4 py-8 text-center text-gray-400 text-sm">
                No standings yet — picks will appear after tournaments complete.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
