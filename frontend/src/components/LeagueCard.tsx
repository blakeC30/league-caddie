/**
 * LeagueCard — rich at-a-glance card for a single league.
 *
 * Pure presentational component — all data comes from the LeagueSummary prop
 * provided by the parent (Leagues page). No hooks or data fetching.
 */

import { Link, useNavigate } from "react-router-dom";
import type { LeagueSummary } from "../api/endpoints";
import { fmtTournamentName, formatDate, formatPurse, formatPoints } from "../utils";

function rankStyle(rank: number): string {
  if (rank === 1) return "text-amber-500";
  if (rank === 2) return "text-slate-400";
  if (rank === 3) return "text-orange-400";
  return "text-gray-800";
}

export function LeagueCard({ summary }: { summary: LeagueSummary }) {
  const navigate = useNavigate();
  const current = summary.current_tournament;

  return (
    <Link
      to={`/leagues/${summary.league_id}`}
      className="group flex flex-col bg-white rounded-2xl border border-gray-200 hover:border-green-400 shadow-sm hover:shadow-xl overflow-hidden transition-all duration-200 hover:-translate-y-0.5"
    >
      {/* Gradient header */}
      <div className="bg-gradient-to-br from-green-900 to-green-700 px-5 pt-5 pb-4">
        <div className="flex items-start justify-between gap-2 mb-1">
          <h2 className="font-bold text-white text-xl leading-tight">
            {summary.league_name}
          </h2>
          {summary.is_manager && (
            <span className="flex-shrink-0 mt-0.5 text-xs font-semibold bg-white/20 text-white px-2.5 py-0.5 rounded-full">
              Manager
            </span>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="px-5 py-4 grid grid-cols-[1fr_2fr_1fr] divide-x divide-gray-100">
        <div className="pr-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1">Rank</p>
          <p className={`text-2xl font-bold tabular-nums leading-none ${summary.rank !== null ? rankStyle(summary.rank) : "text-gray-200"}`}>
            {summary.rank !== null ? (summary.is_tied ? `T${summary.rank}` : `${summary.rank}`) : "—"}
          </p>
        </div>
        <div className="px-4 min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1">Points</p>
          <p className="text-2xl font-bold tabular-nums leading-none text-gray-800 break-all">
            {summary.total_points !== null ? formatPoints(summary.total_points) : "—"}
          </p>
        </div>
        <div className="pl-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1">Members</p>
          <p className="text-2xl font-bold tabular-nums leading-none text-gray-800">
            {summary.member_count || "—"}
          </p>
        </div>
      </div>

      {/* Tournament section */}
      <div className="border-t border-gray-100 bg-gray-50 px-5 py-3">
        {current ? (
          <div className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
                </svg>
                <p className="text-xs font-semibold text-gray-700 truncate">{fmtTournamentName(current.name)}</p>
              </div>
              <div className="flex items-center flex-wrap gap-1.5 mt-0.5">
                <span className="text-[11px] text-gray-400">
                  {formatDate(current.start_date)}–{formatDate(current.end_date)}
                  {current.status === "in_progress" && (
                    <span className="ml-1.5 text-green-600 font-semibold">· Live</span>
                  )}
                  {formatPurse(current.purse_usd) && (
                    <span className="ml-1.5">· {formatPurse(current.purse_usd)} purse</span>
                  )}
                </span>
                {current.effective_multiplier >= 2 && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-500 text-white flex-shrink-0">
                    {current.effective_multiplier}×
                  </span>
                )}
                {current.effective_multiplier > 1 && current.effective_multiplier < 2 && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-500 text-white flex-shrink-0">
                    {current.effective_multiplier}×
                  </span>
                )}
                {summary.is_playoff_week && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500 text-white flex-shrink-0">
                    PLAYOFF
                  </span>
                )}
              </div>
              {summary.is_playoff_week && summary.my_playoff_picks.length > 0 ? (
                <div className="mt-0.5 space-y-0.5">
                  {summary.my_playoff_picks.map((p, i) => (
                    <p key={i} className="text-[11px] text-green-700 font-medium flex items-center gap-1">
                      <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                      </svg>
                      {p.golfer_name}
                    </p>
                  ))}
                </div>
              ) : summary.is_playoff_week && !summary.is_in_playoffs ? (
                <p className="text-[11px] text-gray-400 font-medium mt-0.5">Not in playoffs</p>
              ) : summary.my_pick ? (
                <p className="text-[11px] text-green-700 font-medium mt-0.5 flex items-center gap-1">
                  <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                  {summary.my_pick.golfer_name}
                  {summary.my_pick.is_locked && (
                    <span className="ml-0.5 text-[10px] text-gray-400 font-normal">· locked</span>
                  )}
                </p>
              ) : !summary.pick_window_open && current.status === "scheduled" ? (
                summary.preceding_tournament_name ? (
                  <p className="text-[11px] text-gray-400 font-medium mt-0.5">
                    Picks open after {fmtTournamentName(summary.preceding_tournament_name)} completes
                  </p>
                ) : null
              ) : current.status === "scheduled" || (current.status === "in_progress" && !current.all_r1_teed_off) ? (
                <p className="text-[11px] text-amber-600 font-medium mt-0.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0 inline-block" />
                  No pick yet
                </p>
              ) : (
                <p className="text-[11px] text-red-500 font-medium mt-0.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0 inline-block" />
                  No Pick
                </p>
              )}
            </div>
            {summary.pick_window_open && !summary.my_pick && (current.status === "scheduled" || (current.status === "in_progress" && !current.all_r1_teed_off)) && (
              <button
                onClick={(e) => {
                  e.preventDefault();
                  navigate(`/leagues/${summary.league_id}/pick`);
                }}
                className="flex-shrink-0 text-xs font-bold text-white bg-green-700 hover:bg-green-600 px-2.5 py-2 sm:py-1 rounded-lg transition-colors"
              >
                Pick →
              </button>
            )}
            {summary.pick_window_open && summary.my_pick && !summary.my_pick.is_locked && (
              <button
                onClick={(e) => {
                  e.preventDefault();
                  navigate(`/leagues/${summary.league_id}/pick`);
                }}
                className="flex-shrink-0 text-xs font-bold text-green-800 border border-green-700 hover:bg-green-50 px-2.5 py-2 sm:py-1 rounded-lg transition-colors"
              >
                Change →
              </button>
            )}
          </div>
        ) : (
          <p className="text-xs text-gray-400">No upcoming tournaments</p>
        )}
      </div>
    </Link>
  );
}
