/**
 * Dashboard — per-league home page.
 *
 * Shows: current/upcoming tournament, the user's pick for it, and a
 * standings preview (top 5). If the current user is outside the top 5 they
 * are always shown beneath a visual separator so they can see their own rank.
 */

import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useLeague, useLeagueTournaments, useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import { fmtTournamentName, formatDate, formatPurse, formatPoints, formatRank, rankClass } from "../utils";
import { useMyPicks, useStandings, useTournaments } from "../hooks/usePick";
import { useAuthStore } from "../store/authStore";
import { GolferAvatar } from "../components/GolferAvatar";
import { useBracket, usePlayoffConfig, useMyPlayoffPod, useMyPlayoffPicks } from "../hooks/usePlayoff";
import { Spinner } from "../components/Spinner";
import type { StandingsRow } from "../api/endpoints";

function StandingsTr({
  row,
  isMe,
  stripe,
  borderTop,
}: {
  row: StandingsRow;
  isMe: boolean;
  stripe: boolean;
  borderTop?: string;
}) {
  return (
    <tr
      className={`${borderTop ?? "border-t border-gray-100"} ${
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
        {formatPoints(row.total_points)}
      </td>
    </tr>
  );
}

export function Dashboard() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { data: league } = useLeague(leagueId!);

  useEffect(() => {
    document.title = league ? `${league.name} — League Caddie` : "League Caddie";
  }, [league]);

  const { data: tournaments, isLoading: tournamentsLoading } = useLeagueTournaments(leagueId!);
  const { data: globalScheduled } = useTournaments("scheduled");
  const { data: globalInProgress } = useTournaments("in_progress");
  const { data: allGlobalTournaments } = useTournaments();
  const { data: myPicks } = useMyPicks(leagueId!);
  const { data: standings } = useStandings(leagueId!);
  const { data: playoffConfig } = usePlayoffConfig(leagueId!);
  const { data: bracket } = useBracket(leagueId!);
  const { data: myPod } = useMyPlayoffPod(leagueId!);
  const { data: myPlayoffPicks } = useMyPlayoffPicks(leagueId!);
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { data: members } = useLeagueMembers(leagueId!);
  const isManager = members?.some((m) => m.user_id === currentUserId && m.role === "manager") ?? false;
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");
  const hasPlayoff = playoffConfig && playoffConfig.playoff_size > 0;
  // Only show the playoff button after the bracket is seeded (regular season complete + earnings published).
  const playoffSeeded = hasPlayoff && bracket && bracket.rounds.length > 0;

  // Show spinner while core data is loading (prevents empty state flash on lazy load)
  if (tournamentsLoading || !league) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner className="w-8 h-8 text-green-600" />
      </div>
    );
  }

  // Purchase gate — show before main content if no League Plan
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

  // The "active" tournament is any in_progress one, or the nearest upcoming scheduled
  // one (smallest start_date in the future). The backend returns DESC order, so we
  // sort ASC here to find the soonest scheduled tournament, not the furthest.
  const nearestScheduled = tournaments
    ?.filter((t) => t.status === "scheduled")
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];

  const active =
    tournaments?.find((t) => t.status === "in_progress") ?? nearestScheduled;

  const myPickForActive = myPicks?.find((p) => p.tournament_id === active?.id);

  // Pick window is open when the active tournament is in_progress (always current),
  // or when it's the globally-next scheduled PGA tournament. If the league's next
  // tournament is further out (a PGA event was skipped), picks stay closed until
  // that skipped event completes and earnings publish.
  const globallyNextId = globalScheduled
    ?.slice()
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0]?.id ?? null;
  const hasGloballyInProgress = globalInProgress !== undefined && globalInProgress.length > 0;
  const pickWindowOpen =
    active?.status === "in_progress" ||
    (!hasGloballyInProgress && globalScheduled !== undefined && active?.id === globallyNextId);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
          League Dashboard
        </p>
        <h1 className="text-3xl font-bold text-gray-900">{league?.name ?? "…"}</h1>
      </div>

      {/* Current tournament card */}
      {active ? (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
          {/* Gradient header band — clickable to tournament detail when live */}
          {active.status === "in_progress" ? (
            <Link
              to={`/leagues/${leagueId}/tournaments/${active.id}`}
              className="block bg-gradient-to-r from-green-900 to-green-700 px-5 py-4 text-white hover:from-green-800 hover:to-green-600 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300">
                      Live Now
                    </p>
                  </div>
                  <h2 className="text-xl font-bold text-white leading-tight">
                    {fmtTournamentName(active.name)}
                  </h2>
                  <div className="flex items-center gap-3 flex-wrap text-sm text-white/70">
                    <span>{formatDate(active.start_date)}–{formatDate(active.end_date)}</span>
                    {formatPurse(active.purse_usd) && (
                      <>
                        <span className="text-white/30">·</span>
                        <span>{formatPurse(active.purse_usd)} purse</span>
                      </>
                    )}
                    {active.effective_multiplier >= 2 && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-500 text-white flex-shrink-0">
                        {active.effective_multiplier}×
                      </span>
                    )}
                    {active.effective_multiplier > 1 && active.effective_multiplier < 2 && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-500 text-white flex-shrink-0">
                        {active.effective_multiplier}×
                      </span>
                    )}
                    {myPod?.is_playoff_week && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500 text-white flex-shrink-0">
                        PLAYOFF
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </Link>
          ) : (
            <div className="bg-gradient-to-r from-green-900 to-green-700 px-5 py-4 text-white">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300">
                    Up Next
                  </p>
                  <h2 className="text-xl font-bold text-white leading-tight">
                    {fmtTournamentName(active.name)}
                  </h2>
                  <div className="flex items-center gap-3 flex-wrap text-sm text-white/70">
                    <span>{formatDate(active.start_date)}–{formatDate(active.end_date)}</span>
                    {formatPurse(active.purse_usd) && (
                      <>
                        <span className="text-white/30">·</span>
                        <span>{formatPurse(active.purse_usd)} purse</span>
                      </>
                    )}
                    {active.effective_multiplier >= 2 && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-500 text-white flex-shrink-0">
                        {active.effective_multiplier}×
                      </span>
                    )}
                    {active.effective_multiplier > 1 && active.effective_multiplier < 2 && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-500 text-white flex-shrink-0">
                        {active.effective_multiplier}×
                      </span>
                    )}
                    {myPod?.is_playoff_week && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500 text-white flex-shrink-0">
                        PLAYOFF
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Card body — pick status */}
          <div className="px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
            {(() => {
              // Playoff week cases
              if (myPod?.is_playoff_week) {
                if (myPod.is_in_playoffs) {
                  const tournamentStarted = active?.status === "in_progress" || active?.status === "completed";
                  if (!tournamentStarted && (myPod.round_status === "drafting" || myPod.round_status === "pending")) {
                    return (
                      <>
                        <div className="flex items-center gap-3">
                          {myPod.has_submitted ? (
                            <>
                              <div className="w-9 h-9 rounded-full bg-green-100 text-green-700 flex items-center justify-center flex-shrink-0">
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                                </svg>
                              </div>
                              <div>
                                <p className="text-xs text-gray-400 font-medium">Playoff picks</p>
                                <p className="text-base font-bold text-gray-900">Rankings submitted</p>
                              </div>
                            </>
                          ) : (
                            <>
                              <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center flex-shrink-0">
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                                </svg>
                              </div>
                              <p className="text-base font-bold text-amber-600">No picks yet</p>
                            </>
                          )}
                        </div>
                        <Link
                          to={`/leagues/${leagueId}/pick`}
                          className="text-sm font-semibold text-white bg-green-800 hover:bg-green-700 px-3 py-1.5 rounded-lg transition-colors"
                        >
                          {myPod.has_submitted ? "Update →" : "Submit Picks →"}
                        </Link>
                      </>
                    );
                  }
                  if (myPod.round_status === "locked") {
                    const resolvedPicks = myPod.tournament_id
                      ? (myPlayoffPicks ?? []).find((p) => p.tournament_id === myPod.tournament_id)?.picks ?? []
                      : [];
                    return (
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center flex-shrink-0">
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                          </svg>
                        </div>
                        <div>
                          <p className="text-xs text-gray-400 font-medium">Playoff picks · <span className="text-gray-400">Locked</span></p>
                          {resolvedPicks.length > 0 ? (
                            <p className="text-base font-bold text-gray-900">
                              {resolvedPicks.map((p) => p.golfer_name).join(", ")}
                            </p>
                          ) : (
                            <p className="text-base font-bold text-gray-700">Picks submitted</p>
                          )}
                        </div>
                      </div>
                    );
                  }
                }
                // In playoff week but not in playoffs
                return (
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-purple-50 text-purple-400 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
                      </svg>
                    </div>
                    <p className="text-base font-semibold text-gray-400">Playoff Week</p>
                  </div>
                );
              }

              // Regular week
              if (myPickForActive) {
                return (
                  <>
                    <div className="flex items-center gap-3">
                      <div className="relative shrink-0">
                        <GolferAvatar
                          pgaTourId={myPickForActive.golfer.pga_tour_id}
                          name={myPickForActive.golfer.name}
                          className="w-11 h-11"
                        />
                        <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 bg-green-500 rounded-full flex items-center justify-center border-2 border-white">
                          <svg className="w-2 h-2 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                          </svg>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 font-medium">Your pick</p>
                        <p className="text-base font-bold text-gray-900">{myPickForActive.golfer.name}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {myPickForActive.points_earned !== null ? (
                        <span className="text-lg font-bold text-green-700">
                          ${Math.round(myPickForActive.points_earned).toLocaleString()}
                        </span>
                      ) : !myPickForActive.is_locked && pickWindowOpen ? (
                        <Link
                          to={`/leagues/${leagueId}/pick`}
                          className="text-sm font-semibold text-green-700 hover:text-green-900 border border-green-200 hover:border-green-400 px-3 py-2.5 sm:py-1.5 rounded-lg transition-colors"
                        >
                          Change →
                        </Link>
                      ) : null}
                    </div>
                  </>
                );
              }
              if (active.all_r1_teed_off) {
                return (
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-500 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-base font-semibold text-amber-600">Pick window closed</p>
                      <p className="text-xs text-amber-500">This tournament will count as a no-pick</p>
                    </div>
                  </div>
                );
              }
              if (!pickWindowOpen) {
                // Find the PGA tournament immediately before the league's first scheduled tournament.
                const firstLeagueScheduled = active;
                const precedingTournament = firstLeagueScheduled && allGlobalTournaments
                  ? allGlobalTournaments
                      .filter((t) => t.start_date < firstLeagueScheduled.start_date && t.status !== "completed")
                      .sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
                    ?? globalInProgress?.[0]
                  : globalInProgress?.[0];
                return (
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-gray-100 text-gray-400 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-base font-semibold text-gray-400">Picks not open yet</p>
                      {precedingTournament && (
                        <p className="text-xs text-gray-400">
                          Picks open after {fmtTournamentName(precedingTournament.name)} completes
                        </p>
                      )}
                    </div>
                  </div>
                );
              }
              return (
                <>
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                      </svg>
                    </div>
                    <p className="text-base font-bold text-amber-600">No pick yet</p>
                  </div>
                  <Link
                    to={`/leagues/${leagueId}/pick`}
                    className="text-sm font-semibold text-white bg-green-800 hover:bg-green-700 px-3 py-2.5 sm:py-1.5 rounded-lg transition-colors"
                  >
                    Pick →
                  </Link>
                </>
              );
            })()}
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-gray-200 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
            </svg>
          </div>
          <p className="font-semibold text-gray-700">No tournaments scheduled</p>
          <p className="text-sm text-gray-400 max-w-xs mx-auto">
            {isManager
              ? "Head to Manage League to configure the tournament schedule."
              : "Ask your league manager to set up the tournament schedule."}
          </p>
        </div>
      )}

      {/* Standings preview — top 5, with current user appended if outside top 5 */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="text-lg font-bold text-gray-900">Standings</h2>
          {playoffSeeded && (
            <Link
              to={`/leagues/${leagueId}/leaderboard?view=bracket`}
              className="text-sm font-semibold text-green-700 hover:text-green-900 bg-green-50 hover:bg-green-100 px-4 py-1.5 rounded-lg transition-colors"
            >
              Playoff →
            </Link>
          )}
        </div>
        {standings ? (() => {
          const top5 = standings.rows.slice(0, 5);
          const meInTop5 = top5.some((r) => r.user_id === currentUserId);
          const myRow = meInTop5
            ? null
            : standings.rows.find((r) => r.user_id === currentUserId) ?? null;

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
                  {top5.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-4 py-8 text-center text-gray-400 text-sm">
                        No standings yet — picks will appear after tournaments complete.
                      </td>
                    </tr>
                  ) : (
                    <>
                      {top5.map((row, i) => (
                        <StandingsTr
                          key={row.user_id}
                          row={row}
                          isMe={row.user_id === currentUserId}
                          stripe={i % 2 !== 0}
                        />
                      ))}
                      {myRow && (
                        <StandingsTr
                          key={myRow.user_id}
                          row={myRow}
                          isMe={true}
                          stripe={false}
                          borderTop="border-t-2 border-gray-300"
                        />
                      )}
                    </>
                  )}
                </tbody>
              </table>
              {standings.rows.length > 5 && (
                <Link
                  to={`/leagues/${leagueId}/leaderboard?view=standings`}
                  className="block text-center text-xs text-gray-400 hover:text-green-700 py-2 transition-colors"
                >
                  View all {standings.rows.length} members →
                </Link>
              )}
            </div>
          );
        })() : (
          <div className="flex justify-center py-4"><Spinner /></div>
        )}
      </div>
    </div>
  );
}
