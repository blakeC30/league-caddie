/**
 * ManageLeague — league manager panel.
 *
 * Members management (role changes, removal), join request approval,
 * tournament schedule selection, and league settings editing.
 * Non-managers are redirected to the league dashboard.
 */

import { useEffect, useMemo, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import {
  useLeague,
  useLeagueMembers,
  useLeaguePurchase,
  useLeagueTournaments,
  usePendingRequests,
  usePurchaseEvents,
  useStripePricing,
} from "../hooks/useLeague";
import { useTournaments, useTournamentField } from "../hooks/usePick";
import {
  useBracket,
  usePlayoffConfig,
} from "../hooks/usePlayoff";
import { useAuthStore } from "../store/authStore";
import { REQUIRED_ROUNDS, type ConfirmModalState } from "../components/manage/shared";
import {
  InviteLinkSection,
  LeagueSettingsSection,
  JoinRequestsSection,
  MembersSection,
  TournamentScheduleSection,
  PlayoffConfigSection,
  RevisePickSection,
  LeaguePlanSection,
  DangerZoneSection,
} from "../components/manage";

export function ManageLeague() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const currentUser = useAuthStore((s) => s.user);

  const { data: league } = useLeague(leagueId!);

  useEffect(() => {
    document.title = "Manage League — League Caddie";
  }, []);
  const { data: members, isLoading } = useLeagueMembers(leagueId!);

  const { data: pendingRequests } = usePendingRequests(leagueId!);

  const [confirmModal, setConfirmModal] = useState<ConfirmModalState | null>(null);

  // ---------------------------------------------------------------------------
  // Tournament schedule data
  // ---------------------------------------------------------------------------

  const { data: allTournaments } = useTournaments();
  const { data: leagueTournaments } = useLeagueTournaments(leagueId!);

  const hasInProgressTournament = (leagueTournaments ?? []).some(
    (t) => t.status === "in_progress"
  );

  // The next upcoming scheduled tournament — the current week's pick tournament.
  const nextUpcomingTournamentId = (() => {
    const scheduled = (allTournaments ?? [])
      .filter((t) => t.status === "scheduled")
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    return scheduled[0]?.id ?? null;
  })();

  // Eligible future tournaments from SAVED schedule (for playoff section advisory).
  const eligibleFutureTournaments = useMemo(
    () => {
      const allScheduled = (leagueTournaments ?? []).filter((t) => t.status === "scheduled");
      return allScheduled.filter(
        (t) => hasInProgressTournament || t.id !== nextUpcomingTournamentId
      ).length;
    },
    [leagueTournaments, nextUpcomingTournamentId, hasInProgressTournament]
  );

  // Track editing state from TournamentScheduleSection for cross-section computations
  const [editingSelectedIds, setEditingSelectedIds] = useState<Set<string>>(new Set());
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_editingMultipliers, setEditingMultipliers] = useState<Record<string, number>>({});

  // Eligible future tournaments from EDITING state (for schedule save blocking).
  const editingEligibleFutureTournaments = useMemo(
    () => {
      const allScheduled = (allTournaments ?? []).filter((t) => editingSelectedIds.has(t.id) && t.status === "scheduled");
      return allScheduled.filter(
        (t) => hasInProgressTournament || t.id !== nextUpcomingTournamentId
      ).length;
    },
    [allTournaments, editingSelectedIds, nextUpcomingTournamentId, hasInProgressTournament]
  );

  // ---------------------------------------------------------------------------
  // Playoff data
  // ---------------------------------------------------------------------------
  const { data: playoffConfig, isError: playoffConfigNotFound } = usePlayoffConfig(leagueId!);
  const { data: bracket } = useBracket(leagueId!);

  // True when the first playoff round's pick window has opened.
  const isScheduleLocked = useMemo(() => {
    if (!playoffConfig || playoffConfig.playoff_size === 0) return false;
    return playoffConfig.status !== "pending";
  }, [playoffConfig]);

  // True when the config is active and every round has moved past "pending".
  const playoffFullyLocked = useMemo(
    () =>
      !!playoffConfig &&
      playoffConfig.status !== "pending" &&
      (bracket?.rounds ?? []).every((r) => r.status !== "pending"),
    [playoffConfig, bracket]
  );

  const hasPlayoffScheduleError = useMemo(() => {
    if (!playoffConfig || playoffConfig.status !== "pending") return false;
    const effectiveSize = playoffConfig.playoff_size;
    if (effectiveSize === 0) return false;
    const required = REQUIRED_ROUNDS[effectiveSize] ?? 0;
    return required > 0 && editingEligibleFutureTournaments < required;
  }, [playoffConfig, editingEligibleFutureTournaments]);

  // Same map for the SAVED schedule (non-editing display).
  const savedPlayoffRoundMap = useMemo((): Map<string, number> => {
    if (bracket?.rounds?.length) {
      return new Map(
        bracket.rounds
          .filter((r) => r.tournament_id != null)
          .map((r) => [r.tournament_id!, r.round_number])
      );
    }
    if (!playoffConfig || playoffConfig.playoff_size === 0) return new Map();
    const required = REQUIRED_ROUNDS[playoffConfig.playoff_size] ?? 0;
    if (required === 0) return new Map();
    const allScheduled = (leagueTournaments ?? [])
      .filter((t) => t.status === "scheduled")
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const candidates = allScheduled.filter(
      (t) => hasInProgressTournament || t.id !== nextUpcomingTournamentId
    );
    const playoffSlice = candidates.slice(-required);
    return new Map(playoffSlice.map((t, i) => [t.id, i + 1]));
  }, [bracket, leagueTournaments, playoffConfig, nextUpcomingTournamentId, hasInProgressTournament]);

  // The one round whose tournament is currently in progress.
  const poInProgressRound = useMemo(
    () => (bracket?.rounds ?? []).find((r) => r.tournament_status === "in_progress") ?? null,
    [bracket]
  );

  const poReviseTournamentId = poInProgressRound?.tournament_id ?? undefined;
  const { data: poReviseField, isLoading: poReviseFieldLoading } = useTournamentField(poReviseTournamentId);

  // ---------------------------------------------------------------------------
  // Billing data
  // ---------------------------------------------------------------------------
  const { data: purchase } = useLeaguePurchase(leagueId!);
  const { data: pricingTiers = [] } = useStripePricing();
  const { data: purchaseEvents = [] } = usePurchaseEvents(leagueId!);

  // ---------------------------------------------------------------------------
  // Auth guard
  // ---------------------------------------------------------------------------
  const myMembership = members?.find((m) => m.user_id === currentUser?.id);
  const isManager = myMembership?.role === "manager";

  if (!isLoading && members !== undefined && !isManager) {
    return <Navigate to={`/leagues/${leagueId}`} replace />;
  }

  return (
    <div className="space-y-8">
      {/* Confirmation modal */}
      {confirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <h3 className="text-base font-bold text-gray-900">{confirmModal.title}</h3>
            <p className="text-sm text-gray-600">{confirmModal.message}</p>
            <div className="flex justify-end gap-3 pt-1">
              <button
                onClick={() => setConfirmModal(null)}
                className="px-5 py-2 text-sm font-semibold rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => { confirmModal.onConfirm(); setConfirmModal(null); }}
                className={`px-5 py-2 text-sm font-semibold rounded-xl text-white transition-colors ${
                  confirmModal.danger ? "bg-red-600 hover:bg-red-700" : "bg-green-800 hover:bg-green-700"
                }`}
              >
                {confirmModal.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Page header */}
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
          Manager Panel
        </p>
        <h1 className="text-3xl font-bold text-gray-900">{league?.name ?? "League Management"}</h1>
      </div>


      {/* Invite link — manager only */}
      {isManager && league && (
        <InviteLinkSection league={league} />
      )}

      {/* League Settings — manager only */}
      {isManager && (
        <LeagueSettingsSection league={league} leagueId={leagueId!} />
      )}

      {/* Pending join requests — manager only */}
      {isManager && (
        <JoinRequestsSection
          league={league}
          leagueId={leagueId!}
          pendingRequests={pendingRequests}
          onConfirm={setConfirmModal}
        />
      )}

      {/* Members */}
      <MembersSection
        leagueId={leagueId!}
        members={members}
        isLoading={isLoading}
        isManager={!!isManager}
        currentUser={currentUser}
        purchase={purchase}
        onConfirm={setConfirmModal}
      />

      {/* Tournament Schedule — manager only */}
      {isManager && (
        <TournamentScheduleSection
          leagueId={leagueId!}
          allTournaments={allTournaments}
          leagueTournaments={leagueTournaments}
          isScheduleLocked={isScheduleLocked}
          playoffConfig={playoffConfig}
          hasInProgressTournament={hasInProgressTournament}
          nextUpcomingTournamentId={nextUpcomingTournamentId}
          savedPlayoffRoundMap={savedPlayoffRoundMap}
          hasPlayoffScheduleError={hasPlayoffScheduleError}
          editingEligibleFutureTournaments={editingEligibleFutureTournaments}
          onSelectedIdsChange={setEditingSelectedIds}
          onMultipliersChange={setEditingMultipliers}
        />
      )}

      {/* Playoff Configuration — manager only */}
      {isManager && (
        <PlayoffConfigSection
          leagueId={leagueId!}
          playoffConfig={playoffConfig}
          playoffConfigNotFound={playoffConfigNotFound}
          bracket={bracket}
          members={members}
          eligibleFutureTournaments={eligibleFutureTournaments}
          playoffFullyLocked={playoffFullyLocked}
          poInProgressRound={poInProgressRound}
          poReviseField={poReviseField}
          poReviseFieldLoading={poReviseFieldLoading}
          onConfirm={setConfirmModal}
        />
      )}

      {/* Revise Pick — manager only */}
      {isManager && (
        <RevisePickSection
          leagueId={leagueId!}
          members={members}
          leagueTournaments={leagueTournaments}
          playoffConfig={playoffConfig}
        />
      )}

      {/* League Plan — manager only */}
      {isManager && (
        <LeaguePlanSection
          leagueId={leagueId!}
          purchase={purchase}
          pricingTiers={pricingTiers}
          purchaseEvents={purchaseEvents}
          onConfirm={setConfirmModal}
        />
      )}

      {/* Danger Zone — manager only */}
      {isManager && (
        <DangerZoneSection league={league} leagueId={leagueId!} />
      )}
    </div>
  );
}
