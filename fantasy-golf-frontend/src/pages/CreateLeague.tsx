/**
 * CreateLeague — new league setup page.
 *
 * Lets the user configure name, no-pick penalty, and tournament schedule before
 * the league is created. All tournaments are pre-selected with their global
 * multipliers (majors = 2×, The Players = 1.5×, others = 1×).
 * Everything can be changed later from the Manage page.
 */

import { Fragment, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { leaguesApi, type Tournament } from "../api/endpoints";
import { useTournaments } from "../hooks/usePick";
import { fmtTournamentName, isoWeekKey } from "../utils";
import { Spinner } from "../components/Spinner";

export function CreateLeague() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [name, setName] = useState("");
  const [noPick, setNoPick] = useState("50000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const { data: allTournaments } = useTournaments();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [multipliers, setMultipliers] = useState<Record<string, number>>({});
  const initializedRef = useRef(false);

  // Detect the default multiplier by name since the global tournaments table may
  // store 1.0 for everything (per-league overrides live in league_tournaments).
  function defaultMultiplierFor(t: Tournament): number {
    if (t.multiplier > 1.0) return t.multiplier; // already set correctly in DB
    const name = t.name.toLowerCase();
    if (name.includes("players championship") || name.includes("the players")) return 1.5;
    if (
      name.includes("masters") ||
      name.includes("u.s. open") ||
      name.includes("us open") ||
      name.includes("the open") ||
      name.includes("open championship") ||
      name.includes("pga championship")
    )
      return 2.0;
    return 1.0;
  }

  // Pre-select only upcoming (scheduled) tournaments; exclude completed/in-progress.
  useEffect(() => {
    if (allTournaments && !initializedRef.current) {
      setSelectedIds(
        new Set(allTournaments.filter((t) => t.status === "scheduled").map((t) => t.id))
      );
      setMultipliers(Object.fromEntries(allTournaments.map((t) => [t.id, defaultMultiplierFor(t)])));
      initializedRef.current = true;
    }
  }, [allTournaments]);

  // Group tournaments by YYYY-MM for the month headers.
  const byMonth = allTournaments?.reduce<Record<string, Tournament[]>>((acc, t) => {
    const key = t.start_date.slice(0, 7);
    (acc[key] ??= []).push(t);
    return acc;
  }, {});

  // True when 2+ selected tournaments share an ISO week — blocks form submission.
  const hasConflicts = (() => {
    const counts = new Map<string, number>();
    for (const t of allTournaments ?? []) {
      if (selectedIds.has(t.id)) {
        const wk = isoWeekKey(t.start_date);
        counts.set(wk, (counts.get(wk) ?? 0) + 1);
      }
    }
    return [...counts.values()].some((c) => c > 1);
  })();

  function toggleTournament(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function setMultiplierFor(id: string, value: number) {
    setMultipliers((prev) => ({ ...prev, [id]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError("");
    setLoading(true);
    try {
      const league = await leaguesApi.create(name.trim(), -(parseInt(noPick, 10) || 0));
      const schedule = [...selectedIds].map((id) => ({
        tournament_id: id,
        multiplier: multipliers[id] ?? null,
        is_playoff: false,
      }));
      if (schedule.length > 0) {
        await leaguesApi.updateTournaments(league.id, schedule);
      }
      qc.invalidateQueries({ queryKey: ["myLeagues"] });
      navigate(`/leagues/${league.id}`);
    } catch {
      setError("Failed to create league. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      {/* Page header */}
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
          New League
        </p>
        <h1 className="text-3xl font-bold text-gray-900">Create a League</h1>
        <p className="text-sm text-gray-500 pt-1">
          Most settings can be adjusted later from the Manage page.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* League details */}
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
              </svg>
            </div>
            <h2 className="text-base font-bold text-gray-900">League Details</h2>
          </div>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="leagueName" className="block text-sm font-medium text-gray-700">
                League name <span className="text-red-500">*</span>
              </label>
              <input
                id="leagueName"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Friday Night Golf"
                maxLength={60}
                className="w-full border border-gray-300 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-transparent transition-shadow"
              />
            </div>
          </div>
        </div>

        {/* Rules */}
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25ZM6.75 12h.008v.008H6.75V12Zm0 3h.008v.008H6.75V15Zm0 3h.008v.008H6.75V18Z" />
              </svg>
            </div>
            <h2 className="text-base font-bold text-gray-900">Rules</h2>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="noPick" className="block text-sm font-medium text-gray-700">
              No-pick penalty
            </label>
            <p className="text-xs text-gray-400">
              Points applied when a player misses a week without submitting a pick.
            </p>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-700">−</span>
              <input
                id="noPick"
                type="text"
                inputMode="numeric"
                value={noPick}
                onChange={(e) => setNoPick(e.target.value.replace(/[^0-9]/g, ""))}
                onBlur={() => setNoPick(String(Math.min(500000, parseInt(noPick, 10) || 0)))}
                className="w-36 border border-gray-300 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-transparent transition-shadow"
              />
              <span className="text-xs text-gray-400">per missed pick · max $500,000</span>
            </div>
          </div>
        </div>

        {/* Conflict banner — sticky so it stays visible while scrolling the schedule */}
        {hasConflicts && (
          <div className="sticky top-4 z-10 flex items-start gap-2.5 bg-amber-50 border border-amber-300 text-amber-800 text-sm px-4 py-3 rounded-xl shadow-sm">
            <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            <span>
              <strong>Schedule conflict:</strong> two selected tournaments fall in the same week. Uncheck one in each conflicting week below before creating the league.
            </span>
          </div>
        )}

        {/* Tournament schedule */}
        <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
              </svg>
            </div>
            <h2 className="text-base font-bold text-gray-900">Tournament Schedule</h2>
          </div>
          <p className="text-sm text-gray-500">
            All tournaments are included by default. Majors are worth{" "}
            <span className="font-semibold text-amber-700">2×</span> and The Players Championship is worth{" "}
            <span className="font-semibold text-blue-700">1.5×</span>. Uncheck events you want to exclude,
            or adjust multipliers. This can be changed at any time from the Manage page.
          </p>

          {!allTournaments ? (
            <div className="flex justify-center py-4"><Spinner /></div>
          ) : (
            <div className="space-y-6">
              {Object.entries(byMonth ?? {})
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([month, monthTournaments]) => {
                  // Group tournaments in this month by ISO week so we can detect
                  // when two selected events would fall in the same week.
                  const weekEntries = Object.entries(
                    [...monthTournaments]
                      .sort((a, b) => a.start_date.localeCompare(b.start_date))
                      .reduce<Record<string, Tournament[]>>((acc, t) => {
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
                                return (
                                  <div
                                    key={t.id}
                                    className={`flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-100 ${isPast ? "opacity-50" : ""} ${hasWeekConflict && checked ? "bg-amber-50" : ""}`}
                                    onClick={() => toggleTournament(t.id)}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={() => {}}
                                      className="accent-green-800 h-4 w-4 flex-shrink-0 pointer-events-none"
                                    />
                                    <span className="flex-1 text-sm text-gray-900">{fmtTournamentName(t.name)}</span>
                                    {checked && (
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
                                    )}
                                    <span className="hidden sm:block text-xs text-gray-400 flex-shrink-0">
                                      {t.start_date}
                                    </span>
                                  </div>
                                );
                              })}
                              {hasWeekConflict && (
                                <div key={`conflict-${weekKey}`} className="flex items-start gap-2 px-4 py-2.5 bg-amber-50 text-amber-800 text-xs">
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
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm px-3.5 py-2.5 rounded-xl">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
            {error}
          </div>
        )}

        <div className="flex items-center gap-4 pb-8">
          <button
            type="submit"
            disabled={loading || !name.trim() || hasConflicts}
            className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold py-3 px-8 rounded-xl transition-colors shadow-sm"
          >
            {loading ? "Creating…" : "Create League"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/leagues")}
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
