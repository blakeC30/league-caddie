/**
 * Layout — shared navigation shell + auth guard.
 *
 * Wraps every authenticated page. Redirects to /login if there is no token
 * and bootstrapping is complete (i.e. the silent refresh already failed).
 * Shows a loading screen while the refresh attempt is still in flight.
 *
 * Chrome is the painted board (DESIGN.md §6): one flat fairway-900 fill, square
 * corners, no gradient. Active nav is marked by a rule under the label rather
 * than by a pill, which keeps the bar reading as a single strip of colour.
 */

import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useLeagueMembers } from "../hooks/useLeague";
import { FlagIcon } from "./FlagIcon";

const TRANSITION = "transition-colors duration-[120ms] ease-board";

export function Layout() {
  const { token, user, bootstrapping, logout } = useAuth();
  const { leagueId } = useParams<{ leagueId?: string }>();
  const location = useLocation();

  const { data: leagueMembers, isError: leagueMembersError } = useLeagueMembers(leagueId ?? "");
  const isManager = leagueMembers?.some(
    (m) => m.user_id === user?.id && m.role === "manager"
  ) ?? false;

  function isActive(path: string): boolean {
    return location.pathname === path || location.pathname.startsWith(path + "/");
  }

  function navLink(to: string, label: string, exact = false) {
    const active = exact ? location.pathname === to : isActive(to);
    return (
      <Link
        to={to}
        aria-current={active ? "page" : undefined}
        className={`text-ui pb-1 border-b-2 ${TRANSITION} ${
          active
            ? "text-white border-fairway-400"
            : "text-white/65 border-transparent hover:text-white"
        }`}
      >
        {label}
      </Link>
    );
  }

  function mobileNavTab(to: string, label: string, icon: ReactNode, exact = false) {
    const active = exact ? location.pathname === to : isActive(to);
    return (
      <Link
        key={to}
        to={to}
        aria-current={active ? "page" : undefined}
        className={`flex-1 flex flex-col items-center justify-center gap-1 border-t-2 ${TRANSITION} ${
          active ? "text-white border-fairway-400" : "text-white/55 border-transparent"
        }`}
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
          {icon}
        </svg>
        <span className="text-micro uppercase">{label}</span>
      </Link>
    );
  }

  if (bootstrapping) {
    return <div className="min-h-screen bg-page" />;
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (leagueId && leagueMembersError) {
    return <Navigate to="/leagues" replace />;
  }

  return (
    <div className="min-h-screen bg-page flex flex-col">
      {/* Top nav — the board */}
      <header className="bg-fairway-900 text-white">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <Link
            to="/leagues"
            className={`flex items-center gap-2 font-display font-bold tracking-tight text-white hover:text-fairway-300 ${TRANSITION}`}
          >
            <FlagIcon className="w-4 h-4 shrink-0" />
            League Caddie
          </Link>

          {/* Desktop nav — hidden on mobile */}
          <nav className="hidden sm:flex items-center gap-6">
            {leagueId && (
              <>
                {navLink(`/leagues/${leagueId}`, "Dashboard", true)}
                {navLink(`/leagues/${leagueId}/picks`, "Picks")}
                {navLink(`/leagues/${leagueId}/standings`, "Standings")}
                {isManager && navLink(`/leagues/${leagueId}/manage`, "Manage")}
              </>
            )}

            {user?.is_platform_admin && navLink("/admin", "Admin")}

            <span className="w-px h-5 bg-white/15" aria-hidden="true" />

            <Link
              to="/settings"
              className={`text-ui text-white/65 hover:text-white ${TRANSITION}`}
            >
              {user?.display_name}
            </Link>
            <button
              onClick={logout}
              className={`text-ui text-white/65 hover:text-white ${TRANSITION}`}
            >
              Sign out
            </button>
          </nav>

          {/* Mobile: account + sign out (nav links live in the bottom tab bar) */}
          <div className="sm:hidden flex items-center gap-4">
            <Link
              to="/settings"
              className={`text-white/65 hover:text-white ${TRANSITION}`}
              aria-label="Account settings"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
              </svg>
            </Link>
            <button onClick={logout} className={`text-ui text-white/65 hover:text-white ${TRANSITION}`}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Page content — extra bottom padding on mobile to clear the tab bar */}
      <main className={`flex-1 max-w-5xl mx-auto w-full px-4 py-8 ${leagueId ? "pb-24 sm:pb-8" : ""}`}>
        <Outlet />
      </main>

      {/* Footer — hidden on mobile inside a league (bottom tab bar takes that space) */}
      <footer className={`bg-fairway-950 py-6 ${leagueId ? "hidden sm:block" : ""}`}>
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-small text-fairway-400">
            <span className="inline-flex items-center gap-2 font-semibold">
              <FlagIcon className="w-3.5 h-3.5 shrink-0" />
              League Caddie
            </span>
            <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1">
              <Link to="/leagues" className={`hover:text-white ${TRANSITION}`}>
                My Leagues
              </Link>
              <Link to="/terms" className={`hover:text-white ${TRANSITION}`}>
                Terms
              </Link>
              <Link to="/privacy" className={`hover:text-white ${TRANSITION}`}>
                Privacy
              </Link>
              <a href="mailto:support@league-caddie.com" className={`hover:text-white ${TRANSITION}`}>
                Contact
              </a>
            </div>
          </div>
          <p className="text-small text-fairway-500/70 text-center sm:text-left mt-4">
            © {new Date().getFullYear()} League Caddie LLC
          </p>
        </div>
      </footer>

      {/* Mobile bottom tab bar — only rendered inside a league */}
      {leagueId && (
        <nav className="sm:hidden fixed bottom-0 inset-x-0 bg-fairway-900 z-50">
          <div className="flex h-16">
            {mobileNavTab(
              `/leagues/${leagueId}`,
              "Home",
              <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />,
              true
            )}
            {mobileNavTab(
              `/leagues/${leagueId}/picks`,
              "Picks",
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            )}
            {mobileNavTab(
              `/leagues/${leagueId}/standings`,
              "Standings",
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
            )}
            {isManager && mobileNavTab(
              `/leagues/${leagueId}/manage`,
              "Manage",
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75" />
            )}
          </div>
        </nav>
      )}
    </div>
  );
}
