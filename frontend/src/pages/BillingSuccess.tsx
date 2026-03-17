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
 * Retries up to 3× with a 2s delay on 404 (webhook may not have fired yet).
 * Clears localStorage on success or after all retries are exhausted.
 */

import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { leaguesApi } from "../api/endpoints";

async function savePendingSchedule(leagueId: string): Promise<void> {
  const raw = localStorage.getItem("pendingLeagueSchedule");
  if (!raw) return;

  let schedule: { tournament_id: string; multiplier: number | null; is_playoff: boolean }[];
  try {
    schedule = JSON.parse(raw);
  } catch {
    localStorage.removeItem("pendingLeagueSchedule");
    return;
  }

  if (!schedule.length) {
    localStorage.removeItem("pendingLeagueSchedule");
    return;
  }

  const maxRetries = 3;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      await leaguesApi.updateTournaments(leagueId, schedule);
      localStorage.removeItem("pendingLeagueSchedule");
      return;
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404 && attempt < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
      } else {
        // Final failure — clear anyway so user isn't stuck; they can set schedule in Manage
        localStorage.removeItem("pendingLeagueSchedule");
        return;
      }
    }
  }
}

export function BillingSuccess() {
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id");
  const queryClient = useQueryClient();

  useEffect(() => {
    if (leagueId) {
      queryClient.invalidateQueries({ queryKey: ["leaguePurchase", leagueId] });
      savePendingSchedule(leagueId);
    }
  }, [leagueId, queryClient]);

  const leagueHref = leagueId ? `/leagues/${leagueId}` : "/leagues";

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

        <Link
          to={leagueHref}
          className="block w-full bg-green-800 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-xl transition-colors shadow-sm"
        >
          Go to My League
        </Link>
      </div>
    </div>
  );
}
