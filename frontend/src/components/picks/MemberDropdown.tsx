import { useRef, useEffect, useState } from "react";
import { useDropdownDirection } from "../../hooks/useDropdownDirection";
import type { LeagueMember } from "../../api/endpoints";

export interface MemberDropdownProps {
  approvedMembers: LeagueMember[];
  viewingUserId: string | null;
  onSelectUser: (userId: string) => void;
}

export function MemberDropdown({ approvedMembers, viewingUserId, onSelectUser }: MemberDropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropDir = useDropdownDirection(dropdownRef, open);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const sortedMembers = [...approvedMembers].sort((a, b) =>
    a.user.display_name.localeCompare(b.user.display_name)
  );
  const viewingMember = sortedMembers.find((m) => m.user_id === viewingUserId);
  const filteredMembers = search
    ? sortedMembers.filter((m) =>
        m.user.display_name.toLowerCase().includes(search.toLowerCase())
      )
    : sortedMembers;

  return (
    <div
      ref={dropdownRef}
      className="relative inline-block"
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
        onClick={() => { setOpen((o) => !o); setSearch(""); }}
        className="min-w-[180px] flex items-center gap-2 text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white text-gray-700 hover:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-700 transition-colors"
      >
        <span className="flex-1 text-left truncate">
          {viewingMember ? viewingMember.user.display_name : "Select a member…"}
        </span>
        <svg
          className={`h-4 w-4 text-gray-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className={`absolute left-0 w-64 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-10 ${dropDir === "up" ? "bottom-full mb-1" : "top-full mt-1"}`}>
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
          <div className="max-h-64 overflow-y-auto">
            {filteredMembers.length === 0 ? (
              <p className="px-4 py-3 text-sm text-gray-400">No results.</p>
            ) : (
              filteredMembers.map((m) => (
                <button
                  key={m.user_id}
                  type="button"
                  onClick={() => {
                    onSelectUser(m.user_id);
                    setOpen(false);
                    setSearch("");
                  }}
                  className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between gap-3 transition-colors ${
                    m.user_id === viewingUserId ? "bg-green-50 text-green-900" : "hover:bg-gray-50 text-gray-700"
                  }`}
                >
                  <span className="truncate">{m.user.display_name}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
