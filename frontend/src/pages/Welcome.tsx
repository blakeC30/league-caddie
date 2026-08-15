/**
 * Welcome — public landing page.
 *
 * Shown to unauthenticated visitors at /. Authenticated users are immediately
 * redirected to /leagues.
 *
 * Built to the Pairings Sheet language (frontend/DESIGN.md). The structure is
 * deliberately not the centred-hero → three-icon-cards → pricing-cards
 * skeleton: the page explains the game by *showing the artefacts the game
 * produces* — a leaderboard, a used-golfer ledger, a scorecard row, a
 * bracket — because those are the things only this product has.
 */

import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useStripePricing } from "../hooks/useLeague";
import { FlagIcon } from "../components/FlagIcon";
import { authApi, usersApi } from "../api/endpoints";
import { ButtonLink, Chip } from "../components/ui";

/* Illustrative figures for the landing page only — these are examples of what
   the board looks like mid-season, not live data. */
const BOARD_PREVIEW = [
  { pos: "1", name: "Dave Kellerman", pts: "8.42M", last: "Scheffler" },
  { pos: "2", name: "Priya Raghavan", pts: "7.96M", last: "Åberg" },
  { pos: "T3", name: "Marcus Hoyle", pts: "7.10M", last: "Morikawa" },
  { pos: "T3", name: "You", pts: "7.10M", last: "Cantlay", me: true },
  { pos: "5", name: "Jen Okafor", pts: "6.88M", last: "Hovland" },
];

const USED_LEDGER = [
  { wk: "01", golfer: "Scottie Scheffler", earned: "3,600,000" },
  { wk: "02", golfer: "Xander Schauffele", earned: "412,500" },
  { wk: "03", golfer: "Collin Morikawa", earned: "0" },
  { wk: "04", golfer: "Patrick Cantlay", earned: "1,085,000" },
];

/* Left column is what the league gets; right column is the plain fact about
   how it works. A ruled spec sheet, not a grid of icon cards. */
const SPEC: [string, string][] = [
  ["Scoring", "Prize money from the ESPN PGA Tour feed, posted when the event closes."],
  ["Live leaderboards", "Positions and scores update through the round while play is on."],
  ["The schedule", "The manager picks which Tour events count. Skip the ones nobody watches."],
  ["Multipliers", "Any event can be worth 1.5×, 2×, or whatever the league agrees on."],
  ["Playoffs", "Optional bracket seeded off final standings, played over real Tour events."],
  ["Members", "Invite by link, manager approves. One account, up to five leagues."],
  ["Missed picks", "Cost you points. The penalty is set by the league, not by us."],
  ["Reminders", "An email when the pick window is about to close."],
];

export function Welcome() {
  const token = useAuthStore((s) => s.token);
  const setAuth = useAuthStore((s) => s.setAuth);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const { data: pricingTiers = [] } = useStripePricing();
  // Only attempt silent restore in standalone mode (home screen install).
  // Desktop users get restored by useAuth() in Layout when they navigate to
  // an authenticated page — no need to delay the Welcome page for them.
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in window.navigator && (navigator as { standalone?: boolean }).standalone === true);
  const [restoring, setRestoring] = useState(!token && isStandalone);

  useEffect(() => {
    document.title = "League Caddie";
  }, []);

  // Attempt a silent session restore so returning users (e.g. home screen
  // app after force-close) go straight to /leagues instead of seeing Welcome.
  useEffect(() => {
    if (token || !isStandalone) {
      setRestoring(false);
      return;
    }
    authApi
      .refresh()
      .then(({ access_token }) => {
        // Set the token BEFORE calling me() so the request interceptor
        // attaches it as a Bearer header. Without this, me() gets a 401
        // and the refresh interceptor fires again unnecessarily.
        useAuthStore.getState().setToken(access_token);
        return usersApi.me().then((u) => setAuth(u, access_token));
      })
      .catch(() => {
        // Refresh failed OR me() failed — clear any partial state so the
        // app stays cleanly logged out and shows the Welcome page.
        clearAuth();
      })
      .finally(() => setRestoring(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (token) return <Navigate to="/leagues" replace />;

  // Branded loading state while the refresh attempt is in flight.
  if (restoring) {
    return <div className="min-h-screen bg-fairway-900" />;
  }

  return (
    <main className="min-h-screen bg-page text-ink-950">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 bg-page border-b border-ink-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 font-display font-bold text-ink-950 tracking-tight whitespace-nowrap">
            <FlagIcon className="w-4 h-4 text-fairway-700 shrink-0" />
            League Caddie
          </span>
          <nav className="flex items-center gap-1 shrink-0">
            <Link
              to="/login"
              className="text-ui text-ink-600 hover:text-ink-950 px-3 py-2 rounded-xs hover:bg-ink-100 transition-colors duration-[120ms] ease-board"
            >
              Sign in
            </Link>
            <ButtonLink to="/register" size="sm">
              Start a league
            </ButtonLink>
          </nav>
        </div>
      </header>

      {/* ── Hero — asymmetric, left-aligned, with the real artefact alongside ── */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 pt-12 pb-16 sm:pt-20 sm:pb-24">
        <div className="grid gap-10 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:items-center">
          <div className="min-w-0">
            <h1 className="font-display text-[2.5rem] sm:text-display leading-[1.02] tracking-[-0.03em] font-extrabold text-ink-950">
              One golfer a week.
              <br />
              Once each.
              <br />
              <span className="text-fairway-700">All season.</span>
            </h1>
            <p className="text-body text-ink-600 max-w-prose mt-6">
              League Caddie runs your one-and-done pool off live PGA Tour prize money.
              You make the pick, it does the scoring, the board updates itself. Nobody
              opens a spreadsheet again.
            </p>
            <div className="flex flex-wrap items-center gap-3 mt-8">
              <ButtonLink to="/register">Start a league</ButtonLink>
              <Link
                to="/login"
                className="text-ui text-ink-700 underline underline-offset-4 decoration-ink-300 hover:decoration-ink-700 transition-colors duration-[120ms] ease-board px-1 py-2"
              >
                I already have an account
              </Link>
            </div>
            <p className="text-small text-ink-500 mt-5">
              $29.99 per league for the season. Members join free.
            </p>
          </div>

          {/* The board. Flat painted plywood — square corners, no gradient. */}
          <div className="bg-fairway-900 rounded-sm shadow-sheet overflow-hidden min-w-0">
            <div className="flex items-center justify-between px-4 sm:px-5 py-3 border-b border-white/10">
              <p className="text-micro uppercase text-fairway-400">Saturday · Week 12</p>
              <Chip tone="live">Live</Chip>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-micro uppercase text-fairway-400">
                  <th className="text-left font-semibold pl-4 sm:pl-5 pr-2 py-2 w-10">Pos</th>
                  <th className="text-left font-semibold px-2 py-2">Player</th>
                  <th className="text-left font-semibold px-2 py-2 hidden sm:table-cell">
                    This week
                  </th>
                  <th className="text-right font-semibold pr-4 sm:pr-5 pl-2 py-2">Points</th>
                </tr>
              </thead>
              <tbody className="font-mono text-small">
                {BOARD_PREVIEW.map((r) => (
                  <tr
                    key={r.name}
                    className={`border-t border-white/10 ${r.me ? "bg-white/[0.07]" : ""}`}
                  >
                    <td
                      className={`pl-4 sm:pl-5 pr-2 py-2.5 tabular-nums ${
                        r.me ? "text-white font-semibold" : "text-fairway-400"
                      }`}
                    >
                      {r.pos}
                    </td>
                    <td
                      className={`px-2 py-2.5 font-sans ${
                        r.me ? "text-white font-semibold" : "text-white/85"
                      }`}
                    >
                      {r.name}
                    </td>
                    <td className="px-2 py-2.5 font-sans text-white/50 hidden sm:table-cell">
                      {r.last}
                    </td>
                    <td className="pr-4 sm:pr-5 pl-2 py-2.5 text-right tabular-nums text-white">
                      {r.pts}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-micro uppercase text-fairway-400 px-4 sm:px-5 py-3 border-t border-white/10">
              Example board
            </p>
          </div>
        </div>
      </section>

      {/* ── The rule ── */}
      <section className="bg-sheet border-y border-ink-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
          <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
            <div className="min-w-0">
              <h2 className="font-display text-title text-ink-950">
                Every pick costs you a future option
              </h2>
              <p className="text-body text-ink-600 max-w-prose mt-4">
                Burn Scheffler in week two and he's gone until next season. That single
                constraint is the whole game: the field is deep in January and thin by
                August, and the person who saved a top-ten player for a 2× major beats
                the person who spent him on a Monday qualifier.
              </p>
              <p className="text-body text-ink-600 max-w-prose mt-4">
                League Caddie tracks the ledger for you. Used golfers grey out at pick
                time — you can't take one by accident, and you can't argue about it in
                the group chat afterwards.
              </p>
            </div>

            {/* The ledger. Struck-through names are the product's actual behaviour. */}
            <div className="min-w-0">
              <p className="text-micro uppercase text-ink-500 pb-2 border-b border-ink-200">
                Your used golfers
              </p>
              <ul>
                {USED_LEDGER.map((r) => (
                  <li
                    key={r.wk}
                    className="flex items-baseline gap-3 py-2.5 border-b border-ink-200"
                  >
                    <span className="font-mono text-small text-ink-400 tabular-nums w-6 shrink-0">
                      {r.wk}
                    </span>
                    <span className="text-body text-ink-400 line-through decoration-ink-300 flex-1 min-w-0 truncate">
                      {r.golfer}
                    </span>
                    <span
                      className={`font-mono text-small tabular-nums shrink-0 ${
                        r.earned === "0" ? "text-flag-600" : "text-ink-600"
                      }`}
                    >
                      {r.earned === "0" ? "missed cut" : r.earned}
                    </span>
                  </li>
                ))}
                <li className="flex items-baseline gap-3 py-2.5">
                  <span className="font-mono text-small text-ink-950 tabular-nums w-6 shrink-0">
                    05
                  </span>
                  <span className="text-body text-ink-950 flex-1">
                    Pick due Thursday, 7:41 a.m.
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ── Scoring, shown as a scorecard row ── */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <h2 className="font-display text-title text-ink-950">
          Your score is your golfer's paycheque
        </h2>
        <p className="text-body text-ink-600 max-w-prose mt-4">
          No points formula to look up. If Rory banks $3.6M at the Masters, you banked
          3,600,000 — doubled if your manager set the Masters at 2×. That's the entire
          scoring system.
        </p>

        <div className="mt-10">
          <table className="w-full">
            <thead>
              <tr className="text-micro uppercase text-ink-500 border-b border-ink-950">
                <th className="text-left font-semibold py-2 pr-3">Event</th>
                <th className="text-right font-semibold py-2 px-3">Golfer earned</th>
                <th className="text-right font-semibold py-2 px-3 w-20 hidden sm:table-cell">Mult</th>
                <th className="text-right font-semibold py-2 pl-3">You scored</th>
              </tr>
            </thead>
            <tbody className="font-mono text-data tabular-nums">
              <tr className="border-b border-ink-200">
                <td className="font-sans text-body py-4 pr-3">Valspar Championship</td>
                <td className="text-right py-4 px-3 text-ink-600">$1,620,000</td>
                <td className="text-right py-4 px-3 text-ink-400 hidden sm:table-cell">1×</td>
                <td className="text-right py-4 pl-3 text-ink-950 font-semibold">1,620,000</td>
              </tr>
              <tr className="border-b border-ink-200">
                <td className="font-sans text-body py-4 pr-3">
                  The Masters
                  <span className="ml-2 align-middle">
                    <Chip tone="multiplier">2×</Chip>
                  </span>
                </td>
                <td className="text-right py-4 px-3 text-ink-600">$3,600,000</td>
                <td className="text-right py-4 px-3 text-brass-600 font-semibold hidden sm:table-cell">2×</td>
                <td className="text-right py-4 pl-3 text-ink-950 font-semibold">7,200,000</td>
              </tr>
              <tr className="border-b border-ink-200">
                <td className="font-sans text-body py-4 pr-3 text-ink-500">
                  No pick submitted
                </td>
                <td className="text-right py-4 px-3 text-ink-400">—</td>
                <td className="text-right py-4 px-3 text-ink-400 hidden sm:table-cell">—</td>
                <td className="text-right py-4 pl-3 text-flag-600 font-semibold">
                  −250,000
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-small text-ink-500 mt-4">
          The no-pick penalty is whatever your league sets it to, including zero.
        </p>
      </section>

      {/* ── Spec sheet — the pairings-sheet answer to a feature grid ── */}
      <section className="bg-sheet border-y border-ink-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
          <h2 className="font-display text-title text-ink-950">What the league gets</h2>
          <dl className="mt-8 grid sm:grid-cols-2 sm:gap-x-12">
            {SPEC.map(([term, def]) => (
              <div
                key={term}
                className="border-t border-ink-200 py-4 sm:grid sm:grid-cols-[9rem_1fr] sm:gap-4"
              >
                <dt className="text-subhead font-display text-ink-950">{term}</dt>
                <dd className="text-small text-ink-600 mt-1 sm:mt-0.5">{def}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ── Playoffs, shown as a bracket ── */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <div className="grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-16 lg:items-center">
          <div className="min-w-0">
            <h2 className="font-display text-title text-ink-950">
              Or end it with a bracket
            </h2>
            <p className="text-body text-ink-600 max-w-prose mt-4">
              Turn on playoffs and the last few events of the schedule become knockout
              rounds. The bracket seeds itself off final standings — top seed plays the
              bottom seed, and the field halves every week until one person is left.
            </p>
            <p className="text-body text-ink-600 max-w-prose mt-4">
              Inside a round, everyone in a pod ranks the golfers they want. Picks
              resolve in seed order, so a conflict costs the lower seed their first
              choice and nobody ends the week with nothing.
            </p>
          </div>

          {/* Rounds are laid out so each seed sits centred against the pair it
              came from — the bracket reads left to right the way it plays. */}
          <div className="grid grid-cols-3 gap-x-3 sm:gap-x-6 min-w-0">
            {[
              { label: "Quarters", rows: ["1 Dave", "8 Marcus", "4 Jen", "5 Priya"] },
              { label: "Semis", rows: ["1 Dave", "5 Priya"] },
              { label: "Final", rows: ["1 Dave"] },
            ].map((col, colIdx) => (
              <div key={col.label} className="flex flex-col">
                <p className="text-micro uppercase text-ink-500 pb-2 border-b border-ink-200">
                  {col.label}
                </p>
                <div className="flex-1 flex flex-col justify-around gap-2 py-2">
                  {col.rows.map((row, i) => (
                    <div
                      key={row}
                      className={`text-small px-2 py-2 rounded-xs truncate ${
                        colIdx === 2
                          ? "bg-fairway-700 text-white font-semibold"
                          : i % 2 === 0
                            ? "bg-ink-100 text-ink-950"
                            : "bg-ink-50 text-ink-500"
                      }`}
                    >
                      {row}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing — a rate table, not a row of cards with a "popular" ribbon ── */}
      <section className="bg-sheet border-y border-ink-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
          <h2 className="font-display text-title text-ink-950">One price, one season</h2>
          <p className="text-body text-ink-600 max-w-prose mt-4">
            The manager pays once per season and everyone else joins free. Every plan has
            every feature — the only thing that changes is how many people fit. Upgrade
            mid-season and you pay the difference.
          </p>

          {pricingTiers.length > 0 ? (
            <div className="mt-10">
              <table className="w-full">
                <thead>
                  <tr className="text-micro uppercase text-ink-500 border-b border-ink-950">
                    <th className="text-left font-semibold py-2 pr-3">Plan</th>
                    <th className="text-right font-semibold py-2 px-3">Members</th>
                    <th className="text-right font-semibold py-2 px-3 hidden sm:table-cell">Per member</th>
                    <th className="text-right font-semibold py-2 pl-3">Season</th>
                  </tr>
                </thead>
                <tbody>
                  {pricingTiers.map((t) => (
                    <tr key={t.tier} className="border-b border-ink-200">
                      <td className="py-4 pr-3 text-body text-ink-950 capitalize">
                        {t.tier}
                      </td>
                      <td className="py-4 px-3 text-right font-mono text-data text-ink-600 tabular-nums">
                        up to {t.member_limit.toLocaleString()}
                      </td>
                      <td className="py-4 px-3 text-right font-mono text-data text-ink-400 tabular-nums hidden sm:table-cell">
                        ${(t.amount_cents / t.member_limit / 100).toFixed(2)}
                      </td>
                      <td className="py-4 pl-3 text-right font-display text-subhead text-ink-950 tabular-nums">
                        ${(t.amount_cents / 100).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-body text-ink-500 border-t border-ink-200 mt-10 pt-8">
              Plans start at $29.99 for the season.
            </p>
          )}
        </div>
      </section>

      {/* ── Close ── */}
      <section className="bg-fairway-900">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
          <h2 className="font-display text-title sm:text-display text-white max-w-2xl leading-[1.05]">
            Set it up before Thursday
          </h2>
          <p className="text-body text-fairway-300 max-w-prose mt-5">
            Name the league, tick the events you want off the Tour schedule, send the
            invite link. It takes about as long as reading this page.
          </p>
          <div className="flex flex-wrap items-center gap-6 mt-8">
            <Link
              to="/register"
              className="inline-flex items-center gap-2 bg-white text-fairway-900 text-ui font-semibold px-5 py-3 rounded-xs hover:bg-fairway-50 active:bg-fairway-100 transition-colors duration-[120ms] ease-board"
            >
              Start a league
            </Link>
            <Link
              to="/login"
              className="text-ui text-fairway-300 hover:text-white underline underline-offset-4 decoration-fairway-500 transition-colors duration-[120ms] ease-board"
            >
              Sign in
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="bg-fairway-950">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <span className="inline-flex items-center gap-2 text-small font-semibold text-fairway-400">
              <FlagIcon className="w-3.5 h-3.5 shrink-0" />
              League Caddie
            </span>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-small text-fairway-400">
              <Link to="/register" className="hover:text-white transition-colors duration-[120ms] ease-board">
                Create account
              </Link>
              <Link to="/login" className="hover:text-white transition-colors duration-[120ms] ease-board">
                Sign in
              </Link>
              <Link to="/terms" className="hover:text-white transition-colors duration-[120ms] ease-board">
                Terms
              </Link>
              <Link to="/privacy" className="hover:text-white transition-colors duration-[120ms] ease-board">
                Privacy
              </Link>
              <a
                href="mailto:support@league-caddie.com"
                className="hover:text-white transition-colors duration-[120ms] ease-board"
              >
                Contact
              </a>
            </div>
          </div>
          <p className="text-small text-fairway-500/70 mt-6">
            © {new Date().getFullYear()} League Caddie LLC
          </p>
        </div>
      </footer>
    </main>
  );
}
