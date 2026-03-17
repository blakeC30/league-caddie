/**
 * useLeague — React Query hooks for league data.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { leaguesApi, usersApi } from "../api/endpoints";

export function useMyLeagues() {
  return useQuery({
    queryKey: ["myLeagues"],
    queryFn: usersApi.myLeagues,
  });
}

export function useLeague(leagueId: string) {
  return useQuery({
    queryKey: ["league", leagueId],
    queryFn: () => leaguesApi.get(leagueId),
    enabled: !!leagueId,
  });
}

export function useUpdateLeague(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name?: string; no_pick_penalty?: number; accepting_requests?: boolean }) =>
      leaguesApi.update(leagueId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["league", leagueId] });
      qc.invalidateQueries({ queryKey: ["myLeagues"] });
    },
  });
}

export function useLeagueMembers(leagueId: string) {
  return useQuery({
    queryKey: ["leagueMembers", leagueId],
    queryFn: () => leaguesApi.members(leagueId),
    enabled: !!leagueId,
  });
}

export function useCreateLeague() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      no_pick_penalty,
    }: {
      name: string;
      no_pick_penalty?: number;
    }) => leaguesApi.create(name, no_pick_penalty),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["myLeagues"] }),
  });
}

export function useJoinPreview(inviteCode: string) {
  return useQuery({
    queryKey: ["joinPreview", inviteCode],
    queryFn: () => leaguesApi.joinPreview(inviteCode),
    enabled: !!inviteCode,
    retry: false, // Don't retry 404s (invalid invite code)
  });
}

export function useJoinByCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteCode: string) => leaguesApi.joinByCode(inviteCode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["myLeagues"] });
      qc.invalidateQueries({ queryKey: ["myRequests"] });
    },
  });
}

export function useCancelMyRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leagueId: string) => leaguesApi.cancelMyRequest(leagueId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["myRequests"] }),
  });
}

export function useMyRequests() {
  return useQuery({
    queryKey: ["myRequests"],
    queryFn: leaguesApi.myRequests,
  });
}

export function useUpdateMemberRole(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "manager" | "member" }) =>
      leaguesApi.updateMemberRole(leagueId, userId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leagueMembers", leagueId] }),
  });
}

export function useRemoveMember(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => leaguesApi.removeMember(leagueId, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leagueMembers", leagueId] }),
  });
}

export function useLeaveLeague() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leagueId: string) => leaguesApi.leave(leagueId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["myLeagues"] }),
  });
}

export function useDeleteLeague() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leagueId: string) => leaguesApi.delete(leagueId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["myLeagues"] }),
  });
}

export function useLeagueTournaments(leagueId: string) {
  return useQuery({
    queryKey: ["leagueTournaments", leagueId],
    queryFn: () => leaguesApi.getTournaments(leagueId),
    enabled: !!leagueId,
  });
}

export function useUpdateLeagueTournaments(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tournaments: { tournament_id: string; multiplier: number | null }[]) =>
      leaguesApi.updateTournaments(leagueId, tournaments),
    onSuccess: () => {
      // Invalidate everything that derives from points_earned — the backend
      // re-scores all completed picks when the schedule/multipliers change.
      qc.invalidateQueries({ queryKey: ["leagueTournaments", leagueId] });
      qc.invalidateQueries({ queryKey: ["standings", leagueId] });
      qc.invalidateQueries({ queryKey: ["myPicks", leagueId] });
      qc.invalidateQueries({ queryKey: ["allPicks", leagueId] });
      qc.invalidateQueries({ queryKey: ["tournamentPicksSummary", leagueId] });
      qc.invalidateQueries({ queryKey: ["myLeagues"] });
    },
  });
}

export function usePendingRequests(leagueId: string) {
  return useQuery({
    queryKey: ["pendingRequests", leagueId],
    queryFn: () => leaguesApi.pendingRequests(leagueId),
    enabled: !!leagueId,
  });
}

export function useApproveRequest(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => leaguesApi.approveRequest(leagueId, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pendingRequests", leagueId] });
      qc.invalidateQueries({ queryKey: ["leagueMembers", leagueId] });
    },
  });
}

export function useDenyRequest(leagueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => leaguesApi.denyRequest(leagueId, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pendingRequests", leagueId] }),
  });
}
