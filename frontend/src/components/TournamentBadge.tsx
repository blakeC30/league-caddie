/**
 * TournamentBadge — shows tournament status and major/multiplier indicator.
 *
 * The old version reached for a fresh hue per state (blue upcoming, yellow
 * live, amber 2x, purple playoff). Under the Pairings Sheet palette there are
 * only three signals: LIVE is filled in flag red because it is the one thing
 * that is happening now, a multiplier above 1x is the brass mark, and
 * everything else is a hairline chip in ink.
 */

import type { Tournament } from "../api/endpoints";
import { formatDate as fmt, formatPurse } from "../utils";
import { Chip } from "./ui";

type WithMultiplier = Tournament & { effective_multiplier?: number };

const STATUS_LABEL: Record<Tournament["status"], string> = {
  scheduled: "Upcoming",
  in_progress: "Live",
  completed: "Final",
};

interface Props {
  // Accept both plain Tournament and LeagueTournamentOut (which adds effective_multiplier).
  tournament: WithMultiplier;
  showDates?: boolean;
  isPlayoff?: boolean;
  /** When true, renders badges and dates as separate exported sub-components. */
  compact?: boolean;
}

function StatusChip({ status }: { status: Tournament["status"] }) {
  if (status === "in_progress") return <Chip tone="live">Live</Chip>;
  return <Chip tone={status === "completed" ? "muted" : "default"}>{STATUS_LABEL[status]}</Chip>;
}

function MultiplierChip({ mult }: { mult?: number }) {
  if (mult === undefined || mult <= 1) return null;
  return <Chip tone="multiplier">{mult}×</Chip>;
}

/** Just the chips (status, multiplier, playoff). */
export function TournamentBadgePills({
  tournament,
  isPlayoff = false,
}: {
  tournament: WithMultiplier;
  isPlayoff?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <StatusChip status={tournament.status} />
      <MultiplierChip mult={tournament.effective_multiplier} />
      {isPlayoff && <Chip>Playoff</Chip>}
    </div>
  );
}

/** Just the dates and purse line. */
export function TournamentBadgeDates({ tournament }: { tournament: Tournament }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0 text-small text-ink-500">
      <span>
        {fmt(tournament.start_date)} – {fmt(tournament.end_date)}
      </span>
      {formatPurse(tournament.purse_usd) && (
        <span className="text-ink-400">{formatPurse(tournament.purse_usd)} purse</span>
      )}
    </div>
  );
}

export function TournamentBadge({ tournament, showDates = false, isPlayoff = false }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-small text-ink-500">
      <StatusChip status={tournament.status} />

      {showDates && (
        <span>
          {fmt(tournament.start_date)} – {fmt(tournament.end_date)}
        </span>
      )}

      {formatPurse(tournament.purse_usd) && (
        <span className="text-ink-400">{formatPurse(tournament.purse_usd)} purse</span>
      )}

      <MultiplierChip mult={tournament.effective_multiplier} />
      {isPlayoff && <Chip>Playoff</Chip>}
    </div>
  );
}
