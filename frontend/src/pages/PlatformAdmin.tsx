/**
 * PlatformAdmin — platform-level administration panel.
 *
 * Accessible only to users with is_platform_admin = true.
 * Non-platform-admins are redirected to the leagues list.
 *
 * Responsibilities:
 *   - Platform statistics dashboard (aggregated counts, no PII)
 *   - Manual data sync: trigger ESPN schedule + field + results scraping
 *   - Per-tournament sync: sync or force-sync individual tournaments
 */

import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { adminApi, leaguesApi, type AdminStats } from "../api/endpoints";
import { useAuthStore } from "../store/authStore";
import { useMyLeagues } from "../hooks/useLeague";
import { useTournaments } from "../hooks/usePick";
import { Spinner } from "../components/Spinner";

type ConfirmAction = { label: string; description: string; onConfirm: () => void };

export function PlatformAdmin() {
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    document.title = "Admin — League Caddie";
  }, []);

  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const timersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  useEffect(() => () => { timersRef.current.forEach(clearTimeout); }, []);

  const [syncStatus, setSyncStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [syncResult, setSyncResult] = useState<string>("");

  // Per-tournament sync state — maps pga_tour_id → current sync status
  const [syncState, setSyncState] = useState<Record<string, "idle" | "syncing" | "done" | "error">>({});

  // Bulk sync state
  const [bulkSyncStatus, setBulkSyncStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [bulkSyncProgress, setBulkSyncProgress] = useState<{ done: number; total: number }>({ done: 0, total: 0 });

  // Import members state
  const [importLeagueId, setImportLeagueId] = useState("");
  const [importMembersFile, setImportMembersFile] = useState<File | null>(null);
  const [importMembersStatus, setImportMembersStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [importMembersResult, setImportMembersResult] = useState<string>("");

  // Import picks state
  const [picksLeagueId, setPicksLeagueId] = useState("");
  const [picksTournamentId, setPicksTournamentId] = useState("");
  const [importPicksFile, setImportPicksFile] = useState<File | null>(null);
  const [importPicksStatus, setImportPicksStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [importPicksResult, setImportPicksResult] = useState<string>("");

  // Leagues for dropdowns
  const { data: myLeagues } = useMyLeagues();
  // League tournaments for picks dropdown
  const [leagueTournaments, setLeagueTournaments] = useState<{ id: string; name: string; status: string }[]>([]);
  useEffect(() => {
    if (!picksLeagueId) { setLeagueTournaments([]); return; }
    leaguesApi.getTournaments(picksLeagueId).then((ts) => {
      setLeagueTournaments(
        ts.map((t) => ({
          id: t.id,
          name: t.name,
          status: t.status,
        }))
      );
    }).catch(() => setLeagueTournaments([]));
  }, [picksLeagueId]);

  const { data: tournaments, isLoading: tournamentsLoading } = useTournaments();
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery<AdminStats>({
    queryKey: ["adminStats"],
    queryFn: adminApi.getStats,
    // Only fetch when we know the user is a platform admin — auth guard below
    // handles non-admins, but we skip the network call entirely if user hasn't loaded yet.
    enabled: !!user?.is_platform_admin,
    staleTime: 60_000, // 1 minute — stats don't need to be real-time
  });

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

  async function handleSync(pgaTourId: string) {
    setSyncState((s) => ({ ...s, [pgaTourId]: "syncing" }));
    try {
      await adminApi.syncTournamentForce(pgaTourId);
      setSyncState((s) => ({ ...s, [pgaTourId]: "done" }));
      const t1 = setTimeout(() => setSyncState((s) => ({ ...s, [pgaTourId]: "idle" })), 3000);
      timersRef.current.add(t1);
    } catch {
      setSyncState((s) => ({ ...s, [pgaTourId]: "error" }));
      const t2 = setTimeout(() => setSyncState((s) => ({ ...s, [pgaTourId]: "idle" })), 4000);
      timersRef.current.add(t2);
    }
  }

  async function handleBulkSync() {
    if (!sortedTournaments.length) return;
    setBulkSyncStatus("running");
    setBulkSyncProgress({ done: 0, total: sortedTournaments.length });
    let hadError = false;
    for (const t of sortedTournaments) {
      setSyncState((s) => ({ ...s, [t.pga_tour_id]: "syncing" }));
      try {
        await adminApi.syncTournamentForce(t.pga_tour_id);
        setSyncState((s) => ({ ...s, [t.pga_tour_id]: "done" }));
      } catch {
        setSyncState((s) => ({ ...s, [t.pga_tour_id]: "error" }));
        hadError = true;
      }
      setBulkSyncProgress((p) => ({ ...p, done: p.done + 1 }));
    }
    setBulkSyncStatus(hadError ? "error" : "done");
    const t3 = setTimeout(() => {
      setBulkSyncStatus("idle");
      setSyncState({});
    }, 4000);
    timersRef.current.add(t3);
  }

  // Sort tournaments most-recent-first by start_date
  const sortedTournaments = tournaments
    ? [...tournaments].sort((a, b) => b.start_date.localeCompare(a.start_date))
    : [];

  const TIER_LABELS: Record<string, string> = {
    starter: "Starter",
    standard: "Standard",
    pro: "Pro",
    elite: "Elite",
    unknown: "Unknown",
  };

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-bold text-gray-900">Platform Admin</h1>

      {/* ── Platform Stats ───────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Platform Stats</h2>
          <button
            onClick={() => refetchStats()}
            className="text-xs font-medium text-gray-400 hover:text-gray-700 transition-colors"
          >
            ↻ Refresh
          </button>
        </div>

        {statsLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 animate-pulse">
                <div className="h-3 bg-gray-100 rounded w-2/3 mb-3" />
                <div className="h-6 bg-gray-100 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : stats ? (
          <div className="space-y-4">
            {/* Stat cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Users */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Total Users</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.total_users.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">New (30d)</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.new_users_30d.toLocaleString()}</p>
              </div>
              {/* Leagues */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Total Leagues</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.total_leagues.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Paid This Season</p>
                <p className="text-2xl font-bold text-green-700 tabular-nums">{stats.paid_leagues_this_year.toLocaleString()}</p>
              </div>
              {/* Members */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Active Members</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.total_approved_memberships.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Avg Members / League</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.avg_members_per_league.toFixed(1)}</p>
              </div>
              {/* Leagues — breakdown */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">With Playoffs</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.leagues_with_playoffs.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Accepting Members</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.leagues_accepting_requests.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Deleted Leagues</p>
                <p className="text-2xl font-bold text-gray-500 tabular-nums">{stats.deleted_leagues_total.toLocaleString()}</p>
              </div>
              {/* Picks */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Total Picks</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.total_picks.toLocaleString()}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Picks (7d)</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">{stats.picks_last_7d.toLocaleString()}</p>
              </div>
              {/* Webhook failures — red if any open */}
              <div className={`border rounded-xl p-4 ${stats.open_webhook_failures > 0 ? "bg-red-50 border-red-200" : "bg-white border-gray-200"}`}>
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-1">Webhook Failures</p>
                <p className={`text-2xl font-bold tabular-nums ${stats.open_webhook_failures > 0 ? "text-red-600" : "text-gray-900"}`}>
                  {stats.open_webhook_failures.toLocaleString()}
                </p>
              </div>
            </div>

            {/* Second row: tournaments + tier breakdown side-by-side */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Tournament status breakdown */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-3">Tournaments</p>
                <div className="space-y-2">
                  {[
                    { label: "Completed", value: stats.tournaments_completed, color: "bg-green-500" },
                    { label: "In Progress", value: stats.tournaments_in_progress, color: "bg-yellow-400" },
                    { label: "Scheduled", value: stats.tournaments_scheduled, color: "bg-gray-300" },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${color} shrink-0`} />
                        <span className="text-sm text-gray-600">{label}</span>
                      </div>
                      <span className="text-sm font-semibold text-gray-900 tabular-nums">{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tier breakdown */}
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400 mb-3">
                  Leagues by Tier <span className="normal-case font-normal text-gray-400">(this season)</span>
                </p>
                {stats.leagues_by_tier.length === 0 ? (
                  <p className="text-sm text-gray-400">No paid leagues yet.</p>
                ) : (
                  <div className="space-y-2">
                    {stats.leagues_by_tier.map(({ tier, count }) => (
                      <div key={tier} className="flex items-center justify-between gap-3">
                        <span className="text-sm text-gray-600">{TIER_LABELS[tier] ?? tier}</span>
                        <span className="text-sm font-semibold text-gray-900 tabular-nums">{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-red-500">Failed to load stats.</p>
        )}
      </section>

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
          onClick={() =>
            setConfirmAction({
              label: "Sync Schedule + Force Overwrite All",
              description:
                "This will clear and re-fetch all round data for every in-progress and completed tournament. Continue?",
              onConfirm: handleFullSync,
            })
          }
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
              title="Force sync all tournaments (clear & re-fetch all data)"
              disabled={bulkSyncStatus === "running"}
              onClick={() =>
                setConfirmAction({
                  label: "Force Sync All Tournaments",
                  description:
                    "This will clear and re-fetch all round data for every tournament one by one. This may take a while. Continue?",
                  onConfirm: handleBulkSync,
                })
              }
              className="bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold px-4 py-1.5 rounded-lg text-xs transition-colors"
            >
              {bulkSyncStatus === "running" ? "Syncing…" : "⟳ Force Sync All"}
            </button>
          </div>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Force-sync individual tournaments — clears all cached round data and re-fetches everything from ESPN.
        </p>

        {tournamentsLoading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : sortedTournaments.length === 0 ? (
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

                          {/* Force sync button */}
                          <button
                            title="Force sync (clear & re-fetch all data)"
                            disabled={isSyncing}
                            onClick={() =>
                              setConfirmAction({
                                label: `Force Sync: ${t.name}`,
                                description:
                                  "This will clear all cached round data for this tournament and re-fetch everything from ESPN. Continue?",
                                onConfirm: () => handleSync(t.pga_tour_id),
                              })
                            }
                            className="bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold px-3 py-1.5 rounded-lg text-xs transition-colors"
                          >
                            ⟳ Sync
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

      {/* ── Import Members Section ───────────────────────────────── */}
      <section className="bg-white border border-gray-200 rounded-2xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-800">Import Members</h2>
        <p className="text-sm text-gray-500">
          Upload a CSV file with <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">name,email</code> columns to bulk-add members to a league.
          New accounts are created with password <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">password123</code>.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">League</label>
            <select
              value={importLeagueId}
              onChange={(e) => setImportLeagueId(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              <option value="">Select a league</option>
              {myLeagues?.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CSV File</label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setImportMembersFile(e.target.files?.[0] ?? null)}
              className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
            />
          </div>
        </div>

        <button
          disabled={!importLeagueId || !importMembersFile || importMembersStatus === "running"}
          onClick={async () => {
            if (!importMembersFile) return;
            setImportMembersStatus("running");
            setImportMembersResult("");
            try {
              const result = await adminApi.importMembers(importLeagueId, importMembersFile);
              setImportMembersStatus("done");
              setImportMembersResult(JSON.stringify(result, null, 2));
            } catch (err: unknown) {
              setImportMembersStatus("error");
              const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
              setImportMembersResult(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2));
            }
          }}
          className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors"
        >
          {importMembersStatus === "running" ? <Spinner /> : "Import Members"}
        </button>

        {importMembersResult && (
          <pre className={`text-xs p-4 rounded-xl overflow-x-auto ${importMembersStatus === "error" ? "bg-red-50 text-red-700" : "bg-gray-50 text-gray-700"}`}>
            {importMembersResult}
          </pre>
        )}
      </section>

      {/* ── Import Picks Section ──────────────────────────────────── */}
      <section className="bg-white border border-gray-200 rounded-2xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-800">Import Picks</h2>
        <p className="text-sm text-gray-500">
          Upload a CSV file with <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">email,golfer_name</code> columns.
          Use <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">No Pick</code> for members who didn&apos;t pick.
          Completed tournaments are auto-scored after import.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">League</label>
            <select
              value={picksLeagueId}
              onChange={(e) => { setPicksLeagueId(e.target.value); setPicksTournamentId(""); }}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              <option value="">Select a league</option>
              {myLeagues?.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tournament</label>
            <select
              value={picksTournamentId}
              onChange={(e) => setPicksTournamentId(e.target.value)}
              disabled={!picksLeagueId}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 disabled:opacity-50"
            >
              <option value="">Select a tournament</option>
              {leagueTournaments.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.status})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CSV File</label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setImportPicksFile(e.target.files?.[0] ?? null)}
              className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
            />
          </div>
        </div>

        <button
          disabled={!picksLeagueId || !picksTournamentId || !importPicksFile || importPicksStatus === "running"}
          onClick={async () => {
            if (!importPicksFile) return;
            setImportPicksStatus("running");
            setImportPicksResult("");
            try {
              const result = await adminApi.importPicks(picksLeagueId, picksTournamentId, importPicksFile);
              setImportPicksStatus("done");
              setImportPicksResult(JSON.stringify(result, null, 2));
            } catch (err: unknown) {
              setImportPicksStatus("error");
              const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
              setImportPicksResult(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2));
            }
          }}
          className="bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors"
        >
          {importPicksStatus === "running" ? <Spinner /> : "Import Picks"}
        </button>

        {importPicksResult && (
          <pre className={`text-xs p-4 rounded-xl overflow-x-auto ${importPicksStatus === "error" ? "bg-red-50 text-red-700" : "bg-gray-50 text-gray-700"}`}>
            {importPicksResult}
          </pre>
        )}
      </section>

      {/* Confirmation modal */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
            <h3 className="text-base font-semibold text-gray-900">{confirmAction.label}</h3>
            <p className="text-sm text-gray-600">{confirmAction.description}</p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  confirmAction.onConfirm();
                  setConfirmAction(null);
                }}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-red-600 hover:bg-red-500 transition-colors"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
