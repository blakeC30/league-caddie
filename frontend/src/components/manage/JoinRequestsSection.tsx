import { useState } from "react";
import type { League, LeagueMember } from "../../api/endpoints";
import {
  useApproveRequest,
  useDenyRequest,
  useUpdateLeague,
} from "../../hooks/useLeague";
import { SectionIcon, type ConfirmModalState } from "./shared";

export interface JoinRequestsSectionProps {
  league: League | undefined;
  leagueId: string;
  pendingRequests: LeagueMember[] | undefined;
  onConfirm: (modal: ConfirmModalState) => void;
}

export function JoinRequestsSection({
  league,
  leagueId,
  pendingRequests,
  onConfirm,
}: JoinRequestsSectionProps) {
  const approveRequest = useApproveRequest(leagueId);
  const denyRequest = useDenyRequest(leagueId);
  const updateLeague = useUpdateLeague(leagueId);
  const [approveError, setApproveError] = useState("");

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SectionIcon>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
            </svg>
          </SectionIcon>
          <h2 className="text-base font-bold text-gray-900">
            Join Requests
            {pendingRequests && pendingRequests.length > 0 && (
              <span className="ml-2 text-xs font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                {pendingRequests.length}
              </span>
            )}
          </h2>
        </div>
        {/* Pause / resume toggle */}
        {league && (
          <button
            onClick={() =>
              updateLeague.mutate({ accepting_requests: !league.accepting_requests })
            }
            disabled={updateLeague.isPending}
            className={`text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-40 whitespace-nowrap ${
              league.accepting_requests
                ? "text-gray-600 border-gray-200 hover:bg-gray-50"
                : "text-green-700 border-green-200 bg-green-50 hover:bg-green-100"
            }`}
          >
            {league.accepting_requests ? "Pause requests" : "Reopen requests"}
          </button>
        )}
      </div>
      {/* Auto-accept info banner */}
      {league?.auto_accept_requests && (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 flex-shrink-0 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
          <p className="text-xs text-green-700">
            Join requests are automatically accepted. New members are added as soon as they request to join.
          </p>
        </div>
      )}
      {/* Paused banner */}
      {league && !league.accepting_requests && (
        <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 flex-shrink-0 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
          </svg>
          <p className="text-xs text-gray-500">
            {league.auto_accept_requests
              ? "New join requests are paused. Anyone with the invite link will see a message that the league is not accepting requests."
              : "New join requests are paused. Anyone with the invite link will see a message that the league is not accepting requests. Existing pending requests can still be approved or denied."}
          </p>
        </div>
      )}
      {!pendingRequests || pendingRequests.length === 0 ? (
        !league?.auto_accept_requests && <p className="text-sm text-gray-400">No pending requests.</p>
      ) : (
        <div className="bg-gray-50 rounded-xl border border-gray-100 divide-y divide-gray-100">
          {pendingRequests.map((r) => (
            <div key={r.user_id} className="flex items-center gap-4 px-4 py-3">
              <div className="flex-1">
                <p className="text-sm font-semibold text-gray-900">{r.user.display_name}</p>
                <p className="text-xs text-gray-400">{r.user.email}</p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => {
                    onConfirm({
                      title: `Approve ${r.user.display_name}?`,
                      message: `${r.user.display_name} (${r.user.email}) will be added as a member of this league.`,
                      confirmLabel: "Approve",
                      onConfirm: () => {
                        setApproveError("");
                        approveRequest.mutate(r.user_id, {
                          onError: (err) => {
                            const msg = (err as { response?: { data?: { detail?: string } } })
                              ?.response?.data?.detail;
                            setApproveError(msg ?? "Failed to approve request.");
                          },
                        });
                      },
                    });
                  }}
                  disabled={approveRequest.isPending}
                  className="text-xs font-bold text-green-700 hover:text-green-900 bg-green-50 hover:bg-green-100 px-3 py-1.5 rounded-lg disabled:opacity-40 transition-colors"
                >
                  Approve
                </button>
                <button
                  onClick={() => {
                    onConfirm({
                      title: `Deny ${r.user.display_name}'s request?`,
                      message: `${r.user.display_name} will be notified that their request was denied. They can request to join again later.`,
                      confirmLabel: "Deny",
                      danger: true,
                      onConfirm: () => denyRequest.mutate(r.user_id),
                    });
                  }}
                  disabled={denyRequest.isPending}
                  className="text-xs font-medium text-red-500 hover:underline disabled:opacity-40 transition-colors"
                >
                  Deny
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {approveError && (
        <p className="text-xs text-red-600 mt-2">{approveError}</p>
      )}
      {denyRequest.isError && (
        <p className="text-sm text-red-600">Failed to deny request. Please try again.</p>
      )}
      {updateLeague.isError && (
        <p className="text-sm text-red-600">Failed to update request settings. Please try again.</p>
      )}
    </section>
  );
}
