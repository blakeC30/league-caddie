/**
 * Picks — season history of picks and points earned, viewable for any league member.
 */

import { useState, useEffect, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useMyPicks, useAllPicks, useTournaments, useTournamentField } from "../hooks/usePick";
import { useLeague, useLeagueTournaments, useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import { useAuthStore } from "../store/authStore";
import { useMyPlayoffPicks, useBracket, useMyPlayoffPod } from "../hooks/usePlayoff";
import { Spinner } from "../components/Spinner";
import { MemberDropdown } from "../components/picks/MemberDropdown";
import { SeasonTotalCard } from "../components/picks/SeasonTotalCard";
import { PicksStatCards } from "../components/picks/PicksStatCards";
import { PicksTable } from "../components/picks/PicksTable";
import type { OtherPlayoffEntry } from "../components/picks/PicksTable";

export function MyPicks() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const currentUser = useAuthStore((s) => s.user);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Picks — League Caddie";
  }, []);

  const { data: members } = useLeagueMembers(leagueId!);
  const { data: leagueTournaments, isLoading: tournamentsLoading } = useLeagueTournaments(leagueId!);
  const { data: league } = useLeague(leagueId!);
  const { data: myPicksData, isLoading } = useMyPicks(leagueId!);
  const { data: myPlayoffPicks } = useMyPlayoffPicks(leagueId!);
  const { data: myPod } = useMyPlayoffPod(leagueId!);
  const { data: bracket } = useBracket(leagueId!);
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");
  const approvedMembers = members?.filter((m) => m.status === "approved") ?? [];
  const isManager = members?.some((m) => m.user_id === currentUser?.id && m.role === "manager") ?? false;

  // Default to the current user; allow switching via dropdown.
  const viewingUserId = selectedUserId ?? currentUser?.id ?? null;
  const isViewingSelf = !selectedUserId || selectedUserId === currentUser?.id;

  // When viewing another member, fetch only their picks server-side (not the entire league).
  const { data: allPicks } = useAllPicks(
    leagueId!,
    isViewingSelf ? undefined : (viewingUserId ?? undefined),
  );

  // Current user always uses myPicksData (includes in-progress tournament picks).
  // Other members use allPicks — already filtered by user_id on the server.
  const picks = isViewingSelf
    ? myPicksData ?? null
    : allPicks ?? null;

  const { data: globalScheduled } = useTournaments("scheduled");
  const { data: globalInProgress } = useTournaments("in_progress");

  const liveTournament = leagueTournaments?.find((t) => t.status === "in_progress");
  const hasLiveTournament = !!liveTournament;

  // Only show the next upcoming tournament if there is no live one.
  const nextTournament = hasLiveTournament
    ? undefined
    : leagueTournaments
        ?.filter((t) => t.status === "scheduled")
        .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];

  // Fetch the field for the next scheduled tournament to know if tee times are available.
  // React Query caches this; it's the same data MakePick already fetches.
  const { data: nextField } = useTournamentField(nextTournament?.id);
  const hasTeeTimesForNext = Array.isArray(nextField) && nextField.length > 0 && nextField.some((g) => g.tee_time != null);

  // hasPickForNext always reflects the current user — used for the Make Pick button label.
  const hasPickForNext = nextTournament
    ? myPicksData?.some((p) => p.tournament_id === nextTournament.id)
    : false;

  // Live tournament pick for current user — used to determine if pick button should show.
  const myLivePick = liveTournament
    ? myPicksData?.find((p) => p.tournament_id === liveTournament.id)
    : undefined;

  // The pick window for a scheduled tournament only opens when the league's next
  // tournament is the globally-next PGA Tour event. A league may skip PGA events;
  // the button stays hidden until those skipped events complete and earnings publish.
  const globallyNextId = globalScheduled
    ?.slice()
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0]?.id ?? null;
  const hasGloballyInProgress = globalInProgress !== undefined && globalInProgress.length > 0;
  const nextTournamentIsGloballyNext =
    !hasGloballyInProgress && !!nextTournament && !!globallyNextId && nextTournament.id === globallyNextId;

  // Hide the pick button when the live tournament's pick is locked (golfer has teed off),
  // or when all Round 1 tee times have passed and the member has no pick yet (window permanently closed).
  const pickActionAvailable = hasLiveTournament
    ? (!myLivePick?.is_locked && !(liveTournament?.all_r1_teed_off && !myLivePick))
    : nextTournamentIsGloballyNext;

  // Map submitted picks by tournament id for quick lookup
  const picksByTournamentId = new Map(picks?.map((p) => [p.tournament_id, p]) ?? []);

  const playoffPicksByTournamentId = new Map(
    (myPlayoffPicks ?? []).map((p) => [p.tournament_id, p])
  );

  // Set of tournament IDs that belong to a playoff round — derived directly from
  // the is_playoff_round field on each LeagueTournamentOut (set by the backend when
  // the tournament is assigned to a PlayoffRound for this league). This is the
  // authoritative source; bracket/myPod/myPicks are not needed for this check.
  const playoffTournamentIds = useMemo(
    () => new Set((leagueTournaments ?? []).filter((t) => t.is_playoff_round).map((t) => t.id)),
    [leagueTournaments]
  );

  // For viewing another member: extract their picks from the bracket
  const otherMemberPlayoffMap = (() => {
    if (isViewingSelf || !viewingUserId || !bracket) return new Map<string, OtherPlayoffEntry>();
    const m = new Map<string, OtherPlayoffEntry>();
    for (const round of bracket.rounds) {
      if (!round.tournament_id) continue;
      for (const pod of round.pods) {
        const member = pod.members.find((mb) => mb.user_id === viewingUserId);
        if (!member) continue;
        m.set(round.tournament_id, {
          status: round.status,
          picks: pod.picks.filter((p) => p.pod_member_id === member.id),
          total_points: member.total_points,
          is_picks_visible: pod.is_picks_visible,
        });
      }
    }
    return m;
  })();

  // Tournaments that are locked for picks: completed, in progress, or start date already passed.
  const today = new Date().toISOString().slice(0, 10);
  const completedTournaments = leagueTournaments?.filter(
    (t) => t.status === "completed" || t.status === "in_progress" || t.start_date <= today
  ) ?? [];

  // Restrict all stat calculations to picks for tournaments in the league's active schedule.
  const leagueTournamentIds = new Set(leagueTournaments?.map((t) => t.id) ?? []);
  const scheduledPicks = picks?.filter((p) => leagueTournamentIds.has(p.tournament_id)) ?? null;

  // Fully finished regular-season tournaments with no pick submitted — penalty applies to these.
  // Playoff tournaments are excluded: their penalty is already baked into total_points from the
  // playoff scoring service and must not be double-counted here.
  const noPickCompletedCount = completedTournaments.filter(
    (t) =>
      t.status === "completed" &&
      !playoffTournamentIds.has(t.id) &&
      !scheduledPicks?.some((p) => p.tournament_id === t.id)
  ).length;
  const penaltyTotal = noPickCompletedCount * (league?.no_pick_penalty ?? 0);

  // Playoff earnings (total_points already includes any per-slot penalties from score_round).
  // Only added for the current user — own picks are never hidden, so the data is always accurate.
  const playoffEarned = isViewingSelf
    ? (myPlayoffPicks ?? []).reduce((sum, p) => sum + (p.total_points ?? 0), 0)
    : 0;

  const totalEarned =
    (scheduledPicks?.reduce((sum, p) => sum + (p.points_earned ?? 0), 0) ?? 0) +
    penaltyTotal +
    playoffEarned;
  // Picks for which we have a final score
  const scoredPicks = scheduledPicks?.filter((p) => p.points_earned !== null) ?? [];
  // Picks that earned $0 (missed the cut)
  const cutsMissed = scoredPicks.filter((p) => p.points_earned === 0);
  // Picks submitted for final (status === "completed") tournaments only
  const submittedForFinal = scheduledPicks?.filter((p) =>
    leagueTournaments?.some((t) => t.id === p.tournament_id && t.status === "completed")
  ) ?? [];
  // Best single tournament
  const bestPick = scoredPicks.reduce<(typeof scoredPicks)[0] | null>(
    (best, p) => (best === null || p.points_earned! > best.points_earned! ? p : best),
    null
  );
  const finalTournamentCount = completedTournaments.filter((t) => t.status === "completed").length;
  const avgEarnings = finalTournamentCount > 0 ? totalEarned / finalTournamentCount : null;

  // Loading guard — prevent flash of "No picks yet" while data loads
  if (tournamentsLoading || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner className="w-8 h-8 text-green-600" />
      </div>
    );
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
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
            Season History
          </p>
          <h1 className="text-3xl font-bold text-gray-900">Picks</h1>
        </div>
        {pickActionAvailable && (
          <Link
            to={`/leagues/${leagueId}/pick`}
            className="inline-flex items-center gap-2 bg-green-800 hover:bg-green-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-sm transition-colors"
          >
            {hasPickForNext ? "Change Pick" : "Make Pick"}
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
            </svg>
          </Link>
        )}
      </div>

      {/* Member selector */}
      {approvedMembers.length > 1 && (
        <MemberDropdown
          approvedMembers={approvedMembers}
          viewingUserId={viewingUserId}
          onSelectUser={setSelectedUserId}
        />
      )}

      {/* Season total */}
      <SeasonTotalCard totalEarned={totalEarned} />

      {/* Stats grid */}
      <PicksStatCards
        finalTournamentCount={finalTournamentCount}
        submittedForFinalCount={submittedForFinal.length}
        scoredPicksCount={scoredPicks.length}
        cutsMissedCount={cutsMissed.length}
        bestPickPoints={bestPick?.points_earned ?? null}
        bestPickGolferName={bestPick?.golfer.name}
        avgEarnings={avgEarnings}
      />

      {/* Picks table */}
      <PicksTable
        leagueId={leagueId!}
        league={league}
        leagueTournaments={leagueTournaments ?? []}
        isLoading={isLoading}
        isViewingSelf={isViewingSelf}
        nextTournament={nextTournament}
        liveTournament={liveTournament}
        hasTeeTimesForNext={hasTeeTimesForNext}
        picksByTournamentId={picksByTournamentId}
        playoffTournamentIds={playoffTournamentIds}
        playoffPicksByTournamentId={playoffPicksByTournamentId}
        otherMemberPlayoffMap={otherMemberPlayoffMap}
        completedTournaments={completedTournaments}
        myPod={myPod}
      />
    </div>
  );
}
