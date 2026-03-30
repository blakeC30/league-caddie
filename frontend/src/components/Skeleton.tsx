/**
 * Skeleton primitives for loading states.
 *
 * Use these to build page-specific skeleton screens that mirror the actual
 * layout. The `animate-pulse` animation gives a subtle breathing effect.
 */

/** Generic pulsing block — pass width/height via className. */
export function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 rounded-lg ${className}`} />;
}

/** Skeleton for a single table row (pos + name + points). */
function SkeletonTableRow({ stripe }: { stripe: boolean }) {
  return (
    <tr className={stripe ? "bg-gray-50" : "bg-white"}>
      <td className="px-4 py-3"><SkeletonBlock className="h-4 w-6" /></td>
      <td className="px-4 py-3"><SkeletonBlock className="h-4 w-28" /></td>
      <td className="px-4 py-3 text-right"><SkeletonBlock className="h-4 w-16 ml-auto" /></td>
    </tr>
  );
}

/** Skeleton standings table — green header + N placeholder rows. */
export function SkeletonStandingsTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200">
      <table className="min-w-full text-sm">
        <thead className="bg-gradient-to-r from-green-900 to-green-700">
          <tr>
            <th className="px-4 py-2.5 text-left"><SkeletonBlock className="h-3 w-8 !bg-white/20" /></th>
            <th className="px-4 py-2.5 text-left"><SkeletonBlock className="h-3 w-16 !bg-white/20" /></th>
            <th className="px-4 py-2.5 text-right"><SkeletonBlock className="h-3 w-14 !bg-white/20 ml-auto" /></th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, i) => (
            <SkeletonTableRow key={i} stripe={i % 2 !== 0} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Skeleton for the Dashboard page: header + tournament card + standings. */
export function DashboardSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {/* Page header */}
      <div className="space-y-1">
        <SkeletonBlock className="h-3 w-32" />
        <SkeletonBlock className="h-8 w-48" />
      </div>

      {/* Tournament card */}
      <div className="rounded-2xl border border-gray-200 overflow-hidden">
        <div className="bg-gradient-to-r from-green-900 to-green-700 px-5 py-4 space-y-2">
          <SkeletonBlock className="h-3 w-24 !bg-white/20" />
          <SkeletonBlock className="h-6 w-56 !bg-white/20" />
          <SkeletonBlock className="h-3 w-40 !bg-white/20" />
        </div>
        <div className="px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gray-200" />
            <div className="space-y-1.5">
              <SkeletonBlock className="h-4 w-32" />
              <SkeletonBlock className="h-3 w-20" />
            </div>
          </div>
          <SkeletonBlock className="h-8 w-20 rounded-lg" />
        </div>
      </div>

      {/* Standings */}
      <div className="space-y-3">
        <SkeletonBlock className="h-6 w-24" />
        <SkeletonStandingsTable rows={5} />
      </div>

      {/* Quick links */}
      <div className="flex justify-center gap-2">
        <SkeletonBlock className="h-10 w-36 rounded-lg" />
        <SkeletonBlock className="h-10 w-32 rounded-lg" />
      </div>
    </div>
  );
}

/** Skeleton for the Leaderboard standings view: search + table + pagination. */
export function LeaderboardSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <SkeletonBlock className="h-9 w-full sm:w-72 rounded-lg" />
      <SkeletonStandingsTable rows={10} />
      <div className="flex justify-center">
        <SkeletonBlock className="h-4 w-40" />
      </div>
    </div>
  );
}

/** Generic page skeleton — used as lazy-load Suspense fallback. */
export function PageSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="space-y-1">
        <SkeletonBlock className="h-3 w-28" />
        <SkeletonBlock className="h-8 w-48" />
      </div>
      <SkeletonBlock className="h-48 w-full rounded-2xl" />
      <div className="space-y-3">
        {Array.from({ length: 4 }, (_, i) => (
          <SkeletonBlock key={i} className="h-5 w-full" />
        ))}
      </div>
    </div>
  );
}

/** Skeleton for Roster: header + search + table rows. */
export function RosterSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div>
        <SkeletonBlock className="h-3 w-20 mb-3" />
        <SkeletonBlock className="h-3 w-28 mb-1" />
        <SkeletonBlock className="h-8 w-24" />
      </div>
      <SkeletonBlock className="h-9 w-full sm:w-72 rounded-xl" />
      <div className="overflow-x-auto rounded-2xl border border-gray-200">
        <table className="min-w-full text-sm">
          <thead className="bg-gradient-to-r from-green-900 to-green-700">
            <tr>
              <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-24 !bg-white/20" /></th>
              <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-20 !bg-white/20" /></th>
              <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-20 !bg-white/20" /></th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 8 }, (_, i) => (
              <tr key={i} className={i % 2 !== 0 ? "bg-gray-50" : "bg-white"}>
                <td className="px-4 py-3"><SkeletonBlock className="h-4 w-28" /></td>
                <td className="px-4 py-3"><SkeletonBlock className="h-4 w-20" /></td>
                <td className="px-4 py-3"><SkeletonBlock className="h-4 w-20" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Skeleton for MakePick: header + golfer list. */
export function MakePickSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="space-y-1">
        <SkeletonBlock className="h-3 w-24" />
        <SkeletonBlock className="h-8 w-40" />
      </div>
      <div className="rounded-2xl border border-gray-200 overflow-hidden">
        <div className="bg-gradient-to-r from-green-900 to-green-700 px-5 py-4 space-y-2">
          <SkeletonBlock className="h-5 w-48 !bg-white/20" />
          <SkeletonBlock className="h-3 w-32 !bg-white/20" />
        </div>
        <div className="px-4 py-3">
          <SkeletonBlock className="h-9 w-full rounded-lg" />
        </div>
        <div className="divide-y divide-gray-100">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3">
              <div className="w-9 h-9 rounded-full bg-gray-200 flex-shrink-0" />
              <div className="space-y-1.5 flex-1">
                <SkeletonBlock className="h-4 w-32" />
                <SkeletonBlock className="h-3 w-20" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Skeleton for PlayoffBracket: bracket placeholder. */
export function PlayoffBracketSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="space-y-1">
        <SkeletonBlock className="h-3 w-28" />
        <SkeletonBlock className="h-8 w-40" />
      </div>
      <div className="flex gap-8 overflow-x-auto py-4">
        {Array.from({ length: 3 }, (_, round) => (
          <div key={round} className="flex flex-col gap-4 min-w-[200px]">
            <SkeletonBlock className="h-4 w-20 mx-auto" />
            {Array.from({ length: Math.max(1, 4 >> round) }, (_, pod) => (
              <div key={pod} className="rounded-xl border border-gray-200 p-3 space-y-2">
                <SkeletonBlock className="h-4 w-28" />
                <SkeletonBlock className="h-4 w-24" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Skeleton for TournamentDetail: header + leaderboard table. */
export function TournamentDetailSkeleton() {
  return (
    <div className="max-w-4xl mx-auto space-y-4 animate-pulse">
      <SkeletonBlock className="h-4 w-20" />
      <div className="rounded-2xl border border-gray-200 overflow-hidden">
        <div className="bg-gradient-to-r from-green-900 to-green-700 px-5 py-4 space-y-2">
          <SkeletonBlock className="h-6 w-56 !bg-white/20" />
          <SkeletonBlock className="h-3 w-40 !bg-white/20" />
        </div>
      </div>
      <SkeletonBlock className="h-9 w-full sm:w-64 rounded-lg" />
      <div className="overflow-x-auto rounded-xl border border-gray-200">
        <table className="min-w-full text-sm">
          <thead className="bg-gradient-to-r from-green-900 to-green-700">
            <tr>
              {["w-8", "w-28", "w-12", "w-10", "w-10", "w-10", "w-10", "w-16"].map((w, i) => (
                <th key={i} className="px-3 py-2.5"><SkeletonBlock className={`h-3 ${w} !bg-white/20`} /></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 12 }, (_, i) => (
              <tr key={i} className={i % 2 !== 0 ? "bg-gray-50" : "bg-white"}>
                {["w-6", "w-24", "w-10", "w-8", "w-8", "w-8", "w-8", "w-14"].map((w, j) => (
                  <td key={j} className="px-3 py-2.5"><SkeletonBlock className={`h-4 ${w}`} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Skeleton for a tournament checkbox list (CreateLeague / ManageLeague schedule). */
export function TournamentListSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <div className="w-4 h-4 rounded bg-gray-200 flex-shrink-0" />
          <SkeletonBlock className="h-4 w-40" />
          <SkeletonBlock className="h-3 w-24 ml-auto" />
        </div>
      ))}
    </div>
  );
}

/** Skeleton for a members table (ManageLeague members section). */
export function MembersTableSkeleton() {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-100 animate-pulse">
      <table className="min-w-full text-sm">
        <thead className="bg-gradient-to-r from-green-900 to-green-700">
          <tr>
            <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-20 !bg-white/20" /></th>
            <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-14 !bg-white/20" /></th>
            <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-16 !bg-white/20" /></th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 5 }, (_, i) => (
            <tr key={i} className={i % 2 !== 0 ? "bg-gray-50" : "bg-white"}>
              <td className="px-4 py-3"><SkeletonBlock className="h-4 w-28" /></td>
              <td className="px-4 py-3"><SkeletonBlock className="h-4 w-16" /></td>
              <td className="px-4 py-3"><SkeletonBlock className="h-4 w-20" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Skeleton for the MyPicks page: header + season total + stat cards + picks table. */
export function MyPicksSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <SkeletonBlock className="h-3 w-28" />
          <SkeletonBlock className="h-8 w-20" />
        </div>
        <SkeletonBlock className="h-10 w-28 rounded-xl" />
      </div>

      {/* Season total card */}
      <div className="bg-gradient-to-br from-green-900 via-green-800 to-green-700 rounded-2xl p-6 space-y-2">
        <SkeletonBlock className="h-3 w-24 !bg-white/20" />
        <SkeletonBlock className="h-10 w-40 !bg-white/20" />
      </div>

      {/* Stat cards grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
            <SkeletonBlock className="h-3 w-20" />
            <SkeletonBlock className="h-7 w-16" />
          </div>
        ))}
      </div>

      {/* Picks table */}
      <div className="space-y-2">
        <div className="flex gap-1">
          <SkeletonBlock className="h-7 w-16 rounded-lg" />
          <SkeletonBlock className="h-7 w-20 rounded-lg" />
          <SkeletonBlock className="h-7 w-10 rounded-lg" />
        </div>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="min-w-full text-sm">
            <thead className="bg-gradient-to-r from-green-900 to-green-700">
              <tr>
                <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-24 !bg-white/20" /></th>
                <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-16 !bg-white/20" /></th>
                <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-14 !bg-white/20" /></th>
                <th className="px-4 py-2.5"><SkeletonBlock className="h-3 w-16 !bg-white/20" /></th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 8 }, (_, i) => (
                <tr key={i} className={i % 2 !== 0 ? "bg-gray-50" : "bg-white"}>
                  <td className="px-4 py-3"><SkeletonBlock className="h-4 w-32" /></td>
                  <td className="px-4 py-3"><SkeletonBlock className="h-4 w-24" /></td>
                  <td className="px-4 py-3"><SkeletonBlock className="h-4 w-16" /></td>
                  <td className="px-4 py-3 text-right"><SkeletonBlock className="h-4 w-20 ml-auto" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
