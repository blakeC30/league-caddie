/**
 * BillingSuccess — shown after a successful Stripe checkout.
 *
 * Route: /billing/success (public, outside Layout wrapper)
 *
 * Reads ?session_id and ?league_id from the URL.
 * Invalidates the leaguePurchase cache so league pages reflect the new paid status.
 *
 * If localStorage contains "pendingLeagueSchedule" (set by CreateLeague before
 * redirecting to Stripe), this page saves it via leaguesApi.updateTournaments.
 *
 * League-readiness check (up to 10 attempts, 2s between each):
 *   Polls GET /leagues/{id} until the Stripe webhook has fired and created the
 *   league + member + purchase rows atomically in the database. The "Go to My
 *   League" button is disabled until the league is confirmed ready, preventing
 *   the race condition where the user navigates before the webhook has processed.
 *   On success, related caches (league, leagueMembers, myLeagues) are invalidated
 *   so the league page renders with fresh data immediately.
 *
 * Schedule-save retry policy (up to 3 attempts, 2s between each):
 *   Runs in parallel with the readiness check — it has its own retry loop for
 *   404/402 so it will succeed once the webhook fires.
 *   - 404: league not created yet — webhook may still be in flight
 *   - 402: purchase not yet recorded — webhook may still be in flight
 *   - 5xx: transient server error
 *   Any other error (e.g. 422 bad data, 403 wrong user) gives up immediately.
 *   Clears localStorage on success or after all retries are exhausted.
 *
 * A useRef guard ensures both the readiness check and the schedule save are
 * attempted exactly once per page load, even in React 18 Strict Mode (which
 * double-invokes useEffect in development).
 *
 * If the schedule save ultimately fails, a visible warning is shown so the user
 * knows to set their tournament schedule manually from the Manage League page.
 */

import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { leaguesApi } from "../api/endpoints";

/**
 * Returns true if the HTTP status code is worth retrying:
 *   - 404: league/purchase row not yet created (webhook in flight)
 *   - 402: payment not yet recorded (webhook in flight)
 *   - 5xx: transient server error
 */
function isRetryableStatus(status: number | undefined): boolean {
  if (status === undefined) return false;
  return status === 404 || status === 402 || status >= 500;
}

/**
 * Polls GET /leagues/{id} until the webhook-created league row exists in the
 * database. Returns true when the league is ready, false if all attempts fail.
 *
 * The Stripe webhook creates the League, Season, LeagueMember, and
 * LeaguePurchase rows atomically, but fires asynchronously after the Stripe
 * redirect — this polling loop bridges that gap.
 */
async function waitForLeagueReady(leagueId: string): Promise<boolean> {
  const maxAttempts = 10; // 10 × 2 s = 20 s maximum wait
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      await leaguesApi.get(leagueId);
      return true;
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (isRetryableStatus(status) && attempt < maxAttempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
      } else {
        return false;
      }
    }
  }
  return false;
}

/**
 * Attempts to save the pending tournament schedule from localStorage.
 * Returns true if saved successfully (or nothing to save), false if all retries failed.
 */
async function savePendingSchedule(leagueId: string): Promise<boolean> {
  const raw = localStorage.getItem("pendingLeagueSchedule");
  if (!raw) return true;

  let schedule: { tournament_id: string; multiplier: number | null; is_playoff: boolean }[];
  try {
    schedule = JSON.parse(raw);
  } catch {
    localStorage.removeItem("pendingLeagueSchedule");
    return true;
  }

  if (!schedule.length) {
    localStorage.removeItem("pendingLeagueSchedule");
    return true;
  }

  const maxRetries = 3;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      await leaguesApi.updateTournaments(leagueId, schedule);
      localStorage.removeItem("pendingLeagueSchedule");
      return true;
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (isRetryableStatus(status) && attempt < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
      } else {
        // Non-retryable error or retries exhausted — clear localStorage so
        // the user isn't stuck in a retry loop on refresh.
        localStorage.removeItem("pendingLeagueSchedule");
        return false;
      }
    }
  }
  return false;
}

export function BillingSuccess() {
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id");
  const queryClient = useQueryClient();
  const [scheduleWarning, setScheduleWarning] = useState(false);

  // leagueReady: false while waiting for the webhook-created league to appear
  // in the database. Starts true if there is no league_id in the URL (e.g.
  // renewal flow where the league already exists).
  const [leagueReady, setLeagueReady] = useState(!leagueId);
  const [readinessError, setReadinessError] = useState(false);

  // useRef guard: prevents the readiness check and schedule save from running
  // more than once per page load. React 18 Strict Mode double-invokes useEffect
  // in development; without this guard both invocations fire concurrently.
  const attempted = useRef(false);

  useEffect(() => {
    if (!leagueId || attempted.current) return;
    attempted.current = true;

    // Invalidate the purchase cache so league pages reflect paid status.
    queryClient.invalidateQueries({ queryKey: ["leaguePurchase", leagueId] });
    queryClient.invalidateQueries({ queryKey: ["purchaseEvents", leagueId] });

    // Poll until the Stripe webhook has created the league. On success, warm the
    // React Query cache for all league-related keys so the league page renders
    // correctly without a round-trip on first load.
    waitForLeagueReady(leagueId).then((ready) => {
      if (ready) {
        setLeagueReady(true);
        queryClient.invalidateQueries({ queryKey: ["league", leagueId] });
        queryClient.invalidateQueries({ queryKey: ["leagueMembers", leagueId] });
        queryClient.invalidateQueries({ queryKey: ["myLeagues"] });
      } else {
        setReadinessError(true);
      }
    });

    // Save the schedule in parallel — it has its own retry loop for 404/402
    // and will succeed once the webhook fires.
    savePendingSchedule(leagueId).then((ok) => {
      if (!ok) setScheduleWarning(true);
    });
  }, [leagueId, queryClient]);

  const leagueHref = leagueId ? `/leagues/${leagueId}` : "/leagues";
  const manageHref = leagueId ? `/leagues/${leagueId}/manage` : "/leagues";

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 max-w-sm w-full text-center space-y-6">
        {/* Green checkmark circle */}
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
            <svg
              className="w-8 h-8 text-green-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-gray-900">Payment Successful!</h1>
          <p className="text-gray-500 text-sm">
            Your league is now active for the 2026 season. You can access all features now.
          </p>
        </div>

        {scheduleWarning && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-left space-y-1">
            <p className="text-sm font-semibold text-amber-800">Tournament schedule not saved</p>
            <p className="text-xs text-amber-700">
              Your payment was successful, but we couldn't save your tournament schedule
              automatically. Please set it manually from the{" "}
              <Link to={manageHref} className="underline font-medium">
                Manage League
              </Link>{" "}
              page. If this problem persists, contact support.
            </p>
          </div>
        )}

        {readinessError ? (
          <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-left space-y-1">
            <p className="text-sm font-semibold text-red-800">League setup taking longer than expected</p>
            <p className="text-xs text-red-700">
              Your payment was successful. Please refresh the page in a moment, or go to{" "}
              <Link to="/leagues" className="underline font-medium">
                My Leagues
              </Link>{" "}
              to find your new league. If this problem persists, contact support.
            </p>
          </div>
        ) : leagueReady ? (
          <Link
            to={leagueHref}
            className="block w-full bg-green-800 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-xl transition-colors shadow-sm"
          >
            Go to My League
          </Link>
        ) : (
          <div className="flex items-center justify-center gap-2 w-full bg-green-800/50 text-white font-semibold py-3 px-6 rounded-xl cursor-not-allowed select-none">
            <svg
              className="w-4 h-4 animate-spin flex-shrink-0"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Setting up your league…
          </div>
        )}
      </div>
    </div>
  );
}
