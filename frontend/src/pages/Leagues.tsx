/**
 * Leagues — post-login landing page.
 *
 * Shows all leagues the user belongs to, plus an option to create a new one.
 * Joining a league is done via an invite link shared by the league manager.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LeagueCard } from "../components/LeagueCard";
import { useLeagueSummaries, useMyRequests, useCancelMyRequest } from "../hooks/useLeague";
import { useAppConfig } from "../hooks/useAppConfig";
import { useAuthStore } from "../store/authStore";
import { FlagIcon } from "../components/FlagIcon";
import { SkeletonBlock } from "../components/Skeleton";

export function Leagues() {
  const navigate = useNavigate();
  const { data: summaries, isLoading } = useLeagueSummaries();
  const { data: pendingRequests } = useMyRequests();
  const cancelRequest = useCancelMyRequest();
  const { data: appConfig } = useAppConfig();
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    document.title = "My Leagues — League Caddie";
  }, []);

  const [joinCode, setJoinCode] = useState("");
  const [withdrawLeagueId, setWithdrawLeagueId] = useState<string | null>(null);
  const withdrawLeagueName = pendingRequests?.find((r) => String(r.league_id) === withdrawLeagueId)?.league_name;

  const atLeagueCap = !!summaries && (summaries.length + (pendingRequests?.length ?? 0)) >= 5;
  const createBlocked =
    !!appConfig?.league_creation_restricted && !user?.is_platform_admin;

  function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    // Accept a full URL (e.g. https://…/join/abc123) or just the code itself.
    const raw = joinCode.trim();
    const code = raw.includes("/join/") ? raw.split("/join/").pop()! : raw;
    if (code) navigate(`/join/${code}`);
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="space-y-1">
        <h1 className="text-title text-ink-950">My Leagues</h1>
      </div>

      {/* League list */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 animate-pulse">
          {Array.from({ length: 2 }, (_, i) => (
            <div key={i} className="rounded-sm border border-ink-200 overflow-hidden">
              <div className="bg-fairway-900 px-5 pt-5 pb-4">
                <SkeletonBlock className="h-6 w-40 !bg-white/20" />
              </div>
              <div className="px-5 py-4 grid grid-cols-3 divide-x divide-ink-100">
                <div className="pr-4 space-y-2"><SkeletonBlock className="h-3 w-10" /><SkeletonBlock className="h-7 w-8" /></div>
                <div className="px-4 space-y-2"><SkeletonBlock className="h-3 w-12" /><SkeletonBlock className="h-7 w-16" /></div>
                <div className="pl-4 space-y-2"><SkeletonBlock className="h-3 w-16" /><SkeletonBlock className="h-7 w-8" /></div>
              </div>
              <div className="border-t border-ink-100 bg-ink-50 px-5 py-3">
                <SkeletonBlock className="h-4 w-48" />
              </div>
            </div>
          ))}
        </div>
      ) : summaries && summaries.length > 0 ? (
        <div className={summaries.length === 1 ? "max-w-lg mx-auto" : "grid gap-4 sm:grid-cols-2"}>
          {summaries.map((s) => (
            <LeagueCard key={s.league_id} summary={s} />
          ))}
        </div>
      ) : (
        <div className="bg-ink-50 rounded-sm border border-ink-200 p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-sm bg-fairway-100 text-fairway-700 flex items-center justify-center mx-auto">
            <FlagIcon className="w-6 h-6" />
          </div>
          <p className="font-semibold text-ink-700">No leagues yet</p>
          <p className="text-sm text-ink-400">
            Got an invite link from a friend? <strong className="text-ink-500">Join their league</strong> below.
            Want to run your own? <strong className="text-ink-500">Create a league</strong> and invite others.
          </p>
        </div>
      )}

      {/* Pending join requests */}
      {pendingRequests && pendingRequests.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-base font-bold text-ink-800">Pending Requests</h2>
          <div className="bg-brass-50 border border-brass-100 rounded-sm overflow-hidden divide-y divide-brass-100">
            {pendingRequests.map((req) => (
              <div key={String(req.league_id)} className="flex items-center gap-4 px-5 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink-900 truncate">{req.league_name}</p>
                </div>
                <span className="flex-shrink-0 text-xs font-bold bg-brass-100 text-brass-700 px-2.5 py-1 rounded-xs">
                  Pending approval
                </span>
                <button
                  onClick={() => setWithdrawLeagueId(String(req.league_id))}
                  disabled={cancelRequest.isPending}
                  className="flex-shrink-0 text-xs font-medium text-flag-600 hover:text-flag-700 hover:underline disabled:opacity-40 transition-colors"
                >
                  Withdraw
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Create / Join */}
      <div className="border-t border-ink-200 pt-8 space-y-4">
        <p className="text-micro uppercase text-ink-400">
          Join or create
        </p>

        {atLeagueCap && (
          <div className="flex gap-3 bg-brass-50 border border-brass-100 rounded-xs px-4 py-3">
            <svg className="w-4 h-4 text-brass-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
            <p className="text-sm text-brass-700">
              You've reached the 5-league limit. Leave a league before creating or joining another.
            </p>
          </div>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          {/* Create */}
          <div className={`bg-ink-50 rounded-sm p-6 border transition-all ${atLeagueCap || createBlocked ? "border-ink-100 opacity-60" : "border-ink-100 hover:border-fairway-200"}`}>
            <div className="w-10 h-10 rounded-xs bg-fairway-100 text-fairway-700 flex items-center justify-center mb-4">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <h2 className="font-bold text-ink-900 mb-1">Create a league</h2>
            <p className="text-sm text-ink-500 mb-4 leading-relaxed">
              {createBlocked
                ? "League creation isn't available to the public yet. Check back soon!"
                : "Start your own league and invite friends with a shareable link."}
            </p>
            <button
              onClick={() => navigate("/leagues/new")}
              disabled={atLeagueCap || createBlocked}
              className="w-full bg-fairway-700 hover:bg-fairway-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2 rounded-xs transition-colors"
            >
              Create league
            </button>
          </div>

          {/* Join */}
          <div className={`bg-ink-50 rounded-sm p-6 border transition-all ${atLeagueCap ? "border-ink-100 opacity-60" : "border-ink-100 hover:border-fairway-200"}`}>
            <div className="w-10 h-10 rounded-xs bg-fairway-100 text-fairway-700 flex items-center justify-center mb-4">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
              </svg>
            </div>
            <h2 className="font-bold text-ink-900 mb-1">Join a league</h2>
            <p className="text-sm text-ink-500 mb-4 leading-relaxed">
              Paste an invite link from a league manager to request access.
            </p>
            <form onSubmit={handleJoin} className="space-y-2">
              <input
                type="text"
                placeholder="Paste invite link or code"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
                disabled={atLeagueCap}
                className="w-full border border-ink-300 rounded-xs px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-500 disabled:cursor-not-allowed"
              />
              <button
                type="submit"
                disabled={!joinCode.trim() || atLeagueCap}
                className="w-full bg-fairway-700 hover:bg-fairway-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2 rounded-xs transition-colors"
              >
                Continue
              </button>
            </form>
          </div>
        </div>
      </div>
      {/* Withdraw confirmation modal */}
      {withdrawLeagueId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-sm shadow-raised w-full max-w-sm p-6 space-y-4">
            <h3 className="text-base font-bold text-ink-900">Withdraw request?</h3>
            <p className="text-sm text-ink-600">
              Are you sure you want to withdraw your join request for <span className="font-semibold">{withdrawLeagueName}</span>? You can request to join again later.
            </p>
            {cancelRequest.isError && (
              <p className="text-sm text-flag-600">Failed to withdraw request. Please try again.</p>
            )}
            <div className="flex justify-end gap-3 pt-1">
              <button
                onClick={() => setWithdrawLeagueId(null)}
                className="px-5 py-2 text-sm font-semibold rounded-xs border border-ink-200 text-ink-600 hover:bg-ink-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  cancelRequest.mutate(withdrawLeagueId, {
                    onSuccess: () => setWithdrawLeagueId(null),
                  });
                }}
                disabled={cancelRequest.isPending}
                className="px-5 py-2 text-sm font-semibold rounded-xs text-white bg-flag-600 hover:bg-flag-700 disabled:opacity-40 transition-colors"
              >
                {cancelRequest.isPending ? "Withdrawing…" : "Withdraw"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
