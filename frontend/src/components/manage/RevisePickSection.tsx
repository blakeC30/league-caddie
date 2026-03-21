import { useEffect, useRef, useState } from "react";
import type { LeagueMember, LeagueTournamentOut, PlayoffConfigOut } from "../../api/endpoints";
import { useAdminOverridePick, useAllGolfers, useMemberPickContext } from "../../hooks/usePick";
import { fmtTournamentName } from "../../utils";
import { DropdownSelect, SectionIcon } from "./shared";

export interface RevisePickSectionProps {
  leagueId: string;
  members: LeagueMember[] | undefined;
  leagueTournaments: LeagueTournamentOut[] | undefined;
  playoffConfig: PlayoffConfigOut | undefined;
}

export function RevisePickSection({
  leagueId,
  members,
  leagueTournaments,
  playoffConfig,
}: RevisePickSectionProps) {
  const { data: allGolfers, isLoading: isLoadingGolfers } = useAllGolfers();
  const overridePick = useAdminOverridePick(leagueId);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(savedTimerRef.current), []);

  const [revisePickTournamentId, setRevisePickTournamentId] = useState<string | null>(null);
  const [revisePickMemberId, setRevisePickMemberId] = useState<string | null>(null);
  const [revisePickGolferId, setRevisePickGolferId] = useState<string>("none");
  const [reviseSaved, setReviseSaved] = useState(false);

  // Fetch lightweight context for the selected member + tournament.
  // Returns the existing pick and used golfers — no need to load all 15,000 picks.
  const { data: pickContext } = useMemberPickContext(
    leagueId,
    revisePickMemberId,
    revisePickTournamentId,
  );

  // Reset state when the user changes tournament or member selection.
  useEffect(() => {
    if (!revisePickTournamentId || !revisePickMemberId) {
      setRevisePickGolferId("none");
      return;
    }
    overridePick.reset();
    setReviseSaved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revisePickTournamentId, revisePickMemberId]);

  // Pre-fill the golfer dropdown when context loads (separate from reset).
  useEffect(() => {
    if (pickContext && !reviseSaved) {
      setRevisePickGolferId(pickContext.existing_golfer_id ?? "none");
    }
  }, [pickContext?.existing_golfer_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Detect no-repeat violation using server-provided used golfers list.
  const duplicatePickConflict = (() => {
    if (!revisePickMemberId || revisePickGolferId === "none" || !pickContext) return null;
    const conflict = pickContext.used_golfers.find(
      (g) => g.golfer_id === revisePickGolferId,
    );
    if (!conflict) return null;
    const member = members?.find((m) => m.user_id === revisePickMemberId);
    return {
      memberName: member?.user.display_name ?? "This member",
      golferName: conflict.golfer_name,
      tournamentName: fmtTournamentName(conflict.tournament_name),
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
    clearTimeout(savedTimerRef.current);
    savedTimerRef.current = setTimeout(() => setReviseSaved(false), 4000);
  }

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-gray-900">Revise Pick</h2>
        </div>
        {playoffConfig?.status === "active" && (
          <span className="relative group text-xs font-semibold text-gray-400 flex items-center gap-1 cursor-default">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
            Locked
            <span className="pointer-events-none absolute top-full right-0 mt-2 hidden group-hover:block whitespace-nowrap rounded-lg bg-gray-800 px-2.5 py-1.5 text-xs text-white z-20 shadow-lg font-normal">
              Regular season picks are locked once the playoffs begin
            </span>
          </span>
        )}
      </div>
      <p className="text-sm text-gray-500">
        Override any member's pick for a tournament. Use this to correct errors or apply commissioner decisions.
      </p>

      {playoffConfig?.status === "active" ? (
        <p className="text-sm text-gray-400">Regular season picks cannot be revised after the playoffs have started.</p>
      ) : (
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
                      ? "bg-yellow-100 text-yellow-800"
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
              revisePickGolferId === (pickContext?.existing_golfer_id ?? "none")
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
      )}
    </section>
  );
}
