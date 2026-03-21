/**
 * BillingCanceled — shown when the user cancels out of Stripe checkout.
 *
 * Route: /billing/canceled (public, outside Layout wrapper)
 *
 * Reads ?league_id from the URL.
 * No charge was made — just let the user try again.
 */

import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

export function BillingCanceled() {
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id");

  useEffect(() => {
    document.title = "Payment Canceled — League Caddie";
  }, []);

  const manageHref = leagueId ? `/leagues/${leagueId}` : "/leagues";

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 max-w-sm w-full text-center space-y-6">
        {/* Amber warning icon */}
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-amber-100 flex items-center justify-center">
            <svg
              className="w-8 h-8 text-amber-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
              />
            </svg>
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-gray-900">Payment Canceled</h1>
          <p className="text-gray-500 text-sm">
            No charge was made. You can try again whenever you're ready.
          </p>
        </div>

        <Link
          to={manageHref}
          className="block w-full border border-gray-300 hover:border-gray-400 bg-white text-gray-700 font-semibold py-3 px-6 rounded-xl transition-colors"
        >
          Return to My Leagues
        </Link>
      </div>
    </div>
  );
}
