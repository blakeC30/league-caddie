/**
 * Pricing — public standalone page showing season pass tiers.
 *
 * Route: /pricing (public, outside Layout wrapper)
 *
 * Optional query param: ?league_id=X  — when present, the CTA buttons
 * launch a Stripe checkout session for that league instead of linking to /leagues.
 */

import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { stripeApi } from "../api/endpoints";
import type { PricingTier } from "../api/endpoints";
import { Spinner } from "../components/Spinner";

// ---------------------------------------------------------------------------
// Tier metadata — features list and display overrides per tier
// ---------------------------------------------------------------------------

const TIER_FEATURES: Record<string, string[]> = {
  starter:  ["Up to 20 members", "Weekly picks & standings", "Season scoring"],
  standard: ["Up to 50 members", "Weekly picks & standings", "Season scoring"],
  pro:      ["Up to 150 members", "Weekly picks & standings", "Season scoring"],
  elite:    ["Up to 500 members", "Weekly picks & standings", "Season scoring + playoffs"],
};

function tierFeatures(tier: string): string[] {
  return TIER_FEATURES[tier] ?? ["Weekly picks & standings", "Season scoring"];
}

// ---------------------------------------------------------------------------
// Individual tier card
// ---------------------------------------------------------------------------

function TierCard({
  pricing,
  leagueId,
  currentTier,
}: {
  pricing: PricingTier;
  leagueId: string | null;
  currentTier: string | null;
}) {
  const [loading, setLoading] = useState(false);
  const isStandard = pricing.tier === "standard";
  const isCurrentTier = currentTier === pricing.tier;
  const dollars = Math.floor(pricing.amount_cents / 100);
  const perMember = (pricing.amount_cents / 100 / pricing.member_limit).toFixed(2);
  const tierLabel = pricing.tier.charAt(0).toUpperCase() + pricing.tier.slice(1);
  const features = tierFeatures(pricing.tier);

  async function handleCheckout() {
    if (!leagueId) return;
    setLoading(true);
    try {
      const isUpgrade = !!currentTier && currentTier !== pricing.tier;
      const { url } = await stripeApi.createCheckoutSession(leagueId, pricing.tier, isUpgrade);
      window.location.href = url;
    } catch {
      setLoading(false);
    }
  }

  return (
    <div
      className={`relative rounded-2xl border bg-white shadow-sm p-6 flex flex-col gap-5 transition-shadow hover:shadow-md ${
        isStandard ? "border-2 border-green-600 shadow-md" : "border border-gray-200"
      }`}
    >
      {/* Most Popular badge */}
      {isStandard && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-amber-400 text-amber-900 text-xs font-bold px-3 py-1 rounded-full shadow-sm whitespace-nowrap">
          Most Popular
        </span>
      )}

      {/* Tier name */}
      <div>
        <p className="text-sm font-bold uppercase tracking-[0.12em] text-green-700 mb-1">
          {tierLabel}
        </p>
        <div className="flex items-end gap-1">
          <span className="text-4xl font-bold text-gray-900">${dollars}</span>
          <span className="text-gray-400 text-sm mb-1">/season</span>
        </div>
        {/* Member limit pill */}
        <span className="inline-block mt-2 rounded-full bg-green-100 text-green-800 text-xs font-semibold px-3 py-1">
          Up to {pricing.member_limit.toLocaleString()} members
        </span>
        <p className="text-xs text-gray-400 mt-1">~${perMember} per member</p>
      </div>

      {/* Features */}
      <ul className="space-y-2 flex-1">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm text-gray-700">
            <svg
              className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
            {f}
          </li>
        ))}
      </ul>

      {/* CTA */}
      {leagueId ? (
        <button
          type="button"
          onClick={handleCheckout}
          disabled={loading || isCurrentTier}
          className={`w-full font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2 ${
            isCurrentTier
              ? "bg-gray-100 text-gray-400 cursor-default"
              : isStandard
              ? "bg-green-800 hover:bg-green-700 text-white shadow-sm"
              : "bg-green-800 hover:bg-green-700 text-white shadow-sm"
          } disabled:opacity-50`}
        >
          {loading ? (
            <Spinner />
          ) : isCurrentTier ? (
            "Current Plan"
          ) : currentTier ? (
            "Upgrade"
          ) : (
            "Get Started"
          )}
        </button>
      ) : (
        <Link
          to="/leagues"
          className="w-full font-semibold py-3 rounded-xl text-center transition-colors bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm"
        >
          Select a league first
        </Link>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Pricing() {
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id");

  const { data: tiers, isLoading } = useQuery({
    queryKey: ["stripePricing"],
    queryFn: stripeApi.getPricing,
  });

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top navigation */}
      <div className="max-w-5xl mx-auto px-4 pt-6">
        <Link
          to="/leagues"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          Back to leagues
        </Link>
      </div>

      {/* Hero */}
      <div className="max-w-5xl mx-auto px-4 py-12 text-center space-y-4">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-green-700">
          Simple, Seasonal Pricing
        </p>
        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 leading-tight">
          One payment per season.<br className="hidden sm:block" /> Unlimited picks.
        </h1>
        <p className="text-gray-500 max-w-md mx-auto">
          Choose the plan that fits your league size. Paid annually per season.
        </p>
      </div>

      {/* Tier grid */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto px-4 pb-16">
          {(tiers ?? []).map((tier) => (
            <TierCard
              key={tier.tier}
              pricing={tier}
              leagueId={leagueId}
              currentTier={null}
            />
          ))}
        </div>
      )}
    </div>
  );
}
