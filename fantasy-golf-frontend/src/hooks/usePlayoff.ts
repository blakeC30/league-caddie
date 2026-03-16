/**
 * usePlayoff — React Query hooks for playoff endpoints.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BracketOut,
  MyPlayoffPodOut,
  PlayoffConfigCreate,
  PlayoffConfigUpdate,
  PlayoffDraftStatus,
  PlayoffPickOut,
  PlayoffPodOut,
  PlayoffPreference,
  PlayoffRoundOut,
  PlayoffConfigOut,
  PlayoffTournamentPickOut,
  playoffApi,
} from "../api/endpoints";

// ── Config ──────────────────────────────────────────────────────────────────

export function usePlayoffConfig(leagueId: string) {
  return useQuery({
    queryKey: ["playoffConfig", leagueId],
    queryFn: () => playoffApi.getConfig(leagueId),
    enabled: !!leagueId,
    retry: false, // 404 = no config yet; don't retry
  });
}

export function useCreatePlayoffConfig(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffConfigOut, Error, PlayoffConfigCreate>({
    mutationFn: (data: PlayoffConfigCreate) => playoffApi.createConfig(leagueId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffConfig", leagueId] }),
  });
}

export function useUpdatePlayoffConfig(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffConfigOut, Error, PlayoffConfigUpdate>({
    mutationFn: (data: PlayoffConfigUpdate) => playoffApi.updateConfig(leagueId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffConfig", leagueId] }),
  });
}

// ── Bracket ──────────────────────────────────────────────────────────────────

export function useBracket(leagueId: string) {
  return useQuery({
    queryKey: ["playoffBracket", leagueId],
    queryFn: () => playoffApi.getBracket(leagueId),
    enabled: !!leagueId,
    retry: false, // 404 = no bracket yet
    staleTime: 30_000,         // 30 sec — draft activity updates the bracket
    refetchInterval: 60_000,   // auto-refresh while draft is active
  });
}

// ── Round management ─────────────────────────────────────────────────────────

export function useOpenRoundDraft(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffRoundOut, Error, number>({
    mutationFn: (roundId: number) => playoffApi.openDraft(leagueId, roundId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useScoreRound(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffRoundOut, Error, number>({
    mutationFn: (roundId: number) => playoffApi.scoreRound(leagueId, roundId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useAdvanceBracket(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<BracketOut, Error, number>({
    mutationFn: (roundId: number) => playoffApi.advance(leagueId, roundId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useResolveRoundDraft(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffRoundOut, Error, number>({
    mutationFn: (roundId: number) => playoffApi.resolveDraft(leagueId, roundId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] });
    },
  });
}

// ── Draft preferences ─────────────────────────────────────────────────────────

export function usePodDetail(leagueId: string, podId: number | null) {
  return useQuery({
    queryKey: ["playoffPod", leagueId, podId],
    queryFn: () => playoffApi.getPod(leagueId, podId!),
    enabled: !!leagueId && podId !== null,
  });
}

export function usePodDraftStatus(leagueId: string, podId: number | null) {
  return useQuery({
    queryKey: ["playoffDraftStatus", leagueId, podId],
    queryFn: () => playoffApi.getDraftStatus(leagueId, podId!),
    enabled: !!leagueId && podId !== null,
    staleTime: 30_000,
    refetchInterval: (query) => {
      // Poll every 30 sec while draft window is open
      const data = query.state.data as PlayoffDraftStatus | undefined;
      return data?.round_status === "drafting" ? 30_000 : false;
    },
  });
}

export function useMyPreferences(leagueId: string, podId: number | null) {
  return useQuery({
    queryKey: ["playoffPreferences", leagueId, podId],
    queryFn: () => playoffApi.getPreferences(leagueId, podId!),
    enabled: !!leagueId && podId !== null,
  });
}

export function useSubmitPreferences(leagueId: string, podId: number) {
  const qc = useQueryClient();
  return useMutation<PlayoffPreference[], Error, string[]>({
    mutationFn: (golfer_ids: string[]) => playoffApi.submitPreferences(leagueId, podId, golfer_ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playoffPreferences", leagueId, podId] });
      qc.invalidateQueries({ queryKey: ["playoffDraftStatus", leagueId, podId] });
    },
  });
}

// ── Admin override ────────────────────────────────────────────────────────────

export function useOverridePlayoffResult(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffPodOut, Error, { pod_id: number; winner_user_id: string }>({
    mutationFn: (data: { pod_id: number; winner_user_id: string }) =>
      playoffApi.overrideResult(leagueId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useRevisePlayoffPick(leagueId: string) {
  const qc = useQueryClient();
  return useMutation<PlayoffPickOut, Error, { pickId: string; golferId: string }>({
    mutationFn: ({ pickId, golferId }) => playoffApi.revisePick(leagueId, pickId, golferId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playoffBracket", leagueId] }),
  });
}

export function useMyPlayoffPod(leagueId: string) {
  return useQuery({
    queryKey: ["myPlayoffPod", leagueId],
    queryFn: () => playoffApi.getMyPod(leagueId),
    enabled: !!leagueId,
    retry: false,
    staleTime: 30_000,
    refetchInterval: (q) => {
      const data = q.state.data as MyPlayoffPodOut | undefined;
      return data?.round_status === "drafting" ? 30_000 : false;
    },
  });
}

export function useMyPlayoffPicks(leagueId: string) {
  return useQuery({
    queryKey: ["myPlayoffPicks", leagueId],
    queryFn: () => playoffApi.getMyPicks(leagueId),
    enabled: !!leagueId,
    retry: false,
    staleTime: 60_000,
  });
}

// Re-export types so pages don't need to import from two places
export type {
  BracketOut,
  MyPlayoffPodOut,
  PlayoffConfigCreate,
  PlayoffConfigUpdate,
  PlayoffConfigOut,
  PlayoffDraftStatus,
  PlayoffPickOut,
  PlayoffPickSummary,
  PlayoffPodMemberDraft,
  PlayoffPodMemberOut,
  PlayoffPodOut,
  PlayoffPreference,
  PlayoffRoundOut,
  PlayoffTournamentPickOut,
} from "../api/endpoints";
