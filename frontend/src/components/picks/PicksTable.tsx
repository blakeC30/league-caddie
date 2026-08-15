import { useState } from "react";
import { Link } from "react-router-dom";
import { SortButton } from "./SortButton";
import type { SortDir } from "./SortButton";
import { TournamentBadgePills, TournamentBadgeDates } from "../TournamentBadge";
import { GolferAvatar } from "../GolferAvatar";
import { FlagIcon } from "../FlagIcon";
import { SkeletonBlock } from "../Skeleton";
import { fmtTournamentName, formatPoints } from "../../utils";
import type { LeagueTournamentOut, Pick, League, MyPlayoffPodOut, PlayoffTournamentPickOut } from "../../api/endpoints";

type StatusFilter = "default" | "upcoming" | "all";
type SortField = "date" | "tournament" | "golfer" | "points";

export type OtherPlayoffEntry = {
  status: string;
  picks: { id: string; pod_member_id: number; golfer_id: string; golfer_name: string; golfer_pga_tour_id: string; partner_name: string | null; partner_pga_tour_id: string | null; draft_slot: number; points_earned: number | null; created_at: string }[];
  total_points: number | null;
  is_picks_visible: boolean;
};

export interface PicksTableProps {
  leagueId: string;
  league: League | undefined;
  leagueTournaments: LeagueTournamentOut[];
  isLoading: boolean;
  isViewingSelf: boolean;
  nextTournament: LeagueTournamentOut | undefined;
  liveTournament: LeagueTournamentOut | undefined;
  hasTeeTimesForNext: boolean;
  picksByTournamentId: Map<string, Pick>;
  playoffTournamentIds: Set<string>;
  playoffPicksByTournamentId: Map<string, PlayoffTournamentPickOut>;
  otherMemberPlayoffMap: Map<string, OtherPlayoffEntry>;
  completedTournaments: LeagueTournamentOut[];
  myPod: MyPlayoffPodOut | undefined;
}

export function PicksTable({
  leagueId,
  league,
  leagueTournaments,
  isLoading,
  isViewingSelf,
  nextTournament,
  liveTournament,
  hasTeeTimesForNext,
  picksByTournamentId,
  playoffTournamentIds,
  playoffPicksByTournamentId,
  otherMemberPlayoffMap,
  completedTournaments,
  myPod,
}: PicksTableProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("default");
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "points" ? "desc" : field === "date" ? "desc" : "asc");
    }
  }

  const historyRows = [
    ...leagueTournaments
      .filter((t) => {
        if (statusFilter === "upcoming") return t.status === "scheduled";
        if (statusFilter === "all") return true;
        return t.status !== "scheduled" || t.id === nextTournament?.id;
      })
      .map((t) => ({
        key: `t-${t.id}`,
        tournament: t,
        pick: picksByTournamentId.get(t.id) ?? null,
      })),
  ].sort((a, b) => {
    let cmp = 0;
    if (sortField === "date") {
      cmp = a.tournament.start_date.localeCompare(b.tournament.start_date);
    } else if (sortField === "tournament") {
      cmp = a.tournament.name.localeCompare(b.tournament.name);
    } else if (sortField === "golfer") {
      const aName = a.pick?.golfer.name ?? "\uFFFF";
      const bName = b.pick?.golfer.name ?? "\uFFFF";
      cmp = aName.localeCompare(bName);
    } else if (sortField === "points") {
      const penalty = league?.no_pick_penalty ?? 0;
      const noPick = (row: typeof a) =>
        !row.pick && row.tournament.status === "completed" && !row.tournament.scoring_pending ? penalty : (row.pick?.points_earned ?? 0);
      cmp = noPick(a) - noPick(b);
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  if (isLoading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="flex gap-1">
          <SkeletonBlock className="h-7 w-16 rounded-xs" />
          <SkeletonBlock className="h-7 w-20 rounded-xs" />
          <SkeletonBlock className="h-7 w-10 rounded-xs" />
        </div>
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex items-center gap-3 px-3 py-3 border-b border-ink-100">
            <SkeletonBlock className="h-4 w-32" />
            <SkeletonBlock className="h-4 w-24" />
            <SkeletonBlock className="h-4 w-16 ml-auto" />
          </div>
        ))}
      </div>
    );
  }

  const seasonOver = leagueTournaments.length > 0 && leagueTournaments.every((t) => t.status === "completed");

  if (historyRows.length === 0) {
    // "Upcoming" tab with no scheduled tournaments left
    if (statusFilter === "upcoming" && seasonOver) {
      return (
        <div className="space-y-2">
          {/* Status filter — keep tabs visible so user can switch back */}
          <div className="flex items-center gap-1 pb-1">
            {(
              [
                ["default", "Recent"],
                ["upcoming", "Upcoming"],
                ["all", "All"],
              ] as [StatusFilter, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setStatusFilter(value)}
                className={`px-3 py-1 rounded-xs text-xs font-semibold transition-colors ${
                  statusFilter === value
                    ? "bg-fairway-700 text-white"
                    : "text-ink-500 hover:bg-ink-100"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="bg-ink-50 rounded-sm border border-ink-200 p-10 text-center space-y-2">
            <p className="font-semibold text-ink-700">Season complete</p>
            <p className="text-sm text-ink-400">All tournaments in this league have been played.</p>
          </div>
        </div>
      );
    }

    // Truly empty — no picks and season not over
    if (seasonOver) {
      return (
        <div className="bg-ink-50 rounded-sm border border-ink-200 p-10 text-center space-y-2">
          <p className="font-semibold text-ink-700">Season complete</p>
          <p className="text-sm text-ink-400">All tournaments in this league have been played.</p>
        </div>
      );
    }

    return (
      <div className="bg-ink-50 rounded-sm border border-ink-200 p-16 text-center space-y-3">
        <div className="w-12 h-12 rounded-sm bg-fairway-100 text-fairway-700 flex items-center justify-center mx-auto">
          <FlagIcon className="w-6 h-6" />
        </div>
        <p className="font-semibold text-ink-700">No picks yet this season</p>
        <p className="text-sm text-ink-400">Make your first pick for an upcoming tournament.</p>
        <Link
          to={`/leagues/${leagueId}/pick`}
          className="inline-block text-sm font-semibold text-fairway-700 hover:text-fairway-900 mt-2 transition-colors"
        >
          Make your first pick &rarr;
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Status filter */}
      <div className="flex items-center gap-1 pb-1">
        {(
          [
            ["default", "Recent"],
            ["upcoming", "Upcoming"],
            ["all", "All"],
          ] as [StatusFilter, string][]
        ).map(([val, label]) => (
          <button
            key={val}
            onClick={() => setStatusFilter(val)}
            className={`text-xs font-semibold px-3 py-1 rounded-full transition-colors ${
              statusFilter === val
                ? "bg-fairway-700 text-white"
                : "text-ink-400 hover:text-ink-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Sort controls — hide Tournament/Golfer on mobile to save space */}
      <div className="flex items-center justify-between px-1 pb-1 border-b border-ink-200">
        <div className="flex items-center gap-4">
          <SortButton label="Date" active={sortField === "date"} dir={sortDir} onClick={() => handleSort("date")} />
          <span className="hidden sm:inline">
            <SortButton label="Tournament" active={sortField === "tournament"} dir={sortDir} onClick={() => handleSort("tournament")} />
          </span>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <span className="hidden sm:inline">
            <SortButton label="Golfer" active={sortField === "golfer"} dir={sortDir} onClick={() => handleSort("golfer")} />
          </span>
          <SortButton label="Points" active={sortField === "points"} dir={sortDir} onClick={() => handleSort("points")} />
        </div>
      </div>

      {historyRows.map(({ key, tournament, pick }) => {
        const isPlayoffTournament = playoffTournamentIds.has(tournament.id);
        const ownPlayoffData = isViewingSelf ? playoffPicksByTournamentId.get(tournament.id) : undefined;
        const otherPlayoffData = !isViewingSelf ? otherMemberPlayoffMap.get(tournament.id) : undefined;
        const playoffData = ownPlayoffData ?? otherPlayoffData;

        const playoffPickNames = isPlayoffTournament ? (playoffData?.picks.map((p) => p.partner_name ? `${p.golfer_name} / ${p.partner_name}` : p.golfer_name) ?? []) : [];
        const isClickable = isPlayoffTournament
          ? tournament.status === "in_progress" || tournament.status === "completed" || !!(playoffData || (myPod?.tournament_id === tournament.id && myPod?.is_in_playoffs))
          : tournament.status === "in_progress" || tournament.status === "completed"
            || (tournament.id === nextTournament?.id && hasTeeTimesForNext);
        const rowLinkTarget = isPlayoffTournament && tournament.status !== "scheduled"
          ? `/leagues/${leagueId}/tournaments/${tournament.id}`
          : isPlayoffTournament
          ? `/leagues/${leagueId}/standings?view=bracket`
          : `/leagues/${leagueId}/tournaments/${tournament.id}`;
        const rowLinkState = isPlayoffTournament && tournament.status !== "scheduled" && playoffPickNames.length > 0
          ? { playoffPickNames }
          : undefined;

        // Only show missed-pick styling when picks are revealed. When viewing
        // another member, unrevealed tournaments (next scheduled or live before
        // all R1 tee-off) have no pick data — the red border would leak that
        // the member hasn't picked.
        const isPickHidden = !isViewingSelf && (
          tournament.id === nextTournament?.id ||
          (tournament.id === liveTournament?.id && !liveTournament?.all_r1_teed_off)
        );
        const hasMissedRegularPick = !isPickHidden && !isPlayoffTournament && !pick && completedTournaments.some((t) => t.id === tournament.id);
        const hasPlayoffPenalty = !isPickHidden && isPlayoffTournament && tournament.status === "completed" && playoffData && playoffData.picks.length === 0;
        const rowClass = `bg-white border rounded-xs p-3 sm:p-5 flex items-center justify-between gap-2 sm:gap-4 transition-all ${
          hasMissedRegularPick || hasPlayoffPenalty
            ? "border-flag-100"
            : "border-ink-200"
        } ${isClickable ? "hover:shadow-sheet hover:border-fairway-300 cursor-pointer" : ""}`;
        const rowContent = (
          <>
            <div className="space-y-0.5 min-w-0 flex-1">
              <TournamentBadgePills tournament={tournament} isPlayoff={isPlayoffTournament} />
              <p className="font-semibold text-ink-900 text-sm sm:text-base truncate">{fmtTournamentName(tournament.name)}</p>
              <TournamentBadgeDates tournament={tournament} />
            </div>

            <div className="flex items-center gap-2 sm:gap-3 shrink-0">
              {isPlayoffTournament ? (() => {
                if (!playoffData) {
                  return <p className="text-xs sm:text-sm text-ink-400 text-right">Not in playoff round</p>;
                }
                const { picks: poPicks, total_points, status: roundStatus } = playoffData;
                const is_picks_visible = isViewingSelf ? true : (otherPlayoffData?.is_picks_visible ?? true);
                if (roundStatus === "drafting") {
                  if (isViewingSelf) {
                    const isActiveRound = myPod?.tournament_id === tournament.id;
                    const hasSubmitted = isActiveRound ? (myPod?.has_submitted ?? false) : poPicks.length > 0;
                    return hasSubmitted ? (
                      <div className="flex items-center gap-1.5 text-fairway-700">
                        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                        </svg>
                        <p className="text-xs sm:text-sm font-semibold">Rankings submitted</p>
                      </div>
                    ) : (
                      <p className="text-xs sm:text-sm font-medium text-brass-600">No rankings yet</p>
                    );
                  }
                  return <p className="text-xs sm:text-sm font-medium text-ink-400 text-right">Picks hidden</p>;
                }
                if (roundStatus === "locked" && tournament.status === "in_progress") {
                  if (poPicks.length > 0) {
                    return (
                      <div className="text-right space-y-1">
                        {poPicks.map((p, i) => (
                          <div key={i} className="flex items-center gap-2 justify-end">
                            <p className="text-xs sm:text-sm font-medium text-ink-600">{p.partner_name ? `${p.golfer_name} / ${p.partner_name}` : p.golfer_name}</p>
                            {"golfer_pga_tour_id" in p && (
                              <GolferAvatar pgaTourId={p.golfer_pga_tour_id} name={p.golfer_name} className="w-6 h-6 sm:w-7 sm:h-7 shrink-0 hidden sm:block" />
                            )}
                          </div>
                        ))}
                        <p className="text-[10px] sm:text-xs text-ink-400">In progress</p>
                      </div>
                    );
                  }
                  if (isViewingSelf || is_picks_visible) {
                    return <p className="text-xs sm:text-sm font-medium text-ink-400 text-right">No picks assigned</p>;
                  }
                  return <p className="text-xs sm:text-sm font-medium text-ink-400 text-right">Picks hidden</p>;
                }
                if (roundStatus === "completed" || tournament.status === "completed") {
                  if (poPicks.length > 0) {
                    return (
                      <div className="text-right space-y-1.5">
                        {poPicks.map((p, i) => (
                          <div key={i} className="flex items-center gap-2 justify-end">
                            <div className="space-y-0.5 text-right">
                              <p className="text-xs sm:text-sm font-medium text-ink-600">{p.partner_name ? `${p.golfer_name} / ${p.partner_name}` : p.golfer_name}</p>
                              <p className={`text-xs sm:text-sm font-bold tabular-nums ${
                                p.points_earned === null ? "text-ink-400"
                                : p.points_earned > 0 ? "text-fairway-700"
                                : "text-flag-600"
                              }`}>
                                {formatPoints(p.points_earned)}
                              </p>
                            </div>
                            {"golfer_pga_tour_id" in p && (
                              <GolferAvatar pgaTourId={p.golfer_pga_tour_id} name={p.golfer_name} className="w-6 h-6 sm:w-7 sm:h-7 shrink-0 hidden sm:block" />
                            )}
                          </div>
                        ))}
                        {poPicks.length > 1 && (
                          <p className={`text-[10px] sm:text-xs font-bold tabular-nums border-t border-ink-100 pt-1 ${
                            (total_points ?? 0) >= 0 ? "text-fairway-700" : "text-flag-600"
                          }`}>
                            Total: {formatPoints(total_points)}
                          </p>
                        )}
                      </div>
                    );
                  }
                  return (
                    <div className="text-right space-y-0.5">
                      <p className="text-xs sm:text-sm font-medium text-flag-500">No pick</p>
                      <p className="text-base sm:text-lg font-bold text-flag-600 tabular-nums">
                        {formatPoints(total_points)}
                      </p>
                    </div>
                  );
                }
                return <p className="text-xs sm:text-sm text-ink-400">Playoff round</p>;
              })() : pick ? (() => {
                const multiplier = "effective_multiplier" in tournament
                  ? (tournament as { effective_multiplier: number }).effective_multiplier
                  : 1;
                const displayPoints = pick.points_earned;
                const golferStatus = pick.golfer_status;
                const showBreakdown = multiplier > 1 && pick.earnings_usd !== null && pick.earnings_usd > 0;
                const statusLabel = golferStatus === "CUT" ? "CUT"
                  : golferStatus === "WD" ? "WD"
                  : golferStatus === "DQ" ? "DQ"
                  : null;
                return (
                  <>
                    <div className="text-right space-y-0.5">
                      <p className="text-xs sm:text-sm font-medium text-ink-600">{pick.golfer.name}</p>
                      <p
                        className={`text-base sm:text-lg font-bold leading-tight ${
                          statusLabel || displayPoints === null
                            ? "text-ink-400"
                            : displayPoints > 0
                            ? "text-fairway-700 tabular-nums"
                            : "text-flag-600 tabular-nums"
                        }`}
                      >
                        {statusLabel ?? formatPoints(displayPoints)}
                      </p>
                      {showBreakdown && (
                        <p className="text-[10px] sm:text-xs text-ink-400 tabular-nums leading-tight">
                          {formatPoints(pick.earnings_usd)} &middot; {multiplier}&times;
                        </p>
                      )}
                    </div>
                    <GolferAvatar
                      pgaTourId={pick.golfer.pga_tour_id}
                      name={pick.golfer.name}
                      className="w-7 h-7 sm:w-9 sm:h-9 shrink-0"
                    />
                  </>
                );
              })() : !isViewingSelf && (tournament.id === nextTournament?.id || (tournament.id === liveTournament?.id && !liveTournament?.all_r1_teed_off)) ? (
                <p className="text-xs sm:text-sm font-medium text-ink-400 text-right">Pick hidden</p>
              ) : (
                <div className="text-right space-y-0.5">
                  <p className={`text-xs sm:text-sm font-medium ${tournament.status === "scheduled" ? "text-ink-400" : "text-flag-500"}`}>
                    {tournament.status === "scheduled" ? "No pick yet" : "No pick"}
                  </p>
                  {tournament.status === "completed" && !tournament.scoring_pending && league?.no_pick_penalty !== undefined ? (
                    <p className="text-base sm:text-lg font-bold text-flag-600 tabular-nums">
                      {formatPoints(league.no_pick_penalty)}
                    </p>
                  ) : (
                    <p className="text-base sm:text-lg font-bold text-ink-300 tabular-nums">&mdash;</p>
                  )}
                </div>
              )}
              {isClickable && (
                <svg className="w-4 h-4 text-ink-300 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              )}
            </div>
          </>
        );

        return isClickable ? (
          <Link
            key={key}
            to={rowLinkTarget}
            state={rowLinkState}
            className={rowClass}
          >
            {rowContent}
          </Link>
        ) : (
          <div key={key} className={rowClass}>
            {rowContent}
          </div>
        );
      })}
    </div>
  );
}
