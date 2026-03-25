/**
 * Constants used across ManageLeague sub-sections.
 */

// Tier definitions — prices must match backend PRICING_TIERS
export const TIER_ORDER: Record<string, number> = { starter: 1, standard: 2, pro: 3, elite: 4 };

// Number of playoff tournament rounds required for each bracket size.
export const REQUIRED_ROUNDS: Record<number, number> = { 2: 1, 4: 2, 8: 3, 16: 4, 32: 4 };
