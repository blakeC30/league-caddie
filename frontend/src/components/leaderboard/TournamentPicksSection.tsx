/**
 * TournamentPicksSection — tournament dropdown + pick breakdown (table/chart views)
 * + stats cards + playoff round breakdown.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useLeague, useLeagueTournaments } from "../../hooks/useLeague";
import { useTournamentPicksSummary } from "../../hooks/usePick";
import { useBracket } from "../../hooks/usePlayoff";
import { useAuthStore } from "../../store/authStore";
import { fmtTournamentName } from "../../utils";
import type { PlayoffRoundOut } from "../../api/endpoints";
import { useDropdownDirection } from "../../hooks/useDropdownDirection";
import { Spinner } from "../Spinner";
import { PickBarChart } from "./PickBarChart";
import { StatCard } from "./StatCard";
import { SortButton } from "./SortButton";
import { PlayoffRoundBreakdown } from "./PlayoffRoundBreakdown";

// ---------------------------------------------------------------------------
// Sorting types
// ---------------------------------------------------------------------------

type BreakdownSortField = "member" | "golfer" | "earnings";
type SortDir = "asc" | "desc";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface TournamentPicksSectionProps {
  leagueId: string;
}

export function TournamentPicksSection({ leagueId }: TournamentPicksSectionProps) {
  const { data: leagueTournaments } = useLeagueTournaments(leagueId);
  const { data: league } = useLeague(leagueId);
  const { data: bracket } = useBracket(leagueId);
  const currentUserId = useAuthStore((s) => s.user?.id);
  const [selectedId, setSelectedId] = useState<string>("");
  const [view, setView] = useState<"table" | "chart">("table");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dropdownSearch, setDropdownSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const dropdownTriggerRef = useRef<HTMLButtonElement>(null);
  const dropdownInputRef = useRef<HTMLInputElement>(null);
  const dropDir = useDropdownDirection(dropdownRef, dropdownOpen);

  // Sort state for the breakdown table — resets when a new tournament is selected.
  const [sortField, setSortField] = useState<BreakdownSortField>("member");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [memberSearch, setMemberSearch] = useState("");
  const [breakdownPage, setBreakdownPage] = useState(0);
  const BREAKDOWN_PAGE_SIZE = 50;

  // Reset pagination when tournament changes
  useEffect(() => { setBreakdownPage(0); setMemberSearch(""); }, [selectedId]);

  // Reset sort and search when the selected tournament changes.
  useEffect(() => {
    setSortField("member");
    setSortDir("asc");
    setMemberSearch("");
  }, [selectedId]);

  function handleSort(field: BreakdownSortField) {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "earnings" ? "desc" : "asc");
    }
  }

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
        setDropdownSearch("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (dropdownOpen) dropdownInputRef.current?.focus();
  }, [dropdownOpen]);

  // Sort: in_progress first, then completed desc — upcoming tournaments excluded
  const sorted = [...(leagueTournaments ?? [])]
    .filter((t) => t.status !== "scheduled")
    .sort((a, b) => {
      // In-progress always first, then completed most-recent-first
      if (a.status === "in_progress" && b.status !== "in_progress") return -1;
      if (b.status === "in_progress" && a.status !== "in_progress") return 1;
      return b.start_date.localeCompare(a.start_date);
    });

  const filteredTournaments = dropdownSearch
    ? sorted.filter((t) => fmtTournamentName(t.name).toLowerCase().includes(dropdownSearch.toLowerCase()))
    : sorted;

  const selectedTournament = sorted.find((t) => t.id === selectedId);

  // Map tournament_id -> PlayoffRoundOut for fast playoff detection
  const playoffRoundByTournamentId = useMemo(() => {
    const m = new Map<string, PlayoffRoundOut>();
    for (const r of bracket?.rounds ?? []) {
      if (r.tournament_id) m.set(r.tournament_id, r);
    }
    return m;
  }, [bracket]);

  const selectedPlayoffRound = selectedId ? playoffRoundByTournamentId.get(selectedId) : undefined;

  const {
    data: summary,
    isLoading,
    error,
  } = useTournamentPicksSummary(leagueId, selectedPlayoffRound ? null : (selectedId || null));

  const isCompleted = selectedTournament?.status === "completed";
  const isScheduled = selectedTournament?.status === "scheduled";

  // Derived stats
  const totalPickers = summary
    ? summary.picks_by_golfer.reduce((s, g) => s + g.pick_count, 0)
    : 0;
  const submissionRate = summary ? (totalPickers / summary.member_count) * 100 : 0;
  const topPick = summary?.picks_by_golfer[0];
  const missedCutPicks = summary?.picks_by_golfer
    .filter((g) => g.earnings_usd === 0)
    .reduce((s, g) => s + g.pick_count, 0) ?? 0;
  const missedCutPct = totalPickers > 0 ? Math.round((missedCutPicks / totalPickers) * 100) : 0;
  const multiplier = selectedTournament?.effective_multiplier ?? 1;
  const totalPoints = summary?.picks_by_golfer.reduce(
    (s, g) => s + (g.earnings_usd ?? 0) * g.pick_count * multiplier,
    0
  ) ?? 0;
  const avgPoints = totalPickers > 0 ? Math.round(totalPoints / totalPickers) : null;

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-bold text-gray-900">Tournament Breakdown</h2>
        <div
          ref={dropdownRef}
          className="relative w-full sm:w-auto"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setDropdownOpen(false);
              setDropdownSearch("");
              dropdownTriggerRef.current?.focus();
            }
          }}
        >
          <button
            ref={dropdownTriggerRef}
            type="button"
            onClick={() => { setDropdownOpen((o) => !o); setDropdownSearch(""); }}
            className="w-full sm:min-w-[220px] flex items-center gap-2 text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white text-gray-700 hover:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-700 transition-colors"
          >
            <span className="flex-1 text-left truncate">
              {selectedTournament ? fmtTournamentName(selectedTournament.name) : "Select a tournament…"}
            </span>
            <svg
              className={`h-4 w-4 text-gray-400 shrink-0 transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {dropdownOpen && (
            <div className={`absolute right-0 w-full sm:w-72 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-10 ${dropDir === "up" ? "bottom-full mb-1" : "top-full mt-1"}`}>
              <div className="px-3 py-2 border-b border-gray-100">
                <input
                  ref={dropdownInputRef}
                  type="text"
                  value={dropdownSearch}
                  onChange={(e) => setDropdownSearch(e.target.value)}
                  placeholder="Search…"
                  className="w-full text-sm outline-none placeholder-gray-400 bg-transparent"
                />
              </div>
              <div className="max-h-64 overflow-y-auto">
                {filteredTournaments.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-gray-400">No results.</p>
                ) : (
                  filteredTournaments.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => { setSelectedId(t.id); setDropdownOpen(false); setDropdownSearch(""); }}
                      className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between gap-3 transition-colors ${
                        t.id === selectedId ? "bg-green-50 text-green-900" : "hover:bg-gray-50 text-gray-700"
                      }`}
                    >
                      <span className="truncate">{fmtTournamentName(t.name)}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {playoffRoundByTournamentId.has(t.id) && (
                          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-green-700 text-white">
                            PO
                          </span>
                        )}
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          t.status === "in_progress"
                            ? "bg-green-100 text-green-700"
                            : t.status === "completed"
                            ? "bg-gray-100 text-gray-500"
                            : "bg-blue-50 text-blue-600"
                        }`}>
                          {t.status === "in_progress" ? "Live" : t.status === "completed" ? "Final" : "Upcoming"}
                        </span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {!selectedId && (
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-400 text-sm">
          Select a tournament above to see pick breakdown.
        </div>
      )}

      {selectedId && isScheduled && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center space-y-1">
          <p className="text-sm font-semibold text-amber-800">Picks are locked</p>
          <p className="text-xs text-amber-600">
            Pick selections are revealed once the tournament begins to prevent copying.
          </p>
        </div>
      )}

      {selectedId && isLoading && (
        <div className="flex justify-center py-4"><Spinner /></div>
      )}

      {selectedId && !isScheduled && !isLoading && !selectedPlayoffRound && error && (
        <p className="text-gray-400 text-sm">No pick data available for this tournament yet.</p>
      )}

      {/* Playoff round breakdown — replaces stats/chart for playoff tournaments */}
      {selectedPlayoffRound && (
        <PlayoffRoundBreakdown round={selectedPlayoffRound} />
      )}

      {summary && !isScheduled && !selectedPlayoffRound && (
        <div className="space-y-5">
          {/* Stats row */}
          <div className={`grid grid-cols-2 gap-3 ${
            isCompleted && missedCutPicks > 0 ? "sm:grid-cols-4" :
            isCompleted || missedCutPicks > 0 ? "sm:grid-cols-3" :
            "sm:grid-cols-2"
          }`}>
            <StatCard
              label="Submission rate"
              value={`${Math.round(submissionRate)}%`}
              sub={`${totalPickers} of ${summary.member_count} members`}
              color={submissionRate === 100 ? "text-green-700" : "text-gray-900"}
            />
            {missedCutPicks > 0 && (
              <StatCard
                label="Missed cut"
                value={`${missedCutPct}%`}
                sub={`${missedCutPicks} of ${totalPickers} picks`}
              />
            )}
            <StatCard
              label="Most popular"
              value={topPick ? topPick.golfer_name.split(" ").pop()! : "—"}
              sub={topPick ? `${topPick.pick_count} pick${topPick.pick_count !== 1 ? "s" : ""}` : undefined}
            />
            {isCompleted && (
              <StatCard
                label="Avg points"
                value={avgPoints !== null ? `$${avgPoints.toLocaleString()}` : "—"}
                sub="per pick submitted"
              />
            )}
          </div>

          {/* View toggle */}
          <div className="flex items-center gap-1 bg-gray-200 rounded-lg p-1 w-fit">
            <button
              onClick={() => setView("table")}
              className={`text-xs font-semibold px-3 py-1 rounded-md transition-colors ${
                view === "table" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"
              }`}
            >
              Table
            </button>
            <button
              onClick={() => setView("chart")}
              className={`text-xs font-semibold px-3 py-1 rounded-md transition-colors ${
                view === "chart" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"
              }`}
            >
              Chart
            </button>
          </div>

          {/* Table view */}
          {view === "table" && (() => {
            // Flatten picks_by_golfer into one row per picker, sorted by points desc
            // (nulls / no-picks at the bottom).
            type PickRow = {
              userId: string;
              displayName: string;
              golferName: string | null;
              earningsUsd: number | null;
              pointsEarned: number | null;
            };

            const multiplier = selectedTournament?.effective_multiplier ?? 1.0;
            const showMultiplier = multiplier !== 1.0;

            const pickRows: PickRow[] = summary.picks_by_golfer.flatMap((g) =>
              g.pickers.map((p) => ({
                userId: p.user_id,
                displayName: p.display_name,
                golferName: g.golfer_name,
                earningsUsd: g.earnings_usd,
                pointsEarned: p.points_earned,
              }))
            );

            const noPickPenalty = league?.no_pick_penalty ?? 0;
            const noPickRows: PickRow[] = summary.no_pick_members.map((m) => ({
              userId: m.user_id,
              displayName: m.display_name,
              golferName: null,
              earningsUsd: noPickPenalty !== 0 ? -noPickPenalty : null,
              pointsEarned: noPickPenalty !== 0 ? -noPickPenalty : null,
            }));

            const allRows = [...pickRows, ...noPickRows];

            // Sort all rows (picks + no-picks) together.
            // For earnings sort: no-pick rows sink to the bottom; for member/golfer: fully alphabetical.
            allRows.sort((a, b) => {
              let cmp = 0;
              if (sortField === "member") {
                cmp = a.displayName.localeCompare(b.displayName);
              } else if (sortField === "golfer") {
                // No-pick rows (null golfer) sink to bottom when sorting by golfer
                if (a.golferName === null && b.golferName === null) cmp = a.displayName.localeCompare(b.displayName);
                else if (a.golferName === null) cmp = 1;
                else if (b.golferName === null) cmp = -1;
                else cmp = a.golferName.localeCompare(b.golferName);
              } else if (sortField === "earnings") {
                // No-pick rows sink to bottom when sorting by earnings
                if (a.pointsEarned === null && b.pointsEarned === null) cmp = a.displayName.localeCompare(b.displayName);
                else if (a.pointsEarned === null) cmp = 1;
                else if (b.pointsEarned === null) cmp = -1;
                else cmp = a.pointsEarned - b.pointsEarned;
              }
              return sortDir === "asc" ? cmp : -cmp;
            });

            function renderEarningsCell(row: PickRow) {
              if (!isCompleted) return <span className="text-gray-400">&mdash;</span>;
              if (row.pointsEarned === null) return <span className="text-gray-400">&mdash;</span>;

              // No-pick penalty row: show negative value in red
              if (row.golferName === null) {
                return (
                  <span className="text-red-500 font-semibold">
                    {`-$${Math.abs(Math.round(row.pointsEarned)).toLocaleString()}`}
                  </span>
                );
              }

              if (showMultiplier && row.earningsUsd !== null) {
                return (
                  <div>
                    <span className="text-gray-900 font-semibold">
                      {`$${Math.round(row.earningsUsd).toLocaleString()}`}
                    </span>
                    <br />
                    <span className="text-green-700 text-xs font-medium">
                      {`${Math.round(row.pointsEarned).toLocaleString()} pts`}
                    </span>
                  </div>
                );
              }

              return (
                <span className="text-gray-900 font-semibold">
                  {`$${Math.round(row.pointsEarned).toLocaleString()}`}
                </span>
              );
            }

            const filteredRows = memberSearch.trim()
              ? allRows.filter((r) => r.displayName.toLowerCase().includes(memberSearch.toLowerCase()))
              : allRows;

            const breakdownTotalPages = Math.ceil(filteredRows.length / BREAKDOWN_PAGE_SIZE);
            const visibleRows = filteredRows.slice(
              breakdownPage * BREAKDOWN_PAGE_SIZE,
              (breakdownPage + 1) * BREAKDOWN_PAGE_SIZE,
            );

            return (
              <div className="rounded-xl border border-gray-200 overflow-hidden">
                {/* Member search — shown when there are enough members */}
                {allRows.length > BREAKDOWN_PAGE_SIZE && (
                <div className="px-3 py-2 border-b border-gray-100 bg-white">
                  <input
                    type="text"
                    value={memberSearch}
                    onChange={(e) => { setMemberSearch(e.target.value); setBreakdownPage(0); }}
                    placeholder="Search members…"
                    className="w-full text-sm px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-green-600 focus:border-green-600"
                  />
                </div>
                )}
                <div className="relative">
                <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
                    <tr>
                      <th className="px-4 py-2.5 text-left">
                        <SortButton
                          label="Member"
                          active={sortField === "member"}
                          dir={sortDir}
                          onClick={() => handleSort("member")}
                        />
                      </th>
                      <th className="px-4 py-2.5 text-left">
                        <SortButton
                          label="Golfer"
                          active={sortField === "golfer"}
                          dir={sortDir}
                          onClick={() => handleSort("golfer")}
                        />
                      </th>
                      <th className="px-4 py-2.5 text-right">
                        <SortButton
                          label={showMultiplier ? `Earnings / Points (×${multiplier})` : "Earnings"}
                          active={sortField === "earnings"}
                          dir={sortDir}
                          onClick={() => handleSort("earnings")}
                          align="right"
                        />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {allRows.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-4 py-6 text-center text-gray-400">
                          No picks submitted for this tournament.
                        </td>
                      </tr>
                    ) : (
                      visibleRows.map((row, i) => {
                        const isNoPick = row.golferName === null;
                        return (
                          <tr
                            key={row.userId}
                            className={`border-t border-gray-100 ${
                              isNoPick
                                ? "bg-red-50"
                                : i % 2 === 0
                                ? "bg-white"
                                : "bg-gray-50"
                            }`}
                          >
                            <td className="px-4 py-3 font-medium text-gray-900">
                              {row.displayName}
                            </td>
                            <td className="px-4 py-3 text-gray-600">
                              {isNoPick ? (
                                <span className="italic text-red-400">No pick</span>
                              ) : (
                                row.golferName
                              )}
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums">
                              {renderEarningsCell(row)}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
              <div className="pointer-events-none absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-white to-transparent sm:hidden" />
              </div>
              {breakdownTotalPages > 1 && (
                <div className="flex items-center justify-between gap-4 px-4 py-2 border-t border-gray-100 bg-white">
                  <span className="text-xs text-gray-400 tabular-nums">
                    {breakdownPage * BREAKDOWN_PAGE_SIZE + 1}–{Math.min((breakdownPage + 1) * BREAKDOWN_PAGE_SIZE, filteredRows.length)} of {filteredRows.length}{memberSearch ? " results" : ""}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setBreakdownPage((p) => Math.max(0, p - 1))}
                      disabled={breakdownPage === 0}
                      className="text-sm font-medium text-gray-500 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
                    >
                      ← Prev
                    </button>
                    <button
                      type="button"
                      onClick={() => setBreakdownPage((p) => Math.min(breakdownTotalPages - 1, p + 1))}
                      disabled={breakdownPage >= breakdownTotalPages - 1}
                      className="text-sm font-medium text-gray-500 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
                    >
                      Next →
                    </button>
                  </div>
                </div>
              )}
            </div>
            );
          })()}

          {/* Chart view */}
          {view === "chart" && (
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <p className="text-sm font-semibold text-gray-700 mb-4">Pick Distribution</p>
              {summary.picks_by_golfer.length === 0 ? (
                <p className="text-gray-400 text-sm text-center py-8">No picks to display.</p>
              ) : (
                <PickBarChart
                  groups={summary.picks_by_golfer}
                  noPickMembers={summary.no_pick_members.map((m) => m.display_name)}
                  isCompleted={isCompleted}
                  myGolferName={
                    summary.picks_by_golfer.find((g) =>
                      g.pickers.some((p) => p.user_id === currentUserId)
                    )?.golfer_name ?? null
                  }
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
