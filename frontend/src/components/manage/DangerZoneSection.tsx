import { useState } from "react";
import type { League } from "../../api/endpoints";
import { useDeleteLeague } from "../../hooks/useLeague";
import { useNavigate } from "react-router-dom";

export interface DangerZoneSectionProps {
  league: League | undefined;
  leagueId: string;
}

export function DangerZoneSection({ league, leagueId }: DangerZoneSectionProps) {
  const deleteLeague = useDeleteLeague();
  const navigate = useNavigate();
  const [dangerStep, setDangerStep] = useState<"idle" | "editing" | "confirming">("idle");
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  return (
    <section className="bg-white rounded-2xl border border-red-200 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-red-50 text-red-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <h2 className="text-base font-bold text-gray-900">Danger Zone</h2>
        </div>
        {dangerStep === "idle" && (
          <button
            onClick={() => setDangerStep("editing")}
            className="text-sm font-semibold text-gray-500 hover:text-gray-700 transition-colors"
          >
            Edit
          </button>
        )}
        {dangerStep === "editing" && (
          <button
            onClick={() => setDangerStep("idle")}
            className="text-sm font-semibold text-green-700 hover:text-green-900 transition-colors"
          >
            Done
          </button>
        )}
      </div>

      <p className="text-sm text-gray-500">
        Permanently delete this league and all of its data — members, picks, and standings.
        This action cannot be undone.
      </p>

      {dangerStep === "editing" && (
        <button
          onClick={() => setDangerStep("confirming")}
          className="text-sm font-semibold text-white bg-red-600 hover:bg-red-700 px-4 py-2 rounded-xl transition-colors"
        >
          Delete League
        </button>
      )}

      {dangerStep === "confirming" && (
        <div className="space-y-3 bg-red-50 border border-red-200 rounded-xl p-4">
          {deleteLeague.error && (
            <p className="text-sm text-red-700">Failed to delete league. Please try again.</p>
          )}
          <p className="text-sm text-gray-700">
            Type <span className="font-semibold">{league?.name}</span> to confirm deletion.
          </p>
          <input
            type="text"
            value={deleteConfirmText}
            onChange={(e) => setDeleteConfirmText(e.target.value)}
            placeholder={league?.name}
            className="w-full border border-red-300 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-shadow"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                deleteLeague.mutate(leagueId, {
                  onSuccess: () => navigate("/leagues"),
                });
              }}
              disabled={deleteConfirmText !== league?.name || deleteLeague.isPending}
              className="text-sm font-semibold bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white px-4 py-2 rounded-xl transition-colors"
            >
              {deleteLeague.isPending ? "Deleting…" : "Confirm Delete"}
            </button>
            <button
              onClick={() => { setDangerStep("editing"); setDeleteConfirmText(""); deleteLeague.reset(); }}
              disabled={deleteLeague.isPending}
              className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
