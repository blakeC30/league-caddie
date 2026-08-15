import { useState } from "react";
import type { LeaguePurchaseEvent, LeaguePurchaseStatus, PricingTier } from "../../api/endpoints";
import { stripeApi } from "../../api/endpoints";
import { Spinner } from "../Spinner";
import { TIER_ORDER } from "./constants";
import { SectionIcon, type ConfirmModalState } from "./shared";

export interface LeaguePlanSectionProps {
  leagueId: string;
  purchase: LeaguePurchaseStatus | null | undefined;
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
    <section className="bg-white rounded-sm border border-ink-200 p-4 sm:p-6 space-y-5 overflow-hidden">
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-3 min-w-0">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 0 0 2.25-2.25V6.75A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 19.5Z" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-ink-900">League Plan</h2>
        </div>
        {purchase?.tier !== "elite" && (
          billingEditing ? (
            <button
              onClick={() => { setBillingEditing(false); setUpgradeSelectedTier(""); }}
              className="text-sm font-semibold text-fairway-700 hover:text-fairway-900 transition-colors"
            >
              Done
            </button>
          ) : (
            <button
              onClick={() => setBillingEditing(true)}
              className="text-sm font-semibold text-fairway-700 hover:text-fairway-900 transition-colors"
            >
              Edit
            </button>
          )
        )}
      </div>

      {!purchase?.paid_at ? (
        /* No active purchase */
        <div className="space-y-4">
          <div className="bg-brass-50 border border-brass-100 rounded-xs p-4 text-brass-700 text-sm">
            No active League Plan for 2026. Purchase a League Plan to unlock all league features.
          </div>
          {billingEditing && (
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => handleQuickPurchase("starter")}
                disabled={billingLoading}
                className="text-sm font-semibold text-white bg-fairway-700 hover:bg-fairway-700 px-4 py-2 rounded-xs transition-colors shadow-sheet disabled:opacity-50 flex items-center gap-2"
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
          <div className="bg-ink-50 rounded-xs p-3 sm:p-4 space-y-3 overflow-hidden">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                  purchase.tier === "elite"
                    ? "bg-brass-100 text-brass-700"
                    : purchase.tier === "pro"
                    ? "bg-ink-100 text-ink-800"
                    : purchase.tier === "standard"
                    ? "bg-fairway-100 text-fairway-700"
                    : "bg-ink-200 text-ink-700"
                }`}
              >
                {purchase.tier ? purchase.tier.charAt(0).toUpperCase() + purchase.tier.slice(1) : "—"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-ink-400 font-medium">Member limit</p>
                <p className="font-semibold text-ink-800">
                  Up to {purchase.member_limit?.toLocaleString() ?? "—"} members
                </p>
              </div>
              <div>
                <p className="text-xs text-ink-400 font-medium">Plan price</p>
                <p className="font-semibold text-ink-800">
                  {(() => {
                    const tierPrice = pricingTiers.find((p) => p.tier === purchase.tier)?.amount_cents;
                    return tierPrice != null ? `$${(tierPrice / 100).toFixed(2)}` : "—";
                  })()}
                </p>
              </div>
            </div>
          </div>

          {/* Payment history — always visible when events exist */}
          {purchaseEvents.length > 0 && (
            <div className="space-y-2">
              <p className="text-micro uppercase text-ink-400">Payment History</p>
              <div className="overflow-x-auto -mx-4 sm:-mx-6 px-4 sm:px-6">
                <table className="w-full min-w-[480px] text-sm">
                  <thead>
                    <tr className="text-left text-micro uppercase text-ink-400 border-b border-ink-100">
                      <th className="py-2 pr-3 font-bold">Type</th>
                      <th className="py-2 pr-3 font-bold">Plan</th>
                      <th className="py-2 pr-3 font-bold">Date</th>
                      <th className="py-2 pr-3 font-bold">Paid by</th>
                      <th className="py-2 text-right font-bold">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-50">
                    {purchaseEvents.map((event) => {
                      const label = event.event_type === "upgrade" ? "Upgrade" : "Purchase";
                      const tierLabel = event.tier.charAt(0).toUpperCase() + event.tier.slice(1);
                      const date = new Date(event.paid_at).toLocaleDateString("en-US", {
                        month: "short", day: "numeric", year: "numeric",
                      });
                      return (
                        <tr key={event.id} className="text-ink-700">
                          <td className="py-2.5 pr-3">
                            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full whitespace-nowrap ${
                              event.event_type === "upgrade"
                                ? "bg-ink-50 text-ink-700"
                                : "bg-fairway-50 text-fairway-700"
                            }`}>
                              {label}
                            </span>
                          </td>
                          <td className="py-2.5 pr-3 whitespace-nowrap">{tierLabel}</td>
                          <td className="py-2.5 pr-3 text-ink-400 text-xs whitespace-nowrap">{date}</td>
                          <td className="py-2.5 pr-3 text-ink-400 text-xs truncate max-w-[140px]">
                            {event.paid_by_email ?? "—"}
                          </td>
                          <td className="py-2.5 text-right font-semibold text-ink-800 tabular-nums whitespace-nowrap">
                            ${(event.amount_cents / 100).toFixed(2)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Upgrade League Plan — only shown in edit mode, only if not already on elite */}
          {billingEditing && purchase.tier !== "elite" && (
            <div className="space-y-4">
              <p className="text-sm font-semibold text-ink-700">Upgrade League Plan</p>
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
                        className={`relative flex flex-col items-start gap-1 rounded-xs border-2 p-4 text-left transition-colors ${
                          isSelected
                            ? "border-fairway-700 bg-fairway-50"
                            : "border-ink-200 bg-white hover:border-fairway-300"
                        }`}
                      >
                        <span className={`text-sm font-bold ${isSelected ? "text-fairway-700" : "text-ink-900"}`}>
                          {label}
                        </span>
                        <span className={`text-xl font-extrabold ${isSelected ? "text-fairway-700" : "text-ink-900"}`}>
                          ${upgradeDollars}
                        </span>
                        <span className="text-xs text-ink-500">upgrade cost</span>
                        <span className="mt-2 text-xs text-ink-400">Up to {t.member_limit.toLocaleString()} members</span>
                        <span className="text-xs text-ink-400">{perMember}</span>
                        <span className="text-xs text-ink-400 mt-1">
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
                    <p className="text-xs text-ink-500">
                      You'll be charged{" "}
                      <span className="font-semibold text-ink-700">${(chargeCents / 100).toFixed(2)}</span>
                      {" "}{"—"} the difference between your current League Plan and the{" "}
                      <span className="font-semibold text-ink-700 capitalize">{upgradeSelectedTier}</span> League Plan.
                    </p>
                    <p className="text-xs text-brass-600">
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
                className="text-sm font-semibold text-white bg-fairway-700 hover:bg-fairway-700 px-4 py-2 rounded-xs transition-colors shadow-sheet disabled:opacity-40 flex items-center gap-2"
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
