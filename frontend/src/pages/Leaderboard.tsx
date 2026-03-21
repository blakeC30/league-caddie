/**
 * Leaderboard — full season standings + per-tournament pick analysis.
 *
 * Pick breakdown section:
 *   - Tournament dropdown (all league tournaments, soonest first)
 *   - Picks are hidden until the tournament is in_progress or completed
 *   - Table view:  golfer | pickers | points (if completed)
 *   - Chart view:  CSS bar chart — golfer on X, # picks on Y
 *   - Stats cards: submission rate, most popular pick, contrarian pick,
 *                  best/worst result (completed only)
 */

import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useStandings } from "../hooks/usePick";
import { useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import { useBracket } from "../hooks/usePlayoff";
import { useAuthStore } from "../store/authStore";
import type { StandingsRow } from "../api/endpoints";
import { Spinner } from "../components/Spinner";
import { PlayoffBracket } from "./PlayoffBracket";
import { TournamentPicksSection } from "../components/leaderboard/TournamentPicksSection";
import { StandingsTr } from "../components/leaderboard/StandingsTr";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Leaderboard() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [searchParams] = useSearchParams();
  const { data: standings, isLoading } = useStandings(leagueId!);

  useEffect(() => {
    document.title = "Leaderboard — League Caddie";
  }, []);
  const { data: bracket } = useBracket(leagueId!);
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { data: members } = useLeagueMembers(leagueId!);
  const isManager = members?.some((m) => m.user_id === currentUserId && m.role === "manager") ?? false;
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");
  const [expanded, setExpanded] = useState(() => searchParams.get("expand") === "1");
  const hasPlayoffs = !!bracket;
  // Default to bracket view when the playoff is active (regular season ended).
  const playoffActive = bracket?.playoff_config?.status === "active" || bracket?.playoff_config?.status === "completed";
  const [pageView, setPageView] = useState<"standings" | "bracket">(
    () => searchParams.get("view") === "bracket" ? "bracket"
      : searchParams.get("view") === "standings" ? "standings"
      : "standings" // initial default; updated below once bracket loads
  );
  const defaultedRef = useRef(false);
  useEffect(() => {
    if (!defaultedRef.current && playoffActive && !searchParams.get("view")) {
      setPageView("bracket");
      defaultedRef.current = true;
    }
  }, [playoffActive, searchParams]);
  const totalRows = standings?.rows.length ?? 0;
  const showToggle = totalRows > 5;
  const PAGE_SIZE = 50;
  const [page, setPage] = useState(0);
  const [standingsSearch, setStandingsSearch] = useState("");
  const showStandingsSearch = totalRows > PAGE_SIZE;

  // Filter standings by search when expanded
  const filteredRows = (() => {
    if (!standings) return [];
    if (!expanded || !standingsSearch.trim()) return standings.rows;
    const q = standingsSearch.trim().toLowerCase();
    return standings.rows.filter((r) => r.display_name.toLowerCase().includes(q));
  })();

  const totalFiltered = expanded ? filteredRows.length : totalRows;
  const totalPages = Math.ceil(totalFiltered / PAGE_SIZE);

  // Compute which rows to display
  let displayedRows: StandingsRow[] = [];
  let currentUserSeparatorRow: StandingsRow | null = null;

  if (standings) {
    if (expanded) {
      const start = page * PAGE_SIZE;
      displayedRows = filteredRows.slice(start, start + PAGE_SIZE);
    } else {
      const top5 = standings.rows.slice(0, 5);
      const meInTop5 = top5.some((r) => r.user_id === currentUserId);
      displayedRows = top5;
      if (!meInTop5) {
        const myRow = standings.rows.find((r) => r.user_id === currentUserId) ?? null;
        currentUserSeparatorRow = myRow;
      }
    }
  }

  // Purchase gate
  if (!purchaseLoading && purchase !== undefined && !purchase?.paid_at) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="bg-amber-50 rounded-full p-4 mb-6">
          <svg className="w-12 h-12 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v2m0-2h2m-2 0H10m2-10a4 4 0 100 8 4 4 0 000-8z" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-3">League Plan Required</h2>
        <p className="text-gray-600 max-w-sm mb-8">
          {isManager
            ? "This league needs an active League Plan to access features. Purchase one to get started."
            : "Your league manager needs to purchase a League Plan to unlock all features."}
        </p>
        {isManager ? (
          <Link
            to={`/leagues/${leagueId}/manage`}
            className="bg-green-800 hover:bg-green-700 text-white font-semibold px-6 py-3 rounded-xl transition-colors"
          >
            Manage &amp; Purchase
          </Link>
        ) : (
          <p className="text-sm text-gray-500">Contact your league manager to activate this league.</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div className="space-y-1">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
            Leaderboard
          </p>
          <h1 className="text-3xl font-bold text-gray-900">
            {pageView === "bracket" ? "Playoff Bracket" : "Season Standings"}
          </h1>
          {standings && (
            <p className="text-sm text-gray-500">{standings.season_year} Season</p>
          )}
        </div>

        {/* Standings / Bracket pill toggle — only shown when playoffs are configured */}
        {hasPlayoffs && (
          <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1 self-start">
            <button
              onClick={() => setPageView("standings")}
              className={`text-sm font-semibold px-4 py-1.5 rounded-lg transition-colors ${
                pageView === "standings"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Standings
            </button>
            <button
              onClick={() => setPageView("bracket")}
              className={`text-sm font-semibold px-4 py-1.5 rounded-lg transition-colors ${
                pageView === "bracket"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Playoff
            </button>
          </div>
        )}
      </div>

      {/* Bracket view */}
      {pageView === "bracket" && <PlayoffBracket hideHeader />}

      {/* Season standings */}
      {pageView === "standings" && isLoading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : pageView === "standings" && standings ? (
        <div className="space-y-3">
          {expanded && showStandingsSearch && (
            <input
              type="text"
              placeholder="Search members…"
              value={standingsSearch}
              onChange={(e) => { setStandingsSearch(e.target.value); setPage(0); }}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          )}
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold w-12">Pos</th>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Member</th>
                  <th className="px-4 py-2.5 text-right text-xs uppercase tracking-wider font-semibold">Points</th>
                </tr>
              </thead>
              <tbody>
                {displayedRows.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-gray-400 text-sm">
                      {standingsSearch ? "No members match your search." : "No standings yet — picks will appear after tournaments complete."}
                    </td>
                  </tr>
                ) : (
                  <>
                    {displayedRows.map((row, i) => (
                      <StandingsTr
                        key={row.user_id}
                        row={row}
                        isMe={row.user_id === currentUserId}
                        stripe={i % 2 !== 0}
                      />
                    ))}
                    {currentUserSeparatorRow && (
                      <StandingsTr
                        key={currentUserSeparatorRow.user_id}
                        row={currentUserSeparatorRow}
                        isMe={true}
                        stripe={false}
                        borderTop="border-t-2 border-gray-300"
                      />
                    )}
                  </>
                )}
              </tbody>
            </table>
          </div>

          {showToggle && !expanded && (
            <button
              type="button"
              onClick={() => { setExpanded(true); setPage(0); }}
              className="inline-flex items-center gap-1 text-sm font-medium text-green-700 hover:text-green-900"
            >
              Show all {totalRows} members
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
          )}

          {expanded && totalPages > 1 && (
            <div className="flex items-center justify-between gap-4">
              <button
                type="button"
                onClick={() => { setExpanded(false); setPage(0); }}
                className="inline-flex items-center gap-1 text-sm font-medium text-green-700 hover:text-green-900"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
                </svg>
                Show less
              </button>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="text-sm font-medium text-gray-500 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  ← Prev
                </button>
                <span className="text-xs text-gray-400 tabular-nums">
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalFiltered)} of {totalFiltered}{standingsSearch ? " results" : ""}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="text-sm font-medium text-gray-500 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}

          {expanded && totalPages <= 1 && (
            <button
              type="button"
              onClick={() => { setExpanded(false); setPage(0); }}
              className="inline-flex items-center gap-1 text-sm font-medium text-green-700 hover:text-green-900"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
              </svg>
              Show less
            </button>
          )}
        </div>
      ) : pageView === "standings" ? (
        <p className="text-gray-400">No standings available yet.</p>
      ) : null}

      {/* Pick breakdown — hidden in bracket view */}
      {pageView === "standings" && <TournamentPicksSection leagueId={leagueId!} />}
    </div>
  );
}
