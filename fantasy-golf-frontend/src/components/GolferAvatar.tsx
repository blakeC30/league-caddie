/**
 * GolferAvatar — shows an ESPN headshot for a golfer.
 *
 * ESPN serves headshots at a predictable URL keyed by pga_tour_id:
 *   https://a.espncdn.com/i/headshots/golf/players/full/{pga_tour_id}.png
 *
 * Falls back to a green circle with the fallback content (typically the
 * world ranking number or the golfer's last initial) if the image 404s.
 */

import { useState } from "react";

interface Props {
  pgaTourId: string;
  name: string;
  /** Tailwind size classes applied to both the img and the fallback div. Defaults to w-10 h-10. */
  className?: string;
  /** Shown inside the fallback circle when the image fails to load. */
  fallback?: React.ReactNode;
}

export function GolferAvatar({ pgaTourId, name, className = "w-10 h-10", fallback }: Props) {
  const [failed, setFailed] = useState(false);
  const src = `https://a.espncdn.com/i/headshots/golf/players/full/${pgaTourId}.png`;
  if (failed) {
    return (
      <div
        className={`rounded-full bg-green-800 text-white flex items-center justify-center text-xs font-bold shrink-0 ${className}`}
      >
        {fallback ?? "—"}
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={name}
      className={`rounded-full object-cover object-top bg-gray-100 shrink-0 ${className}`}
      onError={() => setFailed(true)}
    />
  );
}
