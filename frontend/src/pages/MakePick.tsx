/**
 * MakePick — pick a golfer for the next scheduled tournament.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PickForm } from "../components/PickForm";
import { GolferAvatar } from "../components/GolferAvatar";
import { FlagIcon } from "../components/FlagIcon";
import { PlayoffPreferenceEditor } from "../components/PlayoffPreferenceEditor";
import type { GolferInField } from "../api/endpoints";
import { useLeagueTournaments, useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import { useMyPicks, useSubmitPick, useTournamentField, useChangePick, useAllGolfers, useTournaments } from "../hooks/usePick";
import { useAuthStore } from "../store/authStore";
import { useMyPlayoffPod, useMyPreferences } from "../hooks/usePlayoff";
import { fmtTournamentName } from "../utils";
import { Spinner } from "../components/Spinner";

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatPurse(purse: number | null): string | null {
  if (purse === null) return null;
  if (purse >= 1_000_000) {
    const m = purse / 1_000_000;
    return `$${m % 1 === 0 ? m : m.toFixed(1)}M purse`;
  }
  return `$${Math.round(purse / 1000)}K purse`;
}

export function MakePick() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState<{ golferName: string; pgaTourId: string; changed: boolean } | null>(null);
  const [confirmedPlayoff, setConfirmedPlayoff] = useState<{ count: number; wasUpdate: boolean; tournamentName: string } | null>(null);

  const currentUserId = useAuthStore((s) => s.user?.id);
  const { data: members } = useLeagueMembers(leagueId!);
  const isManager = members?.some((m) => m.user_id === currentUserId && m.role === "manager") ?? false;
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");

  const { data: leagueTournaments } = useLeagueTournaments(leagueId!);
  const { data: globalScheduled } = useTournaments("scheduled");
  const { data: globalInProgress } = useTournaments("in_progress");
  const { data: myPicks } = useMyPicks(leagueId!);
  const submitPick = useSubmitPick(leagueId!);
  const changePick = useChangePick(leagueId!);

  // Target the earliest actionable tournament: prefer in_progress over scheduled.
  // If a tournament is currently in progress, it must complete before the member
  // can pick for the next scheduled tournament (rules: previous tournament must
  // complete first). In_progress tournaments are still pickable if the chosen
  // golfer hasn't teed off yet (the backend enforces the tee_time check).
  const tournament = leagueTournaments
    ?.filter((t) => t.status === "scheduled" || t.status === "in_progress")
    .sort((a, b) => {
      // In_progress before scheduled: current week takes priority over upcoming.
      // Within the same status, sort by start_date ascending.
      if (a.status !== b.status) {
        return a.status === "in_progress" ? -1 : 1;
      }
      return a.start_date.localeCompare(b.start_date);
    })[0];

  // Globally-next PGA Tour tournament — earliest scheduled tournament worldwide.
  // The pick window only opens when the league's pick target IS this tournament.
  // A league may skip PGA events; picks are blocked until those pass naturally.
  const globallyNextTournament = globalScheduled
    ?.slice()
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0] ?? null;

  const hasGloballyInProgress = globalInProgress !== undefined && globalInProgress.length > 0;

  // True when the league pick target aligns with the global PGA schedule.
  // Only relevant for scheduled tournaments — in_progress is always current.
  const pickTargetIsGloballyNext =
    !tournament ||
    tournament.status === "in_progress" ||
    (!hasGloballyInProgress && globallyNextTournament !== null && tournament.id === globallyNextTournament.id);

  const { data: myPod } = useMyPlayoffPod(leagueId!);
  const podIdForPrefs = myPod?.is_in_playoffs ? (myPod.active_pod_id ?? null) : null;
  const { data: myPreferences = [] } = useMyPreferences(leagueId!, podIdForPrefs);

  const { data: field } = useTournamentField(tournament?.id);
  const { data: allGolfers } = useAllGolfers();

  const existingPick = myPicks?.find((p) => p.tournament_id === tournament?.id);

  // When the tournament is scheduled but no field entries exist yet, fall back to
  // all known golfers so users can pick early. The backend allows this pre-field pick.
  const fieldNotReleased =
    tournament?.status === "scheduled" && Array.isArray(field) && field.length === 0;
  // allGolfers (Golfer[]) lacks tee_time, but the pre-field path only activates
  // when status === "scheduled", so the teedOffGolferIds logic below never fires
  // for it. The cast is safe.
  const effectiveField: GolferInField[] = fieldNotReleased
    ? ((allGolfers ?? []) as GolferInField[])
    : (field ?? []);

  // Set of golfer IDs already used this season (for the "Used" greyed-out display).
  const usedGolferIds = new Set(myPicks?.map((p) => p.golfer_id) ?? []);

  // When the tournament is in_progress, identify golfers whose Round 1 tee time
  // has already passed. These golfers are no longer eligible for a late pick.
  // We keep them visible in the list (greyed out with a "Teed off" label) so the
  // user understands why they cannot select them, rather than hiding them silently.
  const now = new Date();
  const teedOffGolferIds = new Set(
    tournament?.status === "in_progress"
      ? effectiveField
          .filter((g) => g.tee_time != null && new Date(g.tee_time) <= now)
          .map((g) => g.id)
      : []
  );

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

  async function handleSubmit(golferId: string) {
    setError("");
    const wasChange = !!existingPick;
    try {
      if (existingPick) {
        await changePick.mutateAsync({ pickId: existingPick.id, golfer_id: golferId });
      } else {
        await submitPick.mutateAsync({ tournament_id: tournament!.id, golfer_id: golferId });
      }
      const golfer = effectiveField.find((g) => g.id === golferId);
      setConfirmed({ golferName: golfer?.name ?? "your golfer", pgaTourId: golfer?.pga_tour_id ?? "", changed: wasChange });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Failed to save pick. Please try again.");
    }
  }

  if (confirmed) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center space-y-5">
          <div className="relative w-20 h-20 mx-auto">
            <GolferAvatar
              pgaTourId={confirmed.pgaTourId}
              name={confirmed.golferName}
              className="w-20 h-20"
            />
            <div className="absolute -bottom-1 -right-1 w-6 h-6 bg-green-500 rounded-full flex items-center justify-center border-2 border-white">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
              {confirmed.changed ? "Pick Updated" : "Pick Submitted"}
            </p>
            <h1 className="text-2xl font-bold text-gray-900">{confirmed.golferName}</h1>
            {tournament && (
              <p className="text-sm text-gray-500">{fmtTournamentName(tournament.name)}</p>
            )}
          </div>
          <Link
            to={`/leagues/${leagueId}/picks`}
            className="inline-block w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
          >
            View My Picks
          </Link>
          <Link
            to={`/leagues/${leagueId}`}
            className="inline-block text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  if (confirmedPlayoff) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center space-y-5">
          <div className="relative w-20 h-20 mx-auto">
            <div className="w-20 h-20 rounded-full bg-purple-100 flex items-center justify-center">
              <svg className="w-10 h-10 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
              </svg>
            </div>
            <div className="absolute -bottom-1 -right-1 w-6 h-6 bg-green-500 rounded-full flex items-center justify-center border-2 border-white">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
              {confirmedPlayoff.wasUpdate ? "Rankings Updated" : "Rankings Submitted"}
            </p>
            <h1 className="text-2xl font-bold text-gray-900">
              {confirmedPlayoff.count} golfer{confirmedPlayoff.count !== 1 ? "s" : ""} ranked
            </h1>
            {confirmedPlayoff.tournamentName && (
              <p className="text-sm text-gray-500">{fmtTournamentName(confirmedPlayoff.tournamentName)}</p>
            )}
          </div>
          <p className="text-sm text-gray-400 max-w-xs mx-auto">
            Your preferences are saved. Picks will be assigned automatically when the tournament begins.
          </p>
          <Link
            to={`/leagues/${leagueId}/leaderboard?view=bracket`}
            className="inline-block w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
          >
            View Bracket
          </Link>
          <Link
            to={`/leagues/${leagueId}`}
            className="inline-block text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  // Playoff week: show playoff preference UI instead of regular pick
  if (myPod?.is_playoff_week) {
    const podId = myPod.active_pod_id;
    const tournamentId = myPod.tournament_id;

    if (!myPod.is_in_playoffs) {
      return (
        <div className="max-w-lg mx-auto space-y-6">
          {tournament && (
            <div className="relative overflow-hidden bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5">
              <div className="absolute -top-6 -right-6 w-32 h-32 rounded-full bg-white/5 blur-2xl pointer-events-none" />
              <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-1">
                Playoff Week
              </p>
              <p className="text-xl font-bold text-white">{fmtTournamentName(tournament.name)}</p>
            </div>
          )}
          <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-purple-100 text-purple-600 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
              </svg>
            </div>
            <p className="font-semibold text-gray-700">Playoff Week</p>
            <p className="text-sm text-gray-400 max-w-xs mx-auto">
              This is a playoff round. You're not participating in the playoffs this week.
            </p>
            <Link
              to={`/leagues/${leagueId}`}
              className="inline-block text-sm font-semibold text-green-700 hover:text-green-900 mt-2 transition-colors"
            >
              Back to dashboard →
            </Link>
          </div>
        </div>
      );
    }

    if (myPod.round_status === "locked") {
      return (
        <div className="max-w-lg mx-auto space-y-6">
          {tournament && (
            <div className="relative overflow-hidden bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5">
              <div className="absolute -top-6 -right-6 w-32 h-32 rounded-full bg-white/5 blur-2xl pointer-events-none" />
              <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-1">
                Playoff Round {myPod.active_round_number}
              </p>
              <p className="text-xl font-bold text-white">{fmtTournamentName(tournament.name)}</p>
            </div>
          )}
          <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-gray-200 text-gray-500 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
              </svg>
            </div>
            <p className="font-semibold text-gray-700">Picks submitted</p>
            <p className="text-sm text-gray-400 max-w-xs mx-auto">
              The preference window has closed and your picks have been locked in.
            </p>
            <Link
              to={`/leagues/${leagueId}/leaderboard?view=bracket`}
              className="inline-block text-sm font-semibold text-green-700 hover:text-green-900 mt-2 transition-colors"
            >
              View Bracket →
            </Link>
          </div>
        </div>
      );
    }

    // round_status === "drafting" or "pending" — members can submit preferences
    if ((myPod.round_status === "drafting" || myPod.round_status === "pending") && podId && tournamentId) {
      return (
        <div className="max-w-lg mx-auto space-y-6">
          {tournament ? (
            <div className="relative overflow-hidden bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5">
              <div className="absolute -top-6 -right-6 w-32 h-32 rounded-full bg-white/5 blur-2xl pointer-events-none" />
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-1">
                    Playoff Round {myPod.active_round_number}
                  </p>
                  <p className="text-xl font-bold text-white">{fmtTournamentName(tournament.name)}</p>
                  <div className="flex items-center gap-3 mt-2 flex-wrap">
                    <span className="text-sm text-green-300">{formatDate(tournament.start_date)}–{formatDate(tournament.end_date)}</span>
                    {formatPurse(tournament.purse_usd) && (
                      <>
                        <span className="text-green-600">·</span>
                        <span className="text-sm text-green-300">{formatPurse(tournament.purse_usd)}</span>
                      </>
                    )}
                    {tournament.effective_multiplier >= 2 && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-500 text-white flex-shrink-0">
                        {tournament.effective_multiplier}×
                      </span>
                    )}
                    {tournament.effective_multiplier > 1 && tournament.effective_multiplier < 2 && (
                      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-500 text-white flex-shrink-0">
                        {tournament.effective_multiplier}×
                      </span>
                    )}
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500 text-white flex-shrink-0">
                      PLAYOFF
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-1">
                Playoff Round {myPod.active_round_number}
              </p>
              <p className="text-xl font-bold text-white">Playoff Pick</p>
            </div>
          )}

          <div className="flex items-start gap-2.5 bg-purple-50 border border-purple-200 rounded-xl px-4 py-3">
            <svg className="w-4 h-4 text-purple-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
            </svg>
            <p className="text-xs text-purple-700 leading-relaxed">
              <span className="font-semibold">Playoff picks.</span> Rank your preferred golfers in order. The system will assign picks automatically — each player gets {myPod.picks_per_round} golfer{(myPod.picks_per_round ?? 1) !== 1 ? "s" : ""}. Submit before the tournament starts.
            </p>
          </div>

          <PlayoffPreferenceEditor
            leagueId={leagueId!}
            podId={podId}
            tournamentId={tournamentId}
            currentPreferences={myPreferences}
            picksPerRound={myPod.picks_per_round ?? undefined}
            requiredCount={myPod.required_preference_count ?? undefined}
            deadline={myPod.deadline ?? undefined}
            onSaveSuccess={(count, wasUpdate) =>
              setConfirmedPlayoff({ count, wasUpdate, tournamentName: tournament?.name ?? "" })
            }
          />

          <div className="flex items-center gap-4 pt-2">
            <Link
              to={`/leagues/${leagueId}/leaderboard?view=bracket`}
              className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
            >
              View Bracket →
            </Link>
            <Link
              to={`/leagues/${leagueId}`}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              Back to dashboard
            </Link>
          </div>
        </div>
      );
    }
  }

  // League has a pick target but it doesn't match the globally-next PGA tournament.
  // A skipped PGA event is still upcoming — picks must wait. Guard against the
  // loading state (globalScheduled undefined) to avoid a flash of this screen.
  if (tournament && tournament.status === "scheduled" && !pickTargetIsGloballyNext && globalScheduled !== undefined) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="space-y-1 mb-8">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
            Pick Golfer
          </p>
          <h1 className="text-3xl font-bold text-gray-900">Make Your Pick</h1>
        </div>
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-16 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <p className="font-semibold text-gray-700">Picks not yet available</p>
          <p className="text-sm text-gray-400 max-w-xs mx-auto">
            {globallyNextTournament
              ? `Picks open after ${globallyNextTournament.name} completes and earnings are published.`
              : "Check back soon — picks open once the PGA Tour schedule catches up."}
          </p>
          <Link
            to={`/leagues/${leagueId}`}
            className="inline-block text-sm font-semibold text-green-700 hover:text-green-900 mt-2 transition-colors"
          >
            Back to dashboard →
          </Link>
        </div>
      </div>
    );
  }

  if (!tournament) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="space-y-1 mb-8">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
            Pick Golfer
          </p>
          <h1 className="text-3xl font-bold text-gray-900">Make Your Pick</h1>
        </div>
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-16 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-green-100 text-green-700 flex items-center justify-center mx-auto">
            <FlagIcon className="w-6 h-6" />
          </div>
          <p className="font-semibold text-gray-700">No upcoming tournaments</p>
          <p className="text-sm text-gray-400 max-w-xs mx-auto">
            There are no scheduled tournaments to pick for right now.
          </p>
          <Link
            to={`/leagues/${leagueId}`}
            className="inline-block text-sm font-semibold text-green-700 hover:text-green-900 mt-2 transition-colors"
          >
            Back to dashboard →
          </Link>
        </div>
      </div>
    );
  }

  // Still loading: field query hasn't resolved yet, or pre-field golfers haven't loaded.
  if (field === undefined || (fieldNotReleased && allGolfers === undefined)) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="flex justify-center py-8"><Spinner /></div>
      </div>
    );
  }

  // Tee times are available when the field is released and at least one entry has a tee_time set.
  const hasTeetimes = !fieldNotReleased && (field ?? []).some((g) => g.tee_time != null);
  const tournamentDetailPath = `/leagues/${leagueId}/tournaments/${tournament.id}`;

  // Shared tournament context header — shown whenever a tournament is known.
  // Wraps in a Link to the tournament detail page when tee times are available.
  const headerContent = (
    <>
      <div className="absolute -top-6 -right-6 w-32 h-32 rounded-full bg-white/5 blur-2xl pointer-events-none" />
      <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-1">
        {existingPick ? "Change Your Pick" : "Make Your Pick"}
      </p>
      <p className="text-xl font-bold text-white">{fmtTournamentName(tournament.name)}</p>
      <div className="flex items-center gap-3 mt-2 text-sm text-green-300">
        <span>{formatDate(tournament.start_date)}–{formatDate(tournament.end_date)}</span>
        {formatPurse(tournament.purse_usd) && (
          <>
            <span className="text-green-600">·</span>
            <span>{formatPurse(tournament.purse_usd)}</span>
          </>
        )}
        {tournament.effective_multiplier >= 2 && (
          <>
            <span className="text-green-600">·</span>
            <span className="font-bold text-amber-300">{tournament.effective_multiplier}× MAJOR</span>
          </>
        )}
        {hasTeetimes && (
          <>
            <span className="text-green-600">·</span>
            <span className="text-green-300 underline underline-offset-2">View tee times →</span>
          </>
        )}
      </div>
    </>
  );

  const tournamentHeader = hasTeetimes ? (
    <Link
      to={tournamentDetailPath}
      className="relative overflow-hidden bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5 block hover:from-green-800 hover:to-green-600 transition-colors"
    >
      {headerContent}
    </Link>
  ) : (
    <div className="relative overflow-hidden bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5">
      {headerContent}
    </div>
  );

  // Pick is locked — golfer has already teed off, no changes allowed.
  if (existingPick?.is_locked) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        {tournamentHeader}
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-gray-200 text-gray-500 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
          </div>
          <p className="font-semibold text-gray-700">Pick locked</p>
          <p className="text-sm text-gray-400 max-w-xs mx-auto">
            Your pick of <span className="font-medium text-gray-600">{existingPick.golfer.name}</span> is locked — they've already teed off.
          </p>
          <Link
            to={`/leagues/${leagueId}`}
            className="inline-block text-sm font-semibold text-green-700 hover:text-green-900 mt-2 transition-colors"
          >
            Back to dashboard →
          </Link>
        </div>
      </div>
    );
  }

  // IN_PROGRESS with no field entries — can't pick without tee time data.
  if (effectiveField.length === 0) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        {tournamentHeader}
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <p className="font-semibold text-gray-700">Field not yet available</p>
          <p className="text-sm text-gray-400 max-w-xs mx-auto">
            The player field for this tournament hasn't been announced yet.
            Check back closer to the start date — picks will open automatically.
          </p>
          <Link
            to={`/leagues/${leagueId}`}
            className="inline-block text-sm font-semibold text-green-700 hover:text-green-900 mt-2 transition-colors"
          >
            Back to dashboard →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      {tournamentHeader}
      {fieldNotReleased && (
        <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
          <p className="text-xs text-amber-700 leading-relaxed">
            Early picks are allowed, but the official field hasn't been announced. If your golfer doesn't enter the tournament, you'll earn 0 points and won't be able to use them again this season.
          </p>
        </div>
      )}
      {tournament.status === "in_progress" && (
        <p className="text-xs text-gray-400 leading-relaxed">
          This tournament is underway. You can still pick a golfer who hasn't teed off yet.
        </p>
      )}
      {tournament.is_team_event && (
        <div className="flex items-start gap-2.5 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
          </svg>
          <p className="text-xs text-blue-700 leading-relaxed">
            <span className="font-semibold">Team event.</span> Golfers compete in two-person teams this week. Pick one individual golfer — both partners appear in the list separately. Each golfer is tracked independently: picking one only uses up that golfer for the season, not their teammate. If you've already used one partner in a previous tournament, you can still pick the other. Points are based on that golfer's share of the team's earnings.
          </p>
        </div>
      )}
      <PickForm
        field={effectiveField}
        usedGolferIds={usedGolferIds}
        teedOffGolferIds={teedOffGolferIds}
        existingPick={existingPick}
        onSubmit={handleSubmit}
        submitting={submitPick.isPending || changePick.isPending}
        error={error}
      />
    </div>
  );
}
