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
import { Spinner } from "../components/Spinner";

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
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
          League Caddie
        </p>
        <h1 className="text-3xl font-bold text-gray-900">My Leagues</h1>
      </div>

      {/* League list */}
      {isLoading ? (
        <div className="flex justify-center py-10"><Spinner /></div>
      ) : summaries && summaries.length > 0 ? (
        <div className={summaries.length === 1 ? "max-w-lg mx-auto" : "grid gap-4 sm:grid-cols-2"}>
          {summaries.map((s) => (
            <LeagueCard key={s.league_id} summary={s} />
          ))}
        </div>
      ) : (
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-green-100 text-green-700 flex items-center justify-center mx-auto">
            <FlagIcon className="w-6 h-6" />
          </div>
          <p className="font-semibold text-gray-700">No leagues yet</p>
          <p className="text-sm text-gray-400">
            Got an invite link from a friend? <strong className="text-gray-500">Join their league</strong> below.
            Want to run your own? <strong className="text-gray-500">Create a league</strong> and invite others.
          </p>
        </div>
      )}

      {/* Pending join requests */}
      {pendingRequests && pendingRequests.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-base font-bold text-gray-800">Pending Requests</h2>
          <div className="bg-amber-50 border border-amber-200 rounded-2xl overflow-hidden divide-y divide-amber-100">
            {pendingRequests.map((req) => (
              <div key={String(req.league_id)} className="flex items-center gap-4 px-5 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{req.league_name}</p>
                </div>
                <span className="flex-shrink-0 text-xs font-bold bg-amber-200 text-amber-800 px-2.5 py-1 rounded-full">
                  Pending approval
                </span>
                <button
                  onClick={() => setWithdrawLeagueId(String(req.league_id))}
                  disabled={cancelRequest.isPending}
                  className="flex-shrink-0 text-xs font-medium text-red-500 hover:text-red-700 hover:underline disabled:opacity-40 transition-colors"
                >
                  Withdraw
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Create / Join */}
      <div className="border-t border-gray-200 pt-8 space-y-4">
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-gray-400">
          Join or create
        </p>

        {atLeagueCap && (
          <div className="flex gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
            <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
            <p className="text-sm text-amber-800">
              You've reached the 5-league limit. Leave a league before creating or joining another.
            </p>
          </div>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          {/* Create */}
          <div className={`bg-gray-50 rounded-2xl p-6 border transition-all ${atLeagueCap || createBlocked ? "border-gray-100 opacity-60" : "border-gray-100 hover:border-green-200"}`}>
            <div className="w-10 h-10 rounded-xl bg-green-100 text-green-700 flex items-center justify-center mb-4">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <h2 className="font-bold text-gray-900 mb-1">Create a league</h2>
            <p className="text-sm text-gray-500 mb-4 leading-relaxed">
              {createBlocked
                ? "League creation isn't available to the public yet. Check back soon!"
                : "Start your own league and invite friends with a shareable link."}
            </p>
            <button
              onClick={() => navigate("/leagues/new")}
              disabled={atLeagueCap || createBlocked}
              className="w-full bg-green-800 hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2 rounded-lg transition-colors"
            >
              Create league
            </button>
          </div>

          {/* Join */}
          <div className={`bg-gray-50 rounded-2xl p-6 border transition-all ${atLeagueCap ? "border-gray-100 opacity-60" : "border-gray-100 hover:border-green-200"}`}>
            <div className="w-10 h-10 rounded-xl bg-green-100 text-green-700 flex items-center justify-center mb-4">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
              </svg>
            </div>
            <h2 className="font-bold text-gray-900 mb-1">Join a league</h2>
            <p className="text-sm text-gray-500 mb-4 leading-relaxed">
              Paste an invite link from a league manager to request access.
            </p>
            <form onSubmit={handleJoin} className="space-y-2">
              <input
                type="text"
                placeholder="Paste invite link or code"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
                disabled={atLeagueCap}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 disabled:cursor-not-allowed"
              />
              <button
                type="submit"
                disabled={!joinCode.trim() || atLeagueCap}
                className="w-full bg-green-800 hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold py-2 rounded-lg transition-colors"
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
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <h3 className="text-base font-bold text-gray-900">Withdraw request?</h3>
            <p className="text-sm text-gray-600">
              Are you sure you want to withdraw your join request for <span className="font-semibold">{withdrawLeagueName}</span>? You can request to join again later.
            </p>
            {cancelRequest.isError && (
              <p className="text-sm text-red-600">Failed to withdraw request. Please try again.</p>
            )}
            <div className="flex justify-end gap-3 pt-1">
              <button
                onClick={() => setWithdrawLeagueId(null)}
                className="px-5 py-2 text-sm font-semibold rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
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
                className="px-5 py-2 text-sm font-semibold rounded-xl text-white bg-red-600 hover:bg-red-700 disabled:opacity-40 transition-colors"
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
