/**
 * ManageLeague — league manager panel.
 *
 * Members management (role changes, removal), join request approval,
 * tournament schedule selection, and league settings editing.
 * Non-managers are redirected to the league dashboard.
 */

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useDropdownDirection } from "../hooks/useDropdownDirection";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import {
  useApproveRequest,
  useDeleteLeague,
  useDenyRequest,
  useLeague,
  useLeagueMembers,
  useLeagueTournaments,
  usePendingRequests,
  useRemoveMember,
  useUpdateLeague,
  useUpdateLeagueTournaments,
  useUpdateMemberRole,
} from "../hooks/useLeague";
import { useAdminOverridePick, useAllGolfers, useAllPicks, useTournamentField, useTournaments } from "../hooks/usePick";
import {
  useBracket,
  useCreatePlayoffConfig,
  usePlayoffConfig,
  useRevisePlayoffPick,
  useUpdatePlayoffConfig,
} from "../hooks/usePlayoff";
import { fmtTournamentName, isoWeekKey } from "../utils";
import { useAuthStore } from "../store/authStore";
import { Spinner } from "../components/Spinner";

// ---------------------------------------------------------------------------
// Custom dropdown — matches the Leaderboard tournament picker style
// ---------------------------------------------------------------------------

interface DropdownOption {
  value: string;
  label: string;
  badge?: string;
  badgeColor?: string;
}

function DropdownSelect({
  value,
  onChange,
  placeholder,
  options,
  disabled = false,
}: {
  value: string;
  onChange: (val: string) => void;
  placeholder: string;
  options: DropdownOption[];
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropDir = useDropdownDirection(ref, open);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const selected = options.find((o) => o.value === value);
  const filtered = search
    ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase()))
    : options;

  return (
    <div
      ref={ref}
      className="relative"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          setOpen(false);
          setSearch("");
          triggerRef.current?.focus();
        }
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        onClick={() => { if (!disabled) { setOpen((o) => !o); setSearch(""); } }}
        className={`w-full flex items-center gap-2 text-sm border rounded-lg px-3 py-1.5 bg-white text-left transition-colors focus:outline-none focus:ring-2 focus:ring-green-700 ${
          disabled
            ? "border-gray-200 text-gray-400 cursor-not-allowed opacity-60"
            : "border-gray-300 text-gray-700 hover:border-green-500 cursor-pointer"
        }`}
      >
        <span className="flex-1 truncate">
          {selected ? selected.label : <span className="text-gray-400">{placeholder}</span>}
        </span>
        <svg
          className={`h-4 w-4 text-gray-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && !disabled && (
        <div className={`absolute left-0 right-0 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-20 ${dropDir === "up" ? "bottom-full mb-1" : "top-full mt-1"}`}>
          {/* Search input — filters the list, value is never submitted directly */}
          <div className="px-3 py-2 border-b border-gray-100">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="w-full text-sm outline-none placeholder-gray-400 bg-transparent"
            />
          </div>
          <div className="max-h-56 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-4 py-3 text-sm text-gray-400">No results.</p>
            ) : (
              filtered.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => { onChange(opt.value); setOpen(false); setSearch(""); }}
                  className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between gap-3 transition-colors ${
                    opt.value === value ? "bg-green-50 text-green-900" : "hover:bg-gray-50 text-gray-700"
                  }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {opt.badge && (
                    <span className={`text-xs shrink-0 font-medium px-2 py-0.5 rounded-full ${opt.badgeColor ?? "bg-gray-100 text-gray-500"}`}>
                      {opt.badge}
                    </span>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small icon helpers
// ---------------------------------------------------------------------------

function SectionIcon({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
      {children}
    </div>
  );
}

export function ManageLeague() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const currentUser = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  const { data: league } = useLeague(leagueId!);
  const { data: members, isLoading } = useLeagueMembers(leagueId!);
  const updateRole = useUpdateMemberRole(leagueId!);
  const removeMember = useRemoveMember(leagueId!);

  const { data: pendingRequests } = usePendingRequests(leagueId!);
  const approveRequest = useApproveRequest(leagueId!);
  const denyRequest = useDenyRequest(leagueId!);
  const [approveError, setApproveError] = useState("");

  const deleteLeague = useDeleteLeague();
  const [dangerStep, setDangerStep] = useState<"idle" | "editing" | "confirming">("idle");
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  const [linkCopied, setLinkCopied] = useState(false);
  const [membersEditing, setMembersEditing] = useState(false);

  // ---------------------------------------------------------------------------
  // Revise pick state
  // ---------------------------------------------------------------------------
  const [revisePickTournamentId, setRevisePickTournamentId] = useState<string | null>(null);
  const [revisePickMemberId, setRevisePickMemberId] = useState<string | null>(null);
  const [revisePickGolferId, setRevisePickGolferId] = useState<string>("none");
  const [reviseSaved, setReviseSaved] = useState(false);

  function copyInviteLink() {
    if (!league) return;
    const url = `${window.location.origin}/join/${league.invite_code}`;
    navigator.clipboard.writeText(url).then(() => {
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    });
  }

  // ---------------------------------------------------------------------------
  // League settings state — edit-gated, initialized from server data
  // ---------------------------------------------------------------------------

  const updateLeague = useUpdateLeague(leagueId!);
  const [settingsEditing, setSettingsEditing] = useState(false);
  const [settingsName, setSettingsName] = useState("");
  const [settingsNoPick, setSettingsNoPick] = useState("50000");

  useEffect(() => {
    if (league) {
      setSettingsName(league.name);
      setSettingsNoPick(String(Math.abs(league.no_pick_penalty)));
    }
  }, [league]);

  function handleCancelSettings() {
    if (league) {
      setSettingsName(league.name);
      setSettingsNoPick(String(Math.abs(league.no_pick_penalty)));
    }
    setSettingsEditing(false);
  }

  async function handleSaveSettings() {
    await updateLeague.mutateAsync({
      name: settingsName,
      no_pick_penalty: -(parseInt(settingsNoPick, 10) || 0),
    });
    setSettingsEditing(false);
  }

  // ---------------------------------------------------------------------------
  // Tournament schedule state
  // ---------------------------------------------------------------------------

  const { data: allTournaments } = useTournaments();
  const { data: leagueTournaments } = useLeagueTournaments(leagueId!);
  const updateSchedule = useUpdateLeagueTournaments(leagueId!);

  // True when any league tournament is currently in progress. While in progress,
  // picks for the NEXT tournament haven't opened yet, so that tournament is still
  // eligible as a playoff round.
  const hasInProgressTournament = (leagueTournaments ?? []).some(
    (t) => t.status === "in_progress"
  );
  const [scheduleEditing, setScheduleEditing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // Per-tournament multiplier overrides. Key = tournament id, value = multiplier.
  const [multipliers, setMultipliers] = useState<Record<string, number>>({});
  const [scheduleSaved, setScheduleSaved] = useState(false);

  // Initialize checkboxes, multipliers, and playoff flags from the server's saved
  // schedule exactly once per mount. Using a ref flag prevents background React
  // Query refetches from overwriting the user's unsaved changes.
  const initializedRef = useRef(false);
  useEffect(() => {
    if (leagueTournaments && !initializedRef.current) {
      setSelectedIds(new Set(leagueTournaments.map((t) => t.id)));
      setMultipliers(
        Object.fromEntries(leagueTournaments.map((t) => [t.id, t.effective_multiplier]))
      );
      initializedRef.current = true;
    }
  }, [leagueTournaments]);

  // Fast lookup from tournament id → global tournament (for default multiplier).
  const allTournamentsById = Object.fromEntries(
    (allTournaments ?? []).map((t) => [t.id, t])
  );

  function setMultiplierFor(id: string, value: number) {
    setMultipliers((prev) => ({ ...prev, [id]: value }));
    setScheduleSaved(false);
  }

  function handleCancelSchedule() {
    if (leagueTournaments) {
      setSelectedIds(new Set(leagueTournaments.map((t) => t.id)));
      setMultipliers(
        Object.fromEntries(leagueTournaments.map((t) => [t.id, t.effective_multiplier]))
      );
    }
    setScheduleSaved(false);
    setScheduleEditing(false);
  }

  async function handleSaveSchedule() {
    await updateSchedule.mutateAsync(
      [...selectedIds].map((id) => ({
        tournament_id: id,
        multiplier: multipliers[id] ?? allTournamentsById[id]?.multiplier ?? 1.0,
      }))
    );
    setScheduleSaved(true);
    setScheduleEditing(false);
  }

  // ---------------------------------------------------------------------------
  // Revise pick hooks + effects
  // ---------------------------------------------------------------------------
  const { data: allPicks } = useAllPicks(leagueId!);
  const { data: allGolfers, isLoading: isLoadingGolfers } = useAllGolfers();
  const overridePick = useAdminOverridePick(leagueId!);

  // Pre-fill the golfer dropdown when tournament/member selection changes.
  // allPicks is intentionally excluded: it updates after a save (cache invalidation)
  // and we don't want that to reset the saved confirmation message.
  useEffect(() => {
    if (!revisePickTournamentId || !revisePickMemberId) {
      setRevisePickGolferId("none");
      return;
    }
    if (allPicks) {
      const existing = allPicks.find(
        (p) => p.tournament_id === revisePickTournamentId && p.user_id === revisePickMemberId
      );
      setRevisePickGolferId(existing ? existing.golfer_id : "none");
    }
    overridePick.reset();
    setReviseSaved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revisePickTournamentId, revisePickMemberId]);

  // Detect no-repeat violation: member already used this golfer in another tournament.
  const duplicatePickConflict = (() => {
    if (!revisePickMemberId || revisePickGolferId === "none" || !allPicks) return null;
    const conflict = allPicks.find(
      (p) =>
        p.user_id === revisePickMemberId &&
        p.golfer_id === revisePickGolferId &&
        p.tournament_id !== revisePickTournamentId
    );
    if (!conflict) return null;
    const member = members?.find((m) => m.user_id === revisePickMemberId);
    return {
      memberName: member?.user.display_name ?? "This member",
      golferName: conflict.golfer.name,
      tournamentName: fmtTournamentName(conflict.tournament.name),
    };
  })();

  async function handleSaveRevisePick() {
    if (!revisePickTournamentId || !revisePickMemberId || duplicatePickConflict) return;
    await overridePick.mutateAsync({
      user_id: revisePickMemberId,
      tournament_id: revisePickTournamentId,
      golfer_id: revisePickGolferId === "none" ? null : revisePickGolferId,
    });
    setReviseSaved(true);
    setTimeout(() => setReviseSaved(false), 4000);
  }

  // ---------------------------------------------------------------------------
  // Playoff state
  // ---------------------------------------------------------------------------
  const { data: playoffConfig, isError: playoffConfigNotFound } = usePlayoffConfig(leagueId!);
  const { data: bracket } = useBracket(leagueId!);
  const createPlayoffConfig = useCreatePlayoffConfig(leagueId!);
  const updatePlayoffConfig = useUpdatePlayoffConfig(leagueId!);
  const revisePlayoffPick = useRevisePlayoffPick(leagueId!);

  const [playoffEditing, setPlayoffEditing] = useState(false);
  const [playoffSize, setPlayoffSize] = useState(0);
  const [draftStyle, setDraftStyle] = useState<"snake" | "linear" | "top_seed_priority">("snake");
  const [picksPerRound, setPicksPerRound] = useState<number[]>([]);
  const [playoffSaved, setPlayoffSaved] = useState(false);
  const [playoffSaveError, setPlayoffSaveError] = useState("");

  // Revise playoff pick state
  const [poReviseRoundId, setPoReviseRoundId] = useState<number | null>(null);
  const [poReviseUserId, setPoReviseUserId] = useState<string | null>(null);
  const [poRevisePickId, setPoRevisePickId] = useState<string | null>(null);
  const [poReviseGolferId, setPoReviseGolferId] = useState<string>("none");
  const [poReviseSaved, setPoReviseSaved] = useState(false);

  const playoffInitializedRef = useRef(false);
  useEffect(() => {
    if (playoffConfig && !playoffInitializedRef.current) {
      setPlayoffSize(playoffConfig.playoff_size);
      setDraftStyle(playoffConfig.draft_style as "snake" | "linear" | "top_seed_priority");
      setPicksPerRound(playoffConfig.picks_per_round);
      playoffInitializedRef.current = true;
    }
  }, [playoffConfig]);

  // Number of playoff tournament rounds required for the selected bracket size.
  const REQUIRED_ROUNDS: Record<number, number> = { 2: 1, 4: 2, 8: 3, 16: 4, 32: 4 };
  const requiredPlayoffTournaments = REQUIRED_ROUNDS[playoffSize] ?? 0;

  // Count of approved members — playoff size cannot exceed this.
  const approvedCount = members?.filter((m) => m.status === "approved").length ?? 0;

  // When playoff size changes, resize picksPerRound to match the new round count.
  function handlePlayoffSizeChange(newSize: number) {
    setPlayoffSize(newSize);
    if (newSize === 0) {
      setPicksPerRound([]);
    } else {
      const n = REQUIRED_ROUNDS[newSize] ?? 1;
      setPicksPerRound((prev) => {
        if (prev.length === n) return prev;
        if (prev.length < n) {
          const fill = Math.min(2, Math.max(1, prev[prev.length - 1] ?? 2));
          return [...prev, ...Array(n - prev.length).fill(fill)];
        }
        return prev.slice(0, n);
      });
    }
    setPlayoffSaved(false);
  }

  function handleCancelPlayoff() {
    if (playoffConfig) {
      setPlayoffSize(playoffConfig.playoff_size);
      setDraftStyle(playoffConfig.draft_style as "snake" | "linear" | "top_seed_priority");
      setPicksPerRound(playoffConfig.picks_per_round);
    }
    setPlayoffSaveError("");
    setPlayoffEditing(false);
  }

  async function handleSavePlayoff() {
    setPlayoffSaveError("");
    // Size 0 = "No playoff" — if a config exists, persist the change; otherwise just close.
    if (playoffSize === 0) {
      if (playoffConfig) {
        try {
          await updatePlayoffConfig.mutateAsync({ playoff_size: 0 });
        } catch (e) {
          const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
          setPlayoffSaveError(msg ?? "Failed to save playoff settings.");
          return;
        }
      }
      setPlayoffEditing(false);
      return;
    }
    if (eligibleFutureTournaments < requiredPlayoffTournaments) {
      setPlayoffSaveError(
        `Schedule needs ${requiredPlayoffTournaments} future tournament(s) for a ${playoffSize}-member bracket; ${eligibleFutureTournaments} available.`
      );
      return;
    }
    try {
      if (!playoffConfig) {
        await createPlayoffConfig.mutateAsync({
          playoff_size: playoffSize,
          draft_style: draftStyle,
          picks_per_round: picksPerRound,
        });
      } else {
        await updatePlayoffConfig.mutateAsync({
          playoff_size: playoffSize,
          draft_style: draftStyle,
          picks_per_round: picksPerRound,
        });
      }
      setPlayoffSaved(true);
      setPlayoffEditing(false);
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPlayoffSaveError(msg ?? "Failed to save playoff settings.");
    }
  }

  // Group all tournaments by month, sorted earliest to latest within each group.
  const byMonth = allTournaments?.reduce<Record<string, typeof allTournaments>>((acc, t) => {
    const key = t.start_date.slice(0, 7); // "YYYY-MM"
    (acc[key] ??= []).push(t);
    return acc;
  }, {});

  // True once the last REGULAR SEASON tournament has completed.
  // Playoff tournaments are excluded — the schedule locks when the regular season ends.
  const isScheduleLocked = useMemo(() => {
    if (!leagueTournaments || leagueTournaments.length === 0) return false;
    const regularSeason = leagueTournaments.filter((t) => !t.is_playoff_round);
    if (regularSeason.length === 0) return false;
    const last = [...regularSeason].sort((a, b) => b.start_date.localeCompare(a.start_date))[0];
    return last.status === "completed";
  }, [leagueTournaments]);

  // True when 2+ selected tournaments share an ISO week — blocks schedule save.
  const hasScheduleConflicts = (() => {
    const counts = new Map<string, number>();
    for (const t of allTournaments ?? []) {
      if (selectedIds.has(t.id)) {
        const wk = isoWeekKey(t.start_date);
        counts.set(wk, (counts.get(wk) ?? 0) + 1);
      }
    }
    return [...counts.values()].some((c) => c > 1);
  })();

  // The next upcoming scheduled tournament — the current week's pick tournament.
  const nextUpcomingTournamentId = (() => {
    const scheduled = (allTournaments ?? [])
      .filter((t) => t.status === "scheduled")
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    return scheduled[0]?.id ?? null;
  })();

  // Eligible future tournaments from SAVED schedule (for playoff section advisory).
  const eligibleFutureTournaments = useMemo(
    () => (leagueTournaments ?? []).filter(
      (t) => t.status === "scheduled" && (hasInProgressTournament || t.id !== nextUpcomingTournamentId)
    ).length,
    [leagueTournaments, nextUpcomingTournamentId, hasInProgressTournament]
  );

  // Eligible future tournaments from EDITING state (for schedule save blocking).
  const editingEligibleFutureTournaments = useMemo(
    () => (allTournaments ?? []).filter(
      (t) => selectedIds.has(t.id) && t.status === "scheduled" && (hasInProgressTournament || t.id !== nextUpcomingTournamentId)
    ).length,
    [allTournaments, selectedIds, nextUpcomingTournamentId, hasInProgressTournament]
  );

  const hasPlayoffScheduleError = useMemo(() => {
    if (!playoffConfig || playoffConfig.status !== "pending") return false;
    // Use the currently-editing size if the user is mid-edit; unsaved changes take precedence.
    const effectiveSize = playoffEditing ? playoffSize : playoffConfig.playoff_size;
    if (effectiveSize === 0) return false;
    const required = REQUIRED_ROUNDS[effectiveSize] ?? 0;
    return required > 0 && editingEligibleFutureTournaments < required;
  }, [playoffConfig, playoffEditing, playoffSize, editingEligibleFutureTournaments]);

  // Map<tournamentId, playoffRoundNumber> for the EDITING state.
  // Playoff rounds = last N scheduled tournaments in the selected set.
  const editingPlayoffRoundMap = useMemo((): Map<string, number> => {
    if (!playoffConfig || playoffConfig.playoff_size === 0) return new Map();
    const required = REQUIRED_ROUNDS[playoffConfig.playoff_size] ?? 0;
    if (required === 0) return new Map();
    const scheduled = (allTournaments ?? [])
      .filter((t) => selectedIds.has(t.id) && t.status === "scheduled" && (hasInProgressTournament || t.id !== nextUpcomingTournamentId))
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const playoffSlice = scheduled.slice(-required);
    return new Map(playoffSlice.map((t, i) => [t.id, i + 1]));
  }, [allTournaments, selectedIds, playoffConfig, nextUpcomingTournamentId, hasInProgressTournament]);

  // Same map for the SAVED schedule (non-editing display).
  const savedPlayoffRoundMap = useMemo((): Map<string, number> => {
    if (!playoffConfig || playoffConfig.playoff_size === 0) return new Map();
    const required = REQUIRED_ROUNDS[playoffConfig.playoff_size] ?? 0;
    if (required === 0) return new Map();
    const scheduled = (leagueTournaments ?? [])
      .filter((t) => t.status === "scheduled" && (hasInProgressTournament || t.id !== nextUpcomingTournamentId))
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const playoffSlice = scheduled.slice(-required);
    return new Map(playoffSlice.map((t, i) => [t.id, i + 1]));
  }, [leagueTournaments, playoffConfig, nextUpcomingTournamentId, hasInProgressTournament]);

  // Playoff revise pick — derived from live bracket data
  const poActiveRounds = useMemo(
    () => (bracket?.rounds ?? []).filter((r) => r.status !== "pending"),
    [bracket]
  );

  const poReviseRound = useMemo(
    () => poActiveRounds.find((r) => r.id === poReviseRoundId) ?? null,
    [poActiveRounds, poReviseRoundId]
  );

  // All distinct pod members in the selected round
  const poReviseMembers = useMemo(() => {
    if (!poReviseRound) return [];
    const seen = new Set<string>();
    const result: { userId: string; displayName: string }[] = [];
    for (const pod of poReviseRound.pods) {
      for (const m of pod.members) {
        if (!seen.has(m.user_id)) {
          seen.add(m.user_id);
          result.push({ userId: m.user_id, displayName: m.display_name });
        }
      }
    }
    return result.sort((a, b) => a.displayName.localeCompare(b.displayName));
  }, [poReviseRound]);

  // Picks belonging to the selected member in the selected round
  const poRevisePickOptions = useMemo(() => {
    if (!poReviseRound || !poReviseUserId) return [];
    const picks = [];
    for (const pod of poReviseRound.pods) {
      for (const member of pod.members) {
        if (member.user_id === poReviseUserId) {
          const memberPicks = pod.picks.filter((p) => p.pod_member_id === member.id);
          picks.push(...memberPicks);
        }
      }
    }
    return picks.sort((a, b) => a.draft_slot - b.draft_slot);
  }, [poReviseRound, poReviseUserId]);

  const poReviseTournamentId = poReviseRound?.tournament_id ?? undefined;
  const { data: poReviseField, isLoading: poReviseFieldLoading } = useTournamentField(poReviseTournamentId);

  // Pre-fill golfer dropdown when pick changes
  useEffect(() => {
    const currentPick = poRevisePickOptions.find((p) => p.id === poRevisePickId);
    setPoReviseGolferId(currentPick ? currentPick.golfer_id : "none");
    revisePlayoffPick.reset();
    setPoReviseSaved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poRevisePickId]);

  // Reset picks when member/round changes
  useEffect(() => {
    setPoRevisePickId(null);
    setPoReviseGolferId("none");
    setPoReviseSaved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poReviseRoundId, poReviseUserId]);

  async function handleSavePoRevisePick() {
    if (!poRevisePickId || poReviseGolferId === "none") return;
    await revisePlayoffPick.mutateAsync({ pickId: poRevisePickId, golferId: poReviseGolferId });
    setPoReviseSaved(true);
    setTimeout(() => setPoReviseSaved(false), 4000);
  }

  // Current user's role — redirect non-managers back to the league dashboard.
  const myMembership = members?.find((m) => m.user_id === currentUser?.id);
  const isManager = myMembership?.role === "manager";

  // Wait for members to load before redirecting — avoids a flash redirect
  // on initial render before the query resolves.
  if (!isLoading && members !== undefined && !isManager) {
    return <Navigate to={`/leagues/${leagueId}`} replace />;
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
          Manager Panel
        </p>
        <h1 className="text-3xl font-bold text-gray-900">{league?.name ?? "League Management"}</h1>
      </div>


      {/* Invite link — manager only */}
      {isManager && league && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <div className="flex items-center gap-3">
            <SectionIcon>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
              </svg>
            </SectionIcon>
            <h2 className="text-base font-bold text-gray-900">Invite Link</h2>
          </div>
          <p className="text-sm text-gray-500">
            Share this link to let people request to join your league.
            As league manager, you'll approve or deny requests below.
          </p>
          <div className="bg-gray-50 border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-200">
            {/* Full invite URL */}
            <div className="flex items-center gap-3 px-4 py-3">
              <span className="text-gray-700 flex-1 truncate font-mono text-xs">
                {window.location.origin}/join/{league.invite_code}
              </span>
              <button
                onClick={copyInviteLink}
                className={`flex-shrink-0 text-sm font-semibold px-4 py-1.5 rounded-lg border transition-colors ${
                  linkCopied
                    ? "bg-green-50 border-green-300 text-green-700"
                    : "border-gray-300 text-gray-700 hover:border-green-400 hover:text-green-700"
                }`}
              >
                {linkCopied ? "✓ Copied!" : "Copy link"}
              </button>
            </div>
            {/* Bare join code */}
            <div className="flex items-center gap-3 px-4 py-2.5">
              <span className="text-xs text-gray-400">Join code</span>
              <span className="font-mono text-sm font-semibold text-gray-800 tracking-wider">
                {league.invite_code}
              </span>
            </div>
          </div>
        </section>
      )}

      {/* League Settings — manager only, edit-gated */}
      {isManager && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <SectionIcon>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                </svg>
              </SectionIcon>
              <h2 className="text-base font-bold text-gray-900">League Settings</h2>
            </div>
            {!settingsEditing && (
              <button
                onClick={() => setSettingsEditing(true)}
                className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
              >
                Edit
              </button>
            )}
          </div>
          <div className="bg-gray-50 rounded-xl border border-gray-100 divide-y divide-gray-100">
            {/* Name */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-4 px-4 py-3">
              <span className="text-sm text-gray-500 sm:w-36 sm:flex-shrink-0">Name</span>
              {settingsEditing ? (
                <input
                  type="text"
                  value={settingsName}
                  onChange={(e) => setSettingsName(e.target.value)}
                  maxLength={60}
                  className="flex-1 text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-green-700"
                />
              ) : (
                <span className="text-sm font-medium text-gray-900 break-words">{league?.name}</span>
              )}
            </div>
            {/* No-pick penalty */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-4 px-4 py-3">
              <span className="text-sm text-gray-500 sm:w-36 sm:flex-shrink-0">No-pick penalty</span>
              {settingsEditing ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700">−</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={settingsNoPick}
                    onChange={(e) =>
                      setSettingsNoPick(e.target.value.replace(/[^0-9]/g, ""))
                    }
                    onBlur={() =>
                      setSettingsNoPick(String(Math.min(500000, parseInt(settingsNoPick, 10) || 0)))
                    }
                    className="w-36 text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-green-700"
                  />
                  <span className="text-xs text-gray-400">per missed pick · max $500,000</span>
                </div>
              ) : (
                <span className="text-sm font-medium text-gray-900">
                  −{Math.abs(league?.no_pick_penalty ?? 0).toLocaleString()} pts
                </span>
              )}
            </div>
          </div>
          {settingsEditing && (
            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveSettings}
                disabled={updateLeague.isPending}
                className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl text-sm transition-colors"
              >
                {updateLeague.isPending ? "Saving…" : "Save Settings"}
              </button>
              <button
                onClick={handleCancelSettings}
                className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
        </section>
      )}

      {/* Pending join requests — manager only */}
      {isManager && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <div className="flex items-center gap-3">
            <SectionIcon>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
              </svg>
            </SectionIcon>
            <h2 className="text-base font-bold text-gray-900">
              Join Requests
              {pendingRequests && pendingRequests.length > 0 && (
                <span className="ml-2 text-xs font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                  {pendingRequests.length}
                </span>
              )}
            </h2>
          </div>
          {!pendingRequests || pendingRequests.length === 0 ? (
            <p className="text-sm text-gray-400">No pending requests.</p>
          ) : (
            <div className="bg-gray-50 rounded-xl border border-gray-100 divide-y divide-gray-100">
              {pendingRequests.map((r) => (
                <div key={r.user_id} className="flex items-center gap-4 px-4 py-3">
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-gray-900">{r.user.display_name}</p>
                    <p className="text-xs text-gray-400">{r.user.email}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => {
                        setApproveError("");
                        approveRequest.mutate(r.user_id, {
                          onError: (err) => {
                            const msg = (err as { response?: { data?: { detail?: string } } })
                              ?.response?.data?.detail;
                            setApproveError(msg ?? "Failed to approve request.");
                          },
                        });
                      }}
                      disabled={approveRequest.isPending}
                      className="text-xs font-bold text-green-700 hover:text-green-900 bg-green-50 hover:bg-green-100 px-3 py-1.5 rounded-lg disabled:opacity-40 transition-colors"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Deny ${r.user.display_name}'s request?`))
                          denyRequest.mutate(r.user_id);
                      }}
                      disabled={denyRequest.isPending}
                      className="text-xs font-medium text-red-500 hover:underline disabled:opacity-40 transition-colors"
                    >
                      Deny
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {approveError && (
            <p className="text-xs text-red-600 mt-2">{approveError}</p>
          )}
        </section>
      )}

      {/* Members */}
      <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <SectionIcon>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
              </svg>
            </SectionIcon>
            <h2 className="text-base font-bold text-gray-900">League Members</h2>
          </div>
          {isManager && (
            membersEditing ? (
              <button
                onClick={() => setMembersEditing(false)}
                className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
              >
                Done
              </button>
            ) : (
              <button
                onClick={() => setMembersEditing(true)}
                className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
              >
                Edit
              </button>
            )
          )}
        </div>
        {isLoading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-100">
            <table className="min-w-full text-sm">
              <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Name</th>
                  <th className="hidden sm:table-cell px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Email</th>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Role</th>
                  {membersEditing && (
                    <th className="px-4 py-2.5 text-right text-xs uppercase tracking-wider font-semibold">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {members?.map((m) => {
                  const isMe = m.user_id === currentUser?.id;
                  return (
                    <tr key={m.user_id} className={isMe ? "bg-green-50" : "hover:bg-gray-50"}>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {m.user.display_name}
                        {isMe && <span className="ml-1.5 text-xs text-green-600 font-normal">(you)</span>}
                      </td>
                      <td className="hidden sm:table-cell px-4 py-3 text-gray-500">{m.user.email}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                            m.role === "manager"
                              ? "bg-green-100 text-green-800"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {m.role === "manager" ? "League Manager" : "Member"}
                        </span>
                      </td>
                      {membersEditing && (
                        <td className="px-4 py-3 text-right">
                          {!isMe && (
                            <div className="flex items-center justify-end gap-3">
                              <button
                                onClick={() =>
                                  updateRole.mutate({
                                    userId: m.user_id,
                                    role: m.role === "manager" ? "member" : "manager",
                                  })
                                }
                                className="text-xs font-medium text-blue-600 hover:underline transition-colors"
                              >
                                {m.role === "manager" ? "Remove manager" : "Make manager"}
                              </button>
                              <button
                                onClick={() => {
                                  if (confirm(`Remove ${m.user.display_name} from the league?`))
                                    removeMember.mutate(m.user_id);
                                }}
                                className="text-xs font-medium text-red-500 hover:underline transition-colors"
                              >
                                Remove
                              </button>
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Tournament Schedule — manager only */}
      {isManager && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <SectionIcon>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
                </svg>
              </SectionIcon>
              <h2 className="text-base font-bold text-gray-900">Tournament Schedule</h2>
            </div>
            {isScheduleLocked ? (
              <span className="text-xs font-semibold text-gray-400 flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                </svg>
                Locked
              </span>
            ) : !scheduleEditing && (
              <button
                onClick={() => setScheduleEditing(true)}
                className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
              >
                Edit
              </button>
            )}
          </div>
          <p className="text-sm text-gray-500">
            Select which PGA Tour events count for your league. If playoffs are configured,
            the final scheduled tournaments in your schedule will automatically be used as playoff rounds.
          </p>

          {!allTournaments ? (
            <div className="flex justify-center py-4"><Spinner /></div>
          ) : (
            <div className="space-y-6">
              {Object.entries(byMonth ?? {})
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([month, monthTournaments]) => {
                  // Group by ISO week within this month to detect same-week conflicts.
                  const weekEntries = Object.entries(
                    [...monthTournaments]
                      .sort((a, b) => a.start_date.localeCompare(b.start_date))
                      .reduce<Record<string, typeof monthTournaments>>((acc, t) => {
                        const wk = isoWeekKey(t.start_date);
                        (acc[wk] ??= []).push(t);
                        return acc;
                      }, {})
                  ).sort(([a], [b]) => a.localeCompare(b));

                  return (
                    <div key={month}>
                      <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">
                        {new Date(month + "-15").toLocaleString("default", { month: "long", year: "numeric" })}
                      </p>
                      <div className="bg-gray-50 rounded-xl border border-gray-100 divide-y divide-gray-100 overflow-hidden">
                        {weekEntries.map(([weekKey, weekTournaments]) => {
                          const selectedInWeek = weekTournaments.filter((t) => selectedIds.has(t.id));
                          const hasWeekConflict = selectedInWeek.length > 1;
                          return (
                            <Fragment key={weekKey}>
                              {weekTournaments.map((t) => {
                                const checked = selectedIds.has(t.id);
                                const isPast = t.status === "completed";
                                const effectiveMultiplier = multipliers[t.id] ?? t.multiplier;
                                const playoffRound = checked
                                  ? (scheduleEditing ? editingPlayoffRoundMap : savedPlayoffRoundMap).get(t.id) ?? null
                                  : null;
                                return (
                                  <div
                                    key={t.id}
                                    className={`flex items-center gap-3 px-4 py-3 ${
                                      isPast ? "opacity-50" : ""
                                    } ${hasWeekConflict && checked ? "bg-amber-50" : ""}`}
                                  >
                                    <label className={`flex items-center gap-1 flex-shrink-0 ${scheduleEditing ? "cursor-pointer" : "cursor-default"}`}>
                                      <input
                                        type="checkbox"
                                        checked={checked}
                                        disabled={!scheduleEditing}
                                        onChange={() => {
                                          setSelectedIds((prev) => {
                                            const n = new Set(prev);
                                            if (checked) n.delete(t.id); else n.add(t.id);
                                            return n;
                                          });
                                          setScheduleSaved(false);
                                        }}
                                        className="accent-green-800 h-4 w-4 disabled:opacity-60"
                                      />
                                    </label>

                                    <span className="flex-1 text-sm text-gray-900">{fmtTournamentName(t.name)}</span>

                                    {playoffRound !== null && (
                                      <span className="flex-shrink-0 text-xs font-semibold w-12 text-center py-0.5 rounded bg-violet-100 text-violet-700">
                                        PO R{playoffRound}
                                      </span>
                                    )}

                                    {/* Multiplier — picker when editing and checked, badge otherwise */}
                                    {checked && scheduleEditing ? (
                                      <div
                                        className="flex items-center gap-1 flex-shrink-0"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        {[1.0, 1.5, 2.0].map((preset) => (
                                          <button
                                            key={preset}
                                            type="button"
                                            onClick={() => setMultiplierFor(t.id, preset)}
                                            className={`text-xs px-2 py-0.5 rounded font-semibold transition-colors ${
                                              effectiveMultiplier === preset
                                                ? preset >= 2
                                                  ? "bg-amber-500 text-white"
                                                  : preset === 1.5
                                                  ? "bg-blue-600 text-white"
                                                  : "bg-green-800 text-white"
                                                : "bg-gray-200 text-gray-500 hover:bg-gray-300"
                                            }`}
                                          >
                                            {preset === 1.0 ? "1×" : preset === 1.5 ? "1.5×" : "2×"}
                                          </button>
                                        ))}
                                      </div>
                                    ) : checked && effectiveMultiplier !== 1.0 ? (
                                      <span
                                        className={`flex-shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded ${
                                          effectiveMultiplier >= 2
                                            ? "bg-amber-100 text-amber-700"
                                            : "bg-blue-50 text-blue-700"
                                        }`}
                                      >
                                        {effectiveMultiplier}×
                                      </span>
                                    ) : null}
                                    <span className="hidden sm:block text-xs text-gray-400 flex-shrink-0">{t.start_date}</span>
                                  </div>
                                );
                              })}
                              {hasWeekConflict && (
                                <div className="flex items-start gap-2 px-4 py-2.5 bg-amber-50 text-amber-800 text-xs">
                                  <svg className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                                  </svg>
                                  <span>
                                    Only one tournament per week is allowed. Uncheck either{" "}
                                    <strong>{fmtTournamentName(selectedInWeek[0].name)}</strong>
                                    {" "}or{" "}
                                    <strong>{fmtTournamentName(selectedInWeek[1].name)}</strong>.
                                  </span>
                                </div>
                              )}
                            </Fragment>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
          {scheduleEditing && hasPlayoffScheduleError && (() => {
            const required = REQUIRED_ROUNDS[playoffConfig?.playoff_size ?? 0] ?? 0;
            return (
              <div className="flex items-start gap-2 px-1 text-xs text-red-600">
                <svg className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
                <span>Your playoff bracket needs {required} future tournament(s); schedule only has {editingEligibleFutureTournaments} eligible.</span>
              </div>
            );
          })()}
          {scheduleEditing && (
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleSaveSchedule}
                disabled={updateSchedule.isPending || hasScheduleConflicts || hasPlayoffScheduleError}
                className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl text-sm transition-colors"
              >
                {updateSchedule.isPending ? "Saving…" : "Save Schedule"}
              </button>
              <button
                onClick={handleCancelSchedule}
                className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
          {scheduleSaved && !scheduleEditing && (
            <div className="flex items-center gap-1.5 text-sm text-green-700 font-medium pt-2">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
              Schedule saved.
            </div>
          )}
        </section>
      )}

      {/* Playoff Configuration — manager only */}
      {isManager && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <SectionIcon>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
                </svg>
              </SectionIcon>
              <h2 className="text-base font-bold text-gray-900">Playoff</h2>
            </div>
            {!playoffEditing && (playoffConfig || playoffConfigNotFound) && (
              <button
                onClick={() => { setPlayoffEditing(true); setPlayoffSaved(false); }}
                className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
              >
                Edit
              </button>
            )}
          </div>
          <p className="text-sm text-gray-500">
            Configure the bracket size and picks per round. The final scheduled tournaments in your season will automatically serve as playoff rounds.
          </p>

          {playoffSaved && !playoffEditing && (
            <p className="text-sm text-green-700 font-medium">✓ Playoff settings saved.</p>
          )}

          {/* Playoff tournament count advisory — only shown when schedule is insufficient */}
          {playoffSize > 0 && (playoffEditing || playoffConfig) && eligibleFutureTournaments < requiredPlayoffTournaments && (
            <div className="text-sm px-4 py-2.5 rounded-xl border bg-amber-50 border-amber-200 text-amber-700">
              A <strong>{playoffSize}-member</strong> bracket needs{" "}
              <strong>{requiredPlayoffTournaments}</strong> future tournament{requiredPlayoffTournaments !== 1 ? "s" : ""} —{" "}
              your schedule has <strong>{eligibleFutureTournaments}</strong> eligible. Add more future tournaments to the schedule above.
            </div>
          )}

          {/* Settings grid */}
          <div className="bg-gray-50 rounded-xl border border-gray-100 divide-y divide-gray-100">
            {/* Playoff size */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-4 py-3">
              <span className="text-sm text-gray-500 sm:w-44 flex-shrink-0">Playoff size</span>
              {playoffEditing && (!playoffConfig || playoffConfig.status === "pending") ? (
                <div className="flex gap-1.5 flex-wrap">
                  {[0, 2, 4, 8, 16, 32].map((size) => {
                    const tooLarge = size > 0 && size > approvedCount && approvedCount > 0;
                    return (
                    <button
                      key={size}
                      type="button"
                      disabled={tooLarge}
                      title={tooLarge ? `League only has ${approvedCount} approved member(s)` : undefined}
                      onClick={() => handlePlayoffSizeChange(size)}
                      className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                        playoffSize === size ? "bg-green-800 text-white" : "bg-gray-200 text-gray-600 hover:bg-gray-300"
                      }`}
                    >
                      {size === 0 ? "No playoff" : `${size} members`}
                    </button>
                    );
                  })}
                </div>
              ) : (
                <span className="text-sm font-medium text-gray-900">{playoffSize === 0 ? "No playoff" : `${playoffSize} members`}</span>
              )}
            </div>

            {/* Draft style */}
            {playoffSize > 0 && <div className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-4 px-4 py-3">
              <span className="text-sm text-gray-500 sm:w-44 flex-shrink-0 sm:pt-0.5">Draft style</span>
              {playoffEditing && (!playoffConfig || playoffConfig.status === "pending") ? (
                <div className="flex flex-col gap-1.5">
                  {(["snake", "linear", "top_seed_priority"] as const).map((style) => {
                    const labels: Record<string, string> = {
                      snake: "Snake",
                      linear: "Linear",
                      top_seed_priority: "Top seed priority",
                    };
                    const descs: Record<string, string> = {
                      snake: "Draft order reverses each round",
                      linear: "Same order every round",
                      top_seed_priority: "Highest seed always picks first",
                    };
                    return (
                      <label key={style} className="flex items-start gap-2.5 cursor-pointer">
                        <input
                          type="radio"
                          name="draftStyle"
                          value={style}
                          checked={draftStyle === style}
                          onChange={() => { setDraftStyle(style); setPlayoffSaved(false); }}
                          className="mt-0.5 accent-green-700"
                        />
                        <span className="text-sm">
                          <span className="font-medium text-gray-800">{labels[style]}</span>
                          <span className="text-gray-400 ml-1.5">{descs[style]}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <span className="text-sm font-medium text-gray-900">
                  {{ snake: "Snake", linear: "Linear", top_seed_priority: "Top seed priority" }[draftStyle] ?? draftStyle}
                </span>
              )}
            </div>}

            {/* Per-round picks — one row per round, count driven by playoff size */}
            {playoffSize > 0 && picksPerRound.map((picks, i) => (
              <div key={i} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-4 py-3">
                <span className="text-sm text-gray-500 sm:w-44 flex-shrink-0">Round {i + 1} picks / member</span>
                {playoffEditing && (!playoffConfig || playoffConfig.status === "pending") ? (
                  <div className="flex gap-1.5">
                    {[1, 2].map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => {
                          setPicksPerRound((prev) => prev.map((v, j) => j === i ? n : v));
                          setPlayoffSaved(false);
                        }}
                        className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition-colors ${
                          picks === n ? "bg-green-800 text-white" : "bg-gray-200 text-gray-600 hover:bg-gray-300"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm font-medium text-gray-900">{picks}</span>
                )}
              </div>
            ))}
          </div>

          {/* No config yet */}
          {!playoffConfig && playoffConfigNotFound && !playoffEditing && (
            <p className="text-sm text-gray-400">No playoff configured yet. Click Edit to set up.</p>
          )}

          {/* Save / Cancel */}
          {playoffEditing && (
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleSavePlayoff}
                disabled={createPlayoffConfig.isPending || updatePlayoffConfig.isPending || (playoffSize > 0 && eligibleFutureTournaments < requiredPlayoffTournaments)}
                className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl text-sm transition-colors"
              >
                {(createPlayoffConfig.isPending || updatePlayoffConfig.isPending) ? "Saving…" : "Save Playoff Settings"}
              </button>
              <button
                onClick={handleCancelPlayoff}
                className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
          {playoffSaveError && <p className="text-xs text-red-600">{playoffSaveError}</p>}

          {/* Revise Playoff Pick — shown once bracket is seeded and a round has started */}
          {poActiveRounds.length > 0 && (
            <div className="pt-2 border-t border-gray-100 space-y-4">
              <div>
                <p className="text-sm font-semibold text-gray-700">Revise Playoff Pick</p>
                <p className="text-xs text-gray-400 mt-0.5">Override a member's pick in any active playoff round.</p>
              </div>

              <div className="grid sm:grid-cols-4 gap-3">
                {/* Round */}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Round</label>
                  <DropdownSelect
                    value={poReviseRoundId?.toString() ?? ""}
                    onChange={(val) => { setPoReviseRoundId(val ? Number(val) : null); setPoReviseUserId(null); }}
                    placeholder="Select round…"
                    options={poActiveRounds.map((r) => ({
                      value: r.id.toString(),
                      label: `Round ${r.round_number}${r.tournament_name ? ` — ${r.tournament_name}` : ""}`,
                      badge: r.status === "completed" ? "Final" : r.status === "scoring" ? "Scoring" : r.status === "locked" ? "Locked" : "Active",
                      badgeColor: r.status === "completed" ? "bg-gray-100 text-gray-500" : "bg-green-100 text-green-700",
                    }))}
                  />
                </div>

                {/* Member */}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Member</label>
                  <DropdownSelect
                    value={poReviseUserId ?? ""}
                    onChange={(val) => setPoReviseUserId(val || null)}
                    placeholder="Select member…"
                    options={poReviseMembers.map((m) => ({ value: m.userId, label: m.displayName }))}
                  />
                </div>

                {/* Pick slot */}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Pick slot</label>
                  <DropdownSelect
                    value={poRevisePickId ?? ""}
                    onChange={(val) => setPoRevisePickId(val || null)}
                    placeholder="Select pick…"
                    options={poRevisePickOptions.map((p) => ({
                      value: p.id,
                      label: `Pick ${p.draft_slot} — ${p.golfer_name}`,
                    }))}
                  />
                </div>

                {/* Golfer */}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Golfer</label>
                  <DropdownSelect
                    value={poReviseGolferId}
                    onChange={(val) => { setPoReviseGolferId(val); setPoReviseSaved(false); }}
                    placeholder="Select golfer…"
                    disabled={!poRevisePickId || poReviseFieldLoading}
                    options={[
                      { value: "none", label: "No pick" },
                      ...(poReviseField
                        ?.slice()
                        .sort((a, b) => a.name.localeCompare(b.name))
                        .map((g) => ({ value: g.id, label: g.name })) ?? []),
                    ]}
                  />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={handleSavePoRevisePick}
                  disabled={
                    !poRevisePickId ||
                    poReviseGolferId === "none" ||
                    revisePlayoffPick.isPending ||
                    poReviseGolferId === (poRevisePickOptions.find((p) => p.id === poRevisePickId)?.golfer_id ?? "")
                  }
                  className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl text-sm transition-colors"
                >
                  {revisePlayoffPick.isPending ? "Saving…" : "Save Pick"}
                </button>
                {poReviseSaved && !revisePlayoffPick.isPending && (
                  <div className="flex items-center gap-1.5 text-sm text-green-700 font-medium">
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                    Pick saved successfully.
                  </div>
                )}
                {revisePlayoffPick.isError && (
                  <p className="text-sm text-red-600">
                    {(revisePlayoffPick.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to update pick."}
                  </p>
                )}
              </div>
            </div>
          )}

        </section>
      )}

      {/* Revise Pick — manager only */}
      {isManager && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
          <div className="flex items-center gap-3">
            <SectionIcon>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
              </svg>
            </SectionIcon>
            <h2 className="text-base font-bold text-gray-900">Revise Pick</h2>
          </div>
          <p className="text-sm text-gray-500">
            Override any member's pick for a tournament. Use this to correct errors or apply commissioner decisions.
          </p>

          <div className="space-y-4">
            <div className="grid sm:grid-cols-3 gap-3">
              {/* Tournament */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Tournament</label>
                <DropdownSelect
                  value={revisePickTournamentId ?? ""}
                  onChange={(val) => { setRevisePickTournamentId(val || null); setRevisePickGolferId("none"); setReviseSaved(false); }}
                  placeholder="Select tournament…"
                  options={
                    leagueTournaments
                      ?.filter((t) => t.status !== "scheduled")
                      .slice()
                      .sort((a, b) => b.start_date.localeCompare(a.start_date))
                      .map((t) => ({
                        value: t.id,
                        label: fmtTournamentName(t.name),
                        badge: t.status === "in_progress" ? "Live" : "Final",
                        badgeColor: t.status === "in_progress"
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500",
                      })) ?? []
                  }
                />
              </div>

              {/* Member */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Member</label>
                <DropdownSelect
                  value={revisePickMemberId ?? ""}
                  onChange={(val) => { setRevisePickMemberId(val || null); setReviseSaved(false); }}
                  placeholder="Select member…"
                  options={
                    members
                      ?.filter((m) => m.status === "approved")
                      .slice()
                      .sort((a, b) => a.user.display_name.localeCompare(b.user.display_name))
                      .map((m) => ({ value: m.user_id, label: m.user.display_name })) ?? []
                  }
                />
              </div>

              {/* Golfer */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Golfer</label>
                <DropdownSelect
                  value={revisePickGolferId}
                  onChange={(val) => { setRevisePickGolferId(val); setReviseSaved(false); }}
                  placeholder="Select golfer…"
                  disabled={!revisePickTournamentId || !revisePickMemberId || isLoadingGolfers}
                  options={[
                    { value: "none", label: "No pick" },
                    ...(allGolfers
                      ?.slice()
                      .sort((a, b) => a.name.localeCompare(b.name))
                      .map((g) => ({ value: g.id, label: g.name })) ?? []),
                  ]}
                />
              </div>
            </div>

            {duplicatePickConflict && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
                <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
                <span>
                  <strong>{duplicatePickConflict.memberName}</strong> already picked{" "}
                  <strong>{duplicatePickConflict.golferName}</strong> at the{" "}
                  <strong>{duplicatePickConflict.tournamentName}</strong>. Each golfer can only be used once per season.
                </span>
              </div>
            )}

            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveRevisePick}
                disabled={
                  !revisePickTournamentId ||
                  !revisePickMemberId ||
                  overridePick.isPending ||
                  !!duplicatePickConflict ||
                  revisePickGolferId === (
                    allPicks?.find(
                      (p) => p.tournament_id === revisePickTournamentId && p.user_id === revisePickMemberId
                    )?.golfer_id ?? "none"
                  )
                }
                className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl text-sm transition-colors"
              >
                {overridePick.isPending ? "Saving…" : "Save Pick"}
              </button>
              {reviseSaved && !overridePick.isPending && (
                <div className="flex items-center gap-1.5 text-sm text-green-700 font-medium">
                  <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                  Pick saved successfully.
                </div>
              )}
              {overridePick.isError && (
                <p className="text-sm text-red-600">Failed to update pick. Please try again.</p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Danger Zone — manager only */}
      {isManager && (
        <section className="bg-white rounded-2xl border border-red-200 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-red-50 text-red-600 rounded-lg flex items-center justify-center flex-shrink-0">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
              </div>
              <h2 className="text-base font-bold text-gray-900">Danger Zone</h2>
            </div>
            {dangerStep === "idle" && (
              <button
                onClick={() => setDangerStep("editing")}
                className="text-sm font-semibold text-gray-500 hover:text-gray-700 transition-colors"
              >
                Edit
              </button>
            )}
            {dangerStep === "editing" && (
              <button
                onClick={() => setDangerStep("idle")}
                className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
              >
                Done
              </button>
            )}
          </div>

          <p className="text-sm text-gray-500">
            Permanently delete this league and all of its data — members, picks, and standings.
            This action cannot be undone.
          </p>

          {dangerStep === "editing" && (
            <button
              onClick={() => setDangerStep("confirming")}
              className="text-sm font-semibold text-white bg-red-600 hover:bg-red-700 px-4 py-2 rounded-xl transition-colors"
            >
              Delete League
            </button>
          )}

          {dangerStep === "confirming" && (
            <div className="space-y-3 bg-red-50 border border-red-200 rounded-xl p-4">
              {deleteLeague.error && (
                <p className="text-sm text-red-700">Failed to delete league. Please try again.</p>
              )}
              <p className="text-sm text-gray-700">
                Type <span className="font-semibold">{league?.name}</span> to confirm deletion.
              </p>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder={league?.name}
                className="w-full border border-red-300 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-shadow"
              />
              <div className="flex items-center gap-3">
                <button
                  onClick={() => {
                    deleteLeague.mutate(leagueId!, {
                      onSuccess: () => navigate("/leagues"),
                    });
                  }}
                  disabled={deleteConfirmText !== league?.name || deleteLeague.isPending}
                  className="text-sm font-semibold bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white px-4 py-2 rounded-xl transition-colors"
                >
                  {deleteLeague.isPending ? "Deleting…" : "Confirm Delete"}
                </button>
                <button
                  onClick={() => { setDangerStep("editing"); setDeleteConfirmText(""); deleteLeague.reset(); }}
                  disabled={deleteLeague.isPending}
                  className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
