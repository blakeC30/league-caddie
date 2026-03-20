/**
 * Welcome — public landing page.
 *
 * Shown to unauthenticated visitors at /. Authenticated users are immediately
 * redirected to /leagues.
 */

import { Link, Navigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useStripePricing } from "../hooks/useLeague";
import { FlagIcon } from "../components/FlagIcon";

export function Welcome() {
  const token = useAuthStore((s) => s.token);
  const { data: pricingTiers = [] } = useStripePricing();

  if (token) return <Navigate to="/leagues" replace />;

  return (
    <div className="min-h-screen bg-white text-gray-900 antialiased overflow-x-hidden">
      {/* ── Sticky nav ── */}
      <header className="fixed top-0 inset-x-0 z-50 bg-white/80 backdrop-blur-sm border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 text-lg font-bold text-green-900 tracking-tight whitespace-nowrap">
            <FlagIcon className="w-5 h-5 flex-shrink-0" />
            League Caddie
          </span>
          <nav className="flex items-center gap-2 flex-shrink-0">
            <Link
              to="/login"
              className="text-sm font-medium text-gray-600 hover:text-gray-900 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="text-sm font-semibold bg-green-800 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors whitespace-nowrap"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-green-950 via-green-800 to-green-700 pt-36 pb-28 px-6">
        {/* Decorative blobs */}
        <div className="absolute -top-32 -right-32 w-[500px] h-[500px] rounded-full bg-white/5 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 -left-24 w-80 h-80 rounded-full bg-black/20 blur-3xl pointer-events-none" />
        <div className="absolute top-1/2 right-1/3 w-64 h-64 rounded-full bg-green-400/10 blur-2xl pointer-events-none" />

        <div className="relative max-w-4xl mx-auto text-center">
          <span className="inline-block text-xs font-bold uppercase tracking-[0.2em] text-green-300 mb-5">
            Fantasy golf, reimagined
          </span>
          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold text-white leading-[1.08] tracking-tight mb-6">
            Your fantasy golf league,{" "}
            <span className="text-green-300">
              built for the season.
            </span>
          </h1>
          <p className="text-lg sm:text-xl text-green-100 max-w-2xl mx-auto mb-10 leading-relaxed">
            The modern way to run a One-and-Done fantasy golf league. Pick one PGA Tour golfer each week — your points are based on what they actually earn on Tour, tracked automatically.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/register"
              className="inline-flex items-center justify-center gap-2 bg-white text-green-900 font-bold px-8 py-4 rounded-xl hover:bg-green-50 transition-colors text-base shadow-lg shadow-black/20"
            >
              Create a league
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
              </svg>
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center justify-center bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold px-8 py-4 rounded-xl transition-colors text-base"
            >
              Sign in
            </Link>
          </div>
          <p className="mt-6 text-sm text-green-400">
            Takes 2 minutes to set up
          </p>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900">How it works</h2>
            <p className="text-gray-500 mt-3 text-lg max-w-xl mx-auto">
              Live PGA data, automatic scoring, and playoff brackets.
            </p>
          </div>

          <div className="grid gap-10 sm:grid-cols-3">
            {[
              {
                step: "01",
                title: "Pick a golfer each week",
                description:
                  "Every week, choose one PGA Tour golfer competing in that week's tournament. The pick window closes at the first tee shot.",
                icon: (
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                  </svg>
                ),
              },
              {
                step: "02",
                title: "Earn their prize money",
                description:
                  "Your points equal the real prize money your golfer earns on Tour. Majors are worth double. Miss a week and you lose points.",
                icon: (
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                  </svg>
                ),
              },
              {
                step: "03",
                title: "Win your league",
                description:
                  "Points accumulate all season long. The player with the most points when the season ends wins the league — or advances to the playoffs.",
                icon: (
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
                  </svg>
                ),
              },
            ].map(({ step, title, description, icon }) => (
              <div key={step} className="flex flex-col">
                <div className="w-12 h-12 rounded-2xl bg-green-50 text-green-700 flex items-center justify-center mb-5">
                  {icon}
                </div>
                <p className="text-[11px] font-bold text-green-600 uppercase tracking-[0.15em] mb-2">
                  Step {step}
                </p>
                <h3 className="font-bold text-gray-900 text-xl mb-3">{title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── No-repeat rule highlight ── */}
      <section className="py-20 px-6 bg-green-50 border-y border-green-100">
        <div className="max-w-3xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-green-100 text-green-800 text-xs font-bold uppercase tracking-widest px-3 py-1.5 rounded-full mb-6">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            The rule that makes it interesting
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-5">
            Each golfer can only be picked{" "}
            <span className="text-green-700">once per season.</span>
          </h2>
          <p className="text-gray-600 text-lg max-w-2xl mx-auto leading-relaxed">
            Used Scottie Scheffler in week two? He's gone for the rest of your season. Every pick
            costs you a future option — that's what turns a simple game into a season-long
            strategic puzzle.
          </p>
        </div>
      </section>

      {/* ── Features grid ── */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900">Everything your league needs</h2>
            <p className="text-gray-500 mt-3 text-lg max-w-xl mx-auto">
              Live scoring, playoff brackets, and full league management — all in one place.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                icon: <path strokeLinecap="round" strokeLinejoin="round" d="M8.288 15.038a5.25 5.25 0 0 1 7.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 0 1 1.06 0Z" />,
                title: "Live tournament leaderboards",
                description: "Follow live leaderboards during each tournament — see positions and scores update in real time. Earnings are locked in automatically when play concludes.",
              },
              {
                icon: <path strokeLinecap="round" strokeLinejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" />,
                title: "Automatic scoring",
                description: "Points are calculated and standings updated automatically the moment a tournament closes.",
              },
              {
                icon: <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />,
                title: "Invite links",
                description: "Share a link to bring players in. League managers approve requests before anyone gets access.",
              },
              {
                icon: <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />,
                title: "Tournament multipliers",
                description: "League managers can apply a points multiplier to any tournament. Majors default to 2× — but you're in control of what matters most.",
              },
              {
                icon: <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />,
                title: "Custom schedule",
                description: "League managers choose exactly which PGA Tour events count for their league each season.",
              },
              {
                icon: <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />,
                title: "Multiple leagues",
                description: "One account, up to 5 leagues. Play with your work crew and your golf buddies at the same time.",
              },
            ].map(({ icon, title, description }) => (
              <div
                key={title}
                className="group bg-gray-50 rounded-2xl p-6 border border-gray-100 hover:border-green-200 hover:bg-green-50/50 transition-all duration-200"
              >
                <div className="w-10 h-10 rounded-xl bg-green-100 text-green-700 flex items-center justify-center mb-4">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    {icon}
                  </svg>
                </div>
                <h3 className="font-bold text-gray-900 text-base mb-2">{title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Playoff system ── */}
      <section className="py-24 px-6 bg-gray-50 border-t border-gray-100">
        <div className="max-w-5xl mx-auto">
          <div className="grid gap-12 md:grid-cols-2 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-800 text-xs font-bold uppercase tracking-widest px-3 py-1.5 rounded-full mb-6">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0" />
                </svg>
                Built-in playoff system
              </div>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-5">
                End the season with a{" "}
                <span className="text-green-700">playoff bracket.</span>
              </h2>
              <p className="text-gray-500 leading-relaxed text-lg">
                League managers can enable a full bracket playoff to cap the season. Top finishers from the regular season are automatically seeded, then compete in pod-based draft tournaments until a champion emerges.
              </p>
            </div>
            <div className="space-y-4">
              {[
                {
                  title: "Auto-seeded from standings",
                  desc: "When the regular season ends, the bracket seeds itself from final standings — no manual work required.",
                },
                {
                  title: "Pod-style draft tournaments",
                  desc: "Players in each pod rank their preferred golfers. Picks are auto-resolved by draft order so no one misses out.",
                },
                {
                  title: "Multi-round bracket advancement",
                  desc: "Winners advance, losers are eliminated. Rounds play out across real PGA Tour events until one player is left standing.",
                },
              ].map(({ title, desc }) => (
                <div key={title} className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-green-100 text-green-700 flex items-center justify-center mt-0.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-bold text-gray-900 mb-1">{title}</p>
                    <p className="text-sm text-gray-500 leading-relaxed">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Scoring explainer ── */}
      <section className="py-24 px-6 bg-white border-t border-gray-100">
        <div className="max-w-5xl mx-auto">
          <div className="grid gap-16 md:grid-cols-2 items-center">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.15em] text-green-700 mb-4">
                How scoring works
              </p>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-5">
                Real earnings. Real points. Nothing to calculate.
              </h2>
              <p className="text-gray-500 leading-relaxed mb-5">
                Your score is based on what your golfer earns on Tour. Rory wins
                $3.6 million at the Masters? You get 3,600,000 points — doubled for the major. Watch it happen on the live tournament leaderboard as the round plays out.
              </p>
              <p className="text-gray-500 leading-relaxed">
                Miss a week without a pick and you'll lose points. Saving an elite golfer for a
                major instead of burning them in a weaker field is half the game.
              </p>
            </div>
            <div className="space-y-4">
              {/* Standard event card */}
              <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6 shadow-sm">
                <p className="text-xs text-gray-400 uppercase tracking-wider font-semibold mb-3">
                  Standard tournament
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs sm:text-sm text-gray-500 mb-1">Golfer earns</p>
                    <p className="text-xl sm:text-3xl font-bold text-gray-900 tabular-nums">$1,620,000</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs sm:text-sm text-gray-500 mb-1">You earn</p>
                    <p className="text-xl sm:text-3xl font-bold text-green-700 tabular-nums">1,620,000 pts</p>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-sm text-gray-400">
                  <span>Multiplier</span>
                  <span className="font-medium text-gray-600">1×</span>
                </div>
              </div>
              {/* Major card */}
              <div className="bg-green-900 rounded-2xl p-5 sm:p-6 shadow-lg shadow-green-900/30">
                <p className="text-xs text-green-300 uppercase tracking-wider font-semibold mb-3">
                  Major championship
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs sm:text-sm text-green-400 mb-1">Golfer earns</p>
                    <p className="text-xl sm:text-3xl font-bold text-white tabular-nums">$3,600,000</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs sm:text-sm text-green-400 mb-1">You earn</p>
                    <p className="text-xl sm:text-3xl font-bold text-green-300 tabular-nums">7,200,000 pts</p>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-green-800 flex items-center justify-between text-sm text-green-400">
                  <span>Multiplier</span>
                  <span className="text-xs font-bold bg-amber-500 text-white px-2 py-0.5 rounded-full">2×</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Setup steps ── */}
      <section className="py-24 px-6 bg-gray-50 border-t border-gray-100">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">Up and running in minutes</h2>
          <p className="text-gray-500 mb-14 text-lg">
            No configuration required. Just create, invite, and play.
          </p>
          <div className="relative">
            {/* Connector line */}
            <div className="hidden sm:block absolute top-7 left-[calc(16.67%+1rem)] right-[calc(16.67%+1rem)] h-px bg-gray-200" />
            <div className="grid sm:grid-cols-3 gap-8">
              {[
                { n: "1", label: "Create your account", sub: "Email or Google sign-in." },
                { n: "2", label: "Start a league", sub: "Name it, set your rules, copy the invite link." },
                { n: "3", label: "Invite your group", sub: "Share the link and start picking when week one begins." },
              ].map(({ n, label, sub }) => (
                <div key={n} className="flex flex-col items-center text-center">
                  <div className="relative z-10 w-14 h-14 rounded-full bg-green-800 text-white text-xl font-extrabold flex items-center justify-center mb-4 shadow-md shadow-green-800/30">
                    {n}
                  </div>
                  <p className="font-bold text-gray-900 mb-1">{label}</p>
                  <p className="text-sm text-gray-500">{sub}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Pricing ── */}
      <section className="py-24 px-6 bg-white border-t border-gray-100">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <span className="inline-block text-xs font-bold uppercase tracking-[0.2em] text-green-700 mb-4">
              Pricing
            </span>
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-3">
              One season, one price
            </h2>
            <p className="text-gray-500 text-lg max-w-xl mx-auto">
              One payment per league, per season. Members join for free — every plan includes all features. Upgrade at any time.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {pricingTiers.map((t) => {
              const popular = t.tier === "standard";
              const label = t.tier.charAt(0).toUpperCase() + t.tier.slice(1);
              const price = `$${(t.amount_cents / 100).toFixed(2)}`;
              const members = `Up to ${t.member_limit.toLocaleString()} members`;
              const perMember = `~$${(t.amount_cents / t.member_limit / 100).toFixed(2)} per member`;
              return (
              <div
                key={t.tier}
                className={`relative rounded-2xl p-6 flex flex-col ${
                  popular
                    ? "bg-green-800 text-white shadow-xl shadow-green-900/30 border-2 border-green-700"
                    : "bg-white border border-gray-200"
                }`}
              >
                {popular && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[11px] font-bold uppercase tracking-widest bg-amber-400 text-amber-900 px-3 py-1 rounded-full whitespace-nowrap">
                    Most popular
                  </span>
                )}
                <p className={`text-sm font-bold uppercase tracking-wider mb-3 ${popular ? "text-green-300" : "text-green-700"}`}>
                  {label}
                </p>
                <p className={`text-4xl font-extrabold mb-1 ${popular ? "text-white" : "text-gray-900"}`}>
                  {price}
                </p>
                <p className={`text-xs mb-1 ${popular ? "text-green-300" : "text-gray-400"}`}>
                  per league / season
                </p>
                <p className={`text-xs mb-6 ${popular ? "text-green-400" : "text-gray-400"}`}>
                  {perMember}
                </p>
                <div className={`flex items-center gap-2 text-sm font-medium mt-auto ${popular ? "text-green-100" : "text-gray-700"}`}>
                  <svg className={`w-4 h-4 flex-shrink-0 ${popular ? "text-green-300" : "text-green-600"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
                  </svg>
                  {members}
                </div>
              </div>
              );
            })}
          </div>
          <p className="text-center text-sm text-gray-400 mt-8">
            All League Plans include live scoring, playoffs, custom schedules, and more.
          </p>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="py-28 px-6 bg-gradient-to-br from-green-950 via-green-900 to-green-700 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -bottom-24 -right-24 w-80 h-80 rounded-full bg-white/5 blur-3xl" />
          <div className="absolute top-0 left-1/4 w-64 h-64 rounded-full bg-green-400/10 blur-3xl" />
        </div>
        <div className="relative max-w-2xl mx-auto text-center">
          <h2 className="text-4xl sm:text-5xl font-extrabold text-white mb-5 leading-tight">
            Your best fantasy golf season starts here.
          </h2>
          <p className="text-green-200 text-lg mb-10 leading-relaxed">
            Set up your league in minutes. Invite your group, choose your tournament schedule,
            and let the picks begin.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-3 bg-white text-green-900 font-bold px-10 py-4 rounded-xl hover:bg-green-50 transition-colors text-lg shadow-xl shadow-black/30"
          >
            Create your league
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
            </svg>
          </Link>
          <p className="mt-6 text-green-400 text-sm">
            Already have an account?{" "}
            <Link to="/login" className="text-green-200 hover:text-white underline underline-offset-2">
              Sign in
            </Link>
          </p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="py-8 px-6 bg-green-950 border-t border-green-900">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-green-700">
          <span className="inline-flex items-center gap-1.5 font-semibold text-green-500">
            <FlagIcon className="w-4 h-4 flex-shrink-0" />
            League Caddie
          </span>
          <span>© {new Date().getFullYear()} · League Caddie</span>
          <div className="flex gap-4">
            <a href="mailto:support@league-caddie.com" className="hover:text-green-400 transition-colors">
              Contact Us
            </a>
            <Link to="/register" className="hover:text-green-400 transition-colors">
              Create account
            </Link>
            <Link to="/login" className="hover:text-green-400 transition-colors">
              Sign in
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
