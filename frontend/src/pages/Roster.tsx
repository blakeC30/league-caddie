/**
 * Roster — displays all league members with name and contact details.
 * Searchable and paginated (50 per page).
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ClearableInput } from "../components/ClearableInput";
import { useRoster, useLeagueMembers } from "../hooks/useLeague";
import { useAuthStore } from "../store/authStore";
import { RosterSkeleton } from "../components/Skeleton";

const PAGE_SIZE = 25;

export function Roster() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { data: roster, isLoading } = useRoster(leagueId!);
  const { data: members } = useLeagueMembers(leagueId!);
  const currentUser = useAuthStore((s) => s.user);
  const isManager = members?.some((m) => m.user_id === currentUser?.id && m.role === "manager") ?? false;
  const showEmails = isManager && roster?.some((m) => m.email != null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    document.title = "Roster — League Caddie";
  }, []);

  // Reset to page 1 when search changes
  useEffect(() => {
    setPage(1);
  }, [search]);

  const sorted = useMemo(
    () =>
      roster
        ? [...roster].sort((a, b) =>
            a.display_name
              .trim()
              .localeCompare(b.display_name.trim(), undefined, { sensitivity: "base" }),
          )
        : [],
    [roster],
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return sorted;
    const q = search.toLowerCase();
    return sorted.filter(
      (m) =>
        m.display_name.toLowerCase().includes(q) ||
        m.first_name.toLowerCase().includes(q) ||
        m.last_name.toLowerCase().includes(q) ||
        (m.email && m.email.toLowerCase().includes(q)),
    );
  }, [sorted, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  if (isLoading) {
    return <RosterSkeleton />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to={`/leagues/${leagueId}`}
          className="inline-flex items-center gap-1 text-sm text-ink-500 hover:text-fairway-700 mb-3 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          Dashboard
        </Link>
        <h1 className="text-title text-ink-950">Roster</h1>
      </div>

      {/* Search + count */}
      {sorted.length > 0 && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
          <div className="w-full sm:w-72">
            <ClearableInput
              placeholder="Search members..."
              aria-label="Search members"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch("")}
              className="w-full px-3 py-2 border border-ink-300 rounded-xs text-sm focus:outline-none focus:ring-2 focus:ring-fairway-600 focus:border-transparent transition-shadow"
            />
          </div>
          <p className="text-sm text-ink-500">
            {filtered.length === sorted.length
              ? `${sorted.length} members`
              : `${filtered.length} of ${sorted.length} members`}
          </p>
        </div>
      )}

      {/* Table */}
      {sorted.length === 0 ? (
        <div className="bg-ink-50 rounded-sm border border-ink-200 p-16 text-center space-y-3">
          <div className="w-12 h-12 rounded-sm bg-ink-200 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6 text-ink-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128H9m6 0a5.972 5.972 0 0 0-.786-3.07M9 19.128v-.003c0-1.113.285-2.16.786-3.07M9 19.128H3.375a4.125 4.125 0 0 1 7.533-2.493M9 19.128a5.972 5.972 0 0 1 .786-3.07m5.428 0a6.002 6.002 0 0 0-6.428 0M12 12.75a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
            </svg>
          </div>
          <p className="font-semibold text-ink-700">No members yet</p>
          <p className="text-sm text-ink-400">Invite people to join this league to see them here.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-ink-50 rounded-sm border border-ink-200 p-10 text-center">
          <p className="text-sm text-ink-500">No members match "{search}"</p>
        </div>
      ) : (
        <div className="bg-white border border-ink-200 rounded-sm overflow-hidden shadow-sheet">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead className="bg-fairway-900 text-white">
                <tr>
                  <th className="px-4 py-2.5 text-left text-micro uppercase">
                    Display Name
                  </th>
                  <th className="px-4 py-2.5 text-left text-micro uppercase">
                    First Name
                  </th>
                  <th className="px-4 py-2.5 text-left text-micro uppercase">
                    Last Name
                  </th>
                  <th className="px-4 py-2.5 text-left text-micro uppercase whitespace-nowrap">
                    Role
                  </th>
                  <th className="px-4 py-2.5 text-left text-micro uppercase whitespace-nowrap">
                    Joined
                  </th>
                  {showEmails && (
                    <th className="px-4 py-2.5 text-left text-micro uppercase whitespace-nowrap">
                      Email
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {paginated.map((member, i) => (
                  <tr
                    key={member.user_id}
                    className={`border-t border-ink-100 ${i % 2 !== 0 ? "bg-ink-50" : "bg-white"}`}
                  >
                    <td className="px-4 py-3 font-medium text-ink-900">
                      {member.display_name}
                    </td>
                    <td className="px-4 py-3 text-ink-700">
                      {member.first_name || <span className="text-ink-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-ink-700">
                      {member.last_name || <span className="text-ink-300">—</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                          member.role === "manager"
                            ? "bg-fairway-100 text-fairway-700"
                            : "bg-ink-100 text-ink-600"
                        }`}
                      >
                        {member.role === "manager" ? "Manager" : "Member"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-400 whitespace-nowrap">
                      {member.joined_at ? new Date(member.joined_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : <span className="text-ink-300">—</span>}
                    </td>
                    {showEmails && (
                      <td className="px-4 py-3 text-ink-500 whitespace-nowrap">
                        {member.email}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 px-4 py-3 border-t border-ink-100 bg-ink-50">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="text-sm font-medium text-ink-500 hover:text-ink-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-xs hover:bg-ink-100 transition-colors"
              >
                ← Prev
              </button>
              <span className="text-xs text-ink-400 tabular-nums">
                {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="text-sm font-medium text-ink-500 hover:text-ink-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-xs hover:bg-ink-100 transition-colors"
              >
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
