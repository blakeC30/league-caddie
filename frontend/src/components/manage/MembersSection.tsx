import { useMemo, useState } from "react";
import type { LeagueMember, LeaguePurchaseStatus, User } from "../../api/endpoints";
import { useRemoveMember, useUpdateMemberRole } from "../../hooks/useLeague";
import { Spinner } from "../Spinner";
import { SectionIcon, type ConfirmModalState } from "./shared";

export interface MembersSectionProps {
  leagueId: string;
  members: LeagueMember[] | undefined;
  isLoading: boolean;
  isManager: boolean;
  currentUser: User | null;
  purchase: LeaguePurchaseStatus | null | undefined;
  onConfirm: (modal: ConfirmModalState) => void;
}

const PAGE_SIZE = 50;

export function MembersSection({
  leagueId,
  members,
  isLoading,
  isManager,
  currentUser,
  purchase,
  onConfirm,
}: MembersSectionProps) {
  const updateRole = useUpdateMemberRole(leagueId);
  const removeMember = useRemoveMember(leagueId);
  const [membersEditing, setMembersEditing] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  // Sort: managers first, then alphabetical. Filter by search.
  const filteredMembers = useMemo(() => {
    const sorted = [...(members ?? [])].sort((a, b) => {
      if (a.role === "manager" && b.role !== "manager") return -1;
      if (b.role === "manager" && a.role !== "manager") return 1;
      return a.user.display_name.localeCompare(b.user.display_name);
    });
    if (!search.trim()) return sorted;
    const q = search.trim().toLowerCase();
    return sorted.filter(
      (m) =>
        m.user.display_name.toLowerCase().includes(q) ||
        m.user.email.toLowerCase().includes(q),
    );
  }, [members, search]);

  const totalFiltered = filteredMembers.length;
  const totalPages = Math.ceil(totalFiltered / PAGE_SIZE);
  const pagedMembers = filteredMembers.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Reset page when search changes
  const handleSearchChange = (val: string) => {
    setSearch(val);
    setPage(0);
  };

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-gray-900">League Members</h2>
          {members && purchase && (() => {
            const pct = members.length / (purchase.member_limit ?? 500);
            const colors =
              pct >= 1
                ? "bg-red-100 text-red-700"
                : pct >= 0.8
                ? "bg-amber-100 text-amber-700"
                : "bg-green-100 text-green-700";
            return (
              <span className="relative group">
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${colors}`}>
                  <span className="sm:hidden">{members.length}/{purchase.member_limit}</span>
                  <span className="hidden sm:inline">{members.length} / {purchase.member_limit} members</span>
                </span>
                <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block whitespace-nowrap rounded-lg bg-gray-800 px-2.5 py-1.5 text-xs text-white z-20 shadow-lg">
                  {members.length} of {purchase.member_limit} member slots used
                </span>
              </span>
            );
          })()}
        </div>
        {isManager && (
          membersEditing ? (
            <button
              onClick={() => setMembersEditing(false)}
              className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
            >
              Done
            </button>
          ) : (
            <button
              onClick={() => setMembersEditing(true)}
              className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
            >
              Edit
            </button>
          )
        )}
      </div>

      {/* Search — only shown when there are enough members to warrant it */}
      {(members?.length ?? 0) > 10 && (
        <input
          type="text"
          placeholder="Search members…"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        />
      )}

      {isLoading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-100">
          <table className="min-w-full text-sm">
            <thead className="bg-gradient-to-r from-green-900 to-green-700 text-white">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Name</th>
                <th className="hidden sm:table-cell px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Email</th>
                <th className="px-4 py-2.5 text-left text-xs uppercase tracking-wider font-semibold">Role</th>
                {membersEditing && (
                  <th className="px-4 py-2.5 text-right text-xs uppercase tracking-wider font-semibold">Actions</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {pagedMembers.length === 0 ? (
                <tr>
                  <td colSpan={membersEditing ? 4 : 3} className="px-4 py-8 text-center text-gray-400 text-sm">
                    {search ? "No members match your search." : "No members yet."}
                  </td>
                </tr>
              ) : (
                pagedMembers.map((m) => {
                  const isMe = m.user_id === currentUser?.id;
                  return (
                    <tr key={m.user_id} className={isMe ? "bg-green-50" : "hover:bg-gray-50"}>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {m.user.display_name}
                      </td>
                      <td className="hidden sm:table-cell px-4 py-3 text-gray-500">{m.user.email}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                            m.role === "manager"
                              ? "bg-green-100 text-green-800"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {m.role === "manager" ? "League Manager" : "Member"}
                        </span>
                      </td>
                      {membersEditing && (
                        <td className="px-4 py-3 text-right">
                          {!isMe && (
                            <div className="flex items-center justify-end gap-3">
                              <button
                                onClick={() =>
                                  onConfirm({
                                    title: m.role === "manager" ? "Revoke manager role" : "Make manager",
                                    message: m.role === "manager"
                                      ? `Revoke manager role from ${m.user.display_name}? They will become a regular member.`
                                      : `Make ${m.user.display_name} a league manager? They will be able to manage members, settings, and the schedule.`,
                                    confirmLabel: m.role === "manager" ? "Revoke role" : "Make manager",
                                    onConfirm: () => updateRole.mutate({ userId: m.user_id, role: m.role === "manager" ? "member" : "manager" }),
                                  })
                                }
                                className="text-xs font-medium text-blue-600 hover:underline transition-colors"
                              >
                                {m.role === "manager" ? "Revoke manager role" : "Make manager"}
                              </button>
                              <button
                                onClick={() =>
                                  onConfirm({
                                    title: "Remove member",
                                    message: `Remove ${m.user.display_name} from the league? This cannot be undone.`,
                                    confirmLabel: "Remove",
                                    danger: true,
                                    onConfirm: () => removeMember.mutate(m.user_id),
                                  })
                                }
                                className="text-xs font-medium text-red-500 hover:underline transition-colors"
                              >
                                Remove
                              </button>
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-4">
          <span className="text-xs text-gray-400 tabular-nums">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalFiltered)} of {totalFiltered}{search ? " results" : " members"}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="text-sm font-medium text-gray-500 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
            >
              ← Prev
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="text-sm font-medium text-gray-500 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {updateRole.isError && (
        <p className="text-sm text-red-600">Failed to update member role. Please try again.</p>
      )}
      {removeMember.isError && (
        <p className="text-sm text-red-600">Failed to remove member. Please try again.</p>
      )}
    </section>
  );
}
