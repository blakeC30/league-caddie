/**
 * PlayoffDraft — per-pod draft interface.
 *
 * Shows:
 *   - Pod members and their submission status (who has submitted, how many ranked)
 *   - After resolution: the resolved picks with golfer names and points
 *   - For the current user: a ranked preference list editor with the tournament field
 *
 * Route: /leagues/:leagueId/playoff/draft/:podId
 */

import { Link, useParams } from "react-router-dom";
import { FlagIcon } from "../components/FlagIcon";
import { Spinner } from "../components/Spinner";
import { PlayoffPreferenceEditor } from "../components/PlayoffPreferenceEditor";
import { useAuthStore } from "../store/authStore";
import {
  useBracket,
  useMyPreferences,
  usePodDraftStatus,
} from "../hooks/usePlayoff";
import { useLeagueMembers, useLeaguePurchase } from "../hooks/useLeague";
import type { PlayoffDraftStatus, PlayoffPickOut } from "../hooks/usePlayoff";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPoints(pts: number | null): string {
  if (pts === null) return "—";
  return `$${Math.round(pts).toLocaleString()}`;
}

// ---------------------------------------------------------------------------
// Draft status card — who has submitted
// ---------------------------------------------------------------------------

function DraftStatusCard({ draftStatus }: { draftStatus: PlayoffDraftStatus }) {
  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-5 space-y-3">
      <h2 className="text-sm font-bold text-gray-800">Submission Status</h2>
      <div className="divide-y divide-gray-50">
        {draftStatus.members.map((m) => (
          <div key={m.user_id} className="flex items-center justify-between py-2.5 gap-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold w-5 h-5 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center flex-shrink-0">
                {m.seed}
              </span>
              <span className="text-sm text-gray-700">{m.display_name}</span>
              <span className="text-xs text-gray-400">#{m.draft_position}</span>
            </div>
            {m.has_submitted ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
                {m.preference_count} ranked
              </span>
            ) : (
              <span className="text-[11px] text-amber-600 font-medium bg-amber-50 px-2 py-0.5 rounded-full">
                Not submitted
              </span>
            )}
          </div>
        ))}
      </div>
      {draftStatus.deadline && (
        <p className="text-[11px] text-gray-400">
          Rankings lock at tournament start ·{" "}
          {new Date(draftStatus.deadline).toLocaleDateString(undefined, {
            weekday: "short",
            month: "short",
            day: "numeric",
          })}
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Resolved picks view
// ---------------------------------------------------------------------------

function ResolvedPicksCard({ picks }: { picks: PlayoffPickOut[] }) {
  if (picks.length === 0) return null;

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-5 space-y-3">
      <h2 className="text-sm font-bold text-gray-800">Resolved Picks</h2>
      <div className="space-y-1">
        {picks.map((p) => (
          <div key={p.id} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold w-5 h-5 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center flex-shrink-0">
                {p.draft_slot}
              </span>
              <span className="text-sm text-gray-700">{p.golfer_name}</span>
            </div>
            <span className={`text-sm tabular-nums font-medium ${p.points_earned !== null ? "text-gray-800" : "text-gray-300"}`}>
              {fmtPoints(p.points_earned)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PlayoffDraft() {
  const { leagueId, podId } = useParams<{ leagueId: string; podId: string }>();
  const currentUser = useAuthStore((s) => s.user);
  const { data: members } = useLeagueMembers(leagueId ?? "");
  const isManager = members?.some((m) => m.user_id === currentUser?.id && m.role === "manager") ?? false;
  const { data: purchase, isLoading: purchaseLoading } = useLeaguePurchase(leagueId ?? "");

  const podIdNum = podId ? Number(podId) : null;
  const { data: draftStatus, isLoading, isError, refetch } = usePodDraftStatus(leagueId!, podIdNum);
  const { data: myPreferences = [] } = useMyPreferences(leagueId!, podIdNum);

  // Get tournament_id from the bracket cache (bracket is typically already loaded from PlayoffBracket)
  const { data: bracket } = useBracket(leagueId!);
  const bracketTournamentId = bracket?.rounds
    .flatMap((r) => r.pods.map((p) => ({ podId: p.id, tId: r.tournament_id })))
    .find((x) => x.podId === podIdNum)?.tId ?? undefined;

  // Purchase gate
  if (!purchaseLoading && purchase !== undefined && !purchase?.paid_at) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="bg-amber-50 rounded-full p-4 mb-6">
          <svg className="w-12 h-12 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v2m0-2h2m-2 0H10m2-10a4 4 0 100 8 4 4 0 000-8z" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-3">Season Pass Required</h2>
        <p className="text-gray-600 max-w-sm mb-8">
          {isManager
            ? "This league needs an active season pass to access features. Purchase one to get started."
            : "Your league manager needs to purchase a season pass to unlock all features."}
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="bg-gray-50 rounded-2xl p-12 text-center space-y-3">
        <div className="flex justify-center"><FlagIcon className="w-10 h-10 text-green-700" /></div>
        <p className="font-semibold text-gray-700">Failed to load draft</p>
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => refetch()}
            className="text-sm font-semibold text-green-700 hover:text-green-900 underline"
          >
            Try again
          </button>
          <Link to={`/leagues/${leagueId}/leaderboard?view=bracket`} className="text-sm font-semibold text-green-700 hover:text-green-900">
            ← Back to Bracket
          </Link>
        </div>
      </div>
    );
  }

  if (!draftStatus) {
    return (
      <div className="bg-gray-50 rounded-2xl p-12 text-center space-y-3">
        <div className="flex justify-center"><FlagIcon className="w-10 h-10 text-green-700" /></div>
        <p className="font-semibold text-gray-700">Pod not found</p>
        <Link to={`/leagues/${leagueId}/leaderboard?view=bracket`} className="inline-block text-sm font-semibold text-green-700 hover:text-green-900">
          ← Back to Bracket
        </Link>
      </div>
    );
  }

  const isInPod = draftStatus.members.some((m) => m.user_id === currentUser?.id);
  const isDraftOpen = draftStatus.round_status === "drafting";
  const isResolved = draftStatus.resolved_picks.length > 0;

  return (
    <div className="space-y-6 max-w-xl mx-auto">
      {/* Header */}
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">Playoff Preferences</p>
        <div className="flex items-center justify-between gap-4 mt-1">
          <h1 className="text-2xl font-bold text-gray-900">Pod {podIdNum}</h1>
          <Link
            to={`/leagues/${leagueId}/leaderboard?view=bracket`}
            className="text-sm text-gray-500 hover:text-gray-700 font-medium"
          >
            ← Bracket
          </Link>
        </div>
        <div className="mt-1 flex items-center gap-2">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
            draftStatus.round_status === "drafting"
              ? "bg-amber-100 text-amber-700"
              : draftStatus.round_status === "locked"
              ? "bg-purple-100 text-purple-700"
              : "bg-gray-100 text-gray-500"
          }`}>
            {draftStatus.round_status === "drafting" ? "Open" : draftStatus.round_status === "locked" ? "Locked" : draftStatus.round_status}
          </span>
          {draftStatus.deadline && (
            <span className="text-xs text-gray-400">
              Submit by:{" "}
              {new Date(draftStatus.deadline).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </span>
          )}
        </div>
      </div>

      {/* Who has submitted */}
      <DraftStatusCard draftStatus={draftStatus} />

      {/* Resolved picks */}
      {isResolved && <ResolvedPicksCard picks={draftStatus.resolved_picks} />}

      {/* Preference editor (draft open + user in pod) */}
      {isDraftOpen && isInPod && bracketTournamentId && (
        <PlayoffPreferenceEditor
          leagueId={leagueId!}
          podId={podIdNum!}
          tournamentId={bracketTournamentId}
          currentPreferences={myPreferences}
          requiredCount={draftStatus.required_preference_count ?? undefined}
          deadline={draftStatus.deadline ?? undefined}
        />
      )}

      {isDraftOpen && isInPod && !bracketTournamentId && (
        <div className="bg-amber-50 rounded-2xl p-6 text-center">
          <p className="text-sm text-amber-700">
            Waiting for the manager to assign a tournament to this round.
          </p>
        </div>
      )}

      {!isDraftOpen && !isResolved && isInPod && (
        <div className="bg-gray-50 rounded-2xl p-6 text-center">
          <p className="text-sm text-gray-400">
            Preferences are not open yet. The window opens automatically once the previous round completes.
          </p>
        </div>
      )}

      {!isInPod && (
        <div className="bg-gray-50 rounded-2xl p-6 text-center">
          <p className="text-sm text-gray-400">You are not a member of this pod.</p>
        </div>
      )}
    </div>
  );
}
