import { useMemo, useState } from "react";
import type { LeagueMember, LeaguePurchaseStatus, User } from "../../api/endpoints";
import { ClearableInput } from "../ClearableInput";
import { useRemoveMember, useUpdateMemberRole } from "../../hooks/useLeague";
import { MembersTableSkeleton } from "../Skeleton";
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

const PAGE_SIZE = 25;

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
      return a.user.display_name
        .trim()
        .localeCompare(b.user.display_name.trim(), undefined, { sensitivity: "base" });
    });
    if (!search.trim()) return sorted;
    const q = search.trim().toLowerCase();
    return sorted.filter(
      (m) =>
        m.user.display_name.toLowerCase().includes(q) ||
        m.user.first_name.toLowerCase().includes(q) ||
        m.user.last_name.toLowerCase().includes(q) ||
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
    <section className="bg-white rounded-sm border border-ink-200 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-ink-900">League Members</h2>
          {members && purchase && (() => {
            const pct = members.length / (purchase.member_limit ?? 500);
            const colors =
              pct >= 1
                ? "bg-flag-100 text-flag-700"
                : pct >= 0.8
                ? "bg-brass-100 text-brass-700"
                : "bg-fairway-100 text-fairway-700";
            return (
              <span className="relative group">
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${colors}`}>
                  <span className="sm:hidden">{members.length}/{purchase.member_limit}</span>
                  <span className="hidden sm:inline">{members.length} / {purchase.member_limit} members</span>
                </span>
                <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block whitespace-nowrap rounded-xs bg-ink-800 px-2.5 py-1.5 text-xs text-white z-20 shadow-raised">
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
              className="text-sm font-semibold text-fairway-700 hover:text-fairway-900 transition-colors"
            >
              Done
            </button>
          ) : (
            <button
              onClick={() => setMembersEditing(true)}
              className="text-sm font-semibold text-fairway-700 hover:text-fairway-900 transition-colors"
            >
              Edit
            </button>
          )
        )}
      </div>

      {/* Search — only shown when there are enough members to warrant it */}
      {(members?.length ?? 0) > 10 && (
        <ClearableInput
          placeholder="Search members…"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          onClear={() => handleSearchChange("")}
          className="w-full border border-ink-300 rounded-xs px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fairway-500"
        />
      )}

      {isLoading ? (
        <MembersTableSkeleton />
      ) : (
        <div className="overflow-x-auto rounded-xs border border-ink-100">
          <table className="min-w-[640px] w-full text-sm">
            <thead className="bg-fairway-900 text-white">
              <tr>
                <th className="px-4 py-2.5 text-left text-micro uppercase">Display Name</th>
                <th className="px-4 py-2.5 text-left text-micro uppercase whitespace-nowrap">First</th>
                <th className="px-4 py-2.5 text-left text-micro uppercase whitespace-nowrap">Last</th>
                <th className="px-4 py-2.5 text-left text-micro uppercase whitespace-nowrap">Email</th>
                <th className="px-4 py-2.5 text-left text-micro uppercase">Role</th>
                {membersEditing && (
                  <th className="px-4 py-2.5 text-right text-micro uppercase">Actions</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {pagedMembers.length === 0 ? (
                <tr>
                  <td colSpan={membersEditing ? 6 : 5} className="px-4 py-8 text-center text-ink-400 text-sm">
                    {search ? "No members match your search." : "No members yet."}
                  </td>
                </tr>
              ) : (
                pagedMembers.map((m) => {
                  const isMe = m.user_id === currentUser?.id;
                  return (
                    <tr key={m.user_id} className={isMe ? "bg-fairway-50" : "hover:bg-ink-50"}>
                      <td className="px-4 py-3 font-medium text-ink-900">
                        {m.user.display_name}
                      </td>
                      <td className="px-4 py-3 text-ink-700 whitespace-nowrap">
                        {m.user.first_name || <span className="text-ink-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-ink-700 whitespace-nowrap">
                        {m.user.last_name || <span className="text-ink-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-ink-500 whitespace-nowrap">{m.user.email}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                            m.role === "manager"
                              ? "bg-fairway-100 text-fairway-700"
                              : "bg-ink-100 text-ink-600"
                          }`}
                        >
                          {m.role === "manager" ? "Manager" : "Member"}
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
                                disabled={updateRole.isPending}
                                className="text-xs font-medium text-ink-700 hover:underline transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {updateRole.isPending ? "Updating…" : m.role === "manager" ? "Revoke manager role" : "Make manager"}
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
                                disabled={removeMember.isPending}
                                className="text-xs font-medium text-flag-600 hover:underline transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {removeMember.isPending ? "Removing…" : "Remove"}
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
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="text-sm font-medium text-ink-500 hover:text-ink-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-xs hover:bg-ink-100 transition-colors"
          >
            ← Prev
          </button>
          <span className="text-xs text-ink-400 tabular-nums">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalFiltered)} of {totalFiltered}{search ? " results" : " members"}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="text-sm font-medium text-ink-500 hover:text-ink-900 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded-xs hover:bg-ink-100 transition-colors"
          >
            Next →
          </button>
        </div>
      )}

      {updateRole.isError && (
        <p className="text-sm text-flag-600">Failed to update member role. Please try again.</p>
      )}
      {removeMember.isError && (
        <p className="text-sm text-flag-600">Failed to remove member. Please try again.</p>
      )}
    </section>
  );
}
