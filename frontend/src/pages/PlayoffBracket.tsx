/**
 * PlayoffBracket — tournament bracket view for all league members.
 *
 * Uses absolute positioning + SVG connector lines to render a proper
 * bracket tree. Three states:
 *   1. No playoff config (bracket=undefined) → empty state
 *   2. Config exists, not seeded (rounds=[]) → projected bracket from standings
 *   3. Seeded bracket → live bracket
 */

import { useEffect, useState, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "../store/authStore";
import { useBracket } from "../hooks/usePlayoff";
import { Spinner } from "../components/Spinner";
import { useStandings } from "../hooks/usePick";
import { useLeagueTournaments, useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import { FlagIcon } from "../components/FlagIcon";
import { fmtTournamentName } from "../utils";
import { tournamentsApi } from "../api/endpoints";
import type { PlayoffPodMemberOut, PlayoffPodOut, PlayoffRoundOut } from "../hooks/usePlayoff";

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const SLOT_H = 260;  // vertical px per bracket slot (one round-1 pod = 1 slot)
const COL_W  = 252;  // pod card column width
const CONN_W = 72;   // connector gap width between columns
const HDR_H  = 68;   // round label header height above pod area

// ---------------------------------------------------------------------------
// Layout helpers
// ---------------------------------------------------------------------------

/** Center Y of pod p (0-indexed) in round r (1-indexed), within the pod area. */
function podCenterY(roundNum: number, podIdx: number): number {
  const slotsPerPod = Math.pow(2, roundNum - 1);
  return (podIdx * slotsPerPod + slotsPerPod / 2) * SLOT_H;
}

function podCardHeight(numMembers: number): number {
  return 44 + numMembers * 44; // header + member rows
}

function roundLabel(roundNumber: number, total: number): string {
  const fromEnd = total - roundNumber;
  if (fromEnd === 0) return "Championship";
  if (fromEnd === 1) return "Semifinals";
  if (fromEnd === 2) return "Quarterfinals";
  return `Round ${roundNumber}`;
}

/** Mirror of backend assign_pod(). Returns 1-indexed pod for given seed. */
function assignPod(seed: number, numPods: number): number {
  const tier = Math.floor((seed - 1) / numPods);
  const posInTier = (seed - 1) % numPods;
  return tier % 2 === 0 ? posInTier + 1 : numPods - posInTier;
}

/** Derives bracket shape from playoff_size, matching backend seed_playoff. */
function bracketShape(playoffSize: number) {
  if (playoffSize === 32) {
    // Round 1: 8 pods of 4; subsequent rounds: pods of 2
    return { podSize: 4, numRounds: 4, numPodsRound1: 8 };
  }
  // All other sizes: pods of 2, numRounds = log2(playoffSize)
  const numRounds = Math.log2(playoffSize); // 2→1, 4→2, 8→3, 16→4
  return { podSize: 2, numRounds, numPodsRound1: playoffSize / 2 };
}

// ---------------------------------------------------------------------------
// Connector SVG — bracket lines between adjacent columns
// ---------------------------------------------------------------------------

function ConnectorLines({
  numRounds,
  numPodsRound1,
  totalHeight,
  faint,
}: {
  numRounds: number;
  numPodsRound1: number;
  totalHeight: number;
  faint: boolean;
}) {
  const stroke = faint ? "#e5e7eb" : "#d1d5db";
  const totalWidth = numRounds * COL_W + (numRounds - 1) * CONN_W;
  const paths: React.ReactNode[] = [];

  for (let r = 1; r < numRounds; r++) {
    const numPodsNext = Math.max(1, numPodsRound1 / Math.pow(2, r));
    const xRight = (r - 1) * (COL_W + CONN_W) + COL_W;
    const xMid   = xRight + CONN_W / 2;
    const xLeft  = xRight + CONN_W;

    for (let p = 0; p < numPodsNext; p++) {
      const y1 = podCenterY(r, 2 * p);
      const y2 = podCenterY(r, 2 * p + 1);
      const yt = podCenterY(r + 1, p);

      paths.push(
        <g key={`c${r}-${p}`} stroke={stroke} strokeWidth="2" fill="none">
          <line x1={xRight} y1={y1} x2={xMid} y2={y1} />
          <line x1={xRight} y1={y2} x2={xMid} y2={y2} />
          <line x1={xMid}  y1={y1} x2={xMid} y2={y2} />
          <line x1={xMid}  y1={yt} x2={xLeft} y2={yt} />
        </g>
      );
    }
  }

  return (
    <svg
      className="absolute pointer-events-none"
      style={{ top: HDR_H, left: 0 }}
      width={totalWidth}
      height={totalHeight}
    >
      {paths}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Bracket grid — shared container for both live and projected views
// ---------------------------------------------------------------------------

interface BracketPodSlot {
  position: number;
  numMembers: number;
  node: React.ReactNode;
}

interface BracketRoundSlot {
  roundNumber: number;
  label: string;
  status?: string;
  tournamentName?: string | null;
  pods: BracketPodSlot[];
}

function BracketGrid({
  rounds,
  numPodsRound1,
  numRounds,
  faint,
}: {
  rounds: BracketRoundSlot[];
  numPodsRound1: number;
  numRounds: number;
  faint: boolean;
}) {
  const totalHeight = numPodsRound1 * SLOT_H;
  const totalWidth  = numRounds * COL_W + (numRounds - 1) * CONN_W;

  return (
    <div
      className="relative"
      style={{ width: totalWidth, height: totalHeight + HDR_H }}
    >
      <ConnectorLines
        numRounds={numRounds}
        numPodsRound1={numPodsRound1}
        totalHeight={totalHeight}
        faint={faint}
      />

      {rounds.map((round, rIdx) => {
        const colX = rIdx * (COL_W + CONN_W);
        const sortedPods = [...round.pods].sort((a, b) => a.position - b.position);

        return (
          <div key={round.roundNumber}>
            <div
              className="absolute flex flex-col items-center justify-center gap-1.5"
              style={{ left: colX, top: 0, width: COL_W, height: HDR_H }}
            >
              <p className={`text-[11px] font-bold uppercase tracking-[0.14em] ${faint ? "text-gray-400" : "text-green-700"}`}>
                {round.label}
              </p>
              {round.tournamentName && (
                <p className="text-[10px] text-gray-400 truncate max-w-full px-2">{round.tournamentName}</p>
              )}
              {round.status && (
                <StatusPill status={round.status} />
              )}
            </div>

            {sortedPods.map((pod, pIdx) => {
              const cy    = podCenterY(round.roundNumber, pIdx);
              const cardH = podCardHeight(pod.numMembers);
              const topY  = HDR_H + cy - cardH / 2;

              return (
                <div
                  key={pod.position}
                  className="absolute"
                  style={{ left: colX, top: topY, width: COL_W }}
                >
                  {pod.node}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pod status pill
// ---------------------------------------------------------------------------

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending:   "bg-blue-100 text-blue-700",
    drafting:  "bg-amber-100 text-amber-700",
    locked:    "bg-yellow-100 text-yellow-800",
    scoring:   "bg-orange-100 text-orange-700",
    completed: "bg-green-100 text-green-700",
  };
  const label: Record<string, string> = {
    pending: "Upcoming",
    locked: "Live",
    completed: "Final",
  };
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${map[status] ?? "bg-gray-100 text-gray-500"}`}>
      {label[status] ?? status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Pod detail modal
// ---------------------------------------------------------------------------

type SelectedPod =
  | { kind: "live"; pod: PlayoffPodOut; roundStatus: string; roundNumber: number; tournamentId: string | null; tournamentName: string | null }
  | { kind: "projected"; position: number; members: ProjectedMember[]; tournamentName: string | null }
  | { kind: "pending"; position: number; tournamentName: string | null };

function PodModal({
  selected,
  leagueId,
  currentUserId,
  picksPerRound,
  onClose,
}: {
  selected: SelectedPod;
  leagueId: string;
  currentUserId: string | null;
  picksPerRound?: number[];
  onClose: () => void;
}) {
  // Extract live-pod fields before any early returns (Rules of Hooks).
  const roundStatus  = selected.kind === "live" ? selected.roundStatus  : null;
  const tournamentId = selected.kind === "live" ? selected.tournamentId : null;
  const livePod      = selected.kind === "live" ? selected.pod          : null;

  const needsLeaderboard = roundStatus === "locked" || roundStatus === "scoring";
  const { data: leaderboard } = useQuery({
    queryKey: ["tournament-leaderboard", tournamentId],
    queryFn: () => tournamentsApi.leaderboard(tournamentId!),
    enabled: needsLeaderboard && !!tournamentId,
  });

  const positionMap = useMemo(() => {
    if (!leaderboard) return new Map<string, string>();
    return new Map(
      leaderboard.entries.map((e) => {
        const pos = e.finish_position != null
          ? `${e.is_tied ? "T" : ""}${e.finish_position}`
          : "—";
        const score = e.total_score_to_par != null
          ? e.total_score_to_par === 0 ? "E"
            : e.total_score_to_par > 0 ? `+${e.total_score_to_par}`
            : `${e.total_score_to_par}`
          : "—";
        return [e.golfer_id, `${pos} (${score})`];
      })
    );
  }, [leaderboard]);

  const picksByMemberId = useMemo(() => {
    const map = new Map<number, PlayoffPodOut["picks"]>();
    if (!livePod) return map;
    for (const pick of livePod.picks) {
      const arr = map.get(pick.pod_member_id) ?? [];
      arr.push(pick);
      map.set(pick.pod_member_id, arr);
    }
    return map;
  }, [livePod]);

  // ── Pending pod ──────────────────────────────────────────────────────────
  if (selected.kind === "pending") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden" onClick={(e) => e.stopPropagation()}>
          <div className="bg-gradient-to-r from-gray-500 to-gray-400 px-5 py-3.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="text-white font-bold text-sm flex-shrink-0">Pod {selected.position}</span>
              {selected.tournamentName && <span className="text-gray-200 text-xs truncate">{selected.tournamentName}</span>}
            </div>
            <button onClick={onClose} aria-label="Close" className="text-white/60 hover:text-white transition-colors flex-shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="px-5 py-10 text-center">
            <p className="text-sm text-gray-400">Awaiting results from the previous round.</p>
          </div>
        </div>
      </div>
    );
  }

  // ── Projected pod ─────────────────────────────────────────────────────────
  if (selected.kind === "projected") {
    const sorted = [...selected.members].sort((a, b) => a.seed - b.seed);
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden" onClick={(e) => e.stopPropagation()}>
          <div className="bg-gradient-to-r from-gray-500 to-gray-400 px-5 py-3.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="text-white font-bold text-sm flex-shrink-0">Pod {selected.position}</span>
              {selected.tournamentName && <span className="text-gray-200 text-xs truncate">{selected.tournamentName}</span>}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/20 text-white italic">Projected</span>
              <button onClick={onClose} aria-label="Close" className="text-white/60 hover:text-white transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>
              </button>
            </div>
          </div>
          <div className="max-h-[65vh] overflow-y-auto divide-y divide-gray-100">
            {sorted.map((m, i) => {
              const isMe  = m.user_id === currentUserId;
              const isTbd = m.user_id === "";
              return (
                <div key={isTbd ? `tbd-${m.seed}` : m.user_id}
                  className={`flex items-center gap-2.5 px-5 py-3 ${isMe ? "bg-green-50" : i % 2 !== 0 ? "bg-gray-50" : ""}`}
                >
                  <span className="text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 bg-gray-100 text-gray-500">
                    {isTbd ? "?" : m.seed}
                  </span>
                  <span className={`flex-1 text-sm ${isMe ? "font-semibold text-gray-900" : isTbd ? "text-gray-300 italic" : "text-gray-700"}`}>
                    {m.display_name}
                                      </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Live pod ──────────────────────────────────────────────────────────────
  // roundStatus and tournamentId are already declared above (before early returns).
  const { pod, tournamentName } = selected;

  const isCompleted = roundStatus === "completed";
  const isDrafting  = roundStatus === "drafting";
  const isInPod     = pod.members.some((m) => m.user_id === currentUserId);
  const haspicks    = pod.picks.length > 0;
  const sortedMembers = [...pod.members].sort((a, b) => a.seed - b.seed);
  // Determine expected picks per member for this round.
  // Primary: picks_per_round config array. Fallback: max picks any member has, or 1.
  const expectedPicksPerMember = (() => {
    if (selected.kind === "live" && picksPerRound && picksPerRound.length > 0) {
      return picksPerRound[selected.roundNumber - 1] ?? 1;
    }
    // Fallback: infer from actual pick data (max draft_slot across all picks in this pod).
    if (pod && pod.picks.length > 0) {
      return Math.max(...pod.picks.map((p) => p.draft_slot), 1);
    }
    return 1;
  })();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-green-900 to-green-700 px-5 py-3.5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-white font-bold text-sm flex-shrink-0">Pod {pod.bracket_position}</span>
            {tournamentName && (
              <span className="text-green-300 text-xs truncate">{tournamentName}</span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button onClick={onClose} aria-label="Close" className="text-white/60 hover:text-white transition-colors ml-1">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="max-h-[65vh] overflow-y-auto divide-y divide-gray-100">
          {isDrafting && !haspicks ? (
            <div className="px-5 py-10 text-center space-y-2">
              <p className="text-sm text-gray-400">
                Rankings are being collected — picks will be assigned automatically once the tournament begins.
              </p>
              {isInPod && (
                <Link
                  to={`/leagues/${leagueId}/pick`}
                  className="inline-block text-sm font-semibold text-green-700 hover:text-green-900"
                >
                  Submit your rankings →
                </Link>
              )}
            </div>
          ) : (
            sortedMembers.map((member) => {
              const isWinner  = pod.winner_user_id === member.user_id;
              const picks     =[...(picksByMemberId.get(member.id) ?? [])].sort((a, b) => a.draft_slot - b.draft_slot);

              return (
                <div key={member.user_id}>
                  {/* Member row */}
                  <div className={`flex items-center gap-2.5 px-5 py-3 ${
                    isWinner ? "bg-green-50" : member.is_eliminated ? "bg-gray-50" : ""
                  }`}>
                    <span className="text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 bg-gray-100 text-gray-500">
                      {member.seed}
                    </span>
                    <span className={`flex-1 text-sm font-semibold truncate ${
                      isWinner ? "text-green-800" : "text-gray-900"
                    } ${member.is_eliminated ? "line-through opacity-50" : ""}`}>
                      {member.display_name}
                                          </span>
                    {isWinner && (
                      <svg className="w-4 h-4 text-amber-500 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                        <path fillRule="evenodd" d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" clipRule="evenodd" />
                      </svg>
                    )}
                    {isCompleted && member.total_points != null && (
                      <span className={`text-sm font-semibold tabular-nums flex-shrink-0 ${isWinner ? "text-green-700" : "text-gray-600"}`}>
                        ${Math.round(member.total_points).toLocaleString()}
                      </span>
                    )}
                  </div>

                  {/* Pick rows — show actual picks first, then "No pick" for missing slots */}
                  {Array.from({ length: expectedPicksPerMember }, (_, i) => {
                    const pick = picks[i];
                    if (pick) {
                      const position = positionMap.get(pick.golfer_id);
                      return (
                        <div key={pick.id} className="flex items-center gap-2 pl-12 pr-5 py-2 bg-gray-50">
                          <span className="flex-1 text-xs text-gray-700">{pick.golfer_name}</span>
                          {isCompleted && pick.points_earned != null ? (
                            <span className="text-xs font-semibold text-gray-600 tabular-nums">
                              ${Math.round(pick.points_earned).toLocaleString()}
                            </span>
                          ) : needsLeaderboard && position ? (
                            <span className="text-xs text-gray-500 tabular-nums">{position}</span>
                          ) : null}
                        </div>
                      );
                    }
                    return (
                      <div key={`no-pick-${member.user_id}-${i}`} className="flex items-center gap-2 pl-12 pr-5 py-2 bg-gray-50">
                        <span className="flex-1 text-xs font-medium text-red-400">No pick</span>
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live pod card
// ---------------------------------------------------------------------------

function PodCard({
  pod,
  currentUserId,
  roundStatus,
  onClick,
}: {
  pod: PlayoffPodOut;
  currentUserId: string | null;
  roundStatus: string;
  onClick: () => void;
}) {
  const isDraftOpen = roundStatus === "drafting";
  const isInPod     = pod.members.some((m) => m.user_id === currentUserId);

  return (
    <div
      onClick={onClick}
      className="bg-white rounded-2xl border border-gray-200 hover:shadow-md cursor-pointer transition-shadow overflow-hidden w-full"
    >
      <div className="bg-gradient-to-r from-green-900 to-green-700 px-4 py-2.5">
        <span className="text-[11px] font-bold text-white uppercase tracking-wider">Pod {pod.bracket_position}</span>
      </div>
      <div className="divide-y divide-gray-100">
        {pod.members.map((m: PlayoffPodMemberOut, i) => {
          const isWinner = pod.winner_user_id === m.user_id;
          const isMe     = m.user_id === currentUserId;
          return (
            <div
              key={m.user_id}
              className={`flex items-center gap-2.5 px-4 py-2.5 ${
                isWinner          ? "bg-green-50 border-l-2 border-l-green-400"
                : m.is_eliminated ? "opacity-40"
                : isMe            ? "bg-green-50 border-l-2 border-l-green-400"
                : i % 2 !== 0     ? "bg-gray-50"
                : ""
              }`}
            >
              <span className="text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 bg-gray-100 text-gray-500">
                {m.seed}
              </span>
              <span className={`flex-1 text-sm truncate ${isMe || isWinner ? "font-semibold text-gray-900" : "text-gray-700"} ${m.is_eliminated ? "line-through" : ""}`}>
                {m.display_name}
              </span>
              {isWinner && (
                <svg className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" clipRule="evenodd" />
                </svg>
              )}
            </div>
          );
        })}
      </div>
      {isDraftOpen && isInPod && (
        <div className="bg-amber-50 border-t border-amber-100 px-4 py-2">
          <p className="text-[11px] font-semibold text-amber-700">Rankings open — tap to submit your preferences</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pending pod card (later rounds not yet seeded)
// ---------------------------------------------------------------------------

function PendingPodCard({ position, numMembers, onClick }: { position: number; numMembers: number; onClick?: () => void }) {
  return (
    <div
      className={`bg-white rounded-2xl border border-dashed border-gray-200 overflow-hidden w-full ${onClick ? "cursor-pointer hover:shadow-md transition-shadow" : ""}`}
      onClick={onClick}
    >
      <div className="bg-gradient-to-r from-gray-500 to-gray-400 px-4 py-2.5">
        <span className="text-[11px] font-bold text-white uppercase tracking-wider">Pod {position}</span>
      </div>
      <div className="divide-y divide-gray-100">
        {Array.from({ length: numMembers }).map((_, k) => (
          <div key={k} className={`flex items-center gap-2.5 px-4 py-2.5 ${k % 2 !== 0 ? "bg-gray-50" : ""}`}>
            <span className="w-5 h-5 rounded-full bg-gray-100 flex-shrink-0" />
            <span className="text-sm text-gray-300 italic">Winner advances</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Projected pod card (pre-seeding, from standings)
// ---------------------------------------------------------------------------

type ProjectedMember = {
  seed: number;
  user_id: string;
  display_name: string;
};

function ProjectedPodCard({
  position,
  members,
  currentUserId,
  onClick,
}: {
  position: number;
  members: ProjectedMember[];
  currentUserId: string | null;
  onClick?: () => void;
}) {
  const sorted = [...members].sort((a, b) => a.seed - b.seed);
  return (
    <div
      className={`bg-white rounded-2xl border border-gray-200 overflow-hidden w-full ${onClick ? "cursor-pointer hover:shadow-md transition-shadow" : ""}`}
      onClick={onClick}
    >
      <div className="bg-gradient-to-r from-gray-500 to-gray-400 px-4 py-2.5 flex items-center justify-between">
        <span className="text-[11px] font-bold text-white uppercase tracking-wider">Pod {position}</span>
        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/20 text-white italic">Projected</span>
      </div>
      <div className="divide-y divide-gray-100">
        {sorted.map((m, i) => {
          const isMe  = m.user_id === currentUserId;
          const isTbd = m.user_id === "";
          return (
            <div
              key={isTbd ? `tbd-${m.seed}` : m.user_id}
              className={`flex items-center gap-2.5 px-4 py-2.5 ${
                isMe          ? "bg-green-50 border-l-2 border-l-green-400"
                : i % 2 !== 0 ? "bg-gray-50"
                : ""
              }`}
            >
              <span className="text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 bg-gray-100 text-gray-500">
                {isTbd ? "?" : m.seed}
              </span>
              <span className={`flex-1 text-sm truncate ${isMe ? "font-semibold text-gray-900" : isTbd ? "text-gray-300 italic" : "text-gray-700"}`}>
                {m.display_name}
                              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PlayoffBracket({ hideHeader = false }: { hideHeader?: boolean }) {
  const { leagueId }    = useParams<{ leagueId: string }>();
  const currentUser     = useAuthStore((s) => s.user);

  useEffect(() => {
    document.title = "Playoff Bracket — League Caddie";
  }, []);
  const { data: bracket, isLoading: bracketLoading } = useBracket(leagueId!);
  const { data: standingsData, isLoading: standingsLoading } = useStandings(leagueId!);
  const { data: leagueTournaments } = useLeagueTournaments(leagueId!);
  const { data: members } = useLeagueMembers(leagueId ?? "");
  const isManager = members?.some((m) => m.user_id === currentUser?.id && m.role === "manager") ?? false;
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");

  const [selectedPod, setSelectedPod] = useState<SelectedPod | null>(null);

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

  if (bracketLoading || standingsLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner />
      </div>
    );
  }

  // ── State 1: No config ────────────────────────────────────────────────────
  if (!bracket) {
    return (
      <div className="bg-gray-50 rounded-2xl p-16 text-center space-y-3">
        <div className="flex justify-center"><FlagIcon className="w-10 h-10 text-green-700" /></div>
        <p className="font-semibold text-gray-700">No playoff bracket yet</p>
        <p className="text-sm text-gray-400">The league manager will set up the playoff when the season is ready.</p>
      </div>
    );
  }

  const config = bracket.playoff_config;
  const { podSize, numRounds, numPodsRound1 } = bracketShape(config.playoff_size);

  // Projected playoff tournament names — last numRounds scheduled league tournaments.
  const projectedTournamentNames: (string | null)[] = (() => {
    if (!leagueTournaments) return Array(numRounds).fill(null);
    const scheduled = leagueTournaments
      .filter((t) => t.status === "scheduled")
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const playoffTournaments = scheduled.slice(-numRounds);
    const padded: (string | null)[] = Array(numRounds).fill(null);
    playoffTournaments.forEach((t, i) => {
      padded[numRounds - playoffTournaments.length + i] = fmtTournamentName(t.name);
    });
    return padded;
  })();

  // ── State 2: Projected bracket ────────────────────────────────────────────
  if (bracket.rounds.length === 0) {
    const topMembers = (standingsData?.rows ?? []).slice(0, config.playoff_size);
    const podsByPosition: Record<number, ProjectedMember[]> = {};
    for (let p = 1; p <= numPodsRound1; p++) podsByPosition[p] = [];

    topMembers.forEach((row, i) => {
      const seed   = i + 1;
      const podNum = assignPod(seed, numPodsRound1);
      podsByPosition[podNum].push({ seed, user_id: row.user_id, display_name: row.display_name });
    });

    let tbdCounter = 0;
    for (let p = 1; p <= numPodsRound1; p++) {
      while (podsByPosition[p].length < podSize) {
        podsByPosition[p].push({ seed: config.playoff_size + (++tbdCounter), user_id: "", display_name: "TBD" });
      }
    }

    const rounds: BracketRoundSlot[] = Array.from({ length: numRounds }, (_, i) => {
      const r = i + 1;
      const numPods       = Math.max(1, numPodsRound1 / Math.pow(2, r - 1));
      const membersPerPod = r === 1 ? podSize : 2;

      const pods: BracketPodSlot[] = Array.from({ length: numPods }, (_, pIdx) => {
        const pos = pIdx + 1;
        return {
          position:   pos,
          numMembers: membersPerPod,
          node: r === 1
            ? <ProjectedPodCard
                position={pos}
                members={podsByPosition[pos] ?? []}
                currentUserId={currentUser?.id ?? null}
                onClick={() => setSelectedPod({ kind: "projected", position: pos, members: podsByPosition[pos] ?? [], tournamentName: projectedTournamentNames[i] })}
              />
            : <PendingPodCard
                position={pos}
                numMembers={membersPerPod}
                onClick={() => setSelectedPod({ kind: "pending", position: pos, tournamentName: projectedTournamentNames[i] })}
              />,
        };
      });

      return { roundNumber: r, label: roundLabel(r, numRounds), tournamentName: projectedTournamentNames[i], pods };
    });

    return (
      <div className="space-y-6">
        {!hideHeader && <PageHeader config={config} badge="projected" />}

        <div className="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 text-sm text-amber-700">
          <strong>Projected bracket</strong> based on current standings — seedings will be confirmed when the playoff begins.
        </div>

        <div className="relative">
          <div className="overflow-x-auto pb-4">
            <BracketGrid rounds={rounds} numPodsRound1={numPodsRound1} numRounds={numRounds} faint={true} />
          </div>
          {numRounds > 1 && (
            <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-gray-50 to-transparent sm:hidden" />
          )}
        </div>

        {selectedPod && (
          <PodModal
            selected={selectedPod}
            leagueId={leagueId!}
            currentUserId={currentUser?.id ?? null}
            picksPerRound={config.picks_per_round}
            onClose={() => setSelectedPod(null)}
          />
        )}
      </div>
    );
  }

  // ── State 3: Live seeded bracket ──────────────────────────────────────────
  const totalRounds    = bracket.rounds.length;
  const liveRound1Pods = bracket.rounds[0]?.pods.length ?? numPodsRound1;

  // Determine the playoff champion: winner of the final round's only pod.
  const finalRound  = bracket.rounds[bracket.rounds.length - 1];
  const finalPod    = finalRound?.pods[0] ?? null;
  const championId  = finalPod?.winner_user_id ?? null;
  const champion    = championId
    ? finalPod!.members.find((m) => m.user_id === championId) ?? null
    : null;

  const rounds: BracketRoundSlot[] = bracket.rounds.map((round: PlayoffRoundOut) => {
    const expectedPods  = Math.max(1, liveRound1Pods / Math.pow(2, round.round_number - 1));
    const membersPerPod = round.round_number === 1 ? podSize : 2;

    let pods: BracketPodSlot[];

    if (round.pods.length === 0) {
      pods = Array.from({ length: expectedPods }, (_, i) => ({
        position:   i + 1,
        numMembers: membersPerPod,
        node:       <PendingPodCard
                    position={i + 1}
                    numMembers={membersPerPod}
                    onClick={() => setSelectedPod({ kind: "pending", position: i + 1, tournamentName: round.tournament_name ?? null })}
                  />,
      }));
    } else {
      pods = round.pods.map((pod) => ({
        position:   pod.bracket_position,
        numMembers: Math.max(pod.members.length, membersPerPod),
        node: (
          <PodCard
            pod={pod}
            currentUserId={currentUser?.id ?? null}
            roundStatus={round.status}
            onClick={() => setSelectedPod({
              kind: "live",
              pod,
              roundStatus: round.status,
              roundNumber: round.round_number,
              tournamentId: round.tournament_id ?? null,
              tournamentName: round.tournament_name ?? null,
            })}
          />
        ),
      }));
    }

    return {
      roundNumber:    round.round_number,
      label:          roundLabel(round.round_number, totalRounds),
      status:         round.status,
      tournamentName: round.tournament_name,
      pods,
    };
  });

  return (
    <div className="space-y-6">
      {!hideHeader && <PageHeader config={config} badge={config.status} />}

      {champion && (
        <div className="bg-gradient-to-r from-amber-400 to-yellow-300 rounded-2xl px-6 py-5 flex items-center gap-4 shadow-md">
          <svg className="w-10 h-10 text-amber-700 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" />
          </svg>
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-amber-800">Playoff Champion</p>
            <p className="text-2xl font-bold text-amber-900 truncate">{champion.display_name}</p>
            {champion.total_points != null && (
              <p className="text-sm font-semibold text-amber-800 mt-0.5">
                ${Math.round(champion.total_points).toLocaleString()} earned
              </p>
            )}
          </div>
        </div>
      )}

      <div className="relative">
        <div className="overflow-x-auto pb-4">
          <BracketGrid rounds={rounds} numPodsRound1={liveRound1Pods} numRounds={totalRounds} faint={false} />
        </div>
        {totalRounds > 1 && (
          <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-gray-50 to-transparent sm:hidden" />
        )}
      </div>

      {selectedPod && (
        <PodModal
          selected={selectedPod}
          leagueId={leagueId!}
          currentUserId={currentUser?.id ?? null}
          picksPerRound={config.picks_per_round}
          onClose={() => setSelectedPod(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared page header
// ---------------------------------------------------------------------------

function PageHeader({
  config,
  badge,
}: {
  config: { playoff_size: number; draft_style: string; status: string };
  badge: string;
}) {
  const badgeColors: Record<string, string> = {
    projected: "bg-amber-100 text-amber-700",
    active:    "bg-green-100 text-green-700",
    completed: "bg-slate-100 text-slate-600",
  };
  const cls = badgeColors[badge] ?? "bg-gray-100 text-gray-600";

  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">Playoff</p>
      <div className="flex items-start justify-between gap-4 mt-1">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Bracket</h1>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-xs text-gray-500">
              {config.playoff_size} members · {config.draft_style} draft
            </span>
            {badge !== "projected" && (
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${cls}`}>
                {badge}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
