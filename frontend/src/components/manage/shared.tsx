/**
 * Shared components and constants used across ManageLeague sub-sections.
 */

import { useEffect, useRef, useState } from "react";
import { useDropdownDirection } from "../../hooks/useDropdownDirection";

// ---------------------------------------------------------------------------
// Tier definitions — prices must match backend PRICING_TIERS
// ---------------------------------------------------------------------------

export const TIER_ORDER: Record<string, number> = { starter: 1, standard: 2, pro: 3, elite: 4 };

// Number of playoff tournament rounds required for each bracket size.
export const REQUIRED_ROUNDS: Record<number, number> = { 2: 1, 4: 2, 8: 3, 16: 4, 32: 4 };

// ---------------------------------------------------------------------------
// Custom dropdown — matches the Leaderboard tournament picker style
// ---------------------------------------------------------------------------

export interface DropdownOption {
  value: string;
  label: string;
  badge?: string;
  badgeColor?: string;
}

export function DropdownSelect({
  value,
  onChange,
  placeholder,
  options,
  disabled = false,
}: {
  value: string;
  onChange: (val: string) => void;
  placeholder: string;
  options: DropdownOption[];
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropDir = useDropdownDirection(ref, open);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const selected = options.find((o) => o.value === value);
  const filtered = search
    ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase()))
    : options;

  return (
    <div
      ref={ref}
      className="relative"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          setOpen(false);
          setSearch("");
          triggerRef.current?.focus();
        }
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        onClick={() => { if (!disabled) { setOpen((o) => !o); setSearch(""); } }}
        className={`w-full flex items-center gap-2 text-sm border rounded-lg px-3 py-1.5 bg-white text-left transition-colors focus:outline-none focus:ring-2 focus:ring-green-700 ${
          disabled
            ? "border-gray-200 text-gray-400 cursor-not-allowed opacity-60"
            : "border-gray-300 text-gray-700 hover:border-green-500 cursor-pointer"
        }`}
      >
        <span className="flex-1 truncate">
          {selected ? selected.label : <span className="text-gray-400">{placeholder}</span>}
        </span>
        <svg
          className={`h-4 w-4 text-gray-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && !disabled && (
        <div className={`absolute left-0 right-0 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-20 ${dropDir === "up" ? "bottom-full mb-1" : "top-full mt-1"}`}>
          {/* Search input — filters the list, value is never submitted directly */}
          <div className="px-3 py-2 border-b border-gray-100">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="w-full text-sm outline-none placeholder-gray-400 bg-transparent"
            />
          </div>
          <div className="max-h-56 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-4 py-3 text-sm text-gray-400">No results.</p>
            ) : (
              filtered.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => { onChange(opt.value); setOpen(false); setSearch(""); }}
                  className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between gap-3 transition-colors ${
                    opt.value === value ? "bg-green-50 text-green-900" : "hover:bg-gray-50 text-gray-700"
                  }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {opt.badge && (
                    <span className={`text-xs shrink-0 font-medium px-2 py-0.5 rounded-full ${opt.badgeColor ?? "bg-gray-100 text-gray-500"}`}>
                      {opt.badge}
                    </span>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small icon helpers
// ---------------------------------------------------------------------------

export function SectionIcon({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-8 h-8 bg-green-50 text-green-700 rounded-lg flex items-center justify-center flex-shrink-0">
      {children}
    </div>
  );
}

export function LockedBadge({ tooltip }: { tooltip: string }) {
  return (
    <span className="relative group inline-flex items-center ml-1.5 align-middle">
      <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
      </svg>
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block whitespace-nowrap rounded-lg bg-gray-800 px-2.5 py-1.5 text-xs text-white z-20 shadow-lg">
        {tooltip}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Confirm modal types — shared across sections
// ---------------------------------------------------------------------------

export interface ConfirmModalState {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
}
