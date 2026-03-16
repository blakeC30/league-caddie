/**
 * PickForm — golfer selection form for a specific tournament.
 *
 * Shows the tournament's field filtered to exclude golfers the user has
 * already picked this season. Submits the pick via the API.
 */

import { useState } from "react";
import type { GolferInField, Pick } from "../api/endpoints";
import { GolferCard } from "./GolferCard";

interface Props {
  field: GolferInField[];
  usedGolferIds: Set<string>; // golfer IDs already picked this season
  teedOffGolferIds: Set<string>; // golfer IDs whose Round 1 tee time has passed (in_progress tournaments only)
  existingPick?: Pick; // if the user already has a pick for this tournament
  onSubmit: (golferId: string) => Promise<void>;
  submitting: boolean;
  error?: string;
}

export function PickForm({
  field,
  usedGolferIds,
  teedOffGolferIds,
  existingPick,
  onSubmit,
  submitting,
  error,
}: Props) {
  const [selected, setSelected] = useState<string | null>(
    existingPick?.golfer_id ?? null
  );
  const [search, setSearch] = useState("");

  const filtered = field
    .filter((g) => g.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    await onSubmit(selected);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Search */}
      <input
        type="text"
        placeholder="Search golfers…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
      />

      {/* Golfer list */}
      <div className="space-y-2 max-h-[480px] overflow-y-auto p-1">
        {filtered.length === 0 && (
          <p className="text-center text-gray-400 py-8">No golfers match your search.</p>
        )}
        {filtered.map((g) => (
          <GolferCard
            key={g.id}
            golfer={g}
            selected={selected === g.id}
            alreadyUsed={usedGolferIds.has(g.id) && g.id !== existingPick?.golfer_id}
            alreadyTeedOff={teedOffGolferIds.has(g.id) && g.id !== existingPick?.golfer_id}
            onClick={() => setSelected(g.id)}
          />
        ))}
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={!selected || submitting}
        className="w-full bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold py-2.5 rounded-lg transition-colors"
      >
        {submitting ? "Saving…" : existingPick ? "Change Pick" : "Submit Pick"}
      </button>
    </form>
  );
}
