/**
 * PlayoffPreferenceEditor — reusable ranked preference list editor.
 *
 * Extracted from PlayoffDraft.tsx so it can be used both on the dedicated
 * per-pod draft page AND inline in MakePick during a playoff week.
 */

import { useEffect, useMemo, useState } from "react";
import { ClearableInput } from "./ClearableInput";
import { useTournamentField, useAllGolfers } from "../hooks/usePick";
import { useSubmitPreferences } from "../hooks/usePlayoff";
import type { PlayoffPreference } from "../hooks/usePlayoff";
import type { Golfer, GolferInField } from "../api/endpoints";

interface PlayoffPreferenceEditorProps {
  leagueId: string;
  podId: number;
  tournamentId: string;
  currentPreferences: PlayoffPreference[];
  picksPerRound?: number;
  requiredCount?: number;   // pod_size * picks_per_round — exact number to submit
  deadline?: string;        // ISO datetime; preferences lock when this moment passes
  onSaveSuccess?: (count: number, wasUpdate: boolean) => void;
  isTeamEvent?: boolean;
}

export function PlayoffPreferenceEditor(props: PlayoffPreferenceEditorProps) {
  const { leagueId, podId, tournamentId, currentPreferences, picksPerRound, requiredCount, deadline, onSaveSuccess, isTeamEvent = false } = props;
  const hadExistingPreferences = currentPreferences.length > 0;

  // Preferences are locked once the first R1 tee time has passed.
  const isWindowClosed = deadline ? new Date() >= new Date(deadline) : false;

  const { data: rawField } = useTournamentField(tournamentId);
  const { data: allGolfers } = useAllGolfers();
  const fieldNotReleased = Array.isArray(rawField) && rawField.length === 0;
  const field = useMemo(
    () => fieldNotReleased ? (allGolfers ?? []) : (rawField ?? []),
    [fieldNotReleased, allGolfers, rawField],
  );
  const submit = useSubmitPreferences(leagueId, podId);

  const [ranked, setRanked] = useState<string[]>(() =>
    currentPreferences.map((p) => p.golfer_id)
  );
  const [search, setSearch] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    setRanked(currentPreferences.map((p) => p.golfer_id));
  }, [currentPreferences]);

  const rankedSet = useMemo(() => new Set(ranked), [ranked]);

  // For team events, build a map from golfer_id → partner_golfer_id so we can
  // exclude partners when one half of a team is already ranked.
  const partnerOf = useMemo(() => {
    const m: Record<string, string> = {};
    if (isTeamEvent) {
      for (const g of (rawField ?? []) as GolferInField[]) {
        if (g.partner_golfer_id) m[g.id] = g.partner_golfer_id;
      }
    }
    return m;
  }, [isTeamEvent, rawField]);

  // Display name: "Name / Partner" for team events, "Name" for individual.
  const displayName = useMemo(() => {
    const m: Record<string, string> = {};
    for (const g of field ?? []) {
      const f = g as GolferInField;
      m[g.id] = isTeamEvent && f.partner_name
        ? `${g.name} / ${f.partner_name}`
        : g.name;
    }
    return m;
  }, [field, isTeamEvent]);

  // For team events, track which golfer_ids have their partner already ranked.
  const excludedByPartner = useMemo(() => {
    const s = new Set<string>();
    if (isTeamEvent) {
      for (const id of ranked) {
        const pid = partnerOf[id];
        if (pid) s.add(pid);
      }
    }
    return s;
  }, [isTeamEvent, ranked, partnerOf]);

  const golferMap = useMemo(() => {
    const m: Record<string, Golfer> = {};
    for (const g of field ?? []) m[g.id] = g;
    return m;
  }, [field]);

  const filteredField = useMemo(() => {
    if (field.length === 0) return [];
    const q = search.toLowerCase();
    return field
      .filter((g) => {
        if (rankedSet.has(g.id)) return false;
        // For team events, hide partners that are already covered by ranking the other half.
        if (isTeamEvent && excludedByPartner.has(g.id)) return false;
        if (q && !displayName[g.id]?.toLowerCase().includes(q)) return false;
        return true;
      })
      .sort((a, b) => (displayName[a.id] ?? a.name).localeCompare(displayName[b.id] ?? b.name));
  }, [field, rankedSet, search, isTeamEvent, excludedByPartner, displayName]);

  function addGolfer(id: string) {
    setRanked((prev) => [...prev, id]);
    setSaveSuccess(false);
  }

  function removeGolfer(id: string) {
    setRanked((prev) => prev.filter((g) => g !== id));
    setSaveSuccess(false);
  }

  function moveUp(idx: number) {
    if (idx === 0) return;
    setRanked((prev) => {
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return next;
    });
    setSaveSuccess(false);
  }

  function moveDown(idx: number) {
    if (idx === ranked.length - 1) return;
    setRanked((prev) => {
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      return next;
    });
    setSaveSuccess(false);
  }

  function handleSubmit() {
    setSaveError("");
    setSaveSuccess(false);
    submit.mutate(ranked, {
      onSuccess: () => {
        setSaveSuccess(true);
        onSaveSuccess?.(ranked.length, hadExistingPreferences);
      },
      onError: (e) =>
        setSaveError(
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Failed to submit. Please try again."
        ),
    });
  }

  return (
    <section className="bg-white rounded-sm border border-ink-200 p-5 space-y-4">
      {fieldNotReleased && (
        <div className="flex items-start gap-2.5 bg-brass-50 border border-brass-100 rounded-xs px-4 py-3">
          <svg className="w-4 h-4 text-brass-600 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
          <p className="text-xs text-brass-700 leading-relaxed">
            The official field hasn't been announced yet. If a golfer you rank doesn't enter the tournament, they'll be skipped and your next available pick will be used instead.
          </p>
        </div>
      )}
      {isWindowClosed && (
        <div className="flex items-center gap-2 bg-brass-50 border border-brass-100 rounded-xs px-4 py-3">
          <svg className="w-4 h-4 text-brass-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
          <p className="text-xs text-brass-700 font-medium">
            The preference window is closed — the tournament has started.
          </p>
        </div>
      )}
      <div className="space-y-1">
        <h2 className="text-sm font-bold text-ink-800">Your Rankings</h2>
        {requiredCount !== undefined ? (
          <p className="text-xs text-ink-500">
            Rank exactly <span className="font-semibold text-ink-700">{requiredCount} golfers</span> in order of preference — enough to cover all picks if earlier choices are taken.
          </p>
        ) : picksPerRound !== undefined && (
          <p className="text-xs text-ink-500">
            Rank at least {picksPerRound} golfer{picksPerRound !== 1 ? "s" : ""} in order of preference.
          </p>
        )}
        <p className="text-xs text-ink-500">
          The system assigns picks in draft order using your highest-ranked available golfer. Submit before the tournament starts.
        </p>
      </div>

      {/* Ranked list */}
      {ranked.length > 0 ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between mb-2">
            <p className="text-micro uppercase text-ink-400">Your ranked list</p>
            {requiredCount !== undefined && (
              <span className={`text-[10px] font-semibold ${ranked.length === requiredCount ? "text-fairway-600" : "text-brass-600"}`}>
                {ranked.length}/{requiredCount}
              </span>
            )}
          </div>
          {ranked.map((id, idx) => {
            const g = golferMap[id];
            return (
              <div
                key={id}
                className="flex items-center gap-2 bg-ink-50 rounded-xs px-3 py-2"
              >
                <span className="text-[10px] font-bold text-ink-400 w-5 text-center flex-shrink-0">
                  {idx + 1}
                </span>
                <span className="flex-1 text-sm text-ink-800 truncate">
                  {displayName[id] ?? g?.name ?? id}
                </span>
                {g?.world_ranking && (
                  <span className="text-[10px] text-ink-400 flex-shrink-0">#{g.world_ranking}</span>
                )}
                <div className="flex gap-1">
                  <button
                    onClick={() => moveUp(idx)}
                    disabled={idx === 0}
                    className="w-8 h-8 flex items-center justify-center text-ink-400 hover:text-ink-700 disabled:opacity-20 rounded-xs hover:bg-ink-200 transition-colors"
                    title="Move up"
                    aria-label="Move up"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
                    </svg>
                  </button>
                  <button
                    onClick={() => moveDown(idx)}
                    disabled={idx === ranked.length - 1}
                    className="w-8 h-8 flex items-center justify-center text-ink-400 hover:text-ink-700 disabled:opacity-20 rounded-xs hover:bg-ink-200 transition-colors"
                    title="Move down"
                    aria-label="Move down"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                    </svg>
                  </button>
                  <button
                    onClick={() => removeGolfer(id)}
                    className="w-8 h-8 flex items-center justify-center text-flag-500 hover:text-flag-600 rounded-xs hover:bg-flag-50 transition-colors"
                    title="Remove"
                    aria-label="Remove golfer from preferences"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-ink-50 rounded-xs p-6 text-center">
          <p className="text-xs text-ink-400">Search for golfers below and add them to your ranked list.</p>
        </div>
      )}

      {/* Submit */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={isWindowClosed || submit.isPending || ranked.length === 0 || (requiredCount !== undefined && ranked.length !== requiredCount)}
          className="text-sm font-bold text-white bg-fairway-700 hover:bg-fairway-600 px-4 py-2 rounded-xs transition-colors disabled:opacity-50"
        >
          {submit.isPending ? "Submitting…" : "Save Rankings"}
        </button>
        {requiredCount !== undefined && ranked.length !== requiredCount && ranked.length > 0 && (
          <span className="text-xs text-brass-600">
            {ranked.length < requiredCount
              ? `Add ${requiredCount - ranked.length} more`
              : `Remove ${ranked.length - requiredCount} extra`}
          </span>
        )}
        {saveSuccess && (
          <span className="text-xs text-fairway-700 font-medium flex items-center gap-1">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
            Saved
          </span>
        )}
      </div>
      {saveError && <p className="text-xs text-flag-600">{saveError}</p>}

      {/* Search & add — hidden once the preference window has closed */}
      {!isWindowClosed && <div className="space-y-2 border-t border-ink-100 pt-4">
        <p className="text-micro uppercase text-ink-400">Add golfers</p>
        <ClearableInput
          placeholder="Search tournament field…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onClear={() => setSearch("")}
          className="w-full text-sm border border-ink-200 rounded-xs px-3 py-2 focus:outline-none focus:ring-2 focus:ring-fairway-600"
        />
        <div className="max-h-64 overflow-y-auto space-y-1">
          {filteredField.length === 0 && (
            <p className="text-xs text-ink-400 py-2 text-center">
              {rawField !== undefined ? (search ? "No matches" : "All golfers ranked") : "Loading field…"}
            </p>
          )}
          {filteredField.map((g) => (
            <button
              key={g.id}
              onClick={() => addGolfer(g.id)}
              className="w-full flex items-center justify-between gap-2 text-sm text-left text-ink-700 hover:bg-fairway-50 px-3 py-2 rounded-xs transition-colors"
            >
              <span className="truncate">{displayName[g.id] ?? g.name}</span>
              {g.world_ranking && (
                <span className="text-[10px] text-ink-400 flex-shrink-0">#{g.world_ranking}</span>
              )}
            </button>
          ))}
        </div>
      </div>}
    </section>
  );
}
