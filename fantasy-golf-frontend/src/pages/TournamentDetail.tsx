/**
 * TournamentDetail — full leaderboard for a single tournament with expandable
 * hole-by-hole scorecards.
 *
 * Route: /leagues/:leagueId/tournaments/:tournamentId
 * Accessible by clicking any in_progress or completed row on the MyPicks page.
 *
 * Column order (ESPN-style):
 *   Pos | Golfer | Score | [Today | Thru] | R1 | R2 | R3 | R4 | [PO...] | [Earnings]
 *
 * - Score  = total score to par for the tournament (E, -10, +2)
 * - R1–R4  = score to par for that individual round; blank if not yet played
 * - PO     = playoff round columns, only when any golfer has round_number > 4
 * - Earnings = raw prize money in USD, only shown when tournament is completed
 */

import { useState, useRef, useLayoutEffect } from "react";
import { Link, useParams, useLocation } from "react-router-dom";
import { useMyPicks, useTournamentLeaderboard, useTournamentSyncStatus, useGolferScorecard } from "../hooks/usePick";
import { GolferAvatar } from "../components/GolferAvatar";
import { Spinner } from "../components/Spinner";
import { fmtTournamentName } from "../utils";
import type { LeaderboardEntry, HoleResult } from "../api/endpoints";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format score-to-par ESPN-style: negative = "-3", zero = "E", positive = "+1" */
function fmtStp(stp: number | null | undefined): string {
  if (stp === null || stp === undefined) return "";
  if (stp === 0) return "E";
  return stp > 0 ? `+${stp}` : `${stp}`;
}

function stpClass(stp: number | null | undefined): string {
  if (stp == null) return "text-gray-400";
  if (stp < 0) return "text-green-700 font-semibold";
  if (stp > 0) return "text-red-500 font-semibold";
  return "text-gray-600";
}

function formatEarnings(usd: number | null): string {
  if (usd === null || usd === 0) return "—";
  if (usd >= 1_000_000) return `$${(usd / 1_000_000).toFixed(2)}M`;
  if (usd >= 1_000) return `$${(usd / 1_000).toFixed(0)}K`;
  return `$${usd.toLocaleString()}`;
}

// Golf scorecard shapes:
//   Eagle (≤-2): double circle — rounded-full + outer ring
//   Birdie (-1):  single circle — rounded-full
//   Par (0):      no shape — plain text
//   Bogey (+1):   single square — rounded-sm border
//   Double (+2):  double square — rounded-sm border + outer ring
//   Triple+ (≥3): double square (same as double bogey, darker)
const RESULT_STYLES: Record<HoleResult, { chip: string; shape: "double-circle" | "circle" | "none" | "square" | "double-square" }> = {
  eagle:       { chip: "bg-yellow-50 text-yellow-800 border border-yellow-400 ring-2 ring-yellow-300 ring-offset-1",  shape: "double-circle" },
  birdie:      { chip: "bg-green-100 text-green-800 border border-green-400",                                          shape: "circle" },
  par:         { chip: "text-gray-600",                                                                                shape: "none" },
  bogey:       { chip: "bg-red-50 text-red-600 border border-red-300",                                                shape: "square" },
  double_bogey:{ chip: "bg-red-100 text-red-700 border border-red-400 ring-2 ring-red-300 ring-offset-1",             shape: "double-square" },
  triple_plus: { chip: "bg-red-200 text-red-800 border border-red-500 ring-2 ring-red-400 ring-offset-1",             shape: "double-square" },
};

const RESULT_LABELS: Record<HoleResult, string> = {
  eagle:       "Eagle",
  birdie:      "Birdie",
  par:         "Par",
  bogey:       "Bogey",
  double_bogey:"Double",
  triple_plus: "Triple+",
};

// ---------------------------------------------------------------------------
// Scorecard panel (rendered as a full-width table row)
// ---------------------------------------------------------------------------

function ScorecardPanel({
  tournamentId,
  entry,
  availableRounds,
  colSpan,
  isLive,
}: {
  tournamentId: string;
  entry: LeaderboardEntry;
  availableRounds: number[];
  colSpan: number;
  isLive: boolean;
}) {
  const [round, setRound] = useState<number>(availableRounds[availableRounds.length - 1] ?? 1);
  const [showLegend, setShowLegend] = useState(false);
  const { data: scorecard, isLoading } = useGolferScorecard(tournamentId, entry.golfer_id, round, isLive);

  const isPlayoff = round > 4;

  // Always measure the regular-round table width so the wrapper never shrinks
  // when switching to the narrower playoff scorecard — even if the panel opens
  // directly on a playoff round. A hidden phantom table (same column structure)
  // is always in the DOM so the ref is always populated on first paint.
  const phantomTableRef = useRef<HTMLTableElement>(null);
  const [minWrapperWidth, setMinWrapperWidth] = useState<number | undefined>(undefined);
  useLayoutEffect(() => {
    if (phantomTableRef.current) {
      setMinWrapperWidth(phantomTableRef.current.offsetWidth);
    }
  }, []);

  // Regular rounds: always show all 18 holes; holes not yet played have null scores.
  // This ensures the full scorecard is visible during a live round, not just completed holes.
  // Use Number() to normalize hole keys: ESPN may return period as string "1" instead of int 1.
  // JavaScript Map uses strict equality, so "1" !== 1 — without Number() all lookups would miss.
  const holeMap = new Map(scorecard?.holes.map((h) => [Number(h.hole), h]) ?? []);
  const blankHole = (n: number) => ({ hole: n, par: null, score: null, score_to_par: null, result: null });
  const front = !isPlayoff ? Array.from({ length: 9 }, (_, i) => holeMap.get(i + 1)  ?? blankHole(i + 1))  : [];
  const back  = !isPlayoff ? Array.from({ length: 9 }, (_, i) => holeMap.get(i + 10) ?? blankHole(i + 10)) : [];
  const frontPar = front.reduce((s, h) => s + (h.par ?? 0), 0);
  const backPar  = back.reduce((s,  h) => s + (h.par ?? 0), 0);
  const frontScore = front.every((h) => h.score !== null) ? front.reduce((s, h) => s + (h.score ?? 0), 0) : null;
  const backScore  = back.every((h)  => h.score !== null) ? back.reduce((s,  h) => s + (h.score  ?? 0), 0) : null;

  // Playoff rounds: show all holes in a flat list (typically 1–3 sudden-death holes)
  const playoffHoles = isPlayoff ? (scorecard?.holes ?? []) : [];

  function renderHoleCell(h: { hole: number; par: number | null; score: number | null; score_to_par: number | null; result: HoleResult | null }, tdClass: string) {
    return (
      <td key={h.hole} className={tdClass}>
        {h.score !== null && h.result ? (() => {
          const { chip, shape } = RESULT_STYLES[h.result];
          const rounded = shape === "circle" || shape === "double-circle" ? "rounded-full" : shape === "none" ? "" : "rounded-sm";
          return <span className={`inline-flex items-center justify-center w-6 h-6 text-xs font-bold tabular-nums ${rounded} ${chip}`}>{h.score}</span>;
        })() : <span className="inline-flex items-center justify-center w-6 h-6"><span className="block w-3 h-px bg-gray-600 rounded-full" /></span>}
      </td>
    );
  }

  return (
    <tr>
      <td colSpan={colSpan} className="p-0">
        <div className="bg-gray-50 border-t border-gray-100 px-5 py-4">
          {/* Phantom table — always in the DOM, invisible, zero height.
              Must be a structural clone of the real regular-round table
              (same element types, classes, and representative content)
              so its measured offsetWidth matches the real table exactly.
              This gives minWrapperWidth a correct value even when the panel
              opens directly on a playoff round. */}
          <div aria-hidden style={{ visibility: "hidden", height: 0, overflow: "hidden", position: "absolute", pointerEvents: "none" }}>
            <table ref={phantomTableRef} className="text-xs border-collapse min-w-max">
              <thead>
                <tr className="text-gray-400">
                  <th className="pr-3 pb-1 text-left font-semibold w-14">Hole</th>
                  {[1,2,3,4,5,6,7,8,9].map((n) => (
                    <th key={n} className="px-1 pb-1 text-center w-7 font-medium tabular-nums">{n}</th>
                  ))}
                  <th className="px-2 pb-1 text-center font-semibold text-gray-500 w-10">Out</th>
                  {[10,11,12,13,14,15,16,17,18].map((n) => (
                    <th key={n} className="px-1 pb-1 text-center w-7 font-medium tabular-nums">{n}</th>
                  ))}
                  <th className="px-2 pb-1 text-center font-semibold text-gray-500 w-10">In</th>
                  <th className="pl-2 pb-1 text-center font-semibold text-gray-700 w-12">Total</th>
                </tr>
                <tr className="text-gray-400 border-b border-gray-200">
                  <td className="pr-3 pb-1.5 font-semibold">Par</td>
                  {Array.from({ length: 9 }, (_, i) => (
                    <td key={i} className="px-1 pb-1.5 text-center tabular-nums">4</td>
                  ))}
                  <td className="px-2 pb-1.5 text-center font-semibold text-gray-500 tabular-nums">36</td>
                  {Array.from({ length: 9 }, (_, i) => (
                    <td key={i + 9} className="px-1 pb-1.5 text-center tabular-nums">4</td>
                  ))}
                  <td className="px-2 pb-1.5 text-center font-semibold text-gray-500 tabular-nums">36</td>
                  <td className="pl-2 pb-1.5 text-center font-semibold text-gray-700 tabular-nums">72</td>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="pr-3 pt-1.5 font-semibold text-gray-700">Score</td>
                  {Array.from({ length: 18 }, (_, i) => (
                    <td key={i} className="px-1 pt-1.5 text-center">
                      <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold tabular-nums rounded-sm">4</span>
                    </td>
                  ))}
                  <td className="px-2 pt-1.5 text-center font-bold tabular-nums text-gray-700">36</td>
                  <td className="px-2 pt-1.5 text-center font-bold tabular-nums text-gray-700">36</td>
                  <td className="pl-2 pt-1.5 text-center font-bold tabular-nums">72</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="mx-auto space-y-3" style={{ width: "fit-content", minWidth: minWrapperWidth }}>
          {/* Round tabs */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide mr-1">Round</span>
            {availableRounds.map((r) => (
              <button
                key={r}
                onClick={() => setRound(r)}
                className={`text-xs font-semibold px-2.5 py-1 rounded-full transition-colors ${
                  round === r
                    ? r > 4 ? "bg-amber-500 text-white" : "bg-green-800 text-white"
                    : "bg-white border border-gray-200 text-gray-500 hover:border-green-400 hover:text-green-700"
                }`}
              >
                {r <= 4 ? `R${r}` : `Playoff${availableRounds.filter((x) => x > 4).length > 1 ? ` ${r - 4}` : ""}`}
              </button>
            ))}
            {isPlayoff && (
              <span className="ml-1 text-xs font-semibold text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                Sudden Death
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="py-2"><Spinner className="w-4 h-4 text-gray-300" /></div>
          ) : !scorecard || scorecard.holes.length === 0 ? (
            <p className="text-sm text-gray-400 py-2">
              {isPlayoff
                ? "Hole-by-hole playoff data is not available."
                : "Hole-by-hole data is not available for this round."}
            </p>
          ) : isPlayoff ? (
            /* ── Playoff layout: flat hole list, no front/back split ── */
            <>
              <div className="overflow-x-auto pb-1">
                <table className="text-xs border-collapse">
                  <thead>
                    <tr className="text-gray-400">
                      <th className="pr-4 pb-1 text-left font-semibold w-16">Hole</th>
                      {playoffHoles.map((h) => (
                        <th key={h.hole} className="px-1 pb-1 text-center w-7 font-medium tabular-nums">{h.hole}</th>
                      ))}
                      <th className="pl-3 pb-1 text-center font-semibold text-gray-700 w-14">Result</th>
                    </tr>
                    <tr className="text-gray-400 border-b border-gray-200">
                      <td className="pr-4 pb-1.5 font-semibold">Par</td>
                      {playoffHoles.map((h) => (
                        <td key={h.hole} className="px-1 pb-1.5 text-center tabular-nums">{h.par ?? "—"}</td>
                      ))}
                      <td className="pl-3 pb-1.5 text-center font-semibold text-gray-500 tabular-nums">
                        {playoffHoles.reduce((s, h) => s + (h.par ?? 0), 0) || "—"}
                      </td>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="pr-4 pt-1.5 font-semibold text-gray-700">Score</td>
                      {playoffHoles.map((h) => renderHoleCell(h, "px-1 pt-1.5 text-center"))}
                      <td className={`pl-3 pt-1.5 text-center font-bold tabular-nums ${stpClass(scorecard.total_score_to_par)}`}>
                        {scorecard.total_score ?? "—"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="mt-3">
                <button
                  onClick={() => setShowLegend((v) => !v)}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showLegend ? "Hide legend ▲" : "Legend ▼"}
                </button>
                {showLegend && (
                  <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-2">
                    {(Object.keys(RESULT_STYLES) as HoleResult[]).map((r) => {
                      const { chip, shape } = RESULT_STYLES[r];
                      const rounded = shape === "circle" || shape === "double-circle" ? "rounded-full" : shape === "none" ? "" : "rounded-sm";
                      return (
                        <span key={r} className={`inline-flex items-center justify-center px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${rounded} ${chip}`}>
                          {RESULT_LABELS[r]}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          ) : (
            /* ── Regular round layout: front 9 / Out / back 9 / In / Total ── */
            <>
              <div className="overflow-x-auto pb-1">
                <table className="text-xs border-collapse min-w-max">
                  <thead>
                    <tr className="text-gray-400">
                      <th className="pr-3 pb-1 text-left font-semibold w-14">Hole</th>
                      {front.map((h) => (
                        <th key={h.hole} className="px-1 pb-1 text-center w-7 font-medium tabular-nums">{h.hole}</th>
                      ))}
                      <th className="px-2 pb-1 text-center font-semibold text-gray-500 w-10">Out</th>
                      {back.map((h) => (
                        <th key={h.hole} className="px-1 pb-1 text-center w-7 font-medium tabular-nums">{h.hole}</th>
                      ))}
                      {back.length > 0 && <th className="px-2 pb-1 text-center font-semibold text-gray-500 w-10">In</th>}
                      <th className="pl-2 pb-1 text-center font-semibold text-gray-700 w-12">Total</th>
                    </tr>
                    <tr className="text-gray-400 border-b border-gray-200">
                      <td className="pr-3 pb-1.5 font-semibold">Par</td>
                      {front.map((h) => <td key={h.hole} className="px-1 pb-1.5 text-center tabular-nums">{h.par ?? "—"}</td>)}
                      <td className="px-2 pb-1.5 text-center font-semibold text-gray-500 tabular-nums">{frontPar || "—"}</td>
                      {back.map((h)  => <td key={h.hole} className="px-1 pb-1.5 text-center tabular-nums">{h.par ?? "—"}</td>)}
                      {back.length > 0 && <td className="px-2 pb-1.5 text-center font-semibold text-gray-500 tabular-nums">{backPar || "—"}</td>}
                      <td className="pl-2 pb-1.5 text-center font-semibold text-gray-700 tabular-nums">{(frontPar + backPar) || "—"}</td>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="pr-3 pt-1.5 font-semibold text-gray-700">Score</td>
                      {front.map((h) => renderHoleCell(h, "px-1 pt-1.5 text-center"))}
                      <td className="px-2 pt-1.5 text-center font-bold tabular-nums text-gray-700">{frontScore ?? "—"}</td>
                      {back.map((h) => renderHoleCell(h, "px-1 pt-1.5 text-center"))}
                      {back.length > 0 && <td className="px-2 pt-1.5 text-center font-bold tabular-nums text-gray-700">{backScore ?? "—"}</td>}
                      <td className={`pl-2 pt-1.5 text-center font-bold tabular-nums ${frontScore !== null && backScore !== null ? stpClass(scorecard.total_score_to_par) : ""}`}>
                        {frontScore !== null && backScore !== null ? (scorecard.total_score ?? "—") : "—"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="mt-3">
                <button
                  onClick={() => setShowLegend((v) => !v)}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showLegend ? "Hide legend ▲" : "Legend ▼"}
                </button>
                {showLegend && (
                  <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-2">
                    {(Object.keys(RESULT_STYLES) as HoleResult[]).map((r) => {
                      const { chip, shape } = RESULT_STYLES[r];
                      const rounded = shape === "circle" || shape === "double-circle" ? "rounded-full" : shape === "none" ? "" : "rounded-sm";
                      return (
                        <span key={r} className={`inline-flex items-center justify-center px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${rounded} ${chip}`}>
                          {RESULT_LABELS[r]}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
          </div>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function TournamentDetail() {
  const { leagueId, tournamentId } = useParams<{ leagueId: string; tournamentId: string }>();
  const location = useLocation();
  const [expandedGolferId, setExpandedGolferId] = useState<string | null>(null);

  const { data: leaderboard, isLoading, error, refetch } = useTournamentLeaderboard(tournamentId);
  // Polls sync-status every 30 s and auto-invalidates the leaderboard query when
  // last_synced_at changes, ensuring the table only refreshes after a full sync.
  useTournamentSyncStatus(tournamentId);
  const { data: myPicks } = useMyPicks(leagueId!);

  const myPickedGolferId = myPicks?.find((p) => p.tournament_id === tournamentId)?.golfer_id ?? null;

  // Playoff picks passed via router state when navigating from MyPicks for a playoff tournament.
  // These are used to star the assigned golfers on the leaderboard instead of a regular pick.
  const playoffPickNames: string[] = (location.state as { playoffPickNames?: string[] } | null)?.playoffPickNames ?? [];
  const playoffPickSet = new Set(playoffPickNames);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  if (error || !leaderboard) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <Link to={`/leagues/${leagueId}/picks`} className="inline-flex items-center gap-1.5 text-sm text-green-700 hover:text-green-900 transition-colors">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
          Back to Picks
        </Link>
        <p className="text-gray-500">Leaderboard not available for this tournament.</p>
        {error && (
          <button
            onClick={() => refetch()}
            className="text-sm font-medium text-green-700 hover:text-green-900 underline"
          >
            Try again
          </button>
        )}
      </div>
    );
  }

  const isCompleted = leaderboard.tournament_status === "completed";
  const isTeamEvent = leaderboard.is_team_event;

  // The "current round" is the highest round number where any golfer has started
  // (thru > 0). All Today/Thru display and tie-breaking thru sorts are anchored to
  // this round so every row reflects the same round consistently.
  const currentRoundNumber = !isCompleted
    ? leaderboard.entries.reduce(
        (max, e) => e.rounds.reduce(
          (m, rd) => (rd.thru !== null && rd.thru > 0 ? Math.max(m, rd.round_number) : m), max
        ), 1
      )
    : 0;

  // For team events, deduplicate entries so each pair appears once.
  // Both partners share the same position/score — we keep the first occurrence
  // of each team (by sort order) and skip the partner entry when we encounter it.
  const displayEntries = (() => {
    let entries = leaderboard.entries;
    if (isTeamEvent) {
      const seen = new Set<string>();
      entries = entries.filter((e) => {
        if (seen.has(e.golfer_id)) return false;
        seen.add(e.golfer_id);
        if (e.partner_golfer_id) seen.add(e.partner_golfer_id);
        return true;
      });
    }

    // For live tournaments, sort by:
    // 1. Active players first, then CUT/MDF, then WD/DQ (mirrors backend tier logic)
    // 2. Score ascending within each tier (nulls last)
    // 3. Thru descending within the current round (more holes played ranks higher)
    // 4. Name ascending (alphabetical tiebreaker)
    if (!isCompleted) {
      // Three-tier sort matching the backend: active → CUT/MDF → WD/DQ.
      // This prevents CUT golfers from sorting by score among active players,
      // which would interleave them and produce multiple cut-line dividers.
      const sortTier = (e: typeof entries[0]): number => {
        if (e.status === "WD" || e.status === "DQ") return 2;
        if (e.status === "CUT" || e.status === "MDF") return 1;
        return 0;
      };
      const getThru = (e: typeof entries[0]): number => {
        const rd = e.rounds.find((x) => x.round_number === currentRoundNumber);
        return rd?.thru ?? -1;
      };
      entries = [...entries].sort((a, b) => {
        const tierDiff = sortTier(a) - sortTier(b);
        if (tierDiff !== 0) return tierDiff;
        if (a.total_score_to_par !== b.total_score_to_par) {
          if (a.total_score_to_par === null) return 1;
          if (b.total_score_to_par === null) return -1;
          return a.total_score_to_par - b.total_score_to_par;
        }
        const thruDiff = getThru(b) - getThru(a);
        if (thruDiff !== 0) return thruDiff;
        return a.golfer_name.localeCompare(b.golfer_name);
      });
    }

    return entries;
  })();

  // Detect playoff rounds using the is_playoff flag (not round_number > 4,
  // which can pick up spurious ESPN data for non-playoff entries).
  const playoffRoundNums = [
    ...new Set(
      displayEntries.flatMap((e) =>
        e.rounds.filter((r) => r.is_playoff).map((r) => r.round_number)
      )
    ),
  ].sort((a, b) => a - b);


  function posLabel(entry: LeaderboardEntry): string {
    if (entry.finish_position !== null) {
      return entry.is_tied ? `T${entry.finish_position}` : `${entry.finish_position}`;
    }
    if (entry.status === "WD" || entry.status === "CUT" || entry.status === "MDF" || entry.status === "DQ") {
      return entry.status;
    }
    return "—";
  }

  function isWithdrawnOrCut(entry: LeaderboardEntry): boolean {
    return entry.status === "WD" || entry.status === "CUT" || entry.status === "MDF" || entry.status === "DQ";
  }

  const isLive = !isCompleted;

  // Total column count for scorecard colspan.
  // The rightmost column is always present: Earnings (completed) or a spacer (live/scheduled).
  const totalCols =
    2 /* pos + golfer */ + 1 /* score */ + 4 /* R1-R4 */ +
    playoffRoundNums.length +
    (isLive ? 2 /* Today + Thru */ : 0) +
    1 /* Earnings or spacer */;

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Back link */}
      <Link
        to={`/leagues/${leagueId}/picks`}
        className="inline-flex items-center gap-1.5 text-sm text-green-700 hover:text-green-900 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
        </svg>
        Back to Picks
      </Link>

      {/* Tournament header */}
      <div className="relative overflow-hidden bg-gradient-to-r from-green-900 to-green-700 text-white rounded-2xl px-6 py-5">
        <div className="absolute -top-6 -right-6 w-32 h-32 rounded-full bg-white/5 blur-2xl pointer-events-none" />
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-300 mb-1">
          {isCompleted ? "Final" : "Live"}
        </p>
        <p className="text-xl font-bold">{fmtTournamentName(leaderboard.tournament_name)}</p>
        {(myPickedGolferId || playoffPickNames.length > 0) && (
          <p className="text-sm text-green-300 mt-1">Your pick{playoffPickNames.length > 1 ? "s are" : " is"} highlighted below</p>
        )}
      </div>

      {/* Leaderboard table */}
      {leaderboard.entries.length === 0 ? (
        <p className="text-gray-400 text-sm">No field data available yet.</p>
      ) : (
        <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-left">
                  <th className="px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide w-14">Pos</th>
                  <th className="px-3 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide">Golfer</th>
                  <th className="px-3 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide text-center w-14">Score</th>
                  {isLive && (
                    <>
                      <th className="px-2 py-2.5 text-xs font-semibold text-green-600 uppercase tracking-wide text-center w-14">Today</th>
                      <th className="px-2 py-2.5 text-xs font-semibold text-green-600 uppercase tracking-wide text-center w-12">Thru</th>
                    </>
                  )}
                  {[1, 2, 3, 4].map((r) => (
                    <th key={r} className="px-2 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide text-center w-10">R{r}</th>
                  ))}
                  {playoffRoundNums.map((r, i) => (
                    <th key={r} className="px-2 py-2.5 text-xs font-semibold text-amber-500 uppercase tracking-wide text-center w-10">
                      {playoffRoundNums.length === 1 ? "PO" : `PO${i + 1}`}
                    </th>
                  ))}
                  {isCompleted
                    ? <th className="px-4 py-2.5 text-xs font-semibold text-gray-400 uppercase tracking-wide text-right">Earnings</th>
                    : <th className="w-28" />
                  }
                </tr>
              </thead>
              <tbody>
                {displayEntries.map((entry, idx) => {
                  const isMyPick = (myPickedGolferId !== null && (entry.golfer_id === myPickedGolferId || entry.partner_golfer_id === myPickedGolferId))
                    || playoffPickSet.has(entry.golfer_name);
                  const isFaded = isWithdrawnOrCut(entry);
                  const isExpanded = expandedGolferId === entry.golfer_id;

                  // Rounds that have actually started: have a score or at least one hole played.
                  // Tee times alone don't qualify — R2 tee times are stored days before play begins.
                  const availableRounds = entry.rounds
                    .filter((r) => r.score !== null || (r.thru !== null && r.thru > 0))
                    .map((r) => r.round_number)
                    .sort((a, b) => a - b);

                  // Show the cut line above the first player who did not make the cut
                  const prevEntry = idx > 0 ? displayEntries[idx - 1] : null;
                  const showCutLine = !entry.made_cut && (prevEntry === null || prevEntry.made_cut);

                  return (
                    <>
                      {showCutLine && (
                        <tr key={`cut-line-${idx}`} className="border-b border-gray-100">
                          <td colSpan={totalCols} className="px-4 py-1.5 bg-gray-50">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-px bg-gray-300" />
                              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">Cut Line</span>
                              <div className="flex-1 h-px bg-gray-300" />
                            </div>
                          </td>
                        </tr>
                      )}
                      <tr
                        key={entry.golfer_id}
                        onClick={() => availableRounds.length > 0 && setExpandedGolferId((p) => p === entry.golfer_id ? null : entry.golfer_id)}
                        className={[
                          "border-b border-gray-100 last:border-0 transition-colors",
                          isMyPick ? "border-l-2 border-l-green-600 bg-green-50 hover:bg-green-100" : "hover:bg-gray-50",
                          availableRounds.length > 0 ? "cursor-pointer" : "cursor-default",
                          isFaded ? "opacity-50" : "",
                        ].filter(Boolean).join(" ")}
                      >
                        {/* Position */}
                        <td className={`px-4 py-3 text-sm font-bold tabular-nums ${isFaded ? "text-gray-400" : "text-gray-800"}`}>
                          {posLabel(entry)}
                        </td>

                        {/* Golfer */}
                        <td className="px-3 py-3">
                          {isTeamEvent && entry.partner_name ? (
                            /* Team event: show both partners stacked */
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="relative shrink-0 w-12 h-8">
                                <GolferAvatar
                                  pgaTourId={entry.golfer_pga_tour_id}
                                  name={entry.golfer_name}
                                  className="w-8 h-8 absolute left-0 top-0 ring-2 ring-white"
                                />
                                <GolferAvatar
                                  pgaTourId={entry.partner_golfer_pga_tour_id ?? ""}
                                  name={entry.partner_name}
                                  className="w-8 h-8 absolute left-4 top-0 ring-2 ring-white"
                                />
                              </div>
                              <div className="min-w-0">
                                <p className={`text-sm font-semibold truncate ${isMyPick ? "text-green-900" : "text-gray-800"}`}>
                                  {entry.golfer_id === myPickedGolferId ? (
                                    <><span className="text-green-600">★</span> {entry.golfer_name} / {entry.partner_name}</>
                                  ) : entry.partner_golfer_id === myPickedGolferId ? (
                                    <>{entry.golfer_name} / <span className="text-green-600">★</span> {entry.partner_name}</>
                                  ) : (
                                    <>{entry.golfer_name} / {entry.partner_name}</>
                                  )}
                                </p>
                                {entry.golfer_country && (
                                  <p className="text-xs text-gray-400">{entry.golfer_country}</p>
                                )}
                              </div>
                            </div>
                          ) : (
                            /* Individual event: single golfer */
                            <div className="flex items-center gap-2 min-w-0">
                              <GolferAvatar
                                pgaTourId={entry.golfer_pga_tour_id}
                                name={entry.golfer_name}
                                className="w-8 h-8 shrink-0"
                              />
                              <div className="min-w-0">
                                <p className={`text-sm font-semibold truncate ${isMyPick ? "text-green-900" : "text-gray-800"}`}>
                                  {entry.golfer_name}
                                  {isMyPick && (
                                    <span className="ml-1.5 text-xs font-bold text-green-600">★</span>
                                  )}
                                </p>
                                {entry.golfer_country && (
                                  <p className="text-xs text-gray-400">{entry.golfer_country}</p>
                                )}
                              </div>
                            </div>
                          )}
                        </td>

                        {/* Score (total to par) */}
                        <td className={`px-3 py-3 text-sm text-center font-bold tabular-nums ${stpClass(entry.total_score_to_par)}`}>
                          {fmtStp(entry.total_score_to_par) || "—"}
                        </td>

                        {/* Today + Thru (live tournaments only) */}
                        {isLive && (() => {
                          // Priority: a round actively in progress (0 < thru < 18),
                          // then the most recently completed round (thru === 18).
                          // Anchor to the current round so every row reflects the same round.
                          const currentRd = entry.rounds.find((x) => x.round_number === currentRoundNumber) ?? null;
                          const notStarted = currentRd === null || (currentRd.thru === null || currentRd.thru === 0);
                          const todayStp = !notStarted ? currentRd!.score_to_par : null;
                          const nextRd = entry.rounds.find((x) => x.round_number === currentRoundNumber + 1) ?? null;
                          const thruLabel = notStarted
                            ? currentRd?.tee_time
                                ? new Date(currentRd.tee_time).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) +
                                  (currentRd.started_on_back ? "*" : "")
                                : "—"
                            : currentRd!.thru === 18
                            ? nextRd?.tee_time
                                ? new Date(nextRd.tee_time).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) +
                                  (nextRd.started_on_back ? "*" : "")
                                : "F"
                            : `${currentRd!.thru}${currentRd!.started_on_back ? "*" : ""}`;
                          return (
                            <>
                              <td className={`px-2 py-3 text-xs text-center tabular-nums font-semibold ${todayStp !== null ? stpClass(todayStp) : "text-gray-300"}`}>
                                {todayStp !== null ? fmtStp(todayStp) : "—"}
                              </td>
                              <td className="px-2 py-3 text-xs text-center tabular-nums text-gray-500">
                                {thruLabel}
                              </td>
                            </>
                          );
                        })()}

                        {/* R1–R4 */}
                        {[1, 2, 3, 4].map((r) => {
                          const rd = entry.rounds.find((x) => x.round_number === r);
                          // Show the round score only if it's complete (thru=18) or
                          // the tournament is finished. Suppresses partial in-progress scores.
                          const roundComplete = isCompleted || rd?.thru === 18;
                          const hasScore = roundComplete && rd?.score_to_par !== null && rd?.score_to_par !== undefined;
                          return (
                            <td key={r} className={`px-2 py-3 text-xs text-center tabular-nums ${hasScore ? stpClass(rd!.score_to_par) : ""}`}>
                              {hasScore ? fmtStp(rd!.score_to_par) : <span className="block mx-auto w-3 h-px bg-gray-600 rounded-full" />}
                            </td>
                          );
                        })}

                        {/* Playoff rounds */}
                        {playoffRoundNums.map((r) => {
                          const rd = entry.rounds.find((x) => x.round_number === r);
                          const roundComplete = isCompleted || rd?.thru === 18;
                          const hasScore = roundComplete && rd?.score_to_par !== null && rd?.score_to_par !== undefined;
                          return (
                            <td key={r} className={`px-2 py-3 text-xs text-center tabular-nums ${hasScore ? stpClass(rd!.score_to_par) : ""}`}>
                              {hasScore ? fmtStp(rd!.score_to_par) : <span className="block mx-auto w-3 h-px bg-gray-600 rounded-full" />}
                            </td>
                          );
                        })}

                        {/* Earnings / spacer */}
                        {isCompleted
                          ? <td className="px-4 py-3 text-xs text-right tabular-nums text-gray-600">{formatEarnings(entry.earnings_usd)}</td>
                          : <td />
                        }
                      </tr>

                      {/* Expanded scorecard row */}
                      {isExpanded && availableRounds.length > 0 && (
                        <ScorecardPanel
                          key={`scorecard-${entry.golfer_id}`}
                          tournamentId={tournamentId!}
                          entry={entry}
                          availableRounds={availableRounds}
                          colSpan={totalCols}
                          isLive={isLive}
                        />
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
