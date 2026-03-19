/**
 * Leaderboard — full season standings + per-tournament pick analysis.
 *
 * Pick breakdown section:
 *   - Tournament dropdown (all league tournaments, soonest first)
 *   - Picks are hidden until the tournament is in_progress or completed
 *   - Table view:  golfer | pickers | points (if completed)
 *   - Chart view:  CSS bar chart — golfer on X, # picks on Y
 *   - Stats cards: submission rate, most popular pick, contrarian pick,
 *                  best/worst result (completed only)
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useStandings, useTournamentPicksSummary } from "../hooks/usePick";
import { useLeague, useLeagueTournaments, useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import { useBracket } from "../hooks/usePlayoff";
import { useAuthStore } from "../store/authStore";
import { fmtTournamentName } from "../utils";
import type { GolferPickGroup, PlayoffRoundOut, StandingsRow } from "../api/endpoints";
import { useDropdownDirection } from "../hooks/useDropdownDirection";
import { Spinner } from "../components/Spinner";
import { PlayoffBracket } from "./PlayoffBracket";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Pure CSS bar chart (no library needed)
// ---------------------------------------------------------------------------

interface BarChartProps {
  groups: GolferPickGroup[];
  noPickMembers: string[];
  isCompleted: boolean;
  myGolferName: string | null; // golfer the current user picked, or null if no pick
}

function PickBarChart({ groups, noPickMembers, isCompleted, myGolferName }: BarChartProps) {
  const [tooltip, setTooltip] = useState<string | null>(null);

  // Build chart data: one bar per golfer + one "No Pick" bar if applicable.
  // Sort by pick count desc, then alphabetically by last name for ties.
  const lastName = (name: string) => name.split(" ").pop() ?? name;
  const sortedGroups = [...groups].sort(
    (a, b) => b.pick_count - a.pick_count || lastName(a.golfer_name).localeCompare(lastName(b.golfer_name))
  );
  const bars: { label: string; fullName: string; count: number; points: number | null; names: string[] }[] = [
    ...sortedGroups.map((g) => ({
      label: g.golfer_name.split(" ").pop() ?? g.golfer_name,
      fullName: g.golfer_name,
      count: g.pick_count,
      points: isCompleted ? (g.pickers[0]?.points_earned ?? null) : null,
      names: g.pickers.map((p) => p.display_name),
    })),
    ...(noPickMembers.length > 0
      ? [{ label: "No Pick", fullName: "No Pick", count: noPickMembers.length, points: null, names: noPickMembers }]
      : []),
  ];

  const maxCount = Math.max(...bars.map((b) => b.count), 1);

  // Color scheme consistent with the site's green palette:
  //   dark green  = current user's pick (matches header/button style — "this is yours")
  //   light green = all other golfers (soft, clearly secondary)
  //   muted red   = no pick submitted
  function barColor(b: typeof bars[0]): string {
    if (b.label === "No Pick") return "bg-red-300";
    if (myGolferName && b.fullName === myGolferName) return "bg-green-800";
    return "bg-green-300";
  }

  function labelColor(b: typeof bars[0]): string {
    if (b.label === "No Pick") return "text-red-400";
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-400";
  }

  function countColor(b: typeof bars[0]): string {
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-400";
  }

  return (
    <div className="space-y-2">
      {/*
        The outer div is h-40 with items-end (flex row). Each column child is
        flex-1, which only controls the *width* (main axis). To make percentage
        heights on the bar resolve correctly, each column must have a definite
        height — so we give it h-full. The count label is positioned absolutely
        above the bar so it doesn't consume height that would break the ratio.
      */}
      {/* Scrollable wrapper — on narrow screens the chart scrolls horizontally
          while the tooltip below stays full-width */}
      <div className="overflow-x-auto">
        <div style={{ minWidth: `${bars.length * 48}px` }}>
          <div className="flex items-end gap-2 h-40 px-1">
            {bars.map((b) => (
              <div
                key={b.label}
                className="flex-1 h-full flex flex-col justify-end items-center cursor-pointer group"
                onClick={() => {
                  const text = b.names.length
                    ? `${b.fullName}: ${[...b.names].sort((a, c) => a.localeCompare(c)).join(", ")}`
                    : b.label === "No Pick"
                    ? "No pick submitted"
                    : b.fullName;
                  setTooltip((prev) => (prev === text ? null : text));
                }}
              >
                {/* Count label sits directly above the bar, pushed down by flex justify-end */}
                <span className={`text-[10px] mb-0.5 ${countColor(b)}`}>{b.count}</span>
                {/* Bar — percentage height resolves against the h-full column */}
                <div
                  className={`w-full rounded-t transition-opacity group-hover:opacity-70 ${barColor(b)}`}
                  style={{ height: `${(b.count / maxCount) * 100}%`, minHeight: "4px" }}
                />
              </div>
            ))}
          </div>

          {/* X-axis labels — rotated 45° downward so long names don't collide or overlap bars */}
          <div className="flex gap-2 px-1" style={{ height: "80px" }}>
            {bars.map((b) => (
              <div key={b.label} className="flex-1 relative overflow-visible">
                <span
                  className={`text-[10px] whitespace-nowrap absolute ${labelColor(b)}`}
                  style={{
                    top: "4px",
                    left: "50%",
                    transform: "rotate(45deg)",
                    transformOrigin: "top left",
                  }}
                >
                  {b.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <p className="text-xs text-gray-600 bg-gray-100 rounded px-3 py-1.5 mt-1">{tooltip}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats cards
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

function StatCard({ label, value, sub, color = "text-gray-900" }: StatCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 space-y-0.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sorting types + SortButton (mirrors MyPicks.tsx exactly)
// ---------------------------------------------------------------------------

type BreakdownSortField = "member" | "golfer" | "earnings";
type SortDir = "asc" | "desc";

function SortButton({ label, active, dir, onClick, align = "left" }: {
  label: string; active: boolean; dir: SortDir; onClick: () => void; align?: "left" | "right";
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
        align === "right" ? "flex-row-reverse" : ""
      } ${
        active ? "text-green-300" : "text-white/60 hover:text-white"
      }`}
    >
      {label}
      <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        {active && dir === "asc" ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
        ) : active && dir === "desc" ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" />
        )}
      </svg>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Playoff round breakdown (replaces stats/chart for playoff tournaments)
// ---------------------------------------------------------------------------

function PlayoffRoundBreakdown({ round }: { round: PlayoffRoundOut }) {
  const currentUserId = useAuthStore((s) => s.user?.id);

  // Determine if picks are visible: hidden when status is "locked" but picks arrays are all empty
  // (server enforces this until all R1 tee times pass)
  const allPicksEmpty = round.pods.every((pod) => pod.picks.length === 0);
  const picksHidden = round.status === "locked" && allPicksEmpty;

  if (round.status === "drafting") {
    return (
      <div className="bg-purple-50 border border-purple-200 rounded-xl p-6 text-center space-y-1">
        <p className="text-sm font-semibold text-purple-800">Draft is open</p>
        <p className="text-xs text-purple-600">
          Picks will be revealed after the tournament begins and all golfers have teed off.
        </p>
      </div>
    );
  }

  if (picksHidden) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center space-y-1">
        <p className="text-sm font-semibold text-amber-800">Tournament is underway</p>
        <p className="text-xs text-amber-600">
          Picks will be revealed once all golfers have teed off in Round 1.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {round.pods.map((pod) => {
        // Build a map from pod_member_id → picks for easy lookup
        const picksByMemberId = new Map(
          pod.members.map((m) => [
            m.id,
            pod.picks.filter((p) => p.pod_member_id === m.id),
          ])
        );

        // Sort members: highest total_points first; null floats to bottom
        const sortedMembers = [...pod.members].sort((a, b) => {
          if (a.total_points === null && b.total_points === null) return 0;
          if (a.total_points === null) return 1;
          if (b.total_points === null) return -1;
          return b.total_points - a.total_points;
        });

        return (
          <div key={pod.id} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 bg-gradient-to-r from-purple-900 to-purple-700 flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-white">
                Pod {pod.bracket_position}
              </span>
              {pod.status === "completed" && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/20 text-white">
                  Final
                </span>
              )}
            </div>
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-400">Member</th>
                  <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-400">Picks</th>
                  <th className="px-4 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-400">Points</th>
                </tr>
              </thead>
              <tbody>
                {sortedMembers.map((member, i) => {
                  const isMe = member.user_id === currentUserId;
                  const isWinner = pod.winner_user_id === member.user_id;
                  const picks = picksByMemberId.get(member.id) ?? [];
                  return (
                    <tr
                      key={member.id}
                      className={`border-t border-gray-100 ${
                        isMe ? "bg-green-50" : i % 2 === 0 ? "bg-white" : "bg-gray-50"
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          {isWinner && (
                            <span className="text-amber-500" title="Winner">★</span>
                          )}
                          <span className={`font-medium ${isMe ? "text-green-900" : "text-gray-900"}`}>
                            {member.display_name}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {picks.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {picks
                              .sort((a, b) => a.draft_slot - b.draft_slot)
                              .map((p) => (
                                <span
                                  key={p.id}
                                  className="text-[11px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-700 whitespace-nowrap"
                                >
                                  {p.golfer_name}
                                  {p.points_earned !== null && (
                                    <span className="ml-1 text-green-700 font-medium">
                                      ${Math.round(p.points_earned).toLocaleString()}
                                    </span>
                                  )}
                                </span>
                              ))}
                          </div>
                        ) : (
                          <span className="text-gray-400 text-xs italic">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums font-semibold text-gray-900">
                        {member.total_points !== null
                          ? `$${Math.round(member.total_points).toLocaleString()}`
                          : <span className="text-gray-400 font-normal">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pick breakdown section
// ---------------------------------------------------------------------------

function TournamentPicksSection({ leagueId }: { leagueId: string }) {
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

  // Map tournament_id → PlayoffRoundOut for fast playoff detection
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
                          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500 text-white">
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
          <div className={`grid grid-cols-2 gap-3 ${isCompleted ? "sm:grid-cols-4" : "sm:grid-cols-3"}`}>
            <StatCard
              label="Submission rate"
              value={`${Math.round(submissionRate)}%`}
              sub={`${totalPickers} of ${summary.member_count} members`}
              color={submissionRate === 100 ? "text-green-700" : "text-gray-900"}
            />
            <StatCard
              label="Missed cut"
              value={totalPickers > 0 ? `${missedCutPct}%` : "—"}
              sub={totalPickers > 0 ? `${missedCutPicks} of ${totalPickers} picks` : undefined}
            />
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
              if (!isCompleted) return <span className="text-gray-400">—</span>;
              if (row.pointsEarned === null) return <span className="text-gray-400">—</span>;

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

            const visibleRows = memberSearch.trim()
              ? allRows.filter((r) => r.displayName.toLowerCase().includes(memberSearch.toLowerCase()))
              : allRows;

            return (
              <div className="rounded-xl border border-gray-200 overflow-hidden">
                {/* Member search */}
                <div className="px-3 py-2 border-b border-gray-100 bg-white">
                  <input
                    type="text"
                    value={memberSearch}
                    onChange={(e) => setMemberSearch(e.target.value)}
                    placeholder="Search members…"
                    className="w-full text-sm px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-green-600 focus:border-green-600"
                  />
                </div>
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

// ---------------------------------------------------------------------------
// Inline standings row — mirrors Dashboard's StandingsTr exactly
// ---------------------------------------------------------------------------

function fmtPoints(pts: number): string {
  return `$${Math.round(pts).toLocaleString()}`;
}

function fmtRank(rank: number, isTied: boolean): string {
  return isTied ? `T${rank}` : `${rank}`;
}

function rankCls(rank: number): string {
  if (rank === 1) return "text-amber-500 font-bold";
  if (rank === 2) return "text-slate-400 font-semibold";
  if (rank === 3) return "text-orange-400 font-semibold";
  return "text-gray-500";
}

function StandingsTr({
  row,
  isMe,
  stripe,
  borderTop,
}: {
  row: StandingsRow;
  isMe: boolean;
  stripe: boolean;
  borderTop?: string;
}) {
  return (
    <tr
      className={`${borderTop ?? "border-t border-gray-100"} ${
        isMe
          ? "bg-green-50 border-l-2 border-l-green-400"
          : stripe
          ? "bg-gray-50"
          : "bg-white"
      }`}
    >
      <td className={`px-4 py-3 tabular-nums ${rankCls(row.rank)}`}>
        {fmtRank(row.rank, row.is_tied)}
      </td>
      <td className={`px-4 py-3 ${isMe ? "font-semibold" : ""}`}>
        {row.display_name}
      </td>
      <td className="px-4 py-3 text-right tabular-nums font-medium">
        {fmtPoints(row.total_points)}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Leaderboard() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [searchParams] = useSearchParams();
  const { data: standings, isLoading } = useStandings(leagueId!);
  const { data: bracket } = useBracket(leagueId!);
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { data: members } = useLeagueMembers(leagueId!);
  const isManager = members?.some((m) => m.user_id === currentUserId && m.role === "manager") ?? false;
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");
  const [expanded, setExpanded] = useState(() => searchParams.get("expand") === "1");
  const hasPlayoffs = !!bracket;
  // Default to bracket view when the playoff is active (regular season ended).
  const playoffActive = bracket?.playoff_config?.status === "active" || bracket?.playoff_config?.status === "completed";
  const [pageView, setPageView] = useState<"standings" | "bracket">(
    () => searchParams.get("view") === "bracket" ? "bracket"
      : searchParams.get("view") === "standings" ? "standings"
      : "standings" // initial default; updated below once bracket loads
  );
  const defaultedRef = useRef(false);
  useEffect(() => {
    if (!defaultedRef.current && playoffActive && !searchParams.get("view")) {
      setPageView("bracket");
      defaultedRef.current = true;
    }
  }, [playoffActive, searchParams]);
  const totalRows = standings?.rows.length ?? 0;
  const showToggle = totalRows > 5;

  // Compute which rows to display
  let displayedRows: StandingsRow[] = [];
  let currentUserSeparatorRow: StandingsRow | null = null;

  if (standings) {
    if (expanded) {
      displayedRows = standings.rows;
    } else {
      const top5 = standings.rows.slice(0, 5);
      const meInTop5 = top5.some((r) => r.user_id === currentUserId);
      displayedRows = top5;
      if (!meInTop5) {
        const myRow = standings.rows.find((r) => r.user_id === currentUserId) ?? null;
        currentUserSeparatorRow = myRow;
      }
    }
  }

  // Purchase gate
  if (!purchaseLoading && purchase !== undefined && !purchase?.paid_at) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="bg-amber-50 rounded-full p-4 mb-6">
          <svg className="w-12 h-12 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v2m0-2h2m-2 0H10m2-10a4 4 0 100 8 4 4 0 000-8z" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-3">League Plan Required</h2>
        <p className="text-gray-600 max-w-sm mb-8">
          {isManager
            ? "This league needs an active League Plan to access features. Purchase one to get started."
            : "Your league manager needs to purchase a League Plan to unlock all features."}
        </p>
        {isManager ? (
          <Link
            to={`/leagues/${leagueId}/manage`}
            className="bg-green-800 hover:bg-green-700 text-white font-semibold px-6 py-3 rounded-xl transition-colors"
          >
            Manage &amp; Purchase
          </Link>
        ) : (
          <p className="text-sm text-gray-500">Contact your league manager to activate this league.</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div className="space-y-1">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
            Leaderboard
          </p>
          <h1 className="text-3xl font-bold text-gray-900">
            {pageView === "bracket" ? "Playoff Bracket" : "Season Standings"}
          </h1>
          {standings && (
            <p className="text-sm text-gray-500">{standings.season_year} Season</p>
          )}
        </div>

        {/* Standings / Bracket pill toggle — only shown when playoffs are configured */}
        {hasPlayoffs && (
          <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1 self-start">
            <button
              onClick={() => setPageView("standings")}
              className={`text-sm font-semibold px-4 py-1.5 rounded-lg transition-colors ${
                pageView === "standings"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Standings
            </button>
            <button
              onClick={() => setPageView("bracket")}
              className={`text-sm font-semibold px-4 py-1.5 rounded-lg transition-colors ${
                pageView === "bracket"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Playoff
            </button>
          </div>
        )}
      </div>

      {/* Bracket view */}
      {pageView === "bracket" && <PlayoffBracket hideHeader />}

      {/* Season standings */}
      {pageView === "standings" && isLoading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : pageView === "standings" && standings ? (
        <div className="space-y-3">
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold w-12">Pos</th>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Member</th>
                  <th className="px-4 py-2.5 text-right text-xs uppercase tracking-wider font-semibold">Points</th>
                </tr>
              </thead>
              <tbody>
                {displayedRows.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-gray-400 text-sm">
                      No standings yet — picks will appear after tournaments complete.
                    </td>
                  </tr>
                ) : (
                  <>
                    {displayedRows.map((row, i) => (
                      <StandingsTr
                        key={row.user_id}
                        row={row}
                        isMe={row.user_id === currentUserId}
                        stripe={i % 2 !== 0}
                      />
                    ))}
                    {currentUserSeparatorRow && (
                      <StandingsTr
                        key={currentUserSeparatorRow.user_id}
                        row={currentUserSeparatorRow}
                        isMe={true}
                        stripe={false}
                        borderTop="border-t-2 border-gray-300"
                      />
                    )}
                  </>
                )}
              </tbody>
            </table>
          </div>

          {showToggle && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="inline-flex items-center gap-1 text-sm font-medium text-green-700 hover:text-green-900"
            >
              {expanded ? "Show less" : `Show all ${totalRows} members`}
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                {expanded
                  ? <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
                  : <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />}
              </svg>
            </button>
          )}
        </div>
      ) : pageView === "standings" ? (
        <p className="text-gray-400">No standings available yet.</p>
      ) : null}

      {/* Pick breakdown — hidden in bracket view */}
      {pageView === "standings" && <TournamentPicksSection leagueId={leagueId!} />}
    </div>
  );
}
