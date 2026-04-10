/**
 * PickBarChart — pure CSS bar chart showing pick distribution per golfer.
 *
 * Shows all picked golfers as individual bars sorted by pick count descending.
 * The horizontal scroll container handles wide charts for tournaments with many
 * unique picks.
 */

import { useMemo, useState } from "react";
import type { GolferPickGroup } from "../../api/endpoints";

export interface PickBarChartProps {
  groups: GolferPickGroup[];
  noPickMembers: string[];
  isCompleted: boolean;
  myGolferName: string | null; // golfer the current user picked, or null if no pick
  effectiveMultiplier?: number;
  totalMembers: number; // total approved members in the league (for % calculation)
}

type Bar = {
  label: string;
  fullName: string;
  count: number;
  points: number | null;
  earnings: number | null;
  names: string[];
};

export function PickBarChart({ groups, noPickMembers, isCompleted, myGolferName, effectiveMultiplier, totalMembers }: PickBarChartProps) {
  const [tooltip, setTooltip] = useState<{ header: string; pct: string; names: string } | null>(null);

  const bars = useMemo(() => {
    // Sort by pick count desc, then alphabetically by last name for ties.
    const lastName = (name: string) => name.split(" ").pop() ?? name;
    const sortedGroups = [...groups].sort(
      (a, b) => b.pick_count - a.pick_count || lastName(a.golfer_name).localeCompare(lastName(b.golfer_name))
    );

    const result: Bar[] = sortedGroups.map((g) => ({
      label: g.golfer_name.split(" ").pop() ?? g.golfer_name,
      fullName: g.golfer_name,
      count: g.pick_count,
      points: isCompleted ? (g.pickers[0]?.points_earned ?? null) : null,
      earnings: isCompleted ? (g.earnings_usd ?? 0) : null,
      names: g.pickers.map((p) => p.display_name),
    }));

    // Add "No Pick" bar
    if (noPickMembers.length > 0) {
      result.push({
        label: "No Pick",
        fullName: "No Pick",
        count: noPickMembers.length,
        points: null,
        earnings: null,
        names: noPickMembers,
      });
    }

    return result;
  }, [groups, noPickMembers, isCompleted]);

  const maxCount = Math.max(...bars.map((b) => b.count), 1);

  // Color scheme consistent with the site's green palette:
  //   dark green  = current user's pick (matches header/button style — "this is yours")
  //   light green = all other golfers (soft, clearly secondary)
  //   muted red   = no pick submitted
  function barColor(b: Bar): string {
    if (b.label === "No Pick") return "bg-red-300";
    if (myGolferName && b.fullName === myGolferName) return "bg-green-800";
    return "bg-green-300";
  }

  function labelColor(b: Bar): string {
    if (b.label === "No Pick") return "text-red-400";
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-500";
  }

  function countColor(b: Bar): string {
    if (myGolferName && b.fullName === myGolferName) return "text-green-800 font-semibold";
    return "text-gray-500";
  }

  function buildTooltip(b: Bar): { header: string; pct: string; names: string } {
    let earningsStr = "";
    if (b.earnings != null) {
      const mult = effectiveMultiplier ?? 1;
      if (mult > 1) {
        const multiplied = Math.round(b.earnings * mult);
        earningsStr = ` — $${b.earnings.toLocaleString()} (${mult}× = $${multiplied.toLocaleString()})`;
      } else {
        earningsStr = ` — $${b.earnings.toLocaleString()}`;
      }
    }
    const header = b.label === "No Pick" ? "No Pick" : `${b.fullName}${earningsStr}`;
    const pct = totalMembers > 0
      ? `${((b.count / totalMembers) * 100).toFixed(1)}% of league`
      : "";
    const names = b.names.length
      ? [...b.names].sort((a, c) => a.localeCompare(c)).join(", ")
      : "";
    return { header, pct, names };
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
                key={b.fullName}
                className="flex-1 h-full flex flex-col justify-end items-center cursor-pointer group"
                onClick={() => {
                  const tt = buildTooltip(b);
                  setTooltip((prev) => (prev?.header === tt.header ? null : tt));
                }}
              >
                {/* Count + percentage label sits directly above the bar */}
                <span className={`text-[10px] mb-0.5 ${countColor(b)}`}>
                  {b.count}{totalMembers > 0 && <span className="text-gray-500"> ({((b.count / totalMembers) * 100).toFixed(1)}%)</span>}
                </span>
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
              <div key={b.fullName} className="flex-1 relative overflow-visible">
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
        <div className="text-xs bg-gray-100 rounded-lg px-3 py-2 mt-1 space-y-1">
          <p className="font-semibold text-gray-800">{tooltip.header}</p>
          {tooltip.pct && <p className="text-gray-500">{tooltip.pct}</p>}
          {tooltip.names && <p className="text-gray-600">{tooltip.names}</p>}
        </div>
      )}
    </div>
  );
}
