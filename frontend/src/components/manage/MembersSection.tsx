import { useState } from "react";
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
              {[...(members ?? [])].sort((a, b) => {
                if (a.role === "manager" && b.role !== "manager") return -1;
                if (b.role === "manager" && a.role !== "manager") return 1;
                return a.user.display_name.localeCompare(b.user.display_name);
              }).map((m) => {
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
              })}
            </tbody>
          </table>
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
