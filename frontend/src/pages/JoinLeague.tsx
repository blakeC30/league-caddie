/**
 * JoinLeague — landing page for invite links.
 *
 * The outer component handles the auth gate: unauthenticated users are sent
 * to /login?next=/join/:inviteCode and returned here after signing in or
 * creating an account. Once authenticated, JoinLeagueForm renders and handles
 * the actual preview + confirm flow.
 *
 * Splitting into two components keeps React hook call order consistent —
 * JoinLeagueForm's hooks are never called for unauthenticated visitors.
 *
 * States (inside JoinLeagueForm):
 *   - Loading: fetching preview
 *   - Invalid link: 404 from preview fetch
 *   - Already approved: show "already a member" card with link to league
 *   - Pending: show status + option to cancel the request
 *   - No relationship: show confirm/cancel form
 */

import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useJoinByCode, useJoinPreview, useCancelMyRequest, useMyLeagues, useMyRequests } from "../hooks/useLeague";
import { FlagIcon } from "../components/FlagIcon";
import { Spinner } from "../components/Spinner";

function GradientShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-green-950 via-green-900 to-green-800 flex flex-col items-center justify-center px-4 py-12">
      {/* Logo */}
      <Link to="/" className="inline-flex items-center gap-2 text-lg font-bold text-green-300 hover:text-white mb-10 tracking-tight transition-colors">
        <FlagIcon className="w-5 h-5 flex-shrink-0" />
        League Caddie
      </Link>
      {children}
    </div>
  );
}

export function JoinLeague() {
  const { inviteCode } = useParams<{ inviteCode: string }>();
  const { token, bootstrapping } = useAuth();

  if (bootstrapping) {
    return (
      <GradientShell>
        <Spinner className="w-6 h-6 text-green-300" />
      </GradientShell>
    );
  }

  if (!token) {
    return <Navigate to={`/login?next=/join/${inviteCode}`} replace />;
  }

  return <JoinLeagueForm inviteCode={inviteCode!} />;
}

function JoinLeagueForm({ inviteCode }: { inviteCode: string }) {
  const navigate = useNavigate();
  const { data: preview, isLoading, isError } = useJoinPreview(inviteCode);
  const joinByCode = useJoinByCode();
  const cancelRequest = useCancelMyRequest();
  const { data: leagues } = useMyLeagues();
  const { data: pendingRequests } = useMyRequests();
  const [submitted, setSubmitted] = useState(false);
  const [joinError, setJoinError] = useState("");

  const atLeagueCap = !!leagues && (leagues.length + (pendingRequests?.length ?? 0)) >= 5;

  if (isLoading) {
    return (
      <GradientShell>
        <Spinner className="w-6 h-6 text-green-300" />
      </GradientShell>
    );
  }

  if (isError || !preview) {
    return (
      <GradientShell>
        <div className="bg-white rounded-2xl shadow-xl shadow-black/20 p-8 w-full max-w-sm text-center space-y-4">
          <div className="w-12 h-12 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <p className="font-semibold text-gray-900">Invalid invite link</p>
          <p className="text-sm text-gray-500">This league could not be found. The link may have expired.</p>
          <button
            onClick={() => navigate("/leagues")}
            className="w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
          >
            Back to my leagues
          </button>
        </div>
      </GradientShell>
    );
  }

  // League is not accepting new requests and the user has no existing relationship.
  // Users who already have a pending request can still see their status + withdraw.
  if (!preview.accepting_requests && preview.user_status === null) {
    return (
      <GradientShell>
        <div className="bg-white rounded-2xl shadow-xl shadow-black/20 p-8 w-full max-w-sm text-center space-y-4">
          <div className="w-12 h-12 bg-gray-100 text-gray-400 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-gray-400">
              Not accepting requests
            </p>
            <h1 className="text-2xl font-bold text-gray-900">{preview.name}</h1>
          </div>
          <p className="text-sm text-gray-500">
            This league is not currently accepting new join requests. Contact the league manager for more information.
          </p>
          <button
            onClick={() => navigate("/leagues")}
            className="w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
          >
            Back to my leagues
          </button>
        </div>
      </GradientShell>
    );
  }

  // League cap reached and user has no existing relationship — block the request.
  if (atLeagueCap && preview.user_status === null) {
    return (
      <GradientShell>
        <div className="bg-white rounded-2xl shadow-xl shadow-black/20 p-8 w-full max-w-sm text-center space-y-4">
          <div className="w-12 h-12 bg-amber-100 text-amber-600 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-amber-600">
              League limit reached
            </p>
            <h1 className="text-2xl font-bold text-gray-900">{preview.name}</h1>
          </div>
          <p className="text-sm text-gray-500">
            You've reached the maximum of 5 leagues (including pending requests). Leave a league or withdraw a pending request before joining another.
          </p>
          <button
            onClick={() => navigate("/leagues")}
            className="w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
          >
            Back to my leagues
          </button>
        </div>
      </GradientShell>
    );
  }

  // Already an approved member — show a message instead of silently redirecting.
  if (preview.user_status === "approved") {
    return (
      <GradientShell>
        <div className="bg-white rounded-2xl shadow-xl shadow-black/20 p-8 w-full max-w-sm text-center space-y-5">
          <div className="w-12 h-12 bg-green-100 text-green-700 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
              You're already a member
            </p>
            <h1 className="text-2xl font-bold text-gray-900">{preview.name}</h1>
          </div>
          <button
            onClick={() => navigate(`/leagues/${preview.league_id}`)}
            className="w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
          >
            Go to league →
          </button>
        </div>
      </GradientShell>
    );
  }

  const isPending = preview.user_status === "pending" || submitted;

  async function handleConfirm() {
    setJoinError("");
    try {
      const membership = await joinByCode.mutateAsync(inviteCode);
      if (membership.status === "approved") {
        navigate(`/leagues/${membership.league_id}`);
      } else {
        setSubmitted(true);
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setJoinError(msg ?? "Failed to submit join request.");
    }
  }

  async function handleWithdraw() {
    await cancelRequest.mutateAsync(String(preview!.league_id));
    navigate("/leagues");
  }

  return (
    <GradientShell>
      <div className="bg-white rounded-2xl shadow-xl shadow-black/20 p-8 w-full max-w-sm space-y-5">
        {/* League info */}
        <div className="text-center space-y-1.5">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700">
            {preview.user_status === "pending"
              ? "You've already requested to join"
              : submitted
              ? "Request pending"
              : "You've been invited to join"}
          </p>
          <h1 className="text-2xl font-bold text-gray-900">{preview.name}</h1>
          <p className="text-xs text-gray-400">
            {preview.member_count} member{preview.member_count !== 1 ? "s" : ""}
          </p>
        </div>

        {isPending ? (
          /* Pending state */
          <div className="space-y-3 text-center">
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
              <p className="text-sm text-amber-800">
                {preview.user_status === "pending"
                  ? "You already have an open request for this league. A manager needs to approve it before you get access."
                  : "Your join request has been sent. A manager needs to approve it before you get access."}
              </p>
            </div>
            <button
              onClick={() => navigate("/leagues")}
              className="w-full bg-green-800 hover:bg-green-700 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
            >
              Back to my leagues
            </button>
            <button
              onClick={handleWithdraw}
              disabled={cancelRequest.isPending}
              className="w-full text-sm font-medium text-red-500 hover:text-red-700 disabled:opacity-40 transition-colors py-1"
            >
              {cancelRequest.isPending ? "Withdrawing…" : "Withdraw request"}
            </button>
          </div>
        ) : (
          /* Confirm state */
          <div className="space-y-3">
            <p className="text-sm text-gray-500 text-center">
              Joining requires manager approval. Your request will be reviewed before
              you get access.
            </p>
            {joinError && (
              <p className="text-xs text-red-600 text-center">{joinError}</p>
            )}
            <button
              onClick={handleConfirm}
              disabled={joinByCode.isPending}
              className="w-full bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white text-sm font-semibold py-3 rounded-xl transition-colors"
            >
              {joinByCode.isPending ? "Submitting…" : "Request to Join"}
            </button>
            <button
              onClick={() => navigate("/leagues")}
              className="w-full text-sm font-medium text-gray-500 hover:text-gray-700 py-1 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </GradientShell>
  );
}
