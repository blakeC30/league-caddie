/**
 * PlayoffRoundBreakdown — shows pod-level picks for a playoff tournament round.
 */

import { useAuthStore } from "../../store/authStore";
import type { PlayoffRoundOut } from "../../api/endpoints";

export interface PlayoffRoundBreakdownProps {
  round: PlayoffRoundOut;
}

export function PlayoffRoundBreakdown({ round }: PlayoffRoundBreakdownProps) {
  const currentUserId = useAuthStore((s) => s.user?.id);

  // Determine if picks are visible: hidden when status is "locked" but picks arrays are all empty
  // (server enforces this until all R1 tee times pass)
  const allPicksEmpty = round.pods.every((pod) => pod.picks.length === 0);
  const picksHidden = round.status === "locked" && allPicksEmpty;

  if (round.status === "drafting") {
    return (
      <div className="bg-fairway-50 border border-fairway-200 rounded-xs p-6 text-center space-y-1">
        <p className="text-sm font-semibold text-fairway-700">Draft is open</p>
        <p className="text-xs text-fairway-600">
          Picks will be revealed after the tournament begins and all golfers have teed off.
        </p>
      </div>
    );
  }

  if (picksHidden) {
    return (
      <div className="bg-brass-50 border border-brass-100 rounded-xs p-6 text-center space-y-1">
        <p className="text-sm font-semibold text-brass-700">Tournament is underway</p>
        <p className="text-xs text-brass-600">
          Picks will be revealed once all golfers have teed off in Round 1.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {round.pods.map((pod) => {
        // Build a map from pod_member_id -> picks for easy lookup
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
          <div key={pod.id} className="bg-white border border-ink-200 rounded-xs overflow-hidden">
            <div className="px-4 py-2.5 bg-fairway-900 flex items-center justify-between">
              <span className="text-micro uppercase text-white">
                Pod {pod.bracket_position}
              </span>
              {pod.status === "completed" && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-xs bg-white/20 text-white">
                  Final
                </span>
              )}
            </div>
            <table className="min-w-full text-sm">
              <thead className="bg-ink-50 border-b border-ink-100">
                <tr>
                  <th className="px-4 py-2 text-left text-micro uppercase text-ink-400">Member</th>
                  <th className="px-4 py-2 text-left text-micro uppercase text-ink-400">Picks</th>
                  <th className="px-4 py-2 text-right text-micro uppercase text-ink-400">Points</th>
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
                      className={`border-t border-ink-100 ${
                        isMe ? "bg-fairway-50" : i % 2 === 0 ? "bg-white" : "bg-ink-50"
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          {isWinner && (
                            <span className="text-brass-600" title="Winner">★</span>
                          )}
                          <span className={`font-medium ${isMe ? "text-fairway-900" : "text-ink-900"}`}>
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
                                  className="text-[11px] px-1.5 py-0.5 rounded-xs bg-ink-100 text-ink-700 whitespace-nowrap"
                                >
                                  {p.golfer_name}
                                  {p.points_earned !== null && (
                                    <span className="ml-1 text-fairway-700 font-medium">
                                      ${Math.round(p.points_earned).toLocaleString()}
                                    </span>
                                  )}
                                </span>
                              ))}
                          </div>
                        ) : (
                          <span className="text-ink-400 text-xs italic">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums font-semibold text-ink-900">
                        {member.total_points !== null
                          ? `$${Math.round(member.total_points).toLocaleString()}`
                          : <span className="text-ink-400 font-normal">—</span>}
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
