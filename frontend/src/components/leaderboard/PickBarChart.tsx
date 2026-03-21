/**
 * PickBarChart — pure CSS bar chart showing pick distribution per golfer.
 *
 * When there are more than 20 golfers, the chart shows the top 20 most-picked
 * and aggregates the rest into a single "Other" bar. This keeps the DOM small
 * and the chart readable regardless of league size.
 */

import { useMemo, useState } from "react";
import type { GolferPickGroup } from "../../api/endpoints";

export interface PickBarChartProps {
  groups: GolferPickGroup[];
  noPickMembers: string[];
  isCompleted: boolean;
  myGolferName: string | null; // golfer the current user picked, or null if no pick
}

const MAX_BARS = 20;

type Bar = {
  label: string;
  fullName: string;
  count: number;
  points: number | null;
  names: string[];
  isOther?: boolean;
};

export function PickBarChart({ groups, noPickMembers, isCompleted, myGolferName }: PickBarChartProps) {
  const [tooltip, setTooltip] = useState<string | null>(null);

  const bars = useMemo(() => {
    // Sort by pick count desc, then alphabetically by last name for ties.
    const lastName = (name: string) => name.split(" ").pop() ?? name;
    const sortedGroups = [...groups].sort(
      (a, b) => b.pick_count - a.pick_count || lastName(a.golfer_name).localeCompare(lastName(b.golfer_name))
    );

    // If the current user's pick is outside the top 20, ensure it's included
    // by replacing the last "Other" slot with it.
    let topGroups = sortedGroups;
    let otherGroups: GolferPickGroup[] = [];

    if (sortedGroups.length > MAX_BARS) {
      topGroups = sortedGroups.slice(0, MAX_BARS);
      otherGroups = sortedGroups.slice(MAX_BARS);

      // If user's golfer got pushed into "Other", swap it in
      if (myGolferName) {
        const myInOther = otherGroups.findIndex((g) => g.golfer_name === myGolferName);
        if (myInOther !== -1) {
          const myGroup = otherGroups.splice(myInOther, 1)[0];
          const lastTop = topGroups.pop()!;
          otherGroups.unshift(lastTop);
          topGroups.push(myGroup);
        }
      }
    }

    const result: Bar[] = topGroups.map((g) => ({
      label: g.golfer_name.split(" ").pop() ?? g.golfer_name,
      fullName: g.golfer_name,
      count: g.pick_count,
      points: isCompleted ? (g.pickers[0]?.points_earned ?? null) : null,
      names: g.pickers.map((p) => p.display_name),
    }));

    // Aggregate remaining golfers into "Other" bar
    if (otherGroups.length > 0) {
      const otherCount = otherGroups.reduce((sum, g) => sum + g.pick_count, 0);

      // Build a summary string grouped by pick count:
      // e.g. "3 golfers with 2 picks, 8 golfers with 1 pick"
      const countBuckets = new Map<number, number>();
      for (const g of otherGroups) {
        countBuckets.set(g.pick_count, (countBuckets.get(g.pick_count) ?? 0) + 1);
      }
      const summaryParts = [...countBuckets.entries()]
        .sort((a, b) => b[0] - a[0])
        .map(([picks, golferCount]) =>
          `${golferCount} golfer${golferCount !== 1 ? "s" : ""} with ${picks} pick${picks !== 1 ? "s" : ""}`
        );

      result.push({
        label: "Other",
        fullName: `Other (${otherGroups.length} golfers)`,
        count: otherCount,
        points: null,
        names: summaryParts,
        isOther: true,
      });
    }

    // Add "No Pick" bar
    if (noPickMembers.length > 0) {
      result.push({
        label: "No Pick",
        fullName: "No Pick",
        count: noPickMembers.length,
        points: null,
        names: noPickMembers,
      });
    }

    return result;
  }, [groups, noPickMembers, isCompleted, myGolferName]);

  const maxCount = Math.max(...bars.map((b) => b.count), 1);

  // Color scheme consistent with the site's green palette:
  //   dark green  = current user's pick (matches header/button style — "this is yours")
  //   light green = all other golfers (soft, clearly secondary)
  //   gray        = "Other" aggregated bar
  //   muted red   = no pick submitted
  function barColor(b: Bar): string {
    if (b.label === "No Pick") return "bg-red-300";
    if (b.isOther) return "bg-gray-300";
    if (myGolferName && b.fullName === myGolferName) return "bg-green-800";
    return "bg-green-300";
  }

  function labelColor(b: Bar): string {
    if (b.label === "No Pick") return "text-red-400";
    if (b.isOther) return "text-gray-400 italic";
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-400";
  }

  function countColor(b: Bar): string {
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-400";
  }

  function buildTooltip(b: Bar): string {
    if (b.isOther) {
      return `${b.fullName}: ${b.names.join(", ")}`;
    }
    if (b.names.length) {
      return `${b.fullName}: ${[...b.names].sort((a, c) => a.localeCompare(c)).join(", ")}`;
    }
    return b.label === "No Pick" ? "No pick submitted" : b.fullName;
  }

  return (
    <div className="space-y-2">
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
                  const text = buildTooltip(b);
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
