/**
 * Typed API functions — one function per backend endpoint.
 *
 * All functions return the unwrapped response data (not the axios response).
 * TypeScript types mirror the backend Pydantic schemas exactly.
 */

import { api } from "./client";
import type { User, TokenResponse } from "../types";

// Re-export so existing imports from this module continue to work.
export type { User, TokenResponse };

// ---------------------------------------------------------------------------
// Types (mirror backend schemas)
// ---------------------------------------------------------------------------

export interface League {
  id: string;
  name: string;
  no_pick_penalty: number;
  invite_code: string;
  is_public: boolean;
  accepting_requests: boolean;
  created_at: string;
}

export interface LeagueMember {
  user_id: string;
  league_id: string;
  role: "manager" | "member";
  status: "pending" | "approved";
  joined_at: string;
  user: User;
}

export interface Tournament {
  id: string;
  pga_tour_id: string;
  name: string;
  start_date: string; // "YYYY-MM-DD"
  end_date: string;
  multiplier: number;
  purse_usd: number | null;
  status: "scheduled" | "in_progress" | "completed";
  is_team_event: boolean;
}

// Returned by GET /leagues/{id}/tournaments — includes the league's effective multiplier.
export interface LeagueTournamentOut extends Tournament {
  effective_multiplier: number;
  // true when tournament is in_progress AND every Round 1 tee time has passed — pick window permanently closed.
  all_r1_teed_off: boolean;
  // true when this tournament is assigned to a PlayoffRound for this league.
  is_playoff_round: boolean;
}

export interface Golfer {
  id: string;
  pga_tour_id: string;
  name: string;
  world_ranking: number | null;
  country: string | null;
}

// Returned by GET /tournaments/{id}/field — extends Golfer with the golfer's
// Round 1 tee_time from their TournamentEntry row. tee_time is null when tee
// times haven't been set yet (e.g. early in the week). When the tournament is
// in_progress, the frontend uses this to grey out golfers who have already teed
// off, preventing the user from selecting an ineligible golfer before submitting.
export interface GolferInField extends Golfer {
  tee_time: string | null;
}

export interface Pick {
  id: string;
  user_id?: string; // present on all-picks responses; absent on mine-only responses
  tournament_id: string;
  golfer_id: string;
  points_earned: number | null;
  earnings_usd: number | null; // raw golfer earnings before multiplier
  submitted_at: string;
  is_locked: boolean; // true once the golfer's Round 1 tee time has passed
  position: number | null; // golfer's current or final position; null if not started
  is_tied: boolean; // true when multiple golfers share this position
  golfer_status: string | null; // e.g. "CUT", "WD", "MDF", "DQ"; null if active/finished normally
  golfer: Golfer;
  tournament: Tournament;
}

export interface StandingsRow {
  rank: number;
  is_tied: boolean; // true when two or more players share this rank
  user_id: string;
  display_name: string;
  total_points: number;
  pick_count: number;
  missed_count: number;
}

export interface LeagueJoinPreview {
  league_id: string;
  name: string;
  member_count: number;
  /** null = no relationship, "pending" = awaiting approval, "approved" = already a member */
  user_status: "pending" | "approved" | null;
  /** false when the manager has paused new join requests */
  accepting_requests: boolean;
}

export interface LeagueRequestOut {
  league_id: string;
  league_name: string;
  requested_at: string;
}

export interface StandingsResponse {
  league_id: string;
  season_year: number;
  rows: StandingsRow[];
}

export interface PickerInfo {
  user_id: string;
  display_name: string;
  points_earned: number | null;
}

export interface GolferPickGroup {
  golfer_id: string;
  golfer_name: string;
  pick_count: number;
  pickers: PickerInfo[];
  earnings_usd: number | null;
}

// ---------------------------------------------------------------------------
// Leaderboard & scorecard types
// ---------------------------------------------------------------------------

export interface RoundSummary {
  round_number: number;
  score: number | null;
  score_to_par: number | null;
  position: string | null;
  tee_time: string | null;
  is_playoff: boolean;
  thru: number | null;
  started_on_back: boolean | null;
}

export interface LeaderboardEntry {
  golfer_id: string;
  golfer_name: string;
  golfer_pga_tour_id: string;
  golfer_country: string | null;
  finish_position: number | null;
  is_tied: boolean;
  made_cut: boolean;
  status: string | null;
  earnings_usd: number | null;
  total_score_to_par: number | null;
  rounds: RoundSummary[];
  partner_name: string | null;
  partner_golfer_id: string | null;
  partner_golfer_pga_tour_id: string | null;
}

export interface Leaderboard {
  tournament_id: string;
  tournament_name: string;
  tournament_status: string;
  is_team_event: boolean;
  last_synced_at: string | null;
  entries: LeaderboardEntry[];
}

export interface TournamentSyncStatus {
  tournament_id: string;
  tournament_status: string;
  last_synced_at: string | null;
}

export type HoleResult =
  | "eagle"
  | "birdie"
  | "par"
  | "bogey"
  | "double_bogey"
  | "triple_plus";

export interface HoleScore {
  hole: number;
  par: number | null;
  score: number | null;
  score_to_par: number | null;
  result: HoleResult | null;
}

export interface Scorecard {
  golfer_id: string;
  round_number: number;
  holes: HoleScore[];
  total_score: number | null;
  total_score_to_par: number | null;
}

export interface TournamentPicksSummary {
  tournament_status: "scheduled" | "in_progress" | "completed";
  member_count: number;
  picks_by_golfer: GolferPickGroup[]; // sorted by pick_count desc
  no_pick_members: { user_id: string; display_name: string }[];
  winner: { golfer_name: string; pick_count: number } | null;
}

// ---------------------------------------------------------------------------
// Playoff my-pod / my-picks types (new endpoints)
// ---------------------------------------------------------------------------

export interface MyPlayoffPodOut {
  is_playoff_week: boolean;
  is_in_playoffs: boolean;
  active_pod_id: number | null;
  active_round_number: number | null;
  tournament_id: string | null;
  round_status: string | null; // "drafting" | "locked" | null
  has_submitted: boolean;
  submitted_count: number;
  picks_per_round: number | null;
  required_preference_count: number | null;
  deadline: string | null;
}

export interface PlayoffPickSummary {
  golfer_name: string;
  points_earned: number | null;
}

export interface PlayoffTournamentPickOut {
  tournament_id: string;
  round_number: number;
  status: string;
  picks: PlayoffPickSummary[];
  total_points: number | null;
}

// ---------------------------------------------------------------------------
// Stripe / billing types
// ---------------------------------------------------------------------------

export interface PricingTier {
  tier: string;          // "starter" | "standard" | "pro" | "elite"
  member_limit: number;
  amount_cents: number;
}

export interface LeaguePurchaseStatus {
  league_id: string;
  season_year: number;
  tier: string | null;
  member_limit: number | null;
  amount_cents: number | null;
  paid_at: string | null;
}

export interface LeaguePurchaseEvent {
  id: string;
  tier: string;
  amount_cents: number;
  event_type: string;  // "purchase" | "upgrade"
  paid_at: string;
}

// ---------------------------------------------------------------------------
// Platform config
// ---------------------------------------------------------------------------

export interface AppConfig {
  league_creation_restricted: boolean;
}

export const configApi = {
  get: () => api.get<AppConfig>("/config").then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const authApi = {
  register: (email: string, password: string, display_name: string) =>
    api.post<TokenResponse>("/auth/register", { email, password, display_name }).then((r) => r.data),

  login: (email: string, password: string) =>
    api.post<TokenResponse>("/auth/login", { email, password }).then((r) => r.data),

  google: (id_token: string) =>
    api.post<TokenResponse>("/auth/google", { id_token }).then((r) => r.data),

  refresh: () =>
    api.post<TokenResponse>("/auth/refresh").then((r) => r.data),

  logout: () =>
    api.post("/auth/logout").then((r) => r.data),

  forgotPassword: (email: string) =>
    api.post<{ detail: string }>("/auth/forgot-password", { email }).then((r) => r.data),

  resetPassword: (token: string, new_password: string) =>
    api.post<TokenResponse>("/auth/reset-password", { token, new_password }).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export const usersApi = {
  me: () =>
    api.get<User>("/users/me").then((r) => r.data),

  updateMe: (fields: { display_name?: string; pick_reminders_enabled?: boolean }) =>
    api.patch<User>("/users/me", fields).then((r) => r.data),

  myLeagues: () =>
    api.get<League[]>("/users/me/leagues").then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Leagues
// ---------------------------------------------------------------------------

export const leaguesApi = {
  create: (name: string, no_pick_penalty?: number) =>
    api.post<League>("/leagues", { name, no_pick_penalty }).then((r) => r.data),

  get: (leagueId: string) =>
    api.get<League>(`/leagues/${leagueId}`).then((r) => r.data),

  update: (leagueId: string, data: { name?: string; no_pick_penalty?: number; accepting_requests?: boolean }) =>
    api.patch<League>(`/leagues/${leagueId}`, data).then((r) => r.data),

  leave: (leagueId: string) =>
    api.delete(`/leagues/${leagueId}/members/me`).then((r) => r.data),

  delete: (leagueId: string) =>
    api.delete(`/leagues/${leagueId}`).then((r) => r.data),

  joinPreview: (inviteCode: string) =>
    api.get<LeagueJoinPreview>(`/leagues/join/${inviteCode}`).then((r) => r.data),

  joinByCode: (inviteCode: string) =>
    api.post<LeagueMember>(`/leagues/join/${inviteCode}`).then((r) => r.data),

  cancelMyRequest: (leagueId: string) =>
    api.delete(`/leagues/${leagueId}/requests/me`).then((r) => r.data),

  myRequests: () =>
    api.get<LeagueRequestOut[]>("/leagues/my-requests").then((r) => r.data),

  members: (leagueId: string) =>
    api.get<LeagueMember[]>(`/leagues/${leagueId}/members`).then((r) => r.data),

  updateMemberRole: (leagueId: string, userId: string, role: "manager" | "member") =>
    api.patch<LeagueMember>(`/leagues/${leagueId}/members/${userId}/role`, { role }).then((r) => r.data),

  removeMember: (leagueId: string, userId: string) =>
    api.delete(`/leagues/${leagueId}/members/${userId}`).then((r) => r.data),

  pendingRequests: (leagueId: string) =>
    api.get<LeagueMember[]>(`/leagues/${leagueId}/requests`).then((r) => r.data),

  approveRequest: (leagueId: string, userId: string) =>
    api.post<LeagueMember>(`/leagues/${leagueId}/requests/${userId}/approve`).then((r) => r.data),

  denyRequest: (leagueId: string, userId: string) =>
    api.delete(`/leagues/${leagueId}/requests/${userId}`).then((r) => r.data),

  getTournaments: (leagueId: string) =>
    api.get<LeagueTournamentOut[]>(`/leagues/${leagueId}/tournaments`).then((r) => r.data),

  updateTournaments: (leagueId: string, tournaments: { tournament_id: string; multiplier: number | null }[]) =>
    api.put<LeagueTournamentOut[]>(`/leagues/${leagueId}/tournaments`, { tournaments }).then((r) => r.data),

  getPurchase: (leagueId: string) =>
    api.get<LeaguePurchaseStatus | null>(`/leagues/${leagueId}/purchase`).then((r) => r.data),

  getPurchaseEvents: (leagueId: string) =>
    api.get<LeaguePurchaseEvent[]>(`/leagues/${leagueId}/purchase/events`).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Tournaments
// ---------------------------------------------------------------------------

export const tournamentsApi = {
  list: (status?: Tournament["status"]) =>
    api.get<Tournament[]>("/tournaments", { params: status ? { status } : {} }).then((r) => r.data),

  get: (id: string) =>
    api.get<Tournament>(`/tournaments/${id}`).then((r) => r.data),

  field: (id: string) =>
    api.get<GolferInField[]>(`/tournaments/${id}/field`).then((r) => r.data),

  leaderboard: (id: string) =>
    api.get<Leaderboard>(`/tournaments/${id}/leaderboard`).then((r) => r.data),

  syncStatus: (id: string) =>
    api.get<TournamentSyncStatus>(`/tournaments/${id}/sync-status`).then((r) => r.data),

  scorecard: (tournamentId: string, golferId: string, round: number) =>
    api
      .get<Scorecard>(`/tournaments/${tournamentId}/golfers/${golferId}/scorecard`, {
        params: { round },
      })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Golfers
// ---------------------------------------------------------------------------

export const golfersApi = {
  list: (search?: string) =>
    api.get<Golfer[]>("/golfers", { params: search ? { search } : {} }).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Picks
// ---------------------------------------------------------------------------

export const picksApi = {
  submit: (leagueId: string, tournament_id: string, golfer_id: string) =>
    api.post<Pick>(`/leagues/${leagueId}/picks`, { tournament_id, golfer_id }).then((r) => r.data),

  change: (leagueId: string, pickId: string, golfer_id: string) =>
    api.patch<Pick>(`/leagues/${leagueId}/picks/${pickId}`, { golfer_id }).then((r) => r.data),

  mine: (leagueId: string) =>
    api.get<Pick[]>(`/leagues/${leagueId}/picks/mine`).then((r) => r.data),

  all: (leagueId: string) =>
    api.get<Pick[]>(`/leagues/${leagueId}/picks`).then((r) => r.data),

  tournamentSummary: (leagueId: string, tournamentId: string) =>
    api
      .get<TournamentPicksSummary>(`/leagues/${leagueId}/picks/tournament/${tournamentId}`)
      .then((r) => r.data),

  // Manager-only: create, replace, or delete any member's pick for a tournament.
  // golfer_id = null removes the pick entirely.
  adminOverride: (leagueId: string, data: { user_id: string; tournament_id: string; golfer_id: string | null }) =>
    api.put<Pick | null>(`/leagues/${leagueId}/picks/admin-override`, data).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Standings
// ---------------------------------------------------------------------------

export const standingsApi = {
  get: (leagueId: string) =>
    api.get<StandingsResponse>(`/leagues/${leagueId}/standings`).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Stripe
// ---------------------------------------------------------------------------

export const stripeApi = {
  getPricing: () =>
    api.get<PricingTier[]>("/stripe/pricing").then((r) => r.data),

  createCheckoutSession: (league_id: string, tier: string, upgrade = false) =>
    api
      .post<{ url: string }>("/stripe/create-checkout-session", { league_id, tier, upgrade })
      .then((r) => r.data),

  createLeagueCheckout: (name: string, no_pick_penalty: number, tier: string) =>
    api
      .post<{ url: string }>("/stripe/create-league-checkout", { name, no_pick_penalty, tier })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Playoff types (mirror app/schemas/playoff.py)
// ---------------------------------------------------------------------------

export interface PlayoffConfigOut {
  id: string;
  league_id: string;
  season_id: number;
  is_enabled: boolean;
  playoff_size: number;
  draft_style: "snake" | "linear" | "top_seed_priority";
  picks_per_round: number[];
  status: "pending" | "active" | "completed";
  seeded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlayoffConfigCreate {
  playoff_size?: number;
  draft_style?: "snake" | "linear" | "top_seed_priority";
  picks_per_round?: number[];
}

export type PlayoffConfigUpdate = Partial<PlayoffConfigCreate>;

export interface PlayoffPodMemberOut {
  id: number;
  user_id: string;
  display_name: string;
  seed: number;
  draft_position: number;
  total_points: number | null;
  is_eliminated: boolean;
}

export interface PlayoffPickOut {
  id: string;
  pod_member_id: number; // integer FK to playoff_pod_members.id
  golfer_id: string;
  golfer_name: string;
  draft_slot: number;
  points_earned: number | null;
  created_at: string;
}

export interface PlayoffPodOut {
  id: number;
  bracket_position: number;
  status: "pending" | "drafting" | "scoring" | "completed";
  winner_user_id: string | null;
  members: PlayoffPodMemberOut[];
  picks: PlayoffPickOut[];
  active_draft_slot: number | null;
  is_picks_visible: boolean;
}

export interface PlayoffRoundOut {
  id: number;
  round_number: number;
  tournament_id: string | null;
  tournament_name: string | null;
  tournament_status: string | null;
  draft_opens_at: string | null;
  draft_resolved_at: string | null;
  status: "pending" | "drafting" | "locked" | "scoring" | "completed";
  pods: PlayoffPodOut[];
}

export interface BracketOut {
  playoff_config: PlayoffConfigOut;
  rounds: PlayoffRoundOut[];
}

export interface PlayoffRoundAssign {
  tournament_id: string;
  draft_opens_at?: string; // ISO datetime; optional — backend defaults to null
}

export interface PlayoffPreference {
  golfer_id: string;
  golfer_name: string;
  rank: number;
}

export interface PlayoffPodMemberDraft {
  user_id: string;
  display_name: string;
  seed: number;
  draft_position: number;
  has_submitted: boolean;
  preference_count: number;
}

export interface PlayoffDraftStatus {
  pod_id: number; // integer ID
  round_status: string;
  deadline: string;
  required_preference_count: number | null; // pod_size * picks_per_round; null until seeded
  members: PlayoffPodMemberDraft[];
  resolved_picks: PlayoffPickOut[];
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export interface AdminTierBreakdown {
  tier: string;
  count: number;
}

export interface AdminStats {
  total_users: number;
  new_users_30d: number;
  total_leagues: number;
  paid_leagues_this_year: number;
  total_approved_memberships: number;
  leagues_by_tier: AdminTierBreakdown[];
  total_picks: number;
  picks_last_7d: number;
  tournaments_scheduled: number;
  tournaments_in_progress: number;
  tournaments_completed: number;
  leagues_with_playoffs: number;
  leagues_accepting_requests: number;
  avg_members_per_league: number;
  deleted_leagues_total: number;
  open_webhook_failures: number;
}

export const adminApi = {
  getStats: () =>
    api.get<AdminStats>("/admin/stats").then((r) => r.data),

  fullSync: (year?: number, force = false) =>
    api.post("/admin/sync", null, { params: { ...(year ? { year } : {}), ...(force ? { force: true } : {}) }, timeout: 300_000 }).then((r) => r.data),

  syncTournament: (pgaTourId: string) =>
    api.post(`/admin/sync/${pgaTourId}`, null, { timeout: 300_000 }).then((r) => r.data),

  syncTournamentForce: (pgaTourId: string) =>
    api.post(`/admin/sync/${pgaTourId}`, null, { params: { force: true }, timeout: 300_000 }).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Playoff
// ---------------------------------------------------------------------------

export const playoffApi = {
  getConfig: (leagueId: string) =>
    api.get<PlayoffConfigOut>(`/leagues/${leagueId}/playoff/config`).then((r) => r.data),

  createConfig: (leagueId: string, data: PlayoffConfigCreate) =>
    api.post<PlayoffConfigOut>(`/leagues/${leagueId}/playoff/config`, data).then((r) => r.data),

  updateConfig: (leagueId: string, data: PlayoffConfigUpdate) =>
    api.patch<PlayoffConfigOut>(`/leagues/${leagueId}/playoff/config`, data).then((r) => r.data),



  getBracket: (leagueId: string) =>
    api.get<BracketOut>(`/leagues/${leagueId}/playoff/bracket`).then((r) => r.data),

  openDraft: (leagueId: string, roundId: number) =>
    api.post<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/open`).then((r) => r.data),

  resolveDraft: (leagueId: string, roundId: number) =>
    api.post<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/resolve`).then((r) => r.data),

  scoreRound: (leagueId: string, roundId: number) =>
    api.post<PlayoffRoundOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/score`).then((r) => r.data),

  advance: (leagueId: string, roundId: number) =>
    api.post<BracketOut>(`/leagues/${leagueId}/playoff/rounds/${roundId}/advance`).then((r) => r.data),

  getPod: (leagueId: string, podId: number) =>
    api.get<PlayoffPodOut>(`/leagues/${leagueId}/playoff/pods/${podId}`).then((r) => r.data),

  getDraftStatus: (leagueId: string, podId: number) =>
    api.get<PlayoffDraftStatus>(`/leagues/${leagueId}/playoff/pods/${podId}/draft`).then((r) => r.data),

  getPreferences: (leagueId: string, podId: number) =>
    api.get<PlayoffPreference[]>(`/leagues/${leagueId}/playoff/pods/${podId}/preferences`).then((r) => r.data),

  submitPreferences: (leagueId: string, podId: number, golfer_ids: string[]) =>
    api.put<PlayoffPreference[]>(`/leagues/${leagueId}/playoff/pods/${podId}/preferences`, { golfer_ids }).then((r) => r.data),

  overrideResult: (leagueId: string, data: { pod_id: number; winner_user_id: string }) =>
    api.post<{ detail: string }>(`/leagues/${leagueId}/playoff/override`, data).then((r) => r.data),

  revisePick: (leagueId: string, pickId: string, golferId: string) =>
    api.patch<PlayoffPickOut>(`/leagues/${leagueId}/playoff/picks/${pickId}`, { golfer_id: golferId }).then((r) => r.data),

  adminCreatePick: (leagueId: string, podId: number, userId: string, draftSlot: number, golferId: string) =>
    api.post<PlayoffPickOut>(`/leagues/${leagueId}/playoff/pods/${podId}/admin-pick`, {
      user_id: userId,
      draft_slot: draftSlot,
      golfer_id: golferId,
    }).then((r) => r.data),

  getMyPod: (leagueId: string) =>
    api.get<MyPlayoffPodOut>(`/leagues/${leagueId}/playoff/my-pod`).then((r) => r.data),

  getMyPicks: (leagueId: string) =>
    api.get<PlayoffTournamentPickOut[]>(`/leagues/${leagueId}/playoff/my-picks`).then((r) => r.data),
};
