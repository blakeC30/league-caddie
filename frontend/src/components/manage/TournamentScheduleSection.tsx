import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { LeagueTournamentOut, PlayoffConfigOut, Tournament } from "../../api/endpoints";
import { useUpdateLeagueTournaments } from "../../hooks/useLeague";
import { fmtTournamentName, isoWeekKey } from "../../utils";
import { Spinner } from "../Spinner";
import { REQUIRED_ROUNDS, SectionIcon } from "./shared";

export interface TournamentScheduleSectionProps {
  leagueId: string;
  allTournaments: Tournament[] | undefined;
  leagueTournaments: LeagueTournamentOut[] | undefined;
  isScheduleLocked: boolean;
  playoffConfig: PlayoffConfigOut | undefined;
  hasInProgressTournament: boolean;
  nextUpcomingTournamentId: string | null;
  savedPlayoffRoundMap: Map<string, number>;
  hasPlayoffScheduleError: boolean;
  editingEligibleFutureTournaments: number;
  /** Called by parent to recompute editing-derived values. */
  onSelectedIdsChange: (ids: Set<string>) => void;
  /** Called by parent to recompute editing-derived values. */
  onMultipliersChange: (multipliers: Record<string, number>) => void;
}

export function TournamentScheduleSection({
  leagueId,
  allTournaments,
  leagueTournaments,
  isScheduleLocked,
  playoffConfig,
  hasInProgressTournament,
  nextUpcomingTournamentId,
  savedPlayoffRoundMap,
  hasPlayoffScheduleError: parentHasPlayoffScheduleError,
  editingEligibleFutureTournaments,
  onSelectedIdsChange,
  onMultipliersChange,
}: TournamentScheduleSectionProps) {
  const updateSchedule = useUpdateLeagueTournaments(leagueId);
  const [scheduleEditing, setScheduleEditing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [multipliers, setMultipliers] = useState<Record<string, number>>({});
  const [scheduleSaved, setScheduleSaved] = useState(false);

  const initializedRef = useRef(false);
  useEffect(() => {
    if (leagueTournaments && !initializedRef.current) {
      const ids = new Set(leagueTournaments.map((t) => t.id));
      const mults = Object.fromEntries(leagueTournaments.map((t) => [t.id, t.effective_multiplier]));
      setSelectedIds(ids);
      setMultipliers(mults);
      onSelectedIdsChange(ids);
      onMultipliersChange(mults);
      initializedRef.current = true;
    }
  }, [leagueTournaments]); // eslint-disable-line react-hooks/exhaustive-deps

  const allTournamentsById = Object.fromEntries(
    (allTournaments ?? []).map((t) => [t.id, t])
  );

  function updateSelectedIds(newIds: Set<string>) {
    setSelectedIds(newIds);
    onSelectedIdsChange(newIds);
    setScheduleSaved(false);
  }

  function setMultiplierFor(id: string, value: number) {
    const newMults = { ...multipliers, [id]: value };
    setMultipliers(newMults);
    onMultipliersChange(newMults);
    setScheduleSaved(false);
  }

  function handleCancelSchedule() {
    if (leagueTournaments) {
      const ids = new Set(leagueTournaments.map((t) => t.id));
      const mults = Object.fromEntries(leagueTournaments.map((t) => [t.id, t.effective_multiplier]));
      setSelectedIds(ids);
      setMultipliers(mults);
      onSelectedIdsChange(ids);
      onMultipliersChange(mults);
    } else {
      setSelectedIds(new Set());
      setMultipliers({});
      onSelectedIdsChange(new Set());
      onMultipliersChange({});
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

  // Map<tournamentId, playoffRoundNumber> for the EDITING state.
  const editingPlayoffRoundMap = useMemo((): Map<string, number> => {
    if (!playoffConfig || playoffConfig.playoff_size === 0) return new Map();
    const required = REQUIRED_ROUNDS[playoffConfig.playoff_size] ?? 0;
    if (required === 0) return new Map();
    const allScheduled = (allTournaments ?? [])
      .filter((t) => selectedIds.has(t.id) && t.status === "scheduled")
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const candidates = allScheduled.filter(
      (t) => hasInProgressTournament || t.id !== nextUpcomingTournamentId
    );
    const playoffSlice = candidates.slice(-required);
    return new Map(playoffSlice.map((t, i) => [t.id, i + 1]));
  }, [allTournaments, selectedIds, playoffConfig, nextUpcomingTournamentId, hasInProgressTournament]);

  // Group all tournaments by month, sorted earliest to latest within each group.
  const byMonth = allTournaments?.reduce<Record<string, typeof allTournaments>>((acc, t) => {
    const key = t.start_date.slice(0, 7);
    (acc[key] ??= []).push(t);
    return acc;
  }, {});

  return (
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
          <span className="relative group text-xs font-semibold text-gray-400 flex items-center gap-1 cursor-default">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
            Locked
            <span className="pointer-events-none absolute top-full right-0 mt-2 hidden group-hover:block whitespace-nowrap rounded-lg bg-gray-800 px-2.5 py-1.5 text-xs text-white z-20 shadow-lg font-normal">
              The tournament schedule cannot be changed after picks open for the first playoff round
            </span>
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
                                      const n = new Set(selectedIds);
                                      if (checked) n.delete(t.id); else n.add(t.id);
                                      updateSelectedIds(n);
                                    }}
                                    className="accent-green-800 h-4 w-4 disabled:opacity-60"
                                  />
                                </label>

                                <span className="flex-1 text-sm text-gray-900">{fmtTournamentName(t.name)}</span>

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
                                    className={`flex-shrink-0 text-xs font-bold px-2 py-0.5 rounded-full ${
                                      effectiveMultiplier >= 2
                                        ? "bg-amber-500 text-white"
                                        : "bg-blue-500 text-white"
                                    }`}
                                  >
                                    {effectiveMultiplier}×
                                  </span>
                                ) : null}

                                {playoffRound !== null && (
                                  <span className="flex-shrink-0 text-xs font-bold px-2 py-0.5 rounded-full bg-violet-600 text-white">
                                    PO R{playoffRound}
                                  </span>
                                )}
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
      {scheduleEditing && parentHasPlayoffScheduleError && (() => {
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
        <div className="space-y-2 pt-2">
          <div className="flex items-center gap-3">
            <button
              onClick={handleSaveSchedule}
              disabled={updateSchedule.isPending || hasScheduleConflicts || parentHasPlayoffScheduleError}
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
          {updateSchedule.isError && (
            <p className="text-sm text-red-600">Failed to save schedule. Please try again.</p>
          )}
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
  );
}
