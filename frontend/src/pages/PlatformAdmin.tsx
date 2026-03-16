/**
 * PlatformAdmin — platform-level administration panel.
 *
 * Accessible only to users with is_platform_admin = true.
 * Non-platform-admins are redirected to the leagues list.
 *
 * Responsibilities:
 *   - Manual data sync: trigger ESPN schedule + field + results scraping
 *   - Per-tournament sync: sync or force-sync individual tournaments
 */

import { useState } from "react";
import { Navigate } from "react-router-dom";
import { adminApi } from "../api/endpoints";
import { useAuthStore } from "../store/authStore";
import { useTournaments } from "../hooks/usePick";

export function PlatformAdmin() {
  const user = useAuthStore((s) => s.user);

  const [syncStatus, setSyncStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [syncResult, setSyncResult] = useState<string>("");

  // Per-tournament sync state — maps pga_tour_id → current sync status
  const [syncState, setSyncState] = useState<Record<string, "idle" | "syncing" | "done" | "error">>({});

  // Bulk sync state
  const [bulkSyncStatus, setBulkSyncStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [bulkSyncProgress, setBulkSyncProgress] = useState<{ done: number; total: number }>({ done: 0, total: 0 });

  const { data: tournaments } = useTournaments();

  // Redirect anyone who isn't a platform admin.
  if (user && !user.is_platform_admin) {
    return <Navigate to="/leagues" replace />;
  }

  async function handleFullSync() {
    setSyncStatus("running");
    setSyncResult("");
    try {
      const result = await adminApi.fullSync(undefined, true);
      setSyncResult(JSON.stringify(result, null, 2));
      setSyncStatus("done");
    } catch {
      setSyncStatus("error");
      setSyncResult("Sync failed — check backend logs.");
    }
  }

  async function handleSync(pgaTourId: string, force: boolean) {
    setSyncState((s) => ({ ...s, [pgaTourId]: "syncing" }));
    try {
      if (force) {
        await adminApi.syncTournamentForce(pgaTourId);
      } else {
        await adminApi.syncTournament(pgaTourId);
      }
      setSyncState((s) => ({ ...s, [pgaTourId]: "done" }));
      setTimeout(() => setSyncState((s) => ({ ...s, [pgaTourId]: "idle" })), 3000);
    } catch {
      setSyncState((s) => ({ ...s, [pgaTourId]: "error" }));
      setTimeout(() => setSyncState((s) => ({ ...s, [pgaTourId]: "idle" })), 4000);
    }
  }

  async function handleBulkSync(force: boolean) {
    if (!sortedTournaments.length) return;
    setBulkSyncStatus("running");
    setBulkSyncProgress({ done: 0, total: sortedTournaments.length });
    let hadError = false;
    for (const t of sortedTournaments) {
      setSyncState((s) => ({ ...s, [t.pga_tour_id]: "syncing" }));
      try {
        if (force) {
          await adminApi.syncTournamentForce(t.pga_tour_id);
        } else {
          await adminApi.syncTournament(t.pga_tour_id);
        }
        setSyncState((s) => ({ ...s, [t.pga_tour_id]: "done" }));
      } catch {
        setSyncState((s) => ({ ...s, [t.pga_tour_id]: "error" }));
        hadError = true;
      }
      setBulkSyncProgress((p) => ({ ...p, done: p.done + 1 }));
    }
    setBulkSyncStatus(hadError ? "error" : "done");
    setTimeout(() => {
      setBulkSyncStatus("idle");
      setSyncState({});
    }, 4000);
  }

  // Sort tournaments most-recent-first by start_date
  const sortedTournaments = tournaments
    ? [...tournaments].sort((a, b) => b.start_date.localeCompare(a.start_date))
    : [];

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-bold text-gray-900">Platform Admin</h1>

      {/* Full data sync */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-2">Schedule Sync</h2>
        <p className="text-sm text-gray-500 mb-4">
          Fetches the current year's PGA Tour schedule from ESPN and upserts any new or updated
          tournaments into the database, then clears and re-fetches all round data for every
          in-progress and completed event. Use this to pick up newly announced tournaments,
          date changes, or to force a clean overwrite of all cached results.
          The daily scheduler runs a non-overwrite version of this automatically at 6 AM UTC.
        </p>
        <button
          onClick={handleFullSync}
          disabled={syncStatus === "running"}
          className="bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-lg text-sm transition-colors"
        >
          {syncStatus === "running" ? "Syncing…" : "⟳ Sync Schedule + Force Overwrite All"}
        </button>

        {syncResult && (
          <pre
            className={`mt-4 text-xs rounded-lg p-4 overflow-auto max-h-64 ${
              syncStatus === "error"
                ? "bg-red-50 text-red-700 border border-red-200"
                : "bg-gray-50 text-gray-700 border border-gray-200"
            }`}
          >
            {syncResult}
          </pre>
        )}
      </section>

      {/* Per-tournament sync */}
      <section>
        <div className="flex flex-wrap items-start justify-between gap-4 mb-1">
          <h2 className="text-lg font-semibold text-gray-800">Tournament Sync</h2>
          <div className="flex items-center gap-2">
            {bulkSyncStatus === "running" && (
              <span className="text-xs text-gray-500">
                {bulkSyncProgress.done}/{bulkSyncProgress.total}
              </span>
            )}
            {bulkSyncStatus === "done" && (
              <span className="text-xs text-green-600 font-medium">All done ✓</span>
            )}
            {bulkSyncStatus === "error" && (
              <span className="text-xs text-red-500 font-medium">Some failed ✗</span>
            )}
            <button
              title="Sync all tournaments (update only)"
              disabled={bulkSyncStatus === "running"}
              onClick={() => handleBulkSync(false)}
              className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-4 py-1.5 rounded-lg text-xs transition-colors"
            >
              {bulkSyncStatus === "running" ? "Syncing…" : "↻ Sync All"}
            </button>
            <button
              title="Force sync all tournaments (clear & re-fetch all data)"
              disabled={bulkSyncStatus === "running"}
              onClick={() => handleBulkSync(true)}
              className="bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold px-4 py-1.5 rounded-lg text-xs transition-colors"
            >
              {bulkSyncStatus === "running" ? "Syncing…" : "⟳ Force Sync All"}
            </button>
          </div>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Sync or force-sync individual tournaments. ↻ updates without clearing existing data.
          ⟳ clears and re-fetches everything from scratch.
        </p>

        {sortedTournaments.length === 0 ? (
          <div className="bg-gray-50 rounded-2xl p-10 text-center text-sm text-gray-400">
            No tournaments found. Run a full sync first.
          </div>
        ) : (
          <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th className="text-left px-5 py-3">Tournament</th>
                  <th className="text-left px-5 py-3 hidden sm:table-cell">Dates</th>
                  <th className="text-left px-5 py-3">Status</th>
                  <th className="text-right px-5 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sortedTournaments.map((t) => {
                  const state = syncState[t.pga_tour_id] ?? "idle";
                  const isSyncing = state === "syncing";

                  return (
                    <tr key={t.id} className="hover:bg-gray-50 transition-colors">
                      {/* Name */}
                      <td className="px-5 py-3 font-medium text-gray-900 max-w-[200px] truncate">
                        {t.name}
                      </td>

                      {/* Dates — hidden on mobile */}
                      <td className="px-5 py-3 text-gray-500 text-xs hidden sm:table-cell whitespace-nowrap">
                        {t.start_date} – {t.end_date}
                      </td>

                      {/* Status badge */}
                      <td className="px-5 py-3">
                        {t.status === "completed" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            Completed
                          </span>
                        )}
                        {t.status === "in_progress" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                            In Progress
                          </span>
                        )}
                        {t.status === "scheduled" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                            Scheduled
                          </span>
                        )}
                      </td>

                      {/* Sync action buttons */}
                      <td className="px-5 py-3 text-right">
                        <div className="inline-flex items-center gap-2">
                          {/* Result indicator */}
                          {state === "done" && (
                            <span className="text-xs text-green-600 font-medium">&#10003;</span>
                          )}
                          {state === "error" && (
                            <span className="text-xs text-red-500 font-medium">&#10007;</span>
                          )}
                          {state === "syncing" && (
                            <span className="text-xs text-gray-400">Syncing…</span>
                          )}

                          {/* Sync button */}
                          <button
                            title="Sync (update only)"
                            disabled={isSyncing}
                            onClick={() => handleSync(t.pga_tour_id, false)}
                            className="text-gray-400 hover:text-green-700 disabled:opacity-40 transition-colors px-2 py-1 rounded-lg hover:bg-green-50 text-base leading-none"
                          >
                            ↻
                          </button>

                          {/* Force sync button — destructive style */}
                          <button
                            title="Force sync (clear & re-fetch all data)"
                            disabled={isSyncing}
                            onClick={() => handleSync(t.pga_tour_id, true)}
                            className="text-gray-400 hover:text-red-600 disabled:opacity-40 transition-colors px-2 py-1 rounded-lg hover:bg-red-50 text-base leading-none"
                          >
                            ⟳
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
