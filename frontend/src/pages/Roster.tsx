/**
 * Roster — displays all league members with name and contact details.
 * Searchable and paginated (50 per page).
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useRoster, useLeagueMembers } from "../hooks/useLeague";
import { useAuthStore } from "../store/authStore";
import { Spinner } from "../components/Spinner";

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
            a.display_name.localeCompare(b.display_name, undefined, { sensitivity: "base" }),
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
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner className="w-8 h-8 text-green-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to={`/leagues/${leagueId}`}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-green-700 mb-3 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          Dashboard
        </Link>
        <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700 mb-1">
          League Members
        </p>
        <h1 className="text-3xl font-bold text-gray-900">Roster</h1>
      </div>

      {/* Search + count */}
      {sorted.length > 0 && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
          <div className="relative w-full sm:w-72">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
            <input
              type="text"
              placeholder="Search members..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-transparent transition-shadow"
            />
          </div>
          <p className="text-sm text-gray-500">
            {filtered.length === sorted.length
              ? `${sorted.length} members`
              : `${filtered.length} of ${sorted.length} members`}
          </p>
        </div>
      )}

      {/* Table */}
      {sorted.length === 0 ? (
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-16 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-gray-200 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128H9m6 0a5.972 5.972 0 0 0-.786-3.07M9 19.128v-.003c0-1.113.285-2.16.786-3.07M9 19.128H3.375a4.125 4.125 0 0 1 7.533-2.493M9 19.128a5.972 5.972 0 0 1 .786-3.07m5.428 0a6.002 6.002 0 0 0-6.428 0M12 12.75a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
            </svg>
          </div>
          <p className="font-semibold text-gray-700">No members yet</p>
          <p className="text-sm text-gray-400">Invite people to join this league to see them here.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-10 text-center">
          <p className="text-sm text-gray-500">No members match "{search}"</p>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">
                    Display Name
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">
                    First Name
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">
                    Last Name
                  </th>
                  {showEmails && (
                    <th className="hidden sm:table-cell px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">
                      Email
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {paginated.map((member, i) => (
                  <tr
                    key={member.user_id}
                    className={`border-t border-gray-100 ${i % 2 !== 0 ? "bg-gray-50" : "bg-white"}`}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {member.display_name}
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {member.first_name || <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {member.last_name || <span className="text-gray-300">—</span>}
                    </td>
                    {showEmails && (
                      <td className="hidden sm:table-cell px-4 py-3 text-gray-500">
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
            <div className="flex items-center justify-center gap-3 px-4 py-3 border-t border-gray-100 bg-gray-50 text-sm">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>
              <span className="text-gray-500">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
