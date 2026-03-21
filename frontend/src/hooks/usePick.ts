/**
 * usePick — React Query hooks for picks, tournaments, and standings.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { golfersApi, picksApi, standingsApi, tournamentsApi } from "../api/endpoints";

export function useTournaments(status?: "scheduled" | "in_progress" | "completed") {
  return useQuery({
    queryKey: ["tournaments", status ?? "all"],
    queryFn: () => tournamentsApi.list(status),
  });
}

export function useTournamentField(tournamentId: string | undefined) {
  return useQuery({
    queryKey: ["tournamentField", tournamentId],
    queryFn: () => tournamentsApi.field(tournamentId!),
    enabled: !!tournamentId,
  });
}

export function useAllGolfers() {
  return useQuery({
    queryKey: ["allGolfers"],
    queryFn: () => golfersApi.list(),
    staleTime: 5 * 60 * 1000, // 5 min — golfer roster changes slowly
  });
}

export function useMyPicks(leagueId: string) {
  return useQuery({
    queryKey: ["myPicks", leagueId],
    queryFn: () => picksApi.mine(leagueId),
    enabled: !!leagueId,
  });
}

export function useAllPicks(leagueId: string, userId?: string) {
  return useQuery({
    queryKey: ["allPicks", leagueId, userId ?? "all"],
    queryFn: () => picksApi.all(leagueId, userId),
    enabled: !!leagueId,
  });
}

export function useMemberPickContext(
  leagueId: string,
  userId: string | null,
  tournamentId: string | null,
) {
  return useQuery({
    queryKey: ["memberPickContext", leagueId, userId, tournamentId],
    queryFn: () => picksApi.memberContext(leagueId, userId!, tournamentId!),
    enabled: !!leagueId && !!userId && !!tournamentId,
  });
}

export function useTournamentPicksSummary(leagueId: string, tournamentId: string | null) {
  return useQuery({
    queryKey: ["tournamentPicksSummary", leagueId, tournamentId],
    queryFn: () => picksApi.tournamentSummary(leagueId, tournamentId!),
    enabled: !!leagueId && !!tournamentId,
    retry: false, // don't retry the 403 "scheduled" response
    staleTime: 60 * 1000, // 1 min — pick summaries change only when picks are submitted
  });
}

export function useStandings(leagueId: string) {
  return useQuery({
    queryKey: ["standings", leagueId],
    queryFn: () => standingsApi.get(leagueId),
    enabled: !!leagueId,
    staleTime: 5 * 60 * 1000, // 5 min — standings only change when picks score (nightly)
  });
}

export function useSubmitPick(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tournament_id, golfer_id }: { tournament_id: string; golfer_id: string }) =>
      picksApi.submit(leagueId, tournament_id, golfer_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["myPicks", leagueId] });
      qc.invalidateQueries({ queryKey: ["standings", leagueId] });
    },
  });
}

export function useChangePick(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pickId, golfer_id }: { pickId: string; golfer_id: string }) =>
      picksApi.change(leagueId, pickId, golfer_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["myPicks", leagueId] }),
  });
}

export function useTournamentLeaderboard(tournamentId: string | undefined) {
  return useQuery({
    queryKey: ["tournamentLeaderboard", tournamentId],
    queryFn: () => tournamentsApi.leaderboard(tournamentId!),
    enabled: !!tournamentId,
    // No self-polling — useTournamentSyncStatus drives invalidation instead,
    // ensuring the leaderboard only refreshes after a full sync completes.
  });
}

/**
 * Polls the lightweight sync-status endpoint every 30 s while a tournament is
 * in_progress.  When last_synced_at changes (new sync just completed), it
 * invalidates the full leaderboard query so the table shows fresh data without
 * ever catching the DB mid-sync.
 */
export function useTournamentSyncStatus(tournamentId: string | undefined) {
  const qc = useQueryClient();
  const prevSyncedAt = useRef<string | null | undefined>(undefined);

  const query = useQuery({
    queryKey: ["tournamentSyncStatus", tournamentId],
    queryFn: () => tournamentsApi.syncStatus(tournamentId!),
    enabled: !!tournamentId,
    refetchInterval: (q) =>
      q.state.data?.tournament_status === "in_progress" ? 30_000 : false,
  });

  useEffect(() => {
    const newSyncedAt = query.data?.last_synced_at;
    // Skip the first render (prevSyncedAt.current is undefined sentinel).
    if (prevSyncedAt.current === undefined) {
      prevSyncedAt.current = newSyncedAt ?? null;
      return;
    }
    if (newSyncedAt !== prevSyncedAt.current) {
      prevSyncedAt.current = newSyncedAt ?? null;
      qc.invalidateQueries({ queryKey: ["tournamentLeaderboard", tournamentId] });
    }
  }, [query.data?.last_synced_at, tournamentId, qc]);

  return query;
}

export function useGolferScorecard(
  tournamentId: string | undefined,
  golferId: string | null,
  round: number,
  isLive = false,
) {
  return useQuery({
    queryKey: ["golferScorecard", tournamentId, golferId, round],
    queryFn: () => tournamentsApi.scorecard(tournamentId!, golferId!, round),
    enabled: !!tournamentId && !!golferId,
    // Keep open scorecards in sync during a live tournament.
    refetchInterval: isLive ? 60_000 : false,
  });
}

export function useAdminOverridePick(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { user_id: string; tournament_id: string; golfer_id: string | null }) =>
      picksApi.adminOverride(leagueId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["allPicks", leagueId] });
      qc.invalidateQueries({ queryKey: ["memberPickContext", leagueId] });
      qc.invalidateQueries({ queryKey: ["myPicks", leagueId] });
      qc.invalidateQueries({ queryKey: ["standings", leagueId] });
      qc.invalidateQueries({ queryKey: ["tournamentPicksSummary", leagueId] });
    },
  });
}
