/**
 * SortButton — sortable column header button (mirrors MyPicks.tsx pattern).
 */

export type SortDir = "asc" | "desc";

export interface SortButtonProps {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "left" | "right";
}

export function SortButton({ label, active, dir, onClick, align = "left" }: SortButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
        align === "right" ? "flex-row-reverse" : ""
      } ${
        active ? "text-green-300" : "text-white/60 hover:text-white"
      }`}
    >
      {label}
      <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        {active && dir === "asc" ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
        ) : active && dir === "desc" ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" />
        )}
      </svg>
    </button>
  );
}
