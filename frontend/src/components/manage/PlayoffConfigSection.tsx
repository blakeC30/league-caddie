import { useEffect, useMemo, useRef, useState } from "react";
import type { BracketOut, GolferInField, LeagueMember, PlayoffConfigOut } from "../../api/endpoints";
import {
  useCreatePlayoffConfig,
  useUpdatePlayoffConfig,
  useRevisePlayoffPick,
  useAdminCreatePlayoffPick,
} from "../../hooks/usePlayoff";
import { DropdownSelect, LockedBadge, REQUIRED_ROUNDS, SectionIcon, type ConfirmModalState } from "./shared";

export interface PlayoffConfigSectionProps {
  leagueId: string;
  playoffConfig: PlayoffConfigOut | undefined;
  playoffConfigNotFound: boolean;
  bracket: BracketOut | undefined;
  members: LeagueMember[] | undefined;
  eligibleFutureTournaments: number;
  playoffFullyLocked: boolean;
  poInProgressRound: BracketOut["rounds"][number] | null;
  poReviseField: GolferInField[] | undefined;
  poReviseFieldLoading: boolean;
  onConfirm: (modal: ConfirmModalState) => void;
}

export function PlayoffConfigSection({
  leagueId,
  playoffConfig,
  playoffConfigNotFound,
  bracket,
  members,
  eligibleFutureTournaments,
  playoffFullyLocked,
  poInProgressRound,
  poReviseField,
  poReviseFieldLoading,
  onConfirm,
}: PlayoffConfigSectionProps) {
  const createPlayoffConfig = useCreatePlayoffConfig(leagueId);
  const updatePlayoffConfig = useUpdatePlayoffConfig(leagueId);
  const revisePlayoffPick = useRevisePlayoffPick(leagueId);
  const adminCreatePlayoffPick = useAdminCreatePlayoffPick(leagueId);

  const [playoffEditing, setPlayoffEditing] = useState(false);
  const [playoffSize, setPlayoffSize] = useState(0);
  const [draftStyle, setDraftStyle] = useState<"snake" | "linear" | "top_seed_priority">("snake");
  const [picksPerRound, setPicksPerRound] = useState<number[]>([]);
  const [playoffSaved, setPlayoffSaved] = useState(false);
  const [playoffSaveError, setPlayoffSaveError] = useState("");

  // Revise playoff pick state
  const [poReviseUserId, setPoReviseUserId] = useState<string | null>(null);
  const [poRevisePickId, setPoRevisePickId] = useState<string | null>(null);
  const [poReviseGolferId, setPoReviseGolferId] = useState<string>("none");
  const [poReviseSaved, setPoReviseSaved] = useState(false);
  const poSavedTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(poSavedTimerRef.current), []);

  const playoffInitializedRef = useRef(false);
  useEffect(() => {
    if (playoffConfig && !playoffInitializedRef.current) {
      setPlayoffSize(playoffConfig.playoff_size);
      setDraftStyle(playoffConfig.draft_style as "snake" | "linear" | "top_seed_priority");
      setPicksPerRound(playoffConfig.picks_per_round);
      playoffInitializedRef.current = true;
    }
  }, [playoffConfig]);

  const requiredPlayoffTournaments = REQUIRED_ROUNDS[playoffSize] ?? 0;
  const approvedCount = members?.filter((m) => m.status === "approved").length ?? 0;

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
    if ((!playoffConfig || playoffConfig.status === "pending") && eligibleFutureTournaments < requiredPlayoffTournaments) {
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
      } else if (playoffConfig.status === "pending") {
        await updatePlayoffConfig.mutateAsync({
          playoff_size: playoffSize,
          draft_style: draftStyle,
          picks_per_round: picksPerRound,
        });
      } else {
        await updatePlayoffConfig.mutateAsync({ picks_per_round: picksPerRound });
      }
      setPlayoffSaved(true);
      setPlayoffEditing(false);
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPlayoffSaveError(msg ?? "Failed to save playoff settings.");
    }
  }

  const poReviseRound = poInProgressRound;

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

  // Picks belonging to the selected member in the selected round.
  const poRevisePickOptions = useMemo(() => {
    if (!poReviseRound || !poReviseUserId) return [];

    let podId: number | null = null;
    const existingPicks: { id: string; draft_slot: number; golfer_id: string; golfer_name: string }[] = [];

    for (const pod of poReviseRound.pods) {
      for (const member of pod.members) {
        if (member.user_id === poReviseUserId) {
          podId = pod.id;
          for (const p of pod.picks) {
            if (p.pod_member_id === member.id) {
              existingPicks.push({ id: p.id, draft_slot: p.draft_slot, golfer_id: p.golfer_id, golfer_name: p.golfer_name });
            }
          }
        }
      }
    }

    if (podId === null) return [];

    const roundIdx = poReviseRound.round_number - 1;
    const ppr = bracket?.playoff_config?.picks_per_round ?? [];
    const expectedSlots = ppr[roundIdx] ?? 1;

    const sortedPicks = [...existingPicks].sort((a, b) => a.draft_slot - b.draft_slot);
    const usedSlots = new Set(sortedPicks.map((p) => p.draft_slot));

    const allPodSlots = Array.from({ length: (poReviseRound.pods.find((p) => p.id === podId)?.members.length ?? 2) * expectedSlots }, (_, j) => j + 1);
    const otherMemberSlots = new Set(
      (poReviseRound.pods.find((p) => p.id === podId)?.picks ?? [])
        .filter((p) => p.pod_member_id !== (poReviseRound.pods.find((pp) => pp.id === podId)?.members.find((m) => m.user_id === poReviseUserId)?.id))
        .map((p) => p.draft_slot)
    );
    const availableSlots = allPodSlots.filter((s) => !usedSlots.has(s) && !otherMemberSlots.has(s));

    return Array.from({ length: expectedSlots }, (_, i) => {
      const existing = sortedPicks[i];
      if (existing) {
        return { id: existing.id, draft_slot: existing.draft_slot, golfer_id: existing.golfer_id, golfer_name: existing.golfer_name, isVirtual: false };
      }
      const virtualSlot = availableSlots[i - sortedPicks.length] ?? (i + 1);
      return { id: `new:${podId}:${virtualSlot}`, draft_slot: virtualSlot, golfer_id: null as string | null, golfer_name: null as string | null, isVirtual: true };
    });
  }, [poReviseRound, poReviseUserId, bracket]);

  // Golfer IDs already picked by other members in the same pod
  const poTakenGolferIds = useMemo(() => {
    if (!poReviseRound || !poReviseUserId) return new Set<string>();
    for (const pod of poReviseRound.pods) {
      const myMember = pod.members.find((m) => m.user_id === poReviseUserId);
      if (!myMember) continue;
      const taken = new Set<string>();
      for (const pick of pod.picks) {
        if (pick.pod_member_id !== myMember.id && pick.golfer_id) {
          taken.add(pick.golfer_id);
        }
      }
      return taken;
    }
    return new Set<string>();
  }, [poReviseRound, poReviseUserId]);

  // Pre-fill golfer dropdown when pick changes
  useEffect(() => {
    const currentPick = poRevisePickOptions.find((p) => p.id === poRevisePickId);
    setPoReviseGolferId(currentPick ? (currentPick.golfer_id ?? "none") : "none");
    revisePlayoffPick.reset();
    adminCreatePlayoffPick.reset();
    setPoReviseSaved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poRevisePickId]);

  // Auto-select the in-progress round
  useEffect(() => {
    setPoReviseUserId(null);
  }, [poInProgressRound?.id]);

  // Reset picks when member changes
  useEffect(() => {
    setPoRevisePickId(null);
    setPoReviseGolferId("none");
    setPoReviseSaved(false);
  }, [poReviseUserId]);

  async function handleSavePoRevisePick() {
    if (!poRevisePickId) return;
    if (poReviseGolferId === "none" && poRevisePickId.startsWith("new:")) return;
    if (poRevisePickId.startsWith("new:")) {
      const [, podIdStr, draftSlotStr] = poRevisePickId.split(":");
      await adminCreatePlayoffPick.mutateAsync({
        podId: Number(podIdStr),
        userId: poReviseUserId!,
        draftSlot: Number(draftSlotStr),
        golferId: poReviseGolferId,
      });
    } else {
      await revisePlayoffPick.mutateAsync({ pickId: poRevisePickId, golferId: poReviseGolferId === "none" ? null : poReviseGolferId });
    }
    setPoReviseSaved(true);
    clearTimeout(poSavedTimerRef.current);
    poSavedTimerRef.current = setTimeout(() => setPoReviseSaved(false), 4000);
  }

  return (
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
        {!playoffEditing && playoffFullyLocked ? (
          <span className="relative group text-xs font-semibold text-gray-400 flex items-center gap-1 cursor-default">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
            Locked
            <span className="pointer-events-none absolute top-full right-0 mt-2 hidden group-hover:block whitespace-nowrap rounded-lg bg-gray-800 px-2.5 py-1.5 text-xs text-white z-20 shadow-lg font-normal">
              All rounds have started — there are no remaining settings to configure
            </span>
          </span>
        ) : !playoffEditing && (playoffConfig || playoffConfigNotFound) && (
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

      {/* Playoff tournament count advisory */}
      {playoffSize > 0 && (playoffEditing || playoffConfig) && playoffConfig?.status !== "active" && eligibleFutureTournaments < requiredPlayoffTournaments && (
        <div className="text-sm px-4 py-2.5 rounded-xl border bg-amber-50 border-amber-200 text-amber-700">
          A <strong>{playoffSize}-member</strong> bracket needs{" "}
          <strong>{requiredPlayoffTournaments}</strong> future tournament{requiredPlayoffTournaments !== 1 ? "s" : ""} —{" "}
          your schedule has <strong>{eligibleFutureTournaments}</strong> eligible. Add more future tournaments to the schedule above.
        </div>
      )}

      {/* Schedule-lock warning */}
      {playoffEditing && playoffSize > 0 && (
        <div className="text-sm px-4 py-2.5 rounded-xl border bg-amber-50 border-amber-300 text-amber-800 space-y-1">
          <p className="font-semibold">{"⚠"} Important — review your schedule before enabling playoffs</p>
          <p>Once the first playoff round opens for picks, your tournament schedule is <strong>permanently locked</strong>. No tournaments can be added or removed after that point. If your schedule is incomplete, your season will end earlier than intended and <strong>this cannot be undone</strong>.</p>
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
            <span className="flex items-center text-sm font-medium text-gray-900">
              {playoffSize === 0 ? "No playoff" : `${playoffSize} members`}
              {playoffEditing && <LockedBadge tooltip="Playoff size cannot be changed after the playoffs start" />}
            </span>
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
            <span className="flex items-center text-sm font-medium text-gray-900">
              {{ snake: "Snake", linear: "Linear", top_seed_priority: "Top seed priority" }[draftStyle] ?? draftStyle}
              {playoffEditing && <LockedBadge tooltip="Draft style cannot be changed after the playoffs start" />}
            </span>
          )}
        </div>}

        {/* Per-round picks */}
        {playoffSize > 0 && picksPerRound.map((picks, i) => (
          <div key={i} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-4 py-3">
            <span className="text-sm text-gray-500 sm:w-44 flex-shrink-0">Round {i + 1} picks / member</span>
            {playoffEditing && (!playoffConfig || playoffConfig.status === "pending" || bracket?.rounds[i]?.status === "pending") ? (
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
              <span className="flex items-center text-sm font-medium text-gray-900">
                {picks}
                {playoffEditing && <LockedBadge tooltip={`Round ${i + 1}'s draft window has opened — picks per member can no longer be changed`} />}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* No config yet */}
      {!playoffConfig && playoffConfigNotFound && !playoffEditing && (
        <p className="text-sm text-gray-400">No playoff configured yet. Click Edit to set up.</p>
      )}

      {/* Save / Cancel / Success */}
      {playoffEditing && (
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={() => {
              const needsConfirm = playoffSize > 0 && (!playoffConfig || playoffConfig.status === "pending");
              if (needsConfirm) {
                onConfirm({
                  title: "Enable playoff bracket?",
                  message: "Once the first playoff round opens for picks, your tournament schedule will be permanently locked — no tournaments can be added or removed. Make sure your schedule is complete before proceeding.",
                  confirmLabel: "Enable playoffs",
                  onConfirm: handleSavePlayoff,
                });
              } else {
                handleSavePlayoff();
              }
            }}
            disabled={createPlayoffConfig.isPending || updatePlayoffConfig.isPending || (playoffConfig?.status !== "active" && playoffSize > 0 && eligibleFutureTournaments < requiredPlayoffTournaments)}
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
      {playoffSaved && !playoffEditing && (
        <div className="flex items-center gap-1.5 text-sm text-green-700 font-medium pt-1">
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
          Playoff settings saved.
        </div>
      )}
      {playoffSaveError && <p className="text-xs text-red-600">{playoffSaveError}</p>}

      {/* Revise Playoff Pick — shown once bracket is seeded */}
      {playoffConfig?.status === "active" && (
        <div className="pt-2 border-t border-gray-100 space-y-4">
          <div>
            <p className="text-sm font-semibold text-gray-700">Revise Playoff Pick</p>
            <p className="text-xs text-gray-400 mt-0.5">Override a member's pick while a playoff tournament is in progress.</p>
          </div>

          {poInProgressRound ? (
            <>
              {/* Round context label */}
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-medium text-gray-900">Round {poInProgressRound.round_number}</span>
                {poInProgressRound.tournament_name && (
                  <><span className="text-gray-300">{"—"}</span><span>{poInProgressRound.tournament_name}</span></>
                )}
                <span className="rounded-full bg-yellow-100 text-yellow-800 text-xs font-semibold px-2 py-0.5">Live</span>
              </div>

              <div className="grid sm:grid-cols-3 gap-3">
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
                    options={poRevisePickOptions.map((p, i) => ({
                      value: p.id,
                      label: p.golfer_name ? `Pick ${i + 1} — ${p.golfer_name}` : `Pick ${i + 1} — (empty)`,
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
                        .filter((g) => !poTakenGolferIds.has(g.id))
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
                    (poReviseGolferId === "none" && poRevisePickId.startsWith("new:")) ||
                    revisePlayoffPick.isPending ||
                    adminCreatePlayoffPick.isPending ||
                    (!poRevisePickId?.startsWith("new:") &&
                      poReviseGolferId === (poRevisePickOptions.find((p) => p.id === poRevisePickId)?.golfer_id ?? ""))
                  }
                  className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-xl text-sm transition-colors"
                >
                  {(revisePlayoffPick.isPending || adminCreatePlayoffPick.isPending) ? "Saving…" : "Save Pick"}
                </button>
                {poReviseSaved && !revisePlayoffPick.isPending && !adminCreatePlayoffPick.isPending && (
                  <div className="flex items-center gap-1.5 text-sm text-green-700 font-medium">
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                    Pick saved successfully.
                  </div>
                )}
                {(revisePlayoffPick.isError || adminCreatePlayoffPick.isError) && (
                  <p className="text-sm text-red-600">
                    {(revisePlayoffPick.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail ??
                      (adminCreatePlayoffPick.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail ??
                      "Failed to save pick."}
                  </p>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400">
              Picks can only be revised while a playoff tournament is in progress. Check back once the current round's tournament has started.
            </p>
          )}
        </div>
      )}

    </section>
  );
}
