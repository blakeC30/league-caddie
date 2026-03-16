/**
 * GolferCard — displays a golfer's details in the pick form.
 * Highlights when selected; greyed out when already used this season or
 * when the golfer has already teed off during an in-progress tournament.
 */

import type { Golfer } from "../api/endpoints";
import { GolferAvatar } from "./GolferAvatar";

interface Props {
  golfer: Golfer;
  selected?: boolean;
  alreadyUsed?: boolean;
  /** True when the golfer's Round 1 tee time has passed (in_progress tournament only). */
  alreadyTeedOff?: boolean;
  onClick?: () => void;
}

export function GolferCard({ golfer, selected, alreadyUsed, alreadyTeedOff, onClick }: Props) {
  const base =
    "flex items-center gap-3 px-4 py-3 rounded-xl border cursor-pointer transition-colors";

  // Either flag disables the card — they are mutually exclusive in practice but
  // treated uniformly here for safety.
  const disabled = alreadyUsed || alreadyTeedOff;

  const style = disabled
    ? `${base} cursor-not-allowed border-gray-200 bg-gray-50`
    : selected
    ? `${base} border-green-600 bg-green-50 ring-2 ring-green-500`
    : `${base} border-gray-200 bg-white hover:border-green-400 hover:bg-green-50`;

  return (
    <div
      className={style}
      onClick={disabled ? undefined : onClick}
      role={disabled ? undefined : "button"}
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) => {
        if (!disabled && (e.key === "Enter" || e.key === " ")) onClick?.();
      }}
    >
      <GolferAvatar
        pgaTourId={golfer.pga_tour_id}
        name={golfer.name}
        className={`w-10 h-10${disabled ? " opacity-40" : ""}`}
      />

      <div className="flex-1 min-w-0">
        <p className={`font-medium truncate ${disabled ? "text-gray-400" : "text-gray-900"}`}>
          {golfer.name}
        </p>
        {golfer.country && (
          <p className="text-xs text-gray-400 truncate">{golfer.country}</p>
        )}
      </div>

      {alreadyUsed && (
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-gray-200 text-gray-500 shrink-0">
          Used
        </span>
      )}
      {alreadyTeedOff && !alreadyUsed && (
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 shrink-0">
          Teed off
        </span>
      )}
      {selected && !disabled && (
        <span className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center shrink-0">
          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
        </span>
      )}
    </div>
  );
}
