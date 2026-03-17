/**
 * PlayoffBracketCard — a single pod/matchup card for the bracket view.
 *
 * Displays members with their seed, points, and status (winner / eliminated /
 * current user). Links to the draft page when the user is in this pod and the
 * draft is open.
 */

import { Link } from "react-router-dom";
import { PlayoffPodOut } from "../api/endpoints";

interface PlayoffBracketCardProps {
  pod: PlayoffPodOut;
  leagueId: string;
  currentUserId: string;
  roundNumber: number;
  picksPerPlayer: number; // used to compute the total_slots hint in the "Draft active" badge
}

function TrophyIcon() {
  return (
    <svg
      className="w-3.5 h-3.5 text-green-600 shrink-0"
      fill="currentColor"
      viewBox="0 0 24 24"
    >
      <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
    </svg>
  );
}

export function PlayoffBracketCard({
  pod,
  leagueId,
  currentUserId,
  roundNumber,
  picksPerPlayer,
}: PlayoffBracketCardProps) {
  // Sort members by seed ascending (seed 1 = best regular-season rank)
  const sortedMembers = [...pod.members].sort((a, b) => a.seed - b.seed);

  const currentUserInPod = pod.members.some((m) => m.user_id === currentUserId);
  const isDrafting = pod.status === "drafting";
  const totalSlots = picksPerPlayer * pod.members.length;

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm hover:shadow-md transition-all min-w-[220px] w-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold uppercase tracking-wider text-gray-400">
          Round {roundNumber} &middot; Pod {pod.bracket_position}
        </span>
        {isDrafting && (
          <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            Draft Open
          </span>
        )}
      </div>

      {/* Members */}
      <div className="space-y-1">
        {sortedMembers.map((member) => {
          const isWinner = pod.winner_user_id === member.user_id;
          const isEliminated = member.is_eliminated;
          const isCurrentUser = member.user_id === currentUserId;

          return (
            <div
              key={member.user_id}
              className={[
                "flex items-center gap-2 px-2 py-1.5 rounded-xl transition-colors",
                isWinner
                  ? "bg-green-50 border-l-4 border-l-green-600"
                  : "border-l-4 border-l-transparent",
                isEliminated && !isWinner ? "opacity-50" : "",
              ].join(" ")}
            >
              {/* Seed badge */}
              <span className="text-xs font-bold text-gray-400 w-5 shrink-0 tabular-nums">
                {member.seed}
              </span>

              {/* Name */}
              <span
                className={[
                  "text-sm flex-1 truncate",
                  isCurrentUser ? "font-semibold text-gray-900" : "font-medium text-gray-800",
                ].join(" ")}
              >
                {member.display_name}
              </span>

              {/* Points or winner trophy */}
              <div className="flex items-center gap-1 shrink-0">
                {isWinner && <TrophyIcon />}
                <span className="text-sm font-bold text-gray-700 tabular-nums">
                  {member.total_points !== null
                    ? `$${member.total_points.toLocaleString()}`
                    : "—"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Draft hint — total slots */}
      {isDrafting && (
        <p className="mt-2 text-xs text-gray-400">
          {totalSlots} total draft slots &middot; {picksPerPlayer} picks/player
        </p>
      )}

      {/* CTA: submit rankings if user is in this pod and draft is open */}
      {currentUserInPod && isDrafting && (
        <Link
          to={`/leagues/${leagueId}/playoff/draft/${pod.id}`}
          className="mt-3 flex items-center justify-center gap-1 w-full bg-green-700 hover:bg-green-600 text-white text-sm font-semibold px-4 py-2 rounded-xl transition-colors"
        >
          Submit Rankings
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
          </svg>
        </Link>
      )}
    </div>
  );
}
