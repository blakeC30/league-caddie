import { useState } from "react";
import type { LeaguePurchaseEvent, LeaguePurchaseStatus, PricingTier } from "../../api/endpoints";
import { stripeApi } from "../../api/endpoints";
import { Spinner } from "../Spinner";
import { SectionIcon, TIER_ORDER, type ConfirmModalState } from "./shared";

export interface LeaguePlanSectionProps {
  leagueId: string;
  purchase: LeaguePurchaseStatus | undefined;
  pricingTiers: PricingTier[];
  purchaseEvents: LeaguePurchaseEvent[];
  onConfirm: (modal: ConfirmModalState) => void;
}

export function LeaguePlanSection({
  leagueId,
  purchase,
  pricingTiers,
  purchaseEvents,
  onConfirm,
}: LeaguePlanSectionProps) {
  const [billingLoading, setBillingLoading] = useState(false);
  const [upgradeSelectedTier, setUpgradeSelectedTier] = useState<string>("");
  const [billingEditing, setBillingEditing] = useState(false);

  async function handleQuickPurchase(tier: string, upgrade = false) {
    if (!leagueId) return;
    setBillingLoading(true);
    try {
      const { url } = await stripeApi.createCheckoutSession(leagueId, tier, upgrade);
      window.location.href = url;
    } catch {
      setBillingLoading(false);
    }
  }

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-4 sm:p-6 space-y-5 overflow-hidden">
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-3 min-w-0">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 0 0 2.25-2.25V6.75A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 19.5Z" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-gray-900">League Plan</h2>
        </div>
        {billingEditing ? (
          <button
            onClick={() => { setBillingEditing(false); setUpgradeSelectedTier(""); }}
            className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
          >
            Done
          </button>
        ) : (
          <button
            onClick={() => setBillingEditing(true)}
            className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
          >
            Edit
          </button>
        )}
      </div>

      {!purchase?.paid_at ? (
        /* No active purchase */
        <div className="space-y-4">
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-amber-800 text-sm">
            No active League Plan for 2026. Purchase a League Plan to unlock all league features.
          </div>
          {billingEditing && (
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => handleQuickPurchase("starter")}
                disabled={billingLoading}
                className="text-sm font-semibold text-white bg-green-800 hover:bg-green-700 px-4 py-2 rounded-xl transition-colors shadow-sm disabled:opacity-50 flex items-center gap-2"
              >
                {billingLoading ? <Spinner /> : null}
                Purchase — Starter ($50)
              </button>
            </div>
          )}
        </div>
      ) : (
        /* Has active purchase */
        <div className="space-y-5">
          {/* Plan summary — always visible */}
          <div className="bg-gray-50 rounded-xl p-3 sm:p-4 space-y-3 overflow-hidden">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                  purchase.tier === "elite"
                    ? "bg-amber-100 text-amber-800"
                    : purchase.tier === "pro"
                    ? "bg-blue-100 text-blue-800"
                    : purchase.tier === "standard"
                    ? "bg-green-100 text-green-800"
                    : "bg-gray-200 text-gray-700"
                }`}
              >
                {purchase.tier ? purchase.tier.charAt(0).toUpperCase() + purchase.tier.slice(1) : "—"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-gray-400 font-medium">Member limit</p>
                <p className="font-semibold text-gray-800">
                  Up to {purchase.member_limit?.toLocaleString() ?? "—"} members
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 font-medium">Plan price</p>
                <p className="font-semibold text-gray-800">
                  {(() => {
                    const tierPrice = pricingTiers.find((p) => p.tier === purchase.tier)?.amount_cents;
                    return tierPrice != null ? `$${(tierPrice / 100).toFixed(2)}` : "—";
                  })()}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 font-medium">Paid on</p>
                <p className="font-semibold text-gray-800">
                  {purchase.paid_at
                    ? new Date(purchase.paid_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })
                    : "—"}
                </p>
              </div>
              {purchase.paid_by_email && (
                <div>
                  <p className="text-xs text-gray-400 font-medium">Paid by</p>
                  <p className="font-semibold text-gray-800 break-all">{purchase.paid_by_email}</p>
                </div>
              )}
            </div>
          </div>

          {/* Payment history — always visible when events exist */}
          {purchaseEvents.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Payment History</p>
              <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 overflow-hidden">
                {purchaseEvents.map((event) => {
                  const label = event.event_type === "upgrade" ? "Upgrade" : "League Plan";
                  const tierLabel = event.tier.charAt(0).toUpperCase() + event.tier.slice(1);
                  const date = new Date(event.paid_at).toLocaleDateString("en-US", {
                    month: "short", day: "numeric", year: "numeric",
                  });
                  return (
                    <div key={event.id} className="flex items-center justify-between px-3 py-2.5 bg-white text-sm">
                      <div className="flex items-center gap-2.5">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                          event.event_type === "upgrade"
                            ? "bg-blue-50 text-blue-700"
                            : "bg-green-50 text-green-700"
                        }`}>
                          {label}
                        </span>
                        <span className="text-gray-700">{tierLabel} plan</span>
                      </div>
                      <div className="flex items-center gap-4 text-right">
                        <span className="text-gray-400 text-xs">{date}</span>
                        <span className="font-semibold text-gray-800 tabular-nums">
                          ${(event.amount_cents / 100).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Upgrade League Plan — only shown in edit mode, only if not already on elite */}
          {billingEditing && purchase.tier !== "elite" && (
            <div className="space-y-4">
              <p className="text-sm font-semibold text-gray-700">Upgrade League Plan</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {pricingTiers
                  .filter((t) => (TIER_ORDER[t.tier] ?? 0) > (TIER_ORDER[purchase.tier ?? ""] ?? 0))
                  .map((t) => {
                    const isSelected = upgradeSelectedTier === t.tier;
                    const currentTierFullPrice = pricingTiers.find((p) => p.tier === purchase.tier)?.amount_cents ?? 0;
                    const upgradeCostCents = t.amount_cents - currentTierFullPrice;
                    const totalDollars = (t.amount_cents / 100).toFixed(2);
                    const upgradeDollars = (Math.max(0, upgradeCostCents) / 100).toFixed(2);
                    const label = t.tier.charAt(0).toUpperCase() + t.tier.slice(1);
                    const perMember = `~$${(t.amount_cents / t.member_limit / 100).toFixed(2)}/member`;
                    return (
                      <button
                        key={t.tier}
                        type="button"
                        onClick={() => setUpgradeSelectedTier(t.tier)}
                        className={`relative flex flex-col items-start gap-1 rounded-xl border-2 p-4 text-left transition-colors ${
                          isSelected
                            ? "border-green-700 bg-green-50"
                            : "border-gray-200 bg-white hover:border-green-300"
                        }`}
                      >
                        <span className={`text-sm font-bold ${isSelected ? "text-green-800" : "text-gray-900"}`}>
                          {label}
                        </span>
                        <span className={`text-xl font-extrabold ${isSelected ? "text-green-800" : "text-gray-900"}`}>
                          ${upgradeDollars}
                        </span>
                        <span className="text-xs text-gray-500">upgrade cost</span>
                        <span className="mt-2 text-xs text-gray-400">Up to {t.member_limit.toLocaleString()} members</span>
                        <span className="text-xs text-gray-400">{perMember}</span>
                        <span className="text-xs text-gray-400 mt-1">
                          Full plan price: ${totalDollars}/season
                        </span>
                      </button>
                    );
                  })}
              </div>
              {upgradeSelectedTier && (() => {
                const selected = pricingTiers.find((t) => t.tier === upgradeSelectedTier);
                const currentTierFullPrice = pricingTiers.find((p) => p.tier === purchase.tier)?.amount_cents ?? 0;
                const chargeCents = Math.max(0, (selected?.amount_cents ?? 0) - currentTierFullPrice);
                return (
                  <div className="space-y-1">
                    <p className="text-xs text-gray-500">
                      You'll be charged{" "}
                      <span className="font-semibold text-gray-700">${(chargeCents / 100).toFixed(2)}</span>
                      {" "}{"—"} the difference between your current League Plan and the{" "}
                      <span className="font-semibold text-gray-700 capitalize">{upgradeSelectedTier}</span> League Plan.
                    </p>
                    <p className="text-xs text-amber-600">
                      This is a personal payment charged to your card, not the original purchaser's.
                    </p>
                  </div>
                );
              })()}
              <button
                type="button"
                disabled={!upgradeSelectedTier || billingLoading}
                onClick={() => {
                  if (!upgradeSelectedTier) return;
                  const selected = pricingTiers.find((t) => t.tier === upgradeSelectedTier);
                  const currentTierFullPrice = pricingTiers.find((p) => p.tier === purchase.tier)?.amount_cents ?? 0;
                  const chargeCents = Math.max(0, (selected?.amount_cents ?? 0) - currentTierFullPrice);
                  const tierLabel = upgradeSelectedTier.charAt(0).toUpperCase() + upgradeSelectedTier.slice(1);
                  onConfirm({
                    title: `Upgrade to ${tierLabel}?`,
                    message: `You will be charged $${(chargeCents / 100).toFixed(2)} to your personal card. This upgrades the league to the ${tierLabel} plan (up to ${selected?.member_limit?.toLocaleString()} members).`,
                    confirmLabel: `Pay $${(chargeCents / 100).toFixed(2)} & Upgrade`,
                    onConfirm: () => handleQuickPurchase(upgradeSelectedTier, true),
                  });
                }}
                className="text-sm font-semibold text-white bg-green-800 hover:bg-green-700 px-4 py-2 rounded-xl transition-colors shadow-sm disabled:opacity-40 flex items-center gap-2"
              >
                {billingLoading ? <Spinner /> : null}
                {upgradeSelectedTier
                  ? `Upgrade to ${upgradeSelectedTier.charAt(0).toUpperCase() + upgradeSelectedTier.slice(1)}`
                  : "Upgrade"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
