/**
 * PickBarChart — pure CSS bar chart showing pick distribution per golfer.
 */

import { useState } from "react";
import type { GolferPickGroup } from "../../api/endpoints";

export interface PickBarChartProps {
  groups: GolferPickGroup[];
  noPickMembers: string[];
  isCompleted: boolean;
  myGolferName: string | null; // golfer the current user picked, or null if no pick
}

export function PickBarChart({ groups, noPickMembers, isCompleted, myGolferName }: PickBarChartProps) {
  const [tooltip, setTooltip] = useState<string | null>(null);

  // Build chart data: one bar per golfer + one "No Pick" bar if applicable.
  // Sort by pick count desc, then alphabetically by last name for ties.
  const lastName = (name: string) => name.split(" ").pop() ?? name;
  const sortedGroups = [...groups].sort(
    (a, b) => b.pick_count - a.pick_count || lastName(a.golfer_name).localeCompare(lastName(b.golfer_name))
  );
  const bars: { label: string; fullName: string; count: number; points: number | null; names: string[] }[] = [
    ...sortedGroups.map((g) => ({
      label: g.golfer_name.split(" ").pop() ?? g.golfer_name,
      fullName: g.golfer_name,
      count: g.pick_count,
      points: isCompleted ? (g.pickers[0]?.points_earned ?? null) : null,
      names: g.pickers.map((p) => p.display_name),
    })),
    ...(noPickMembers.length > 0
      ? [{ label: "No Pick", fullName: "No Pick", count: noPickMembers.length, points: null, names: noPickMembers }]
      : []),
  ];

  const maxCount = Math.max(...bars.map((b) => b.count), 1);

  // Color scheme consistent with the site's green palette:
  //   dark green  = current user's pick (matches header/button style — "this is yours")
  //   light green = all other golfers (soft, clearly secondary)
  //   muted red   = no pick submitted
  function barColor(b: typeof bars[0]): string {
    if (b.label === "No Pick") return "bg-red-300";
    if (myGolferName && b.fullName === myGolferName) return "bg-green-800";
    return "bg-green-300";
  }

  function labelColor(b: typeof bars[0]): string {
    if (b.label === "No Pick") return "text-red-400";
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-400";
  }

  function countColor(b: typeof bars[0]): string {
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-400";
  }

  return (
    <div className="space-y-2">
      {/*
        The outer div is h-40 with items-end (flex row). Each column child is
        flex-1, which only controls the *width* (main axis). To make percentage
        heights on the bar resolve correctly, each column must have a definite
        height — so we give it h-full. The count label is positioned absolutely
        above the bar so it doesn't consume height that would break the ratio.
      */}
      {/* Scrollable wrapper — on narrow screens the chart scrolls horizontally
          while the tooltip below stays full-width */}
      <div className="overflow-x-auto">
        <div style={{ minWidth: `${bars.length * 48}px` }}>
          <div className="flex items-end gap-2 h-40 px-1">
            {bars.map((b) => (
              <div
                key={b.label}
                className="flex-1 h-full flex flex-col justify-end items-center cursor-pointer group"
                onClick={() => {
                  const text = b.names.length
                    ? `${b.fullName}: ${[...b.names].sort((a, c) => a.localeCompare(c)).join(", ")}`
                    : b.label === "No Pick"
                    ? "No pick submitted"
                    : b.fullName;
                  setTooltip((prev) => (prev === text ? null : text));
                }}
              >
                {/* Count label sits directly above the bar, pushed down by flex justify-end */}
                <span className={`text-[10px] mb-0.5 ${countColor(b)}`}>{b.count}</span>
                {/* Bar — percentage height resolves against the h-full column */}
                <div
                  className={`w-full rounded-t transition-opacity group-hover:opacity-70 ${barColor(b)}`}
                  style={{ height: `${(b.count / maxCount) * 100}%`, minHeight: "4px" }}
                />
              </div>
            ))}
          </div>

          {/* X-axis labels — rotated 45deg downward so long names don't collide or overlap bars */}
          <div className="flex gap-2 px-1" style={{ height: "80px" }}>
            {bars.map((b) => (
              <div key={b.label} className="flex-1 relative overflow-visible">
                <span
                  className={`text-[10px] whitespace-nowrap absolute ${labelColor(b)}`}
                  style={{
                    top: "4px",
                    left: "50%",
                    transform: "rotate(45deg)",
                    transformOrigin: "top left",
                  }}
                >
                  {b.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <p className="text-xs text-gray-600 bg-gray-100 rounded px-3 py-1.5 mt-1">{tooltip}</p>
      )}
    </div>
  );
}
